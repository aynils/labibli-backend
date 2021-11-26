import os
import uuid
from pathlib import Path
from typing import List

import firebase_admin
import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import IntegrityError
from django.http import HttpResponse
from django.views.generic import View
from firebase_admin import credentials, firestore

from src.accounts.models import Organization, User
from src.customers.models import Customer
from src.items.models import Book, Category, Collection, Lending

DEFAULT_PICTURE_PLACEHOLDER = (
    "https://sfo3.digitaloceanspaces.com/labibli-s3/pictures/"
    "4916.jpg?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=BGLZPAXQMT7H2HGFREQI%2F20211107%2Fsfo3%2Fs3%2"
    "Faws4_request&X-Amz-Date=20211107T214553Z&X-Amz-Expires=3600&X-Amz-SignedHeaders=host"
    "&X-Amz-Signature=630b9a090fbd47165367a45bc2d19ca50b27af1349abb1995af89980da5863c4"
)

home = str(Path.home())
GOOGLE_SERVICE_ACCOUNT_JSON_PATH = os.path.join(
    settings.BASE_DIR, "google_service_account.json"
)
cred = credentials.Certificate(GOOGLE_SERVICE_ACCOUNT_JSON_PATH)
firebase_admin.initialize_app(cred)
db = firestore.client()

user_link = {}
organization_link = {}
customer_link = {}
categories_link = {}
books_link = {}
collections_link = {}
picture_errors = []
collection_errors = []
categories_errors = []
books_errors = []
books_duplicates = []


class ImportFromV1(View):
    def get(self, request):
        result = import_data_from_v1()
        if result.get("status") == "success":
            return HttpResponse(status=200, content={"success": "done"})
        else:
            return HttpResponse(status=500, content={"error": result.get("error")})


def import_data_from_v1() -> dict:
    result = import_users()
    if result.get("status") == "success":
        result = import_organizations()
    if result.get("status") == "success":
        result = create_default_collections()
    if result.get("status") == "success":
        result = import_customers()
    if result.get("status") == "success":
        result = import_categories()
    if result.get("status") == "success":
        result = import_books()
    if result.get("status") == "success":
        result = import_lendings()

    print(f"Collections_error - {collection_errors.__len__()} {collection_errors}")
    print(f"Pictures_error - {picture_errors.__len__()} {picture_errors}")
    print(f"Categories_error - {categories_errors.__len__()} {categories_errors}")
    print(f"Books_error - {books_errors.__len__()} {books_errors}")
    print(f"Duplicate_books - {books_duplicates.__len__()} {books_duplicates}")

    return result


def import_users() -> dict:
    result = {"status": "success"}
    try:
        firebase_users = import_from_firebase(collection="userProfiles")
        for user in firebase_users:
            try:
                user_link[user.id] = user._data.get("email")
                User.objects.create_user(
                    email=user._data.get("email"),
                    first_name=user._data.get("nickname"),
                    last_name=user._data.get("nickname"),
                    password=uuid.uuid4().hex,
                )
            except IntegrityError:
                print(f"This user already exists. {user._data.get('email')}")

    except Exception as e:
        print(e)
        result["status"] = "error"
        result["error"] = e

    return result


def import_organizations() -> dict:
    result = {"status": "success"}
    try:
        firebase_items = import_from_firebase(collection="organizations")
        for item in firebase_items:
            owner_email = user_link[item._data.get("owner")]
            owner = User.objects.get(email=owner_email)
            try:
                organization = Organization.objects.get(
                    name=owner.email.split("@")[1].split(".")[0].capitalize(),
                    owner=owner,
                )
            except Organization.DoesNotExist:
                organization = Organization(
                    name=owner.email.split("@")[1].split(".")[0].capitalize(),
                    owner=owner,
                )
                organization.save()
            organization_link[item.id] = organization.id
            owner.employee_of_organization = organization
            owner.save()

    except Exception as e:
        print(e)
        result["status"] = "error"
        result["error"] = e

    return result


def create_default_collections() -> dict:
    result = {"status": "success"}
    try:
        for collection_id, organization_id in organization_link.items():
            organization = Organization.objects.get(id=organization_id)
            try:
                collection = Collection.objects.get(
                    name=organization.name, organization=organization
                )
            except Collection.DoesNotExist:
                collection = Collection.objects.create(
                    name=organization.name, organization=organization
                )
                collection.save()
            collections_link[collection_id] = collection.id

    except Exception as e:
        print(e)
        result["status"] = "error"
        result["error"] = e

    return result


def import_customers() -> dict:
    result = {"status": "success"}
    try:
        firebase_items = import_from_firebase(collection="customers")
        for item in firebase_items:
            organization_id = organization_link[item._data.get("organizationId")]
            organization = Organization.objects.get(id=organization_id)
            try:
                customer = Customer.objects.get(
                    email=item._data.get("email"), organization=organization
                )
            except Customer.DoesNotExist:
                customer = Customer(
                    email=item._data.get("email") or None,
                    organization=organization,
                    first_name=item._data.get("firstName"),
                    last_name=item._data.get("lastName"),
                    phone=item._data.get("phoneNumber") or None,
                    language=item._data.get("language"),
                    note=item._data.get("note"),
                )
                customer.save()
            customer_link[item.id] = customer.id

    except Exception as e:
        print(e)
        result["status"] = "error"
        result["error"] = e

    return result


