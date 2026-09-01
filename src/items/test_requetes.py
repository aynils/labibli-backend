"""Le verrou anti N+1 sur ``/api/items/collections/``.

Ce point d'API sert la page « Mon compte » du produit ET la vitrine publique.
Il faisait **126 requêtes SQL** pour une bibliothèque de 24 ouvrages, parce que
la sérialisation allait chercher, ouvrage par ouvrage : ses catégories (deux
fois), ses collections, son organisation, et le compte de ses prêts en cours.
Rien de tout ça ne lève d'erreur ni ne se voit dans la réponse — la seule chose
qui le montre est le compteur de requêtes. D'où ce fichier.

⚠️ Le nombre attendu est un BUDGET, pas une décoration : il est constant, il ne
doit pas dépendre du nombre d'ouvrages. Le second test le vérifie en doublant
la collection — c'est lui qui rattrapera un N+1 réintroduit, même si le premier
est ajusté à la hausse un jour pour une bonne raison.
"""
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from src.helpers.tests import (
    authenticate_user,
    create_admin_user,
    create_category,
    create_customer,
    create_lending,
    create_organization,
    create_user,
)
from src.items.models import Book, Category, Collection

# Mesuré, pas estimé. Le détail, dans l'ordre où elles partent :
#   1. le jeton d'authentification et la personne qui le porte (une jointure) ;
#   2. son organisation, pour le contrôle d'accès ;
#   3. les collections de cette organisation, avec l'organisation et sa
#      propriétaire jointes (`select_related`) ;
#   4. le COUNT de la pagination des ouvrages ;
#   5. la page d'ouvrages, avec leur organisation jointe et le compte des
#      prêts en cours en sous-requête corrélée ;
#   6. toutes les catégories de la page, d'un coup (`prefetch_related`) ;
#   7. toutes les collections de la page, d'un coup (`prefetch_related`).
BUDGET_REQUETES = 7


class NombreDeRequetesCollectionsTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.organization = create_organization(owner=cls.user)
        # ⚠️ Une collection est créée AUTOMATIQUEMENT avec l'organisation ;
        # en ajouter une seconde donnerait deux collections à sérialiser et
        # fausserait le budget. On travaille dans celle qui existe.
        cls.collection = Collection.objects.get(organization=cls.organization)
        cls.collection.slug = "collection-a-nous"
        cls.collection.save()
        cls.categorie = create_category(organization=cls.organization)
        cls.membre = create_customer(cls.organization)

        cls.livres = [cls.ajouter_livre(index) for index in range(6)]
        # Un prêt en cours : la pastille « emprunté » est justement ce qui
        # coûtait une requête par ouvrage.
        create_lending(cls.organization, book=cls.livres[0], customer=cls.membre)

        # 🔴 La voisine. Elle existe pour deux raisons : vérifier que rien de
        # chez elle ne ressort, et s'assurer que le compteur de requêtes ne
        # dépend pas de ce que les AUTRES bibliothèques ont en base.
        cls.voisine_user = create_admin_user()
        cls.voisine = create_organization(owner=cls.voisine_user)
        cls.voisine.name = "Bibliothèque voisine"
        cls.voisine.save()
        cls.collection_voisine = Collection.objects.get(organization=cls.voisine)
        cls.categorie_voisine = Category.objects.create(
            organization=cls.voisine, name="Catégorie de la voisine"
        )
        for index in range(6):
            livre = Book.objects.create(
                organization=cls.voisine,
                title=f"Livre voisin {index}",
                author="Autrice voisine",
                isbn=f"999000000{index:04d}",
            )
            livre.collections.add(cls.collection_voisine)
            livre.categories.add(cls.categorie_voisine)

    @classmethod
    def ajouter_livre(cls, index):
        livre = Book.objects.create(
            organization=cls.organization,
            title=f"Livre {index}",
            author="Autrice de test",
            isbn=f"111000000{index:04d}",
        )
        livre.collections.add(cls.collection)
        livre.categories.add(cls.categorie)
        return livre

    def test_le_nombre_de_requetes_tient_dans_le_budget(self):
        authenticate_user(self)
        url = reverse("list_post_collections")
        with self.assertNumQueries(BUDGET_REQUETES):
            reponse = self.client.get(url)
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        self.assertEqual(len(reponse.data[0]["books"]["results"]), 6)

    def test_le_nombre_de_requetes_ne_depend_pas_du_nombre_d_ouvrages(self):
        """Le vrai verrou : un N+1 se voit à ce que le compteur SUIVE la page."""
        authenticate_user(self)
        url = reverse("list_post_collections")

        with self.assertNumQueries(BUDGET_REQUETES):
            self.client.get(url)

        for index in range(6, 18):
            self.ajouter_livre(index)

        with self.assertNumQueries(BUDGET_REQUETES):
            reponse = self.client.get(url)
        self.assertEqual(len(reponse.data[0]["books"]["results"]), 18)

    def test_une_page_reduite_coute_le_meme_nombre_de_requetes(self):
        authenticate_user(self)
        url = reverse("list_post_collections")
        with self.assertNumQueries(BUDGET_REQUETES):
            reponse = self.client.get(f"{url}?size=1")
        self.assertEqual(len(reponse.data[0]["books"]["results"]), 1)

    def test_rien_de_la_voisine_ne_ressort(self):
        """🔴 Le `prefetch_related` ne doit pas élargir ce qui est rendu."""
        authenticate_user(self)
        reponse = self.client.get(reverse("list_post_collections"))

        self.assertEqual(len(reponse.data), 1)
        self.assertEqual(reponse.data[0]["slug"], "collection-a-nous")

        for livre in reponse.data[0]["books"]["results"]:
            noms = [categorie["name"] for categorie in livre["categories"]]
            self.assertNotIn(
                "Catégorie de la voisine",
                noms,
                "Une catégorie d'une AUTRE bibliothèque est ressortie.",
            )
            self.assertNotIn(
                self.collection_voisine.id,
                livre["collections"],
                "La collection d'une AUTRE bibliothèque est ressortie.",
            )
            self.assertEqual(livre["organization"], self.organization.name)
