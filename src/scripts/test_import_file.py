"""Tests de la commande `import_file`.

Elle écrit en base, à la main, éventuellement en production. Ce qui est
éprouvé ici est d'abord le cloisonnement : se tromper d'organisation
verserait une collection entière chez une autre bibliothèque, sans qu'aucune
erreur ne soit levée.
"""
import json
import tempfile
from io import BytesIO, StringIO
from pathlib import Path
from unittest.mock import patch

import openpyxl
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from src.accounts.models import Organization, User
from src.customers.models import Customer
from src.items.models import Book, Collection

LOOKUP = "src.items.book_import.find_book_details"
RESOLVE = "src.items.book_import.find_isbn"
# Voir `sans_reseau` dans tests.py : ces deux recours par titre sortent sur le
# réseau sans passer par `find_book_details`.
SUMMARY_BY_TITLE = "src.items.book_import.get_wikipedia_fr_summary"
COVER_BY_TITLE = "src.items.book_import.get_cover_by_title"


def xlsx_path(rows, directory):
    workbook = openpyxl.Workbook()
    for row in rows:
        workbook.active.append(row)
    path = Path(directory) / "import.xlsx"
    workbook.save(path)
    return str(path)


def csv_path(text, directory):
    path = Path(directory) / "membres.csv"
    path.write_text(text, encoding="utf-8")
    return str(path)


def make_user(email):
    user = User.objects.create_user(first_name=email, email=email, password="testing")
    user.is_verified = True
    user.save()
    return user, Organization.objects.get(owner=user)