def import_categories() -> dict:
    result = {"status": "success"}
    try:
        firebase_items = import_from_firebase(collection="categories")
        for item in firebase_items:
            organization_id = organization_link[item._data.get("organizationId")]
            organization = Organization.objects.get(id=organization_id)
            try:
                category = Category.objects.get(
                    name=item._data.get("name"), organization=organization
                )
            except Category.DoesNotExist:
                category = Category(
                    name=item._data.get("name"), organization=organization
                )
                category.save()
            categories_link[item.id] = category.id

    except Exception as e:
        print(e)
        result["status"] = "error"
        result["error"] = e

    return result


def import_books() -> dict:
    result = {"status": "success"}
    try:
        firebase_items = import_from_firebase(collection="books")
        count = 0
        for item in firebase_items:
            count += 1
            if (
                item._data.get("collectionId")
                and item._data.get("collectionId") in collections_link
            ):  # reject old books not linked to a collection or to a deprecated cone
                organization_id = organization_link[item._data.get("collectionId")]
                organization = Organization.objects.get(id=organization_id)
                try:
                    if item._data.get("isbn"):
                        book = Book.objects.get(
                            isbn=item._data.get("isbn"), organization=organization
                        )
                        print(
                            f"Duplicate boook - {item._data.get('isbn')} - {organization.name}"
                        )
                        books_duplicates.append(
                            {
                                organization.name: {
                                    "title": item._data.get("title"),
                                    "isbn": item._data.get("isbn"),
                                }
                            }
                        )
                    elif item._data.get("title"):
                        book = Book.objects.get(
                            title=item._data.get("title"), organization=organization
                        )
                        print(
                            f"Duplicate boook - {item._data.get('title')} - {organization.name}"
                        )
                        books_duplicates.append(
                            {
                                organization.name: {
                                    "title": item._data.get("title"),
                                    "isbn": item._data.get("isbn"),
                                }
                            }
                        )
                    else:
                        print(
                            f"No ISBN nor title for book - {item.id} - {organization.name}"
                        )
                        books_errors.append(
                            {
                                "organization": organization.name,
                                "title": item._data.get("title"),
                                "isbn": item._data.get("isbn"),
                            }
                        )
                except Book.DoesNotExist:
                    collections = [collections_link[item._data.get("collectionId")]]
                    categories = []
                    for category_id in item._data.get("categories", []):
                        if categories_link.get(category_id):
                            categories.append(categories_link.get(category_id))
                        else:
                            categories_errors.append(
                                {"book_firebase_id": item.id, "category": category_id}
                            )
                            print(f"Category not found {category_id}")

                    picture = download_picture_from_url(item._data.get("picture"))
                    book = Book(
                        title=item._data.get("title") or None,
                        organization=organization,
                        archived=item._data.get("archived") or False,
                        deleted=item._data.get("deleted") or False,
                        featured=item._data.get("featured") or False,
                        status=item._data.get("status"),
                        author=item._data.get("author"),
                        isbn=item._data.get("isbn") or None,
                        publisher=item._data.get("publisher"),
                        lang=item._data.get("lang"),
                        published_year=item._data.get("publishYear"),
                        description=item._data.get("description"),
                        inventory=item._data.get("inventory"),
                    )
                    book.save()
                    book.picture.save(f"{book.id}.jpg", picture, save=True)
                    for collection in collections:
                        book.collections.add(collection)
                    for category in categories:
                        book.categories.add(category)
                    book.save()
                books_link[item.id] = book.id
            else:
                print(f"CollectionId not found {item._data.get('collectionId')}")
                collection_errors.append(item._data.get("collectionId"))

            print(f"{count}/{firebase_items.__len__()}")

    except Exception as e:
        print(e)
        result["status"] = "error"
        result["error"] = e

    return result


def import_lendings() -> dict:
    result = {"status": "success"}
    try:
        firebase_items = import_from_firebase(collection="lendings")
        for item in firebase_items:
            organization_id = organization_link[item._data.get("collectionId")]
            customer_id = customer_link[item._data.get("customerId")]
            book_id = books_link[item._data.get("bookId")]
            organization = Organization.objects.get(id=organization_id)
            customer = Customer.objects.get(id=customer_id)
            book = Book.objects.get(id=book_id)
            try:
                Lending.objects.get(
                    organization=organization,
                    customer=customer,
                    book=book,
                    lent_at=item._data.get("startDate"),
                )
            except Lending.DoesNotExist:
                lending = Lending(
                    organization=organization,
                    customer=customer,
                    book=book,
                    allowance_days=item._data.get("allowance"),
                    lent_at=item._data.get("startDate"),
                    returned_at=item._data.get("endDate") or None,
                )
                lending.save()

    except Exception as e:
        print(e)
        result["status"] = "error"
        result["error"] = e

    return result


def import_from_firebase(collection: str) -> List:
    ref = db.collection(collection)
    results = ref.get()
    return results


def download_picture_from_url(url: str):
    url = url or DEFAULT_PICTURE_PLACEHOLDER
    try:
        response = requests.get(url, timeout=20)
        if response.status_code == 200:
            return ContentFile(response.content)
        else:
            return download_picture_from_url(url="")
    except Exception as e:
        print(e, url)
        picture_errors.append(url)
        return download_picture_from_url(url="")
