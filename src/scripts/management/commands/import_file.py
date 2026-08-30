"""Importer un fichier d'ouvrages ou de membres, hors requête HTTP.

Pourquoi une commande plutôt que l'endpoint `/scripts/import/` : une
collection entière demande plus d'une heure — environ 7 s par ouvrage, le
temps d'interroger les catalogues — alors que le service web tue son worker
au bout de vingt minutes (`gunicorn --timeout 1200`). L'import s'arrêterait
en chemin, sans compte rendu, avec une partie des lignes déjà écrites. Une
commande ne passe pas par gunicorn : elle n'a aucune limite de durée.

    manage.py import_file collection.xlsx --organization 12
    manage.py import_file membres.csv --organization 12 --kind customers

L'endpoint reste en place pour les petits fichiers envoyés depuis
l'interface ; le jour où les bibliothèques importeront elles-mêmes, ce
travail passera dans une file d'attente.
"""
import json

from django.core.management.base import BaseCommand, CommandError

from src.accounts.models import Organization
from src.customers.customer_import import COLUMNS as CUSTOMER_COLUMNS
from src.customers.customer_import import CustomerImporter
from src.imports.readers import ImportFileError, read_rows
from src.imports.runner import run_import
from src.items.book_import import COLUMNS as BOOK_COLUMNS
from src.items.book_import import BookImporter
from src.items.models import Collection

MARKS = {"created": "✅", "duplicate": "⚠️ ", "not_found": "∅ ", "error": "❌"}


class Command(BaseCommand):
    help = "Importe des ouvrages ou des membres dans une organisation."

    def add_arguments(self, parser):
        parser.add_argument("fichier", help="Chemin du .xlsx ou du .csv à importer.")
        parser.add_argument(
            "--organization", type=int, required=True,
            help="Identifiant de l'organisation qui reçoit l'import. Obligatoire : "
                 "rien dans ce produit n'existe hors d'une organisation.",
        )
        parser.add_argument("--kind", choices=["books", "customers"], default="books")
        parser.add_argument(
            "--collection", type=int, default=None,
            help="Collection de rangement des ouvrages. Par défaut, la première "
                 "de l'organisation.",
        )
        parser.add_argument(
            "--limit", type=int, default=None,
            help="N'importer que les N premières lignes. Pour éprouver un fichier "
                 "avant de le charger en entier.",
        )
        parser.add_argument(
            "--no-enrich", action="store_true",
            help="Ne pas interroger les catalogues : ni ISBN retrouvé, ni résumé, "
                 "ni couverture. L'import devient instantané.",
        )
        parser.add_argument(
            "--rapport", default=None,
            help="Écrire le compte rendu complet en JSON dans ce fichier, pour "
                 "reprendre les lignes en échec.",
        )
        parser.add_argument("--yes", action="store_true", help="Ne pas demander confirmation.")

    def handle(self, *args, **options):
        organization = self.get_organization(options["organization"])
        kind = options["kind"]
        columns = BOOK_COLUMNS if kind == "books" else CUSTOMER_COLUMNS

        try:
            with open(options["fichier"], "rb") as handle:
                # `handle.name` porte déjà le chemin : c'est lui qui dit au
                # lecteur s'il a affaire à un classeur ou à un CSV.
                # Pas de plafond de taille ici : celui de la vue protège le
                # service web, pas un fichier posé sur le disque.
                records = read_rows(file=handle, columns=columns, max_bytes=None)
        except FileNotFoundError:
            raise CommandError(f"Fichier introuvable : {options['fichier']}")
        except ImportFileError as error:
            raise CommandError(str(error))

        if options["limit"]:
            records = records[: options["limit"]]
        if not records:
            raise CommandError("Le fichier ne contient aucune ligne exploitable.")

        importer = self.get_importer(kind, organization, options)
        self.confirm(records, organization, kind, options)

        report = run_import(
            records=records, importer=importer,
            organization_id=organization.id, on_progress=self.show_progress,
        )
        self.summarize(report, options.get("rapport"))

    def get_organization(self, organization_id):
        """L'organisation est nommée à l'écran avant toute écriture.

        Se tromper d'identifiant verserait une collection entière chez une
        autre bibliothèque, sans qu'aucune erreur ne soit levée.
        """
        try:
            return Organization.objects.get(pk=organization_id)
        except Organization.DoesNotExist:
            raise CommandError(f"Aucune organisation n'a l'identifiant {organization_id}.")

    def get_importer(self, kind, organization, options):
        if kind == "customers":
            if options["collection"] is not None:
                # Refuser plutôt qu'ignorer : sur une commande qui écrit en
                # production, un argument sans effet se lit comme un ordre reçu.
                raise CommandError("--collection ne s'applique qu'à --kind books.")
            return CustomerImporter()
        collection = None
        if options["collection"] is not None:
            collection = Collection.objects.filter(
                pk=options["collection"], organization=organization
            ).first()
            if collection is None:
                raise CommandError(
                    f"La collection {options['collection']} n'appartient pas à "
                    f"« {organization.name} »."
                )
        else:
            collection = Collection.objects.filter(organization=organization).first()
        enrich = not options["no_enrich"]
        return BookImporter(collection=collection, resolve_isbn=enrich, enrich=enrich)

    def confirm(self, records, organization, kind, options):
        noun = "ouvrages" if kind == "books" else "membres"
        self.stdout.write("")
        self.stdout.write(f"  Organisation : « {organization.name} » (id {organization.id})")
        self.stdout.write(f"  À importer   : {len(records)} {noun}")
        if options["no_enrich"]:
            self.stdout.write("  Catalogues   : non interrogés (--no-enrich)")
        elif kind == "books":
            minutes = round(len(records) * 7.4 / 60)
            self.stdout.write(f"  Durée        : environ {minutes} min (≈7 s par ouvrage)")
        self.stdout.write("")
        if options["yes"]:
            return
        if input("  Confirmer ? [o/N] ").strip().lower() not in ("o", "oui"):
            raise CommandError("Import annulé.")

    def show_progress(self, index, total, label, outcome):
        self.stdout.write(f"  {MARKS[outcome]} {index}/{total} {label[:60]}")

    def summarize(self, report, rapport_path):
        summary = report.as_dict()
        self.stdout.write("")
        for key, text in (
            ("created_count", "créés"), ("duplicates_count", "doublons"),
            ("not_found_count", "introuvables"), ("errors_count", "erreurs"),
        ):
            self.stdout.write(f"  {text:14} {summary[key]}")
        if rapport_path:
            with open(rapport_path, "w", encoding="utf-8") as handle:
                json.dump(summary, handle, ensure_ascii=False, indent=1)
            self.stdout.write(f"\n  Compte rendu écrit dans {rapport_path}")
        elif summary["errors"]:
            self.stdout.write("\n  Lignes en échec :")
            for failure in summary["errors"][:10]:
                self.stdout.write(f"    • {failure['line']} — {failure['reason'][:80]}")