@patch(RESOLVE, return_value=None)
@patch(LOOKUP, return_value=None)
class ImportFileCommandTests(TestCase):
    def setUp(self):
        # Les recours par titre sortent sur le réseau sans passer par
        # `find_book_details` : sans ça, la suite dépend de Wikipédia.
        for cible in (SUMMARY_BY_TITLE, COVER_BY_TITLE):
            patcher = patch(cible, return_value=None)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.premier, self.premiere_organisation = make_user("premier@test.com")
        # La seconde organisation est créée APRÈS : une lecture non cloisonnée
        # tomberait sur la première, et les tests passeraient quand même.
        self.second, self.seconde_organisation = make_user("second@test.com")
        self.directory = tempfile.mkdtemp()
        self.rows = [(None, "Kukum", "Michel Jean", "Libre Expression")]

    def call(self, path, **options):
        out = StringIO()
        call_command("import_file", path, stdout=out, yes=True, **options)
        return out.getvalue()

    def test_importe_dans_l_organisation_demandee(self, lookup, resolve):
        self.call(xlsx_path(self.rows, self.directory),
                  organization=self.seconde_organisation.id, no_enrich=True)
        book = Book.objects.get()
        self.assertEqual(book.organization_id, self.seconde_organisation.id)
        self.assertEqual(book.title, "Kukum")

    def test_exige_une_organisation(self, lookup, resolve):
        """Sans organisation nommée, la commande doit refuser de tourner.

        Un défaut implicite enverrait la collection dans l'organisation 1,
        qui appartient à quelqu'un.
        """
        out = StringIO()
        # Le message doit désigner l'argument manquant. Se contenter d'un
        # CommandError quelconque laisserait passer un « --organization »
        # devenu optionnel avec une valeur par défaut : l'erreur viendrait
        # alors de l'organisation introuvable, pas de l'argument absent.
        with self.assertRaisesRegex(CommandError, "--organization"):
            call_command("import_file", xlsx_path(self.rows, self.directory),
                         stdout=out, yes=True, no_enrich=True)
        self.assertEqual(Book.objects.count(), 0)

    def test_refuse_une_organisation_inconnue(self, lookup, resolve):
        with self.assertRaises(CommandError):
            self.call(xlsx_path(self.rows, self.directory), organization=999999, no_enrich=True)
        self.assertEqual(Book.objects.count(), 0)

    def test_refuse_la_collection_d_une_autre_organisation(self, lookup, resolve):
        """Le cas qui verserait une collection chez la voisine.

        Rien ne doit être écrit : la commande refuse AVANT d'importer.
        """
        collection_du_premier = Collection.objects.filter(
            organization=self.premiere_organisation
        ).first()
        with self.assertRaises(CommandError):
            self.call(xlsx_path(self.rows, self.directory),
                      organization=self.seconde_organisation.id,
                      collection=collection_du_premier.id, no_enrich=True)
        self.assertEqual(Book.objects.count(), 0)

    def test_range_dans_une_collection_de_son_organisation(self, lookup, resolve):
        self.call(xlsx_path(self.rows, self.directory),
                  organization=self.seconde_organisation.id, no_enrich=True)
        collection = Book.objects.get().collections.get()
        self.assertEqual(collection.organization_id, self.seconde_organisation.id)

    def test_refuse_une_collection_avec_un_import_de_membres(self, lookup, resolve):
        collection = Collection.objects.filter(organization=self.seconde_organisation).first()
        with self.assertRaises(CommandError):
            self.call(csv_path("Josette;COUTURE;j@example.com;613\n", self.directory),
                      organization=self.seconde_organisation.id,
                      kind="customers", collection=collection.id)

    def test_importe_des_membres(self, lookup, resolve):
        self.call(csv_path("Josette;COUTURE;j@example.com;613\n", self.directory),
                  organization=self.seconde_organisation.id, kind="customers")
        customer = Customer.objects.get()
        self.assertEqual(customer.organization_id, self.seconde_organisation.id)
        self.assertEqual(customer.last_name, "COUTURE")

    def test_n_importe_que_les_premieres_lignes_avec_limit(self, lookup, resolve):
        rows = [(None, f"Titre {index}", "Michel Jean") for index in range(5)]
        self.call(xlsx_path(rows, self.directory),
                  organization=self.seconde_organisation.id, no_enrich=True, limit=2)
        self.assertEqual(Book.objects.count(), 2)

    def test_charge_un_fichier_que_le_plafond_du_web_refuserait(self, lookup, resolve):
        """La commande existe pour les fichiers que l'endpoint refuse.

        Le plafond est abaissé à quelques octets le temps du test : si la
        commande cessait de le lever, l'import échouerait ici.
        """
        with patch("src.imports.readers.MAX_UPLOAD_BYTES", 10):
            self.call(xlsx_path(self.rows, self.directory),
                      organization=self.seconde_organisation.id, no_enrich=True)
        self.assertEqual(Book.objects.count(), 1)

    def test_refuse_un_fichier_introuvable(self, lookup, resolve):
        with self.assertRaises(CommandError):
            self.call("/chemin/qui/n/existe/pas.xlsx",
                      organization=self.seconde_organisation.id, no_enrich=True)

    def test_ecrit_le_compte_rendu_demande(self, lookup, resolve):
        rapport = str(Path(self.directory) / "rapport.json")
        self.call(xlsx_path(self.rows, self.directory),
                  organization=self.seconde_organisation.id, no_enrich=True, rapport=rapport)
        with open(rapport, encoding="utf-8") as handle:
            summary = json.load(handle)
        self.assertEqual(summary["created_count"], 1)
        self.assertEqual(summary["created"], ["Kukum"])

    def test_affiche_la_progression_et_le_total(self, lookup, resolve):
        output = self.call(xlsx_path(self.rows, self.directory),
                           organization=self.seconde_organisation.id, no_enrich=True)
        self.assertIn("1/1", output)
        self.assertIn("Kukum", output)
        self.assertIn(self.seconde_organisation.name, output)

    def test_n_interroge_aucun_catalogue_avec_no_enrich(self, lookup, resolve):
        self.call(xlsx_path(self.rows, self.directory),
                  organization=self.seconde_organisation.id, no_enrich=True)
        resolve.assert_not_called()
        lookup.assert_not_called()
