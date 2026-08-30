from io import BytesIO
from unittest.mock import patch

import openpyxl
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from src.accounts.models import Organization, User
from src.customers.models import Customer
from src.helpers.tests import authenticate_user, create_user
from src.items.book_lookup import BookDetails
from src.items.models import Book, Category, Collection

LOOKUP = "src.items.book_import.find_book_details"
RESOLVE = "src.items.book_import.find_isbn"


def xlsx_upload(rows, name="import.xlsx"):
    """Un classeur en mémoire, tel que le reçoit la vue."""
    workbook = openpyxl.Workbook()
    for row in rows:
        workbook.active.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    return SimpleUploadedFile(name, buffer.getvalue())


def csv_upload(text, name="membres.csv"):
    return SimpleUploadedFile(name, text.encode("utf-8"))


def book_details(isbn="9782764813447", title="Kukum"):
    return BookDetails(
        isbn=isbn, title=title, picture=None, author="Michel Jean",
        publisher="Libre Expression", published_year="2019",
        description="Un roman.", page_count=224, language="fr",
    )


def second_user_with_organization():
    """Une deuxième organisation, créée APRÈS la première.

    L'ordre compte : un contrôle de cloisonnement qui lirait la table sans
    filtrer tomberait sur la première organisation créée. C'est donc la
    seconde qui importe dans les tests de scope, sinon ils passent aussi
    quand le scope a disparu.
    """
    user = User.objects.create_user(
        first_name="voisine", email="voisine@test.com", password="testing"
    )
    user.is_verified = True
    user.save()
    return user, Organization.objects.get(owner=user)


