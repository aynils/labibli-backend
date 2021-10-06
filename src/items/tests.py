from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from helpers.tests import (authenticate_user,
                           create_admin_user,
                           create_user,
                           create_organization,
                           authenticate_admin,
                           create_collection,
                           create_lending,
                           create_customer
                           )
from items.models import Book

books_seed = [
    {
        "archived": False,
        "featured": False,
        "status": "available",
        "author": "Marcel",
        "title": "L'amour de la bière",
        "isbn": "1234567890123",
        "publisher": "La maison des boissons",
        "lang": "fr",
        "published_year": "2013",
        "description": "This is a wonderful book",
    },
    {
        "archived": False,
        "featured": False,
        "status": "available",
        "author": "Marcel",
        "title": "L'amour de la bière 2",
        "isbn": "9234567890123",
        "publisher": "",
        "picture": "",
        "lang": "fr",
        "published_year": "2014",
        "description": "This is a wonderful book",
    }
]

new_book = {
    "archived": False,
    "featured": False,
    "status": "available",
    "author": "Marcel",
    "title": "L'amour de la bière 3",
    "isbn": "8234567890123",
    "publisher": "La maison des boissons",
    "lang": "fr",
    "published_year": "2019",
    "description": "This is a wonderful book",
}


class BookTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.admin_user = create_admin_user()
        cls.organization = create_organization(owner=cls.user)
        cls.admin_organization = create_organization(owner=cls.admin_user)
        cls.books = []

        for book in books_seed:
            new_book = Book.objects.create(**book, organization=cls.organization)
            cls.books.append(new_book)

    def setUp(self):
        pass

    def test_list_books(self):
        """
        Ensure an user can list books from the organisation they're an employee of.
        """
        authenticate_user(self)
        url = reverse('get_post_books')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        books = response.json()
        self.assertEqual(len(books), len(books_seed))
        self.assertTrue(
            all([book.get('organization') == self.organization.name for book in books])
        )

    def test_list_books_of_other_organization(self):
        """
        Ensure an user cannot list books from the organisation they're an employee of.
        """
        Book.objects.create(**books_seed[0], organization=self.admin_organization)

        authenticate_user(self)
        url = reverse('get_post_books')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        books = response.json()
        self.assertEqual(len(books), len(books_seed))
        # Check that all books belongs to the user's organization
        self.assertTrue(
            all([book.get('organization') == self.organization.name for book in books])
        )

    def test_get_book(self):
        authenticate_user(self)
        url = reverse('get_put_patch_delete_book', kwargs={"pk": 1})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json().get('title'), books_seed[0].get('title'))

    def test_get_book_other_organization(self):
        """
        Ensure an user cannot get a book from another organization
        """
        authenticate_admin(self)
        url = reverse('get_put_patch_delete_book', kwargs={"pk": 1})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_post_book(self):
        authenticate_user(self)
        url = reverse('get_post_books')
        data = dict(**new_book, organization=self.organization)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json().get('title'), new_book.get('title'))
        self.assertEqual(response.json().get('organization'), self.organization.name)

    def test_update_book(self):
        authenticate_user(self)
        url = reverse('get_put_patch_delete_book', kwargs={"pk": 1})
        data = {'title': 'New Title'}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json().get('title'), 'New Title')


class CollectionTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.admin_user = create_admin_user()
        cls.organization = create_organization(owner=cls.user)
        cls.admin_organization = create_organization(owner=cls.admin_user)
        cls.books = []

        cls.collection = create_collection(cls.organization)

        for book in books_seed:
            new_book = Book.objects.create(**book, organization=cls.organization)
            new_book.collections.add(cls.collection)
            new_book.save()
            cls.books.append(new_book)

    def setUp(self):
        pass

    def test_get_collection(self):
        """
        Ensure collections are public
        """
        url = reverse('get_put_patch_delete_collection', kwargs={"pk": 1})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data.get('books').__len__(),
            self.collection.book_set.all().__len__()
        )

    def test_update_collection(self):
        """
        Ensure collections can be updated by an user of the organization the collection belongs to
        """
        authenticate_user(self)
        url = reverse('get_put_patch_delete_collection', kwargs={"pk": 1})
        data = {"name": "New collection name"}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_update_collection_anonymous(self):
        """
        Ensure collections can only be updated by authenticated user
        """
        url = reverse('get_put_patch_delete_collection', kwargs={"pk": 1})
        data = {"name": "New collection name"}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_update_collection_other_organization(self):
        """
        Ensure collections can only be updated by an user of the organization the collection belongs to
        """
        authenticate_admin(self)
        url = reverse('get_put_patch_delete_collection', kwargs={"pk": 1})
        data = {"name": "New collection name"}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class LendingTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.admin_user = create_admin_user()
        cls.organization = create_organization(owner=cls.user)
        cls.admin_organization = create_organization(owner=cls.admin_user)
        cls.books = []

        for book in books_seed:
            new_book = Book.objects.create(**book, organization=cls.organization)
            cls.books.append(new_book)

        cls.collection = create_collection(cls.organization)

        cls.customer = create_customer(cls.organization)

        cls.lending = create_lending(cls.organization, book=cls.books[0], customer=cls.customer)

    def setUp(self):
        pass

    def test_get_lending(self):
        """
        Ensure collections are public
        """
        url = reverse('get_put_patch_delete_lending', kwargs={"pk": 1})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_update_lending(self):
        """
        Ensure collections can be updated by an user of the organization the collection belongs to
        """
        authenticate_user(self)
        url = reverse('get_put_patch_delete_lending', kwargs={"pk": 1})
        data = {"name": "New collection name"}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_update_lending_anonymous(self):
        """
        Ensure collections can only be updated by authenticated user
        """
        url = reverse('get_put_patch_delete_lending', kwargs={"pk": 1})
        data = {"name": "New collection name"}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_update_lending_other_organization(self):
        """
        Ensure collections can only be updated by an user of the organization the collection belongs to
        """
        authenticate_admin(self)
        url = reverse('get_put_patch_delete_lending', kwargs={"pk": 1})
        data = {"name": "New collection name"}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_get_lendings(self):
        """
        Ensure collections are public
        """
        authenticate_user(self)
        url = reverse('list_lending')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
