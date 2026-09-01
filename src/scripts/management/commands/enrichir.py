"""Compléter les fiches pauvres d'une collection, sans jamais rien écraser.

Le problème que cette commande résout, et pourquoi le réimport ne le résout
pas : **une fiche pauvre ne se rattrape pas en rejouant l'import**. Le
dédoublonnage la reconnaît et la saute, donc rien ne change ; et les rares
lignes qui passent au travers — parce qu'un éditeur diffère d'un caractère —
créent des DOUBLONS. Mesuré sur l'inventaire de Siem Reap : 182 lignes sautées
sur 185, et 3 doublons ajoutés en production.

La seule autre issue connue était de SUPPRIMER les fiches avant de les
réimporter. Elle marche, mais elle est destructive, elle perd les
modifications faites à la main depuis, et elle demande le fichier d'origine.

Cette commande part de la BASE, pas d'un fichier :

  1. elle cherche les ouvrages à qui il manque une couverture ou un résumé ;
  2. elle interroge les catalogues ;
  3. ⛔ elle n'écrit QUE dans les champs vides. Ce que la bibliothèque a
     catalogué, corrigé ou choisi ne bouge jamais.

Elle est donc **idempotente** et **reprenable** : on peut la relancer chaque
jour, elle ne refait pas ce qui est fait.

🔴 ET ELLE S'ARRÊTE QUAND LA QUOTA MEURT. C'est la leçon du 31/08 : la passe
d'hier a continué après l'épuisement du quota Google et la qualité s'est
dégradée de façon monotone — 30 % de couvertures sur la première tranche, 20 %
sur la dernière. Persister ne remplit rien ; ça consomme la seule chose qu'on
ait, c'est-à-dire les fiches encore à traiter.

    manage.py enrichir --organization 37 --limit 200
    manage.py enrichir --organization 37 --dry-run
"""
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from src.accounts.models import Organization
from src.items.book_lookup import (
    download_image,
    find_book_details,
    get_cover_by_title,
    get_wikipedia_fr_summary,
)
from src.items.isbn_resolution import find_isbn
from src.items.models import Book

# Nombre d'ouvrages consécutifs sans le MOINDRE apport avant d'abandonner.
# Une fiche qui ne trouve rien est ordinaire ; vingt d'affilée veut dire que
# les catalogues ne répondent plus, pas que la collection est introuvable.
SEUIL_ABANDON = 20


class Command(BaseCommand):
    help = "Complète les couvertures et résumés manquants, sans rien écraser."

    def add_arguments(self, parser):
        parser.add_argument(
            "--organization", type=int, required=True,
            help="Organisation à enrichir. Obligatoire : rien dans ce produit "
                 "n'existe hors d'une organisation.",
        )
        parser.add_argument(
            "--limit", type=int, default=None,
            help="S'arrêter après N ouvrages. Pour étaler sur plusieurs jours "
                 "quand la quota d'un catalogue est journalière.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Dire ce qui serait rempli, sans rien écrire.",
        )
        parser.add_argument(
            "--seuil-abandon", type=int, default=SEUIL_ABANDON,
            help="Ouvrages consécutifs sans apport avant d'abandonner.",
        )

    def handle(self, *args, **options):
        organization = self.get_organization(options["organization"])
        a_blanc = options["dry_run"]

        # 🔴 Le filtre porte l'organisation. Sans elle, on enrichirait — donc
        # on ÉCRIRAIT — dans le fonds d'une autre bibliothèque.
        manquants = Book.objects.filter(organization=organization).filter(
            Q(picture__isnull=True) | Q(picture="")
            | Q(description__isnull=True) | Q(description="")
        ).order_by("id")

        total_pauvres = manquants.count()
        total = Book.objects.filter(organization=organization).count()
        if options["limit"]:
            manquants = manquants[: options["limit"]]

        a_traiter = len(manquants)
        self.stdout.write(
            f"\n  Organisation : « {organization.name} » (id {organization.id})\n"
            f"  Collection   : {total} ouvrages, dont {total_pauvres} incomplets\n"
            f"  À traiter    : {a_traiter}"
            + ("   ⚠️ À BLANC, rien ne sera écrit" if a_blanc else "")
            + f"\n  Durée        : environ {a_traiter * 7 // 60 + 1} min\n"
        )

        couvertures = resumes = isbns = 0
        sans_apport = 0

        for rang, book in enumerate(manquants, 1):
            apport = self.enrichir(book, a_blanc)
            couvertures += "couverture" in apport
            resumes += "résumé" in apport
            isbns += "ISBN" in apport

            if apport:
                sans_apport = 0
                self.stdout.write(
                    f"  ✅ {rang}/{a_traiter} « {book.title[:44]:44} » "
                    f"+ {', '.join(apport)}"
                )
            else:
                sans_apport += 1
                self.stdout.write(f"  ∅  {rang}/{a_traiter} « {book.title[:44]:44} »")

            if sans_apport >= options["seuil_abandon"]:
                self.stdout.write(self.style.WARNING(
                    f"\n  ⛔ ARRÊT : {sans_apport} ouvrages d'affilée sans le moindre apport.\n"
                    "     Les catalogues ne répondent plus — ce n'est pas la collection\n"
                    "     qui est introuvable. Continuer ne remplirait rien et\n"
                    "     consommerait les fiches qu'il reste à traiter.\n"
                    "     Relancer la même commande plus tard : elle reprendra ici."
                ))
                break

        self.stdout.write(
            f"\n  couvertures ajoutées : {couvertures}\n"
            f"  résumés ajoutés      : {resumes}\n"
            f"  ISBN retrouvés       : {isbns}\n"
        )
        if a_blanc:
            self.stdout.write(self.style.WARNING("  Exécution à blanc : rien n'a été écrit.\n"))

    def enrichir(self, book, a_blanc) -> list:
        """Ce qui a été ajouté à cette fiche. Jamais ce qui a été remplacé."""
        apport = []

        isbn = book.isbn
        if not isbn:
            trouve = find_isbn(title=book.title, author=book.author or "")
            if trouve:
                isbn = trouve.isbn
                apport.append("ISBN")
                if not a_blanc:
                    book.isbn = isbn
                    book.save(update_fields=["isbn"])

        details = None
        if isbn:
            try:
                details = find_book_details(isbn=isbn)
            except Exception:
                # Un catalogue indisponible ne doit pas coûter la fiche.
                details = None

        # ── Le résumé ────────────────────────────────────────────────────
        if not book.description:
            resume = (details.description if details else None) or get_wikipedia_fr_summary(
                title=book.title, author=book.author or ""
            )
            if resume:
                apport.append("résumé")
                if not a_blanc:
                    book.description = resume
                    book.save(update_fields=["description"])

        # ── La couverture ────────────────────────────────────────────────
        if not book.picture:
            url = (details.picture if details else None) or get_cover_by_title(
                title=book.title, author=book.author or ""
            )
            if url:
                image = download_image(url=url)
                if image:
                    apport.append("couverture")
                    if not a_blanc:
                        book.picture.save(
                            name=book.title, content=ContentFile(image), save=True
                        )
        return apport

    def get_organization(self, identifiant):
        organization = Organization.objects.filter(pk=identifiant).first()
        if not organization:
            raise CommandError(f"Organisation {identifiant} introuvable.")
        return organization