class ImportBooksTests(APITestCase):
    def setUp(self):
        self.user = create_user()
        self.organization = Organization.objects.get(owner=self.user)
        self.url = reverse("import_file")
        authenticate_user(self)

    @patch(LOOKUP, return_value=book_details())
    def test_importe_un_fichier_d_isbn_nus(self, lookup):
        """Le format historique — une colonne d'ISBN — reste valable."""
        response = self.client.post(
            self.url, {"file": xlsx_upload([("9782764813447",)])}, format="multipart"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["status"]["created_count"], 1)
        book = Book.objects.get(organization=self.organization)
        self.assertEqual(book.title, "Kukum")

    @patch(RESOLVE)
    @patch(LOOKUP)
    def test_importe_un_ouvrage_sans_isbn(self, lookup, resolve):
        """Une ligne sans ISBN entre au catalogue même si rien n'est trouvé.

        C'est le cas d'un tiers des lignes du RFNB et de la totalité de
        l'inventaire de l'Alliance Française de Siem Reap.
        """
        resolve.return_value = None
        response = self.client.post(
            self.url,
            {"file": xlsx_upload([(None, "Kukum", "Michel Jean", "Libre Expression")])},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["status"]["created_count"], 1)
        book = Book.objects.get(organization=self.organization)
        self.assertEqual(book.title, "Kukum")
        self.assertEqual(book.author, "Michel Jean")
        self.assertIsNone(book.isbn)
        lookup.assert_not_called()

    @patch(LOOKUP, return_value=book_details())
    def test_resout_l_isbn_par_titre_et_auteur(self, lookup):
        """Sans ISBN, on tente de le retrouver pour enrichir la fiche."""
        with patch(RESOLVE) as resolve:
            resolve.return_value = type("Match", (), {"isbn": "9782764813447"})()
            response = self.client.post(
                self.url,
                {"file": xlsx_upload([(None, "Kukum", "Michel Jean")])},
                format="multipart",
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        resolve.assert_called_once()
        # C'est l'ISBN RÉSOLU qui doit être interrogé, pas un autre : sans
        # cette assertion, remplacer la résolution par un ISBN inventé
        # laissait la suite verte.
        lookup.assert_called_once_with(isbn="9782764813447")
        self.assertEqual(Book.objects.get(organization=self.organization).isbn, "9782764813447")

    @patch(LOOKUP, return_value=book_details())
    def test_le_fichier_prime_sur_le_catalogue(self, lookup):
        """Ce que la bibliothèque a catalogué ne doit pas être réécrit."""
        self.client.post(
            self.url,
            {"file": xlsx_upload([("9782764813447", "Kukum", "M. Jean", "Mon éditeur")])},
            format="multipart",
        )
        book = Book.objects.get(organization=self.organization)
        self.assertEqual(book.author, "M. Jean")
        self.assertEqual(book.publisher, "Mon éditeur")
        # Ce que le fichier ne dit pas est comblé par le catalogue.
        self.assertEqual(book.description, "Un roman.")

    @patch(LOOKUP, return_value=book_details())
    def test_importe_un_isbn_deja_catalogue_par_une_autre_organisation(self, lookup):
        """Le doublon se juge DANS l'organisation qui importe.

        Panne du 30/08/2026 : le contrôle cherchait l'ISBN dans toute la
        base, si bien qu'un titre catalogué par n'importe quelle autre
        bibliothèque était rejeté en silence.
        """
        voisine_user, voisine = second_user_with_organization()
        Book.objects.create(
            organization=voisine, title="Kukum", isbn="9782764813447", author="Michel Jean"
        )
        response = self.client.post(
            self.url, {"file": xlsx_upload([("9782764813447",)])}, format="multipart"
        )
        self.assertEqual(response.json()["status"]["created_count"], 1)
        self.assertEqual(response.json()["status"]["duplicates_count"], 0)
        self.assertTrue(Book.objects.filter(organization=self.organization, isbn="9782764813447").exists())

    @patch(LOOKUP, return_value=book_details())
    def test_saute_un_isbn_deja_catalogue_par_l_organisation(self, lookup):
        Book.objects.create(
            organization=self.organization, title="Kukum", isbn="9782764813447"
        )
        response = self.client.post(
            self.url, {"file": xlsx_upload([("9782764813447",)])}, format="multipart"
        )
        self.assertEqual(response.json()["status"]["duplicates_count"], 1)
        self.assertEqual(Book.objects.filter(organization=self.organization).count(), 1)

    @patch(RESOLVE, return_value=None)
    @patch(LOOKUP)
    def test_dedoublonne_les_lignes_du_fichier_lui_meme(self, lookup, resolve):
        """L'inventaire de Siem Reap porte 87 fiches en double.

        Sans ISBN, `unique_together` ne contraint rien en base : le
        dédoublonnage doit se faire à l'import, sinon la bibliothèque voit
        chaque doublon de son tableur apparaître dans son catalogue.
        """
        rows = [
            (None, "Kukum", "Michel Jean"),
            (None, "kukum", "michel jean"),
        ]
        response = self.client.post(self.url, {"file": xlsx_upload(rows)}, format="multipart")
        self.assertEqual(response.json()["status"]["created_count"], 1)
        self.assertEqual(response.json()["status"]["duplicates_count"], 1)

    @patch(LOOKUP, return_value=book_details())
    def test_rattache_a_la_collection_et_a_la_categorie_de_son_organisation(self, lookup):
        """Le rangement d'un ouvrage importé reste dans son organisation.

        La première organisation reçoit elle aussi une collection et une
        catégorie : c'est la SECONDE qui importe, donc une lecture non
        cloisonnée rattacherait l'ouvrage au rangement de la voisine.
        """
        Collection.objects.create(organization=self.organization, name="Collection du premier")
        Category.objects.create(organization=self.organization, name="Romans")

        voisine_user, voisine = second_user_with_organization()
        # Le jeton du premier compte doit partir, sinon c'est encore lui qui
        # importe et le test passerait même sans cloisonnement.
        self.client.credentials()
        self.client.force_authenticate(user=voisine_user)

        self.client.post(
            self.url,
            {"file": xlsx_upload([("9782764813447", "Kukum", "Michel Jean", None, None, None, "Romans")])},
            format="multipart",
        )
        book = Book.objects.get(organization=voisine)
        # Une lecture non cloisonnée prendrait le rangement du premier compte,
        # dont la collection et la catégorie ont le plus petit identifiant.
        self.assertEqual(book.collections.get().organization_id, voisine.id)
        category = book.categories.get()
        self.assertEqual(category.name, "Romans")
        self.assertEqual(category.organization, voisine)

    @patch(LOOKUP, side_effect=RuntimeError("catalogue indisponible"))
    @patch(RESOLVE, return_value=None)
    def test_un_catalogue_indisponible_ne_perd_pas_la_ligne(self, resolve, lookup):
        response = self.client.post(
            self.url, {"file": xlsx_upload([("9782764813447", "Kukum")])}, format="multipart"
        )
        self.assertEqual(response.json()["status"]["created_count"], 1)

    def test_conserve_la_liste_des_lignes_en_echec(self):
        """Le compte rendu garde les libellés, pas seulement les totaux.

        Le rapport écrasait sa propre liste d'erreurs par sa longueur : la
        bibliothécaire perdait les lignes à reprendre.
        """
        with patch("src.items.book_import.BookImporter.build", side_effect=ValueError("boum")):
            response = self.client.post(
                self.url, {"file": xlsx_upload([("9782764813447", "Kukum")])}, format="multipart"
            )
        report = response.json()["status"]
        self.assertEqual(report["errors_count"], 1)
        self.assertEqual(report["errors"][0]["line"], "Kukum")
        self.assertIn("boum", report["errors"][0]["reason"])

    def test_refuse_une_requete_sans_fichier(self):
        response = self.client.post(self.url, {}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_refuse_un_type_d_import_inconnu(self):
        response = self.client.post(
            self.url, {"file": xlsx_upload([("x",)]), "kind": "chaises"}, format="multipart"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch(RESOLVE, return_value=None)
    @patch(LOOKUP, return_value=None)
    def test_conserve_l_isbn_resolu_meme_sans_fiche_de_catalogue(self, lookup, resolve):
        """La résolution ne doit pas être jetée faute de métadonnées.

        Retrouver l'ISBN est la raison d'être de la brique : le perdre parce
        qu'aucun catalogue ne rend la fiche annulerait tout le travail.
        """
        resolve.return_value = type("Match", (), {"isbn": "9782764813447"})()
        self.client.post(
            self.url, {"file": xlsx_upload([(None, "Kukum", "Michel Jean")])}, format="multipart"
        )
        self.assertEqual(Book.objects.get(organization=self.organization).isbn, "9782764813447")

    @patch(LOOKUP, return_value=book_details())
    def test_reconnait_un_isbn_ecrit_avec_des_tirets(self, lookup):
        Book.objects.create(
            organization=self.organization, title="Kukum", isbn="9782764813447", author="Michel Jean"
        )
        response = self.client.post(
            self.url, {"file": xlsx_upload([("978-2-7648-1344-7",)])}, format="multipart"
        )
        self.assertEqual(response.json()["status"]["duplicates_count"], 1)
        self.assertEqual(Book.objects.filter(organization=self.organization).count(), 1)

    @patch(RESOLVE, return_value=None)
    @patch(LOOKUP)
    def test_reconnait_un_ouvrage_deja_catalogue_avec_son_isbn(self, lookup, resolve):
        """Un inventaire sans ISBN ne doit pas dupliquer un catalogue bâti par ISBN."""
        Book.objects.create(
            organization=self.organization, title="Kukum", author="Michel Jean",
            publisher="Libre Expression", isbn="9782764813447",
        )
        response = self.client.post(
            self.url,
            {"file": xlsx_upload([(None, "Kukum", "Michel Jean", "Libre Expression")])},
            format="multipart",
        )
        self.assertEqual(response.json()["status"]["duplicates_count"], 1)
        self.assertEqual(Book.objects.filter(organization=self.organization).count(), 1)

    @patch(RESOLVE, return_value=None)
    @patch(LOOKUP)
    def test_garde_deux_editions_distinctes_du_meme_titre(self, lookup, resolve):
        """Deux éditions ne sont pas un doublon : l'éditeur les distingue.

        Les fondre perdrait une ligne légitime en silence, exactement le
        défaut payé le 30/08/2026.
        """
        rows = [
            (None, "Les misérables", "Victor Hugo", "Gallimard"),
            (None, "Les misérables", "Victor Hugo", "Livre de Poche"),
        ]
        response = self.client.post(self.url, {"file": xlsx_upload(rows)}, format="multipart")
        self.assertEqual(response.json()["status"]["created_count"], 2)

    @patch(LOOKUP, return_value=book_details())
    def test_supporte_une_categorie_en_double_dans_l_organisation(self, lookup):
        """`Category.unique_together` est déclaré hors de `Meta` : les
        homonymes existent réellement en base."""
        Category.objects.create(organization=self.organization, name="Romans")
        Category.objects.create(organization=self.organization, name="Romans")
        response = self.client.post(
            self.url,
            {"file": xlsx_upload([("9782764813447", "Kukum", "Michel Jean", None, None, None, "Romans")])},
            format="multipart",
        )
        self.assertEqual(response.json()["status"]["created_count"], 1)
        self.assertEqual(response.json()["status"]["errors_count"], 0)

    @patch(LOOKUP, return_value=book_details())
    def test_une_ligne_en_echec_ne_laisse_pas_d_ouvrage_derriere_elle(self, lookup):
        """Sinon le compte rendu annonce un échec sur une ligne enregistrée,
        et la rejouer crée un doublon."""
        with patch("src.items.book_import.BookImporter.attach_category", side_effect=ValueError("boum")):
            response = self.client.post(
                self.url,
                {"file": xlsx_upload([("9782764813447", "Kukum", "Michel Jean", None, None, None, "Romans")])},
                format="multipart",
            )
        self.assertEqual(response.json()["status"]["errors_count"], 1)
        self.assertEqual(Book.objects.filter(organization=self.organization).count(), 0)

    def test_refuse_une_requete_anonyme(self):
        self.client.credentials()
        self.client.force_authenticate(user=None)
        response = self.client.post(
            self.url, {"file": xlsx_upload([("9782764813447",)])}, format="multipart"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refuse_un_compte_sans_organisation(self):
        self.user.employee_of_organization = None
        self.user.save()
        response = self.client.post(
            self.url, {"file": xlsx_upload([("9782764813447",)])}, format="multipart"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ImportCustomersTests(APITestCase):
    """Le second usage du socle : la liste des membres, en CSV point-virgule."""

    def setUp(self):
        self.user = create_user()
        self.organization = Organization.objects.get(owner=self.user)
        self.url = reverse("import_file")
        authenticate_user(self)

    def test_importe_des_membres(self):
        csv = "Josette;COUTURE;josette.couture@example.com;613-601-2441\n"
        response = self.client.post(
            self.url, {"file": csv_upload(csv), "kind": "customers"}, format="multipart"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["status"]["created_count"], 1)
        customer = Customer.objects.get(organization=self.organization)
        self.assertEqual(customer.last_name, "COUTURE")
        self.assertEqual(customer.email, "josette.couture@example.com")

    def test_saute_un_membre_deja_inscrit(self):
        Customer.objects.create(
            organization=self.organization, first_name="Josette", last_name="COUTURE",
            email="josette.couture@example.com",
        )
        csv = "Josette;COUTURE;josette.couture@example.com;613-601-2441\n"
        response = self.client.post(
            self.url, {"file": csv_upload(csv), "kind": "customers"}, format="multipart"
        )
        self.assertEqual(response.json()["status"]["duplicates_count"], 1)
        self.assertEqual(Customer.objects.filter(organization=self.organization).count(), 1)

    def test_saute_un_membre_reconnu_par_son_telephone(self):
        """`unique_together` reconnaît un membre par courriel OU téléphone."""
        Customer.objects.create(
            organization=self.organization, first_name="Josette", last_name="COUTURE",
            phone="613-601-2441",
        )
        csv = "Josette;COUTURE;autre@example.com;613-601-2441\n"
        response = self.client.post(
            self.url, {"file": csv_upload(csv), "kind": "customers"}, format="multipart"
        )
        self.assertEqual(response.json()["status"]["duplicates_count"], 1)

    def test_saute_un_membre_sans_courriel_ni_telephone(self):
        """Sans clé de repli, ceux-là n'étaient jamais vus comme doublons et
        chaque réimport les inscrivait une fois de plus."""
        Customer.objects.create(
            organization=self.organization, first_name="Josette", last_name="COUTURE"
        )
        csv = "Josette;COUTURE;;\n"
        response = self.client.post(
            self.url, {"file": csv_upload(csv), "kind": "customers"}, format="multipart"
        )
        self.assertEqual(response.json()["status"]["duplicates_count"], 1)
        self.assertEqual(Customer.objects.filter(organization=self.organization).count(), 1)

    def test_un_membre_d_une_autre_organisation_n_est_pas_un_doublon(self):
        voisine_user, voisine = second_user_with_organization()
        Customer.objects.create(
            organization=voisine, first_name="Josette", last_name="COUTURE",
            email="josette.couture@example.com",
        )
        csv = "Josette;COUTURE;josette.couture@example.com;613-601-2441\n"
        response = self.client.post(
            self.url, {"file": csv_upload(csv), "kind": "customers"}, format="multipart"
        )
        self.assertEqual(response.json()["status"]["created_count"], 1)
