from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Organization
from helpers.tests import authenticate_user, authenticate_admin, create_admin_user, create_user


class OrganizationTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.admin_user = create_admin_user()
        cls.organization = Organization.objects.create(
            owner=cls.admin_user,
            name="Admin organisation",
        )

    def setUp(self):
        pass

    def test_create_organization(self):
        """
        Ensure we can create a new organization object.
        """
        authenticate_user(self)
        url = reverse('post_organizations')
        data = {'name': 'Test Organization'}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        new_organization = Organization.objects.get(id=2)
        self.assertEqual(new_organization.name, 'Test Organization')
        self.assertEqual(new_organization.owner, self.user)

    def test_get_organizations(self):
        authenticate_admin(self)
        url = reverse('get_put_patch_delete_organizations', kwargs={"pk": 1})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json().get('name'), self.organization.name)

    def test_get_other_organizations(self):
        """
        Ensure only owner can retrieve an organization
        """
        authenticate_user(self)
        url = reverse('get_put_patch_delete_organizations', kwargs={"pk": 1})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_update_organizations(self):
        authenticate_admin(self)
        url = reverse('get_put_patch_delete_organizations', kwargs={"pk": 1})
        data = {'name': 'Test Rename Organization'}
        response = self.client.put(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json().get('name'), 'Test Rename Organization')

    def test_update_other_organizations(self):
        """
        Ensure only owner can update an organization
        """
        authenticate_user(self)
        url = reverse('get_put_patch_delete_organizations', kwargs={"pk": 1})
        data = {'name': 'Test Rename Organization'}
        response = self.client.put(url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
