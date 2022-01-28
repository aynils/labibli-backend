from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from src.helpers.tests import (
    authenticate_admin,
    authenticate_user,
    create_admin_user,
    create_category,
    create_collection,
    create_customer,
    create_lending,
    create_organization,
    create_user,
    generate_photo_file,
)
from src.items.models import Book

books_seed = [
    {
        "archived": False,
        "featured": False,
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
        "author": "Marcel",
        "title": "L'amour de la bière 2",
        "isbn": "9234567890123",
        "publisher": "",
        "picture": "",
        "lang": "fr",
        "published_year": "2014",
        "description": "This is a wonderful book",
    },
]

new_book = {
    "archived": False,
    "featured": False,
    "author": "Marcel",
    "title": "L'amour de la bière 3",
    "isbn": "8234567890123",
    "publisher": "La maison des boissons",
    "lang": "fr",
    "published_year": "2019",
    "description": "This is a wonderful book",
    "categories": [],
}

find_book_details_test_data = [
    {
        "isbn": "9782897113148",
        "title": "Les saveurs gastronomiques de la bière",
        "picture": "https://images.leslibraires.ca/books/9782897113148/front/9782897113148_large.jpg",
    },
    {
        "isbn": "9780980200447",
        "title": "Slow reading",
        "picture": "http://covers.openlibrary.org/b/isbn/9780980200447-L.jpg?default=false",
    },
]

TEST_PICTURE_URL = (
    "https://images.leslibraires.ca/books/9782897113148/front/9782897113148_large.jpg"
)


class BookTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.admin_user = create_admin_user()
        cls.organization = create_organization(owner=cls.user)
        cls.admin_organization = create_organization(owner=cls.admin_user)
        cls.books = []
        cls.picture = generate_photo_file()

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
        url = reverse("list_post_books")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        books = response.json()
        self.assertEqual(len(books), len(books_seed))
        self.assertTrue(
            all([book.get("organization") == self.organization.name for book in books])
        )

    def test_list_books_of_other_organization(self):
        """
        Ensure an user cannot list books from the organisation they're an employee of.
        """
        Book.objects.create(**books_seed[0], organization=self.admin_organization)

        authenticate_user(self)
        url = reverse("list_post_books")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        books = response.json()
        self.assertEqual(len(books), len(books_seed))
        # Check that all books belongs to the user's organization
        self.assertTrue(
            all([book.get("organization") == self.organization.name for book in books])
        )

    def test_get_book(self):
        authenticate_user(self)
        url = reverse("get_put_patch_delete_book", kwargs={"pk": self.books[0].id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json().get("title"), books_seed[0].get("title"))

    def test_get_book_other_organization(self):
        """
        Ensure an user cannot get a book from another organization
        """
        authenticate_admin(self)
        url = reverse("get_put_patch_delete_book", kwargs={"pk": self.books[0].id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_post_book(self):
        authenticate_user(self)
        url = reverse("list_post_books")
        data = dict(**new_book, organization=self.organization, picture=self.picture)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json().get("title"), new_book.get("title"))
        self.assertEqual(response.json().get("organization"), self.organization.name)

    def test_post_book_anonymous(self):
        """
        Ensure books cannot be created by anonymous users
        """
        url = reverse("list_post_books")
        data = dict(**new_book, organization=self.organization, picture=self.picture)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_update_book(self):
        authenticate_user(self)
        url = reverse("get_put_patch_delete_book", kwargs={"pk": self.books[0].id})
        data = {"title": "New Title", "collections": []}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json().get("title"), "New Title")

    def test_delete_book(self):
        authenticate_user(self)
        url = reverse("get_put_patch_delete_book", kwargs={"pk": self.books[0].id})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)


class CollectionTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.admin_user = create_admin_user()
        cls.organization = create_organization(owner=cls.user)
        cls.admin_organization = create_organization(owner=cls.admin_user)
        cls.books = []

        cls.collection = create_collection(cls.organization, slug="collection-slug")
        create_collection(cls.admin_organization, slug="admin-collection-slug")

        for book in books_seed:
            new_book = Book.objects.create(**book, organization=cls.organization)
            new_book.collections.add(cls.collection)
            new_book.save()
            cls.books.append(new_book)

    def setUp(self):
        pass

    def test_get_collection(self):
        """
        Ensure collections are not public
        """
        authenticate_user(self)
        url = reverse(
            "get_put_patch_delete_collection", kwargs={"pk": self.collection.id}
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data.get("books").__len__(),
            self.collection.book_set.all().__len__(),
        )

    def test_list_collections(self):
        """
        Test list all collections from account
        """
        authenticate_user(self)
        url = reverse("list_post_collections")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.__len__(), 1)
        self.assertEqual(response.data[0].get("name"), self.collection.name)

    def test_update_collection(self):
        """
        Ensure collections can be updated by an user of the organization the collection belongs to
        """
        authenticate_user(self)
        url = reverse(
            "get_put_patch_delete_collection", kwargs={"pk": self.collection.id}
        )
        data = {"name": "New collection name"}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_update_collection_anonymous(self):
        """
        Ensure collections can only be updated by authenticated user
        """
        url = reverse(
            "get_put_patch_delete_collection", kwargs={"pk": self.collection.id}
        )
        data = {"name": "New collection name"}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_update_collection_other_organization(self):
        """
        Ensure collections can only be updated by an user of the organization the collection belongs to
        """
        authenticate_admin(self)
        url = reverse(
            "get_put_patch_delete_collection", kwargs={"pk": self.collection.id}
        )
        data = {"name": "New collection name"}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_post_collection(self):
        """
        Ensure collections can be created by an user of the organization the collection belongs to
        """
        authenticate_user(self)
        url = reverse("list_post_collections")
        data = {"name": "New collection name", "slug": "new-collection-slug"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json().get("name"), "New collection name")

    def test_post_collection_anonymous(self):
        """
        Ensure collections cannot be created by anonymous users
        """
        url = reverse("list_post_collections")
        data = {"name": "New collection name"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_collection_shared(self):
        """
        Ensure collections are public
        """
        url = reverse("get_collection_shared", kwargs={"slug": "collection-slug"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get("slug"), "collection-slug")
        self.assertEqual(
            response.data.get("books").__len__(),
            self.collection.book_set.all().__len__(),
        )


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

        cls.collection = create_collection(cls.organization, slug="foo")

        cls.customer = create_customer(cls.organization)

        cls.lending = create_lending(
            cls.organization, book=cls.books[0], customer=cls.customer
        )

    def setUp(self):
        pass

    def test_get_lending_anonymous(self):
        """
        Ensure lendings are not public
        """
        url = reverse("get_put_patch_delete_lending", kwargs={"pk": self.lending.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_lending(self):
        """
        Ensure lendings are not public
        """
        authenticate_user(self)
        url = reverse("get_put_patch_delete_lending", kwargs={"pk": self.lending.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_update_lending(self):
        """
        Ensure lendings can be updated by an user of the organization the lendings belongs to
        """
        authenticate_user(self)
        url = reverse("get_put_patch_delete_lending", kwargs={"pk": self.lending.id})
        data = {"name": "New collection name"}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_update_lending_anonymous(self):
        """
        Ensure collections can only be updated by authenticated user
        """
        url = reverse("get_put_patch_delete_lending", kwargs={"pk": self.lending.id})
        data = {"name": "New collection name"}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_update_lending_other_organization(self):
        """
        Ensure collections can only be updated by an user of the organization the collection belongs to
        """
        authenticate_admin(self)
        url = reverse("get_put_patch_delete_lending", kwargs={"pk": self.lending.id})
        data = {"name": "New collection name"}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_lendings(self):
        """
        Ensure collections are public
        """
        authenticate_user(self)
        url = reverse("list_post_lending")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_post_lending(self):
        """
        Ensure lendings can be created by an user of the organization the lending belongs to
        """
        authenticate_user(self)
        url = reverse("list_post_lending")
        data = {
            "customer": self.customer.id,
            "book": self.books[0].id,
            "allowance_days": 31,
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            response.json().get("customer").get("email"), self.customer.email
        )
        self.assertEqual(response.json().get("organization"), self.organization.name)

    def test_return_lending(self):
        """
        Ensure lendings can be returned
        """
        authenticate_user(self)
        url = reverse("return_lending", kwargs={"pk": 1})
        data = {}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.json().get("returned_at"))

    def test_post_lending_anonymous(self):
        """
        Ensure lendings cannot be created by anonymous users
        """
        url = reverse("list_post_lending")
        data = {
            "customer": self.customer.id,
            "book": self.books[0].id,
            "allowance_days": 31,
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class CategoryTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.admin_user = create_admin_user()
        cls.organization = create_organization(owner=cls.user)
        cls.admin_organization = create_organization(owner=cls.admin_user)
        cls.books = []

        cls.category = create_category(organization=cls.organization)
        cls.collection = create_collection(cls.organization, slug="collection-slug")

    def setUp(self):
        pass

    def test_get_category(self):
        """
        Ensure categories are only accessible in the context of an org
        """
        authenticate_user(self)
        url = reverse("get_put_patch_delete_category", kwargs={"pk": self.category.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_category_anonymous(self):
        """
        Ensure categories are not public
        """
        url = reverse("get_put_patch_delete_category", kwargs={"pk": self.category.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_post_category(self):
        """
        Ensure categories can be created by an user of the organization the collection belongs to
        """
        authenticate_user(self)
        url = reverse("list_post_category")
        data = {"name": "New category name"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json().get("name"), "New category name")

    def test_post_category_anonymous(self):
        """
        Ensure categories cannot be created by anonymous users
        """
        url = reverse("list_post_category")
        data = {"name": "New category name"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_update_category(self):
        """
        Ensure categories can be updated by an user of the organization the collection belongs to
        """
        authenticate_user(self)
        url = reverse("get_put_patch_delete_category", kwargs={"pk": self.category.id})
        data = {"name": "New category name"}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_update_category_anonymous(self):
        """
        Ensure categories can only be updated by authenticated user
        """
        url = reverse("get_put_patch_delete_category", kwargs={"pk": self.category.id})
        data = {"name": "New category name"}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_update_category_other_organization(self):
        """
        Ensure categories can only be updated by an user of the organization the collection belongs to
        """
        authenticate_admin(self)
        url = reverse("get_put_patch_delete_category", kwargs={"pk": self.category.id})
        data = {"name": "New category name"}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_categories(self):
        """
        Ensure categories are only accessible by logged-in user
        """
        authenticate_user(self)
        url = reverse("list_post_category")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_categories_shared(self):
        """
        Ensure unauthenticated user can get collection's categories
        """
        url = reverse("get_categories_shared", kwargs={"slug": "collection-slug"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data.__len__(),
            1,
        )
        self.assertEqual(response.data[0].get("name"), "Catégorie de test")


class FindBookTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_user()
        cls.organization = create_organization(owner=cls.user)

    def setUp(self):
        pass

    def test_get_book_details(self):
        """
        Ensure book details are returned
        """
        authenticate_user(self)
        url = reverse("get_book_details")
        for book in find_book_details_test_data:
            data = {"isbn": book.get("isbn")}
            response = self.client.get(url, data)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.json().get("title"), book.get("title"))
            self.assertEqual(response.json().get("isbn"), book.get("isbn"))
            self.assertEqual(response.json().get("picture"), book.get("picture"))

    def test_get_image_file(self):
        """
        Ensure image file is returned
        """
        authenticate_user(self)
        url = reverse("get_picture_file")
        data = {"image_url": TEST_PICTURE_URL}
        response = self.client.get(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
