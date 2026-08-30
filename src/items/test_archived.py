"""Un ouvrage archivé est un ouvrage caché.

Archiver sort un ouvrage de la circulation sans le perdre. Il ne doit donc
apparaître ni dans la vitrine publique — le public ne peut ni l'emprunter ni
savoir pourquoi il est grisé — ni dans la liste de la bibliothèque, sauf
demande explicite : sans cette porte de sortie, un ouvrage archivé
deviendrait impossible à désarchiver.
"""
from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from src.accounts.models import Organization
from src.helpers.query_params import is_true, positive_int
from src.helpers.tests import authenticate_user, create_collection, create_user
from src.items.models import Book


class IsTrueTests(SimpleTestCase):
    def test_reconnait_les_facons_de_dire_oui(self):
        for value in ("true", "True", "1", "t", "y", "yes", " TRUE "):
            self.assertTrue(is_true(value), value)

    def test_tout_le_reste_vaut_non(self):
        """Le défaut masque les archivés : il doit être le moins surprenant."""
        for value in (None, "", "false", "0", "n", "non", "peut-être"):
            self.assertFalse(is_true(value), repr(value))


class PositiveIntTests(SimpleTestCase):
    """Les vitrines sont publiques : n'importe qui peut taper n'importe quoi."""

    def test_lit_un_entier_positif(self):
        self.assertEqual(positive_int("3", 1), 3)

    def test_retombe_sur_le_defaut_pour_tout_le_reste(self):
        for value in (None, "", "abc", "1.5", "0", "-1", "-42"):
            self.assertEqual(positive_int(value, 7), 7, repr(value))


class ArchivedBooksTests(APITestCase):
    def setUp(self):
        self.user = create_user()
        self.organization = Organization.objects.get(owner=self.user)
        self.collection = create_collection(self.organization, slug="ma-collection")
        self.visible = Book.objects.create(
            organization=self.organization, title="En rayon", author="Michel Jean"
        )
        self.archive = Book.objects.create(
            organization=self.organization, title="Au grenier",
            author="Michel Jean", archived=True,
        )
        for book in (self.visible, self.archive):
            book.collections.add(self.collection)

    def titles_from_public(self, query=""):
        url = reverse("get_collection_shared", kwargs={"slug": self.collection.slug})
        response = self.client.get(url + query)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return [book["title"] for book in response.json()["books"]["results"]]

    def titles_from_list(self, query=""):
        authenticate_user(self)
        response = self.client.get(reverse("list_post_books") + query)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return [book["title"] for book in response.json()["results"]]

    def test_la_vitrine_publique_ne_montre_pas_les_archives(self):
        self.assertEqual(self.titles_from_public(), ["En rayon"])

    def test_le_public_ne_peut_pas_reclamer_les_archives(self):
        """Le paramètre existe pour la bibliothèque, pas pour ses visiteurs."""
        self.assertEqual(self.titles_from_public("?archived=true"), ["En rayon"])

    def test_la_liste_interne_masque_les_archives_par_defaut(self):
        self.assertEqual(self.titles_from_list(), ["En rayon"])

    def test_la_liste_interne_les_montre_sur_demande(self):
        titles = self.titles_from_list("?archived=true")
        self.assertIn("Au grenier", titles)
        self.assertIn("En rayon", titles)

    def test_un_parametre_qui_ne_dit_pas_oui_laisse_les_archives_caches(self):
        self.assertEqual(self.titles_from_list("?archived=false"), ["En rayon"])

    def test_l_ecran_de_collection_de_la_bibliotheque_les_montre_sur_demande(self):
        """L'autre sens du drapeau public, sans quoi la bibliothèque perdrait
        l'accès à ses archivés par ses propres écrans."""
        authenticate_user(self)
        url = reverse("get_put_patch_delete_collection", kwargs={"pk": self.collection.pk})
        response = self.client.get(url + "?archived=true")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = [book["title"] for book in response.json()["books"]["results"]]
        self.assertIn("Au grenier", titles)

    def test_l_ecran_de_collection_les_masque_par_defaut(self):
        authenticate_user(self)
        url = reverse("get_put_patch_delete_collection", kwargs={"pk": self.collection.pk})
        titles = [b["title"] for b in self.client.get(url).json()["books"]["results"]]
        self.assertEqual(titles, ["En rayon"])

    def test_le_decompte_public_ignore_les_archives(self):
        """Le compte et le nombre de pages doivent suivre le filtre.

        Sinon la vitrine annonce des ouvrages qu'elle n'affichera jamais.
        """
        url = reverse("get_collection_shared", kwargs={"slug": self.collection.slug})
        books = self.client.get(url).json()["books"]
        self.assertEqual(books["count"], 1)
        self.assertEqual(books["num_pages"], 1)

    def test_la_recherche_publique_ne_ramene_pas_un_archive(self):
        url = reverse("get_collection_shared", kwargs={"slug": self.collection.slug})
        response = self.client.get(url + "?query=grenier")
        self.assertEqual(response.json()["books"]["results"], [])

    def test_une_page_hors_bornes_ne_fait_pas_tomber_la_vitrine(self):
        """Masquer des ouvrages fait rétrécir la pagination.

        Un lien partagé vers une page devenue inexistante doit rendre la
        dernière page, pas une erreur 500 sur une vitrine publique.
        """
        url = reverse("get_collection_shared", kwargs={"slug": self.collection.slug})
        response = self.client.get(url + "?page=99")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()["books"]["results"]), 1)

    def test_une_page_ou_une_taille_absurde_ne_fait_pas_tomber_la_vitrine(self):
        """Six façons de rendre un 500 sans même être authentifié.

        Le bornage traitait la plage, pas le type, ni la taille de page.
        """
        url = reverse("get_collection_shared", kwargs={"slug": self.collection.slug})
        for query in ("?page=0", "?page=-3", "?page=abc", "?page=1.5",
                      "?size=0", "?size=abc", "?size=-1"):
            with self.subTest(query=query):
                response = self.client.get(url + query)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(len(response.json()["books"]["results"]), 1)

    def test_l_ecran_de_collection_ignore_un_parametre_qui_ne_dit_pas_oui(self):
        """La règle « ce qui ne dit pas oui vaut non » est écrite deux fois ;
        elle doit être tenue des deux côtés."""
        authenticate_user(self)
        url = reverse("get_put_patch_delete_collection", kwargs={"pk": self.collection.pk})
        titles = [b["title"] for b in self.client.get(url + "?archived=false").json()["books"]["results"]]
        self.assertEqual(titles, ["En rayon"])

    def test_la_liste_des_collections_montre_les_archives_sur_demande(self):
        """Le drapeau public ne doit pas non plus être posé sur cette vue."""
        authenticate_user(self)
        response = self.client.get(reverse("list_post_collections") + "?archived=true")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = [b["title"] for c in response.json() for b in c["books"]["results"]]
        self.assertIn("Au grenier", titles)

    def test_la_vitrine_n_expose_plus_les_identifiants_de_tous_les_ouvrages(self):
        """`book_set` listait tous les ids, archivés compris."""
        url = reverse("get_collection_shared", kwargs={"slug": self.collection.slug})
        self.assertNotIn("book_set", self.client.get(url).json())
