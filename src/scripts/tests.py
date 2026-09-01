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
# Les deux recours par titre partent sur le réseau sans passer par
# `find_book_details` : sans les neutraliser, la suite passe de 0,2 s à 39 s
# et devient dépendante de Wikipédia et d'OpenLibrary.
SUMMARY_BY_TITLE = "src.items.book_import.get_wikipedia_fr_summary"
COVER_BY_TITLE = "src.items.book_import.get_cover_by_title"


def sans_reseau(test):
    """Coupe les recours par titre pour la durée du test."""
    for cible in (SUMMARY_BY_TITLE, COVER_BY_TITLE):
        patcher = patch(cible, return_value=None)
        patcher.start()
        test.addCleanup(patcher.stop)


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
        sans_reseau(self)
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

    @patch(RESOLVE, return_value=None)
    @patch(LOOKUP, return_value=book_details())
    def test_lit_les_colonnes_dans_l_ordre_de_l_entete(self, lookup, resolve):
        """Un en-tête qui nomme ses colonnes fait foi, quel que soit leur ordre.

        Avant le 31/08/2026 l'en-tête n'était que sauté et les colonnes
        lues dans l'ordre interne : un fichier commençant par « Titre »
        chargeait le titre dans l'ISBN et l'auteur dans le titre. Aucune
        erreur, aucun journal — trente-deux fiches fausses en production, et
        le défaut ne se voit qu'en regardant la vitrine.
        """
        response = self.client.post(
            self.url,
            {"file": xlsx_upload([
                ("Titre", "Auteur", "Catégorie"),
                ("Kukum", "Michel Jean", "Romans"),
            ])},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        book = Book.objects.get(organization=self.organization)
        self.assertEqual(book.title, "Kukum")
        self.assertEqual(book.author, "Michel Jean")
        # La colonne que l'en-tête ne nomme pas reste vide : mieux vaut un
        # champ absent qu'un champ rempli avec le contenu du voisin.
        self.assertFalse(book.isbn)
        self.assertEqual([c.name for c in book.categories.all()], ["Romans"])

    @patch(RESOLVE, return_value=None)
    @patch(LOOKUP, return_value=None)
    def test_trouve_resume_et_couverture_sans_aucune_notice(self, lookup, resolve):
        """Aucun catalogue ne répond : Wikipédia et OpenLibrary restent joignables.

        `find_book_details` abandonne TOUT dès qu'aucune notice ne sort d'un
        catalogue interrogé par ISBN — couverture comprise. Or la recherche
        par titre n'a pas besoin d'ISBN. Le 31/08/2026, quota Google épuisé,
        « Le petit prince » et « Maus » entraient nus dans la médiathèque de
        démonstration alors que leur article existe.

        Et c'est le titre DU FICHIER qui sert : la bibliothèque écrit « La
        servante écarlate », le catalogue « La servante écarlate : roman », et
        seul le premier trouve quoi que ce soit.
        """
        with patch(SUMMARY_BY_TITLE, return_value="Un roman dystopique.") as resume, \
                patch(COVER_BY_TITLE, return_value=None) as couverture:
            self.client.post(
                self.url,
                {"file": xlsx_upload([(None, "La servante écarlate", "Margaret Atwood")])},
                format="multipart",
            )
        book = Book.objects.get(organization=self.organization)
        self.assertEqual(book.description, "Un roman dystopique.")
        resume.assert_called_once_with(title="La servante écarlate", author="Margaret Atwood")
        couverture.assert_called_once_with(title="La servante écarlate", author="Margaret Atwood")

    @patch(RESOLVE, return_value=None)
    @patch(LOOKUP, return_value=book_details())
    def test_ne_cherche_pas_par_titre_quand_la_notice_suffit(self, lookup, resolve):
        """Le recours coûte une requête réseau : il ne part que s'il manque."""
        with patch(SUMMARY_BY_TITLE) as resume:
            self.client.post(
                self.url,
                {"file": xlsx_upload([("9782764813447", "Kukum", "Michel Jean")])},
                format="multipart",
            )
        resume.assert_not_called()

    @patch(LOOKUP, return_value=book_details())
    def test_un_isbn_retrouve_sur_un_ouvrage_deja_present_est_un_doublon(self, lookup):
        """Renvoyer son fichier ne doit pas produire un mur d'erreurs Postgres.

        Le fichier ne porte pas d'ISBN ; la fiche en base en porte un, posé
        par la résolution au premier passage. Les clés de la ligne ne se
        reconnaissent donc pas, et l'écriture partait sur la contrainte
        d'unicité (isbn, organization, title) : dix-neuf pavés d'erreur
        Postgres dans le compte rendu du 31/08/2026, là où « doublon » est
        la bonne réponse. C'est le geste le plus banal d'une bibliothèque —
        « j'ai ajouté vingt titres, je renvoie le fichier ».
        """
        # L'éditeur est la clé du défaut : la fiche en base le porte, posé
        # par le catalogue au premier passage, et le fichier ne l'a jamais eu.
        # La clé de repli (titre|auteur|éditeur) ne se reconnaît donc PAS, et
        # sans l'ISBN retrouvé rien n'arrête l'écriture avant la contrainte.
        Book.objects.create(
            organization=self.organization, title="Kukum",
            author="Michel Jean", isbn="9782764813447",
            publisher="Libre Expression",
        )
        with patch(RESOLVE) as resolve:
            resolve.return_value = type("Match", (), {"isbn": "9782764813447"})()
            response = self.client.post(
                self.url,
                {"file": xlsx_upload([(None, "Kukum", "Michel Jean")])},
                format="multipart",
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"]["duplicates_count"], 1)
        self.assertEqual(response.data["status"]["errors"], [])
        self.assertEqual(Book.objects.filter(organization=self.organization).count(), 1)

    @patch(LOOKUP, return_value=book_details())
    def test_un_isbn_deja_present_ailleurs_ne_bloque_pas_l_import(self, lookup):
        """🔴 Le contrôle porte l'organisation, sinon il rejette le voisin.

        Une autre bibliothèque a catalogué le même titre sous le même ISBN.
        Le nôtre doit entrer : c'est exactement la panne payée le 30/08, où
        un titre déjà connu ailleurs était refusé en silence.
        """
        voisine_user, voisine = second_user_with_organization()
        Book.objects.create(
            organization=voisine, title="Kukum",
            author="Michel Jean", isbn="9782764813447",
        )
        with patch(RESOLVE) as resolve:
            resolve.return_value = type("Match", (), {"isbn": "9782764813447"})()
            self.client.post(
                self.url,
                {"file": xlsx_upload([(None, "Kukum", "Michel Jean")])},
                format="multipart",
            )
        self.assertEqual(Book.objects.filter(organization=self.organization).count(), 1)
        self.assertEqual(Book.objects.filter(organization=voisine).count(), 1)

    @patch(LOOKUP, return_value=book_details())
    def test_lit_un_fichier_sans_entete_dans_l_ordre_interne(self, lookup):
        """Sans en-tête, l'ordre des colonnes internes reste la seule règle.

        La moitié des fichiers reçus n'ont pas d'en-tête — celui des membres
        de l'Alliance Française n'en a pas. La correction de l'en-tête ne
        doit pas leur retirer leur mode de lecture.
        """
        self.client.post(
            self.url,
            {"file": xlsx_upload([("9782764813447", "Kukum", "Michel Jean")])},
            format="multipart",
        )
        book = Book.objects.get(organization=self.organization)
        self.assertEqual(book.isbn, "9782764813447")
        self.assertEqual(book.title, "Kukum")

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

    def test_ne_REINSCRIT_pas_un_membre_deja_la_et_complete_sa_fiche(self):
        """La garantie de ce test n'a pas changé : la personne n'entre pas deux
        fois. Ce qui a changé le 01/09/2026, c'est ce qu'on fait de la ligne —
        elle était jetée, elle complète maintenant les champs vides. Le
        téléphone que la bibliothèque a collecté depuis entre enfin.
        """
        customer = Customer.objects.create(
            organization=self.organization, first_name="Josette", last_name="COUTURE",
            email="josette.couture@example.com",
        )
        csv = "Josette;COUTURE;josette.couture@example.com;613-601-2441\n"
        response = self.client.post(
            self.url, {"file": csv_upload(csv), "kind": "customers"}, format="multipart"
        )
        # 🔑 L'assertion qui compte, et qui n'a pas bougé.
        self.assertEqual(Customer.objects.filter(organization=self.organization).count(), 1)
        self.assertEqual(response.json()["status"]["updated_count"], 1)
        customer.refresh_from_db()
        self.assertEqual(customer.phone, "613-601-2441")

    def test_reconnait_un_membre_par_son_TELEPHONE_et_complete_son_courriel(self):
        """`unique_together` reconnaît un membre par courriel OU téléphone."""
        customer = Customer.objects.create(
            organization=self.organization, first_name="Josette", last_name="COUTURE",
            phone="613-601-2441",
        )
        csv = "Josette;COUTURE;autre@example.com;613-601-2441\n"
        response = self.client.post(
            self.url, {"file": csv_upload(csv), "kind": "customers"}, format="multipart"
        )
        self.assertEqual(Customer.objects.filter(organization=self.organization).count(), 1)
        self.assertEqual(response.json()["status"]["updated_count"], 1)
        customer.refresh_from_db()
        # Le courriel était vide : il se comble. Il n'aurait PAS été remplacé.
        self.assertEqual(customer.email, "autre@example.com")

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
