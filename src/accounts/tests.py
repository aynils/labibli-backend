from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from src.accounts.models import NOM_PAR_DEFAUT, Organization
from src.helpers.tests import (
    authenticate_admin,
    authenticate_user,
    create_admin_user,
    create_user,
)


class OrganizationTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.admin_user = create_admin_user()
        # ⚠️ L'organisation naît d'un signal `post_save` sur `User` : on la
        # RELIT plutôt que de la créer. Et on la garde, parce que ces tests
        # visaient « pk=1 » en dur — or la séquence de clés n'est pas
        # réinitialisée entre classes de test. Ajouter un fichier de tests
        # ailleurs dans le dépôt les faisait rougir, pour une raison qui
        # n'avait rien à voir avec ce qu'ils éprouvent.
        cls.organization = cls.user.employee_of_organization

    def setUp(self):
        pass

    def test_auto_create_organization(self):
        """🔴 Le nom d'attente ne doit contenir NI courriel NI « default ».

        Il valait « <courriel> - default organization » jusqu'au 01/09/2026. Ce
        nom se propageait à la collection, et la vitrine publique l'affiche en
        titre : vingt-deux bibliothèques ont publié l'adresse de leur direction
        sur une page ouverte à tous.
        """
        organization = Organization.objects.get(owner=self.user)
        self.assertEqual(organization.name, NOM_PAR_DEFAUT)
        self.assertNotIn("@", organization.name)
        self.assertNotIn("default", organization.name.lower())

    def test_get_organizations(self):
        authenticate_admin(self)
        url = reverse("get_put_patch_delete_organizations", kwargs={"pk": self.organization.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_current_organizations(self):
        authenticate_user(self)
        organization = Organization.objects.get(owner=self.user)
        url = reverse("get_current_organization")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get("name"), organization.name)

    def test_get_other_organizations(self):
        """
        Ensure only owner can retrieve an organization
        """
        authenticate_admin(self)
        url = reverse("get_put_patch_delete_organizations", kwargs={"pk": self.organization.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_update_organizations(self):
        authenticate_user(self)
        url = reverse("get_put_patch_delete_organizations", kwargs={"pk": self.organization.pk})
        data = {"name": "Test Rename Organization"}
        response = self.client.put(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get("name"), "Test Rename Organization")

    def test_update_other_organizations(self):
        """
        Ensure only owner can update an organization
        """
        authenticate_admin(self)
        url = reverse("get_put_patch_delete_organizations", kwargs={"pk": self.organization.pk})
        data = {"name": "Test Rename Organization"}
        response = self.client.put(url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
