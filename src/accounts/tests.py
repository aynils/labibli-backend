from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from src.accounts.models import Organization
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

    def setUp(self):
        pass

    def test_auto_create_organization(self):
        organization = Organization.objects.get(owner=self.user)
        self.assertEqual(organization.name, f"{self.user.email} - default organization")

    def test_get_organizations(self):
        authenticate_admin(self)
        url = reverse("get_put_patch_delete_organizations", kwargs={"pk": 1})
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
        url = reverse("get_put_patch_delete_organizations", kwargs={"pk": 1})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_update_organizations(self):
        authenticate_user(self)
        url = reverse("get_put_patch_delete_organizations", kwargs={"pk": 1})
        data = {"name": "Test Rename Organization"}
        response = self.client.put(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get("name"), "Test Rename Organization")

    def test_update_other_organizations(self):
        """
        Ensure only owner can update an organization
        """
        authenticate_admin(self)
        url = reverse("get_put_patch_delete_organizations", kwargs={"pk": 1})
        data = {"name": "Test Rename Organization"}
        response = self.client.put(url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
