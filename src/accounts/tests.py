from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Organization, User


def authenticate_user(self):
    result = self.client.post('/api/users/login/', {"email": self.user.email, "password": "testing"})
    assert result.status_code == 200
    token = result.json().get('token')
    self.client.credentials(HTTP_AUTHORIZATION='Token ' + token)


def authenticate_admin(self):
    result = self.client.post('/api/users/login/', {"email": self.admin_user.email, "password": "testing"})
    assert result.status_code == 200
    token = result.json().get('token')
    self.client.credentials(HTTP_AUTHORIZATION='Token ' + token)


def create_admin_user():
    admin_user = User.objects.create_superuser(
        first_name='test_admin_user',
        email='test_admin_user@test.com',
        password='testing'
    )
    admin_user.is_verified = True
    admin_user.save()
    return admin_user


def create_user():
    user = User.objects.create_user(
        first_name='testuser',
        email='testuser@test.com',
        password='testing'
    )
    user.is_verified = True
    user.save()
    return user


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
        url = reverse('get_put_patch_organizations', kwargs={"pk": 1})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json().get('name'), self.organization.name)

    def test_get_other_organizations(self):
        authenticate_user(self)
        url = reverse('get_put_patch_organizations', kwargs={"pk": 1})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_update_organizations(self):
        authenticate_admin(self)
        url = reverse('get_put_patch_organizations', kwargs={"pk": 1})
        data = {'name': 'Test Rename Organization'}
        response = self.client.put(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_update_other_organizations(self):
        """
        Ensure only owner can update an organization
        """
        authenticate_user(self)
        url = reverse('get_put_patch_organizations', kwargs={"pk": 1})
        data = {'name': 'Test Rename Organization'}
        response = self.client.put(url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
