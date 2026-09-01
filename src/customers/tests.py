from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from src.customers.customer_import import CustomerImporter
from src.customers.membership import archive, find_archived
from src.customers.models import Customer
from src.helpers.tests import (
    authenticate_admin,
    authenticate_user,
    create_admin_user,
    create_customer,
    create_lending,
    create_organization,
    create_user,
)
from src.imports.runner import run_import
from src.items.models import Book, Lending


# Create your tests here.
class CustomerTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.admin_user = create_admin_user()
        cls.organization = create_organization(owner=cls.user)
        cls.admin_organization = create_organization(owner=cls.admin_user)
        cls.books = []

        cls.customer = create_customer(organization=cls.organization)

    def setUp(self):
        pass

    def test_get_customer(self):
        """
        Ensure customers can only be seen by their org
        """
        authenticate_user(self)
        url = reverse(
            "get_put_patch_delete_customer", kwargs={"pk": self.customer.id}
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_customer_anonymous(self):
        """
        Ensure customers can only be seen by their org
        """
        url = reverse("get_put_patch_delete_customer", kwargs={"pk": 1})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_update_customer(self):
        """
        Ensure customers can be updated by an user of the organization the collection belongs to
        """
        authenticate_user(self)
        url = reverse(
            "get_put_patch_delete_customer", kwargs={"pk": self.customer.id}
        )
        response = self.client.patch(url, {"email": "jean@nouveau.ca"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.email, "jean@nouveau.ca")

    def test_update_customer_anonymous(self):
        """
        Ensure customers can only be updated by authenticated user
        """
        url = reverse("get_put_patch_delete_customer", kwargs={"pk": 1})
        data = {"name": "New customer name"}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_update_customer_other_organization(self):
        """
        Ensure customers can only be updated by an user of the organization the collection belongs to
        """
        authenticate_admin(self)
        url = reverse(
            "get_put_patch_delete_customer", kwargs={"pk": self.customer.id}
        )
        response = self.client.patch(url, {"email": "vole@ailleurs.ca"})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.email, "jean@michel.ca")

    def test_get_customers(self):
        """
        Ensure customers access is limited to the org they belongs to
        """
        authenticate_user(self)
        url = reverse("list_post_customer")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_customers_anonymous(self):
        """
        Ensure customers access is limited to the org they belongs to
        """
        url = reverse("list_post_customer")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_post_customer(self):
        """
        Ensure customers can be created by an user of the organization the collection belongs to
        """
        authenticate_user(self)
        url = reverse("list_post_customer")
        data = {
            "first_name": "Jean",
            "last_name": "Petit",
            "email": "jean@petit.be",
            "phone": "1234567890",
            "language": "fr",
            "note": "Il est gentil",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json().get("email"), "jean@petit.be")
        self.assertEqual(response.json().get("organization"), self.organization.name)

    def test_post_customer_anonymous(self):
        """
        Ensure customers cannot be created by anonymous users
        """
        url = reverse("list_post_customer")
        data = {
            "first_name": "Jean",
            "last_name": "Petit",
            "email": "jean@petit.be",
            "phone": "1234567890",
            "language": "fr",
            "note": "Il est gentil",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class RemoveCustomerTests(APITestCase):
    """Retirer un membre : ce que ça doit faire, et surtout ce que ça ne doit pas.

    `Lending.customer` porte `on_delete=CASCADE`. Une suppression réelle
    emporterait donc l'historique des prêts, que la documentation promet de
    conserver. Ces tests tiennent la promesse ; si l'un d'eux tombe, c'est
    l'historique d'une bibliothèque qui part avec.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.admin_user = create_admin_user()
        cls.organization = create_organization(owner=cls.user)
        # L'organisation d'en face est créée APRÈS, pour qu'une lecture non
        # cloisonnée ne tombe pas sur la bonne par hasard.
        cls.admin_organization = create_organization(owner=cls.admin_user)
        cls.customer = create_customer(organization=cls.organization)
        cls.book = Book.objects.create(
            organization=cls.organization, title="Kukum", author="Michel Jean"
        )
        cls.lending = create_lending(
            organization=cls.organization, customer=cls.customer, book=cls.book
        )

    def url(self, customer=None):
        return reverse(
            "get_put_patch_delete_customer",
            kwargs={"pk": (customer or self.customer).id},
        )

    def test_retirer_un_membre_conserve_ses_prets(self):
        authenticate_user(self)
        response = self.client.delete(self.url())
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        # Le prêt est toujours là, et il désigne toujours la même personne.
        self.assertTrue(Lending.objects.filter(id=self.lending.id).exists())
        self.assertEqual(
            Lending.objects.get(id=self.lending.id).customer_id, self.customer.id
        )
        # Et la fiche elle-même n'a pas disparu : elle est retirée.
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.archived)

    def test_un_membre_retire_sort_de_la_liste(self):
        authenticate_user(self)
        self.client.delete(self.url())
        response = self.client.get(reverse("list_post_customer"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [customer["id"] for customer in response.json()],
            [],
        )

    def test_retirer_le_membre_d_une_autre_organisation_est_impossible(self):
        """🔴 Le cas qui compte : on ne retire pas chez le voisin."""
        authenticate_admin(self)
        response = self.client.delete(self.url())
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.archived)

    def test_retirer_un_membre_anonymement_est_impossible(self):
        response = self.client.delete(self.url())
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.archived)

    def test_rajouter_un_membre_retire_le_reinscrit(self):
        """Sans ça, `unique_together` rend une erreur Postgres illisible."""
        authenticate_user(self)
        self.client.delete(self.url())
        response = self.client.post(
            reverse("list_post_customer"),
            {
                "first_name": self.customer.first_name,
                "last_name": self.customer.last_name,
                "email": self.customer.email,
                "phone": "0000000000",
                "language": "fr",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # Réinscrit, pas dupliqué : c'est la même fiche, donc les mêmes prêts.
        self.assertEqual(
            Customer.objects.filter(organization=self.organization).count(), 1
        )
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.archived)
        self.assertEqual(self.customer.phone, "0000000000")

    def test_un_patch_ne_peut_pas_retirer_un_membre(self):
        """`archived` est en lecture seule : le retrait passe par DELETE."""
        authenticate_user(self)
        response = self.client.patch(self.url(), {"archived": True})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.archived)

    def test_reimporter_une_liste_reinscrit_un_membre_retire(self):
        """Le membre retiré ne doit pas être rangé en « doublon » et rester caché."""
        archive(self.customer)
        report = run_import(
            records=[
                {
                    "first_name": self.customer.first_name,
                    "last_name": self.customer.last_name,
                    "email": self.customer.email,
                    "phone": self.customer.phone,
                    "language": "fr",
                    "note": None,
                }
            ],
            importer=CustomerImporter(),
            organization_id=self.organization.id,
        )
        self.assertEqual(report.duplicates, [])
        self.assertEqual(len(report.created), 1)
        self.assertEqual(
            Customer.objects.filter(organization=self.organization).count(), 1
        )
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.archived)

    def test_un_import_ne_reinscrit_pas_le_membre_d_une_autre_organisation(self):
        """🔴 `find_archived` sans organisation réinscrirait chez le voisin."""
        archive(self.customer)
        run_import(
            records=[
                {
                    "first_name": self.customer.first_name,
                    "last_name": self.customer.last_name,
                    "email": self.customer.email,
                    "phone": self.customer.phone,
                    "language": "fr",
                    "note": None,
                }
            ],
            importer=CustomerImporter(),
            organization_id=self.admin_organization.id,
        )
        # La fiche du voisin reste retirée, et une NOUVELLE fiche est créée
        # dans l'organisation qui importe.
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.archived)
        self.assertEqual(
            Customer.objects.filter(organization=self.admin_organization).count(), 1
        )


class CustomerScopeTests(APITestCase):
    """Le cloisonnement de la LISTE, tenu par un test et non par la relecture.

    Il manquait : retirer `organization=...` de `CustomersList.get_queryset`
    laissait tous les autres tests verts. C'est la ligne la plus dangereuse
    du fichier — une liste non cloisonnée rend les membres d'une autre
    bibliothèque sans lever la moindre erreur.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.admin_user = create_admin_user()
        cls.organization = create_organization(owner=cls.user)
        cls.admin_organization = create_organization(owner=cls.admin_user)
        cls.mien = create_customer(organization=cls.organization)
        cls.du_voisin = Customer.objects.create(
            organization=cls.admin_organization,
            first_name="Ailleurs",
            last_name="Voisine",
            email="ailleurs@example.com",
        )

    def test_la_liste_ne_rend_que_les_membres_de_l_organisation(self):
        authenticate_user(self)
        response = self.client.get(reverse("list_post_customer"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [customer["id"] for customer in response.json()], [self.mien.id]
        )

    def test_la_liste_du_voisin_ne_rend_que_les_siens(self):
        """Pris dans les deux sens : un filtre inversé passerait sinon."""
        authenticate_admin(self)
        response = self.client.get(reverse("list_post_customer"))
        self.assertEqual(
            [customer["id"] for customer in response.json()], [self.du_voisin.id]
        )


class ReinstatementBoundaryTests(APITestCase):
    """Ce que `find_archived` ne doit SURTOUT pas attraper.

    Trois mutants survivaient à la première version de ces tests : sans
    `archived=True`, sans `first_name`, sans `last_name`, les dix-sept
    tests restaient verts. Le code était juste ; rien ne le tenait.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.organization = create_organization(owner=cls.user)

    def setUp(self):
        authenticate_user(self)

    def post(self, **fields):
        data = {"first_name": "Jean", "last_name": "Michel", "language": "fr"}
        data.update(fields)
        return self.client.post(reverse("list_post_customer"), data)

    def test_rajouter_un_membre_ACTIF_ne_reecrit_pas_sa_fiche(self):
        """Sans `archived=True`, l'ajout écrasait une fiche active en silence."""
        actif = Customer.objects.create(
            organization=self.organization,
            first_name="Jean",
            last_name="Michel",
            email="jean@michel.ca",
            note="Note d'origine",
        )
        response = self.post(email="jean@michel.ca", note="Note écrasante")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        actif.refresh_from_db()
        self.assertEqual(actif.note, "Note d'origine")
        self.assertEqual(Customer.objects.count(), 1)

    def test_un_telephone_partage_ne_reinscrit_pas_un_homonyme(self):
        """Un téléphone de foyer est partagé : le nom fait la personne."""
        retire = Customer.objects.create(
            organization=self.organization,
            first_name="Jeanne",
            last_name="Michel",
            phone="5551234",
            archived=True,
        )
        response = self.post(first_name="Jean", phone="5551234")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # La fiche de Jeanne n'a pas bougé, et Jean a bien la sienne.
        retire.refresh_from_db()
        self.assertTrue(retire.archived)
        self.assertEqual(retire.first_name, "Jeanne")
        self.assertEqual(Customer.objects.filter(archived=False).count(), 1)

    def test_un_membre_sans_contact_retire_puis_rajoute_retrouve_sa_fiche(self):
        """🔴 Le trou mesuré en relecture : deux fiches, l'historique sur la cachée.

        `unique_together` ne dit rien ici — deux NULL sont distincts en
        Postgres — donc rien n'empêchait la seconde fiche. La personne
        redevenait visible, ses prêts restaient accrochés à la fiche cachée.
        """
        book = Book.objects.create(
            organization=self.organization, title="Kukum", author="Michel Jean"
        )
        sans_contact = Customer.objects.create(
            organization=self.organization, first_name="Sans", last_name="Contact"
        )
        lending = create_lending(
            organization=self.organization, customer=sans_contact, book=book
        )
        archive(sans_contact)

        response = self.post(first_name="Sans", last_name="Contact")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Customer.objects.count(), 1)
        sans_contact.refresh_from_db()
        self.assertFalse(sans_contact.archived)
        # Et l'historique est sur la fiche VISIBLE, pas sur une fiche cachée.
        self.assertEqual(
            Lending.objects.get(id=lending.id).customer_id, sans_contact.id
        )

    def test_un_membre_sans_contact_reimporte_retrouve_aussi_sa_fiche(self):
        sans_contact = Customer.objects.create(
            organization=self.organization, first_name="Sans", last_name="Contact"
        )
        archive(sans_contact)
        run_import(
            records=[{
                "first_name": "Sans", "last_name": "Contact",
                "email": None, "phone": None, "language": None, "note": None,
            }],
            importer=CustomerImporter(),
            organization_id=self.organization.id,
        )
        self.assertEqual(Customer.objects.count(), 1)
        sans_contact.refresh_from_db()
        self.assertFalse(sans_contact.archived)

    def test_une_collision_a_l_edition_rend_un_400_et_non_un_500(self):
        """Corriger un courriel vers celui d'un autre membre.

        La contrainte partait en `IntegrityError` nue, donc un 500, et
        l'interface affichait « Une erreur inconnue est survenue ».
        """
        Customer.objects.create(
            organization=self.organization,
            first_name="Jean", last_name="Michel", email="pris@example.com",
        )
        autre = Customer.objects.create(
            organization=self.organization,
            first_name="Jean", last_name="Michel", email="libre@example.com",
        )
        response = self.client.patch(
            reverse("get_put_patch_delete_customer", kwargs={"pk": autre.id}),
            {"email": "pris@example.com"},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.json())
        autre.refresh_from_db()
        self.assertEqual(autre.email, "libre@example.com")

    def test_une_collision_ne_regarde_pas_les_autres_bibliotheques(self):
        """🔴 Le contrôle neuf est lui aussi une requête à cloisonner."""
        ailleurs_user = create_admin_user()
        ailleurs = create_organization(owner=ailleurs_user)
        Customer.objects.create(
            organization=ailleurs,
            first_name="Jean", last_name="Michel", email="jean@michel.ca",
        )
        response = self.post(email="jean@michel.ca")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class FindRemovedTests(TestCase):
    """`find_archived` éprouvé DIRECTEMENT, et pas seulement à travers l'API.

    Deux mutants ont survécu à la couverture par les vues : la validation du
    sérialiseur refuse désormais la collision avant que `find_archived` ait
    son mot à dire, donc le défaut n'était plus visible de l'extérieur. Il
    reste réel : `CustomerImporter` n'utilise PAS le sérialiseur, et
    `take_removed` retombe sur cette fonction dès que son index n'est pas
    celui de l'organisation traitée. Une fonction dont le contrat n'est tenu
    que par ses appelants finit par être appelée autrement.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.admin_user = create_admin_user()
        cls.organization = create_organization(owner=cls.user)
        cls.voisine = create_organization(owner=cls.admin_user)

    def customer(self, organization, archived=False, **fields):
        data = {
            "first_name": "Jean", "last_name": "Michel", "email": "jean@michel.ca",
        }
        data.update(fields)
        return Customer.objects.create(
            organization=organization, archived=archived, **data
        )

    def test_ne_rend_jamais_une_fiche_ACTIVE(self):
        """Sinon un ajout écrase la fiche d'un membre bien inscrit."""
        self.customer(self.organization, archived=False)
        self.assertIsNone(
            find_archived(
                organization_id=self.organization.id,
                first_name="Jean", last_name="Michel", email="jean@michel.ca",
            )
        )

    def test_rend_la_fiche_retiree(self):
        retire = self.customer(self.organization, archived=True)
        self.assertEqual(
            find_archived(
                organization_id=self.organization.id,
                first_name="Jean", last_name="Michel", email="jean@michel.ca",
            ),
            retire,
        )

    def test_ne_traverse_pas_les_organisations(self):
        """🔴 Réinscrire le membre d'une autre bibliothèque."""
        self.customer(self.voisine, archived=True)
        self.assertIsNone(
            find_archived(
                organization_id=self.organization.id,
                first_name="Jean", last_name="Michel", email="jean@michel.ca",
            )
        )

    def test_exige_une_organisation(self):
        self.customer(self.organization, archived=True)
        self.assertIsNone(
            find_archived(
                organization_id=None,
                first_name="Jean", last_name="Michel", email="jean@michel.ca",
            )
        )


class TakeRemovedTests(TestCase):
    """La garde d'organisation de l'index préchargé de `CustomerImporter`.

    L'index est bâti une fois, pour une organisation. Réutiliser
    l'importateur sur une autre sans garde réinscrirait le membre du voisin
    — et l'index, lui, ne porte plus trace de son origine.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.admin_user = create_admin_user()
        cls.organization = create_organization(owner=cls.user)
        cls.voisine = create_organization(owner=cls.admin_user)
        cls.retire = Customer.objects.create(
            organization=cls.organization,
            first_name="Jean", last_name="Michel", email="jean@michel.ca",
            archived=True,
        )

    def record(self):
        return {
            "first_name": "Jean", "last_name": "Michel",
            "email": "jean@michel.ca", "phone": None,
        }

    def test_l_index_d_une_organisation_ne_sert_pas_a_une_autre(self):
        importer = CustomerImporter()
        importer.load_removed(self.organization.id)
        self.assertIsNone(
            importer.take_removed(self.record(), self.voisine.id)
        )

    def test_l_index_sert_bien_a_son_organisation(self):
        importer = CustomerImporter()
        importer.load_removed(self.organization.id)
        self.assertEqual(
            importer.take_removed(self.record(), self.organization.id), self.retire
        )

    def test_une_fiche_n_est_reinscrite_qu_une_fois(self):
        """Deux lignes d'un même fichier ne se partagent pas la fiche."""
        importer = CustomerImporter()
        importer.load_removed(self.organization.id)
        self.assertEqual(
            importer.take_removed(self.record(), self.organization.id), self.retire
        )
        self.assertIsNone(
            importer.take_removed(self.record(), self.organization.id)
        )
