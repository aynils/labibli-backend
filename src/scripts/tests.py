import io
import os
from unittest import mock

import openpyxl
from django.test import TestCase
from rest_framework.test import APIClient

from src.accounts.models import User
from src.items.book_lookup import BookDetails
from src.items.models import Book, Collection

URL_IMPORT = "/scripts/import/"


def fichier_isbn(isbns) -> io.BytesIO:
    """Le classeur attendu par la vue : une ligne d'en-tête, puis un ISBN par ligne."""
    classeur = openpyxl.Workbook()
    feuille = classeur.active
    feuille.append(["isbn"])
    for isbn in isbns:
        feuille.append([isbn])
    tampon = io.BytesIO()
    classeur.save(tampon)
    tampon.seek(0)
    tampon.name = "isbns.xlsx"
    return tampon


def details(isbn: str, titre: str = "Kukum") -> BookDetails:
    return BookDetails(
        isbn=isbn,
        title=titre,
        picture="",
        author="Michel Jean",
        publisher="Libre Expression",
        published_year=2019,
        description="",
        page_count="220",
        language="fr",
    )


class ImportBooksFromISBNSTest(TestCase):
    def setUp(self):
        # Le signal post_save de User crée l'organisation, celui d'Organization
        # crée sa collection par défaut.
        self.utilisateur = User.objects.create_user(
            email="bibliothecaire@example.com", password="motdepasse"
        )
        self.organisation = self.utilisateur.employee_of_organization
        voisine = User.objects.create_user(
            email="voisine@example.com", password="motdepasse"
        )
        self.autre_organisation = voisine.employee_of_organization
        self.api = APIClient()
        self.api.force_authenticate(user=self.utilisateur)

    def tearDown(self):
        if os.path.exists("import_log.json"):
            os.remove("import_log.json")

    def poster(self, isbns):
        with mock.patch(
            "src.scripts.views.find_book_details",
            side_effect=lambda isbn: details(isbn),
        ), mock.patch("src.scripts.views.download_image", return_value=None):
            return self.api.post(
                URL_IMPORT, {"file": fichier_isbn(isbns)}, format="multipart"
            )

    def test_importe_un_isbn_deja_catalogue_par_une_autre_organisation(self):
        """Le doublon se juge dans l'organisation, pas dans toute la base."""
        Book.objects.create(
            organization=self.autre_organisation,
            author="Michel Jean",
            title="Kukum",
            isbn="9782764813447",
        )

        reponse = self.poster(["9782764813447"])

        self.assertEqual(reponse.status_code, 200)
        statut = reponse.json()["status"]
        self.assertEqual(statut["success"], ["9782764813447"])
        self.assertEqual(statut["duplicates"], [])
        self.assertTrue(
            Book.objects.filter(
                organization=self.organisation, isbn="9782764813447"
            ).exists()
        )

    def test_signale_un_isbn_deja_catalogue_par_la_meme_organisation(self):
        Book.objects.create(
            organization=self.organisation,
            author="Michel Jean",
            title="Kukum",
            isbn="9782764813447",
        )

        reponse = self.poster(["9782764813447"])

        statut = reponse.json()["status"]
        self.assertEqual(statut["duplicates"], ["9782764813447"])
        self.assertEqual(statut["success"], [])
        self.assertEqual(
            Book.objects.filter(
                organization=self.organisation, isbn="9782764813447"
            ).count(),
            1,
        )

    def test_rattache_le_livre_a_la_collection_de_son_organisation(self):
        reponse = self.poster(["9782764813447"])

        self.assertEqual(reponse.status_code, 200)
        livre = Book.objects.get(organization=self.organisation, isbn="9782764813447")
        collection = Collection.objects.get(organization=self.organisation)
        self.assertEqual(list(livre.collections.all()), [collection])

    def test_refuse_un_compte_sans_organisation(self):
        orpheline = User.objects.create_user(
            email="orpheline@example.com", password="motdepasse"
        )
        orpheline.employee_of_organization = None
        orpheline.save()
        self.api.force_authenticate(user=orpheline)

        reponse = self.poster(["9782764813447"])

        self.assertEqual(reponse.status_code, 400)
