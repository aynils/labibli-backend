from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from helpers.tests import (
    authenticate_admin,
    authenticate_user,
    create_admin_user,
    create_customer,
    create_organization,
    create_user,
)


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
        url = reverse("get_put_patch_delete_customer", kwargs={"pk": 1})
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
        url = reverse("get_put_patch_delete_customer", kwargs={"pk": 1})
        data = {"name": "New customer name"}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

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
        url = reverse("get_put_patch_delete_customer", kwargs={"pk": 1})
        data = {"name": "New customer name"}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

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
