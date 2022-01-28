# Create your tests here.
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from src.helpers.tests import (
    authenticate_user,
    create_admin_user,
    create_organization,
    create_subscription,
    create_user,
)

PRICE_ID_MONTHLY = "price_1KMdUcCpTgAka9PhrPJ3SnpI"


class SubscriptionTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.admin_user = create_admin_user()
        cls.organization = create_organization(owner=cls.user)
        cls.admin_organization = create_organization(owner=cls.admin_user)
        cls.subscription = create_subscription(
            organization=cls.organization, active=True
        )
        create_subscription(organization=cls.admin_organization, active=False)

    def setUp(self):
        pass

    # def test_create_subscription(self):
    #     """
    #     Ensure we can create a new subscription object.
    #     """

    def test_get_current_subscription(self):
        authenticate_user(self)
        url = reverse("get_current_subscription")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get("active"), self.subscription.active)


class PaymentProviderTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.admin_user = create_admin_user()
        cls.organization = create_organization(owner=cls.user)
        cls.admin_organization = create_organization(owner=cls.admin_user)

    def setUp(self):
        pass

    def test_create_checkout_session(self):
        authenticate_user(self)
        url = reverse("post_create_checkout_session")
        data = {"priceId": PRICE_ID_MONTHLY}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data.get("url")[:32], "https://checkout.stripe.com/pay/"
        )
