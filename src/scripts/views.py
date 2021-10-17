import os
import uuid
from pathlib import Path
from typing import List

import firebase_admin
import requests
from django.core.files.base import ContentFile
from django.db import IntegrityError
from django.http import HttpResponse
from django.views.generic import View
from firebase_admin import credentials
from firebase_admin import firestore

from accounts.models import User, Organization
from customers.models import Customer
from items.models import Book, Category, Collection

DEFAULT_PICTURE_PLACEHOLDER = 'https://firebasestorage.googleapis.com/v0/b/biblio-44466.appspot.com/o/aW1hZ2UucG5nV2VkIEFwciAyOCAyMDIxIDE0OjI5OjU1IEdNVC0wMzAwIChoZXVyZSBhdmFuY8OpZSBkZSBs4oCZQXRsYW50aXF1ZSk%3D?alt=media&token=a7be9af5-3072-4040-a0d8-2870d0cc3d9e'

home = str(Path.home())
GOOGLE_SERVICE_ACCOUNT_JSON_PATH = os.path.join(home, 'dev', 'labibli', 'google_service_account.json')
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
    # if result.get("status") == "success":
    #     result = import_lendings()

    return result


def import_users() -> dict:
    result = {"status": "success"}
    try:
        firebase_users = import_from_firebase(collection="userProfiles")
        for user in firebase_users:
            try:
                user_link[user.id] = user._data.get('email')
                User.objects.create_user(
                    email=user._data.get('email'),
                    first_name=user._data.get('nickname'),
                    last_name=user._data.get('nickname'),
                    password=uuid.uuid4().hex,
                )
            except IntegrityError:
                print(f"This user already exists. {user}")

    except Exception as e:
        result['status'] = "error"
        result['error'] = e

    return result


def import_organizations() -> dict:
    result = {"status": "success"}
    try:
        firebase_items = import_from_firebase(collection="organizations")
        for item in firebase_items:
            owner_email = user_link[item._data.get('owner')]
            owner = User.objects.get(email=owner_email)
            try:
                organization = Organization.objects.get(name=owner.email.split('@')[1].split('.')[0].capitalize(),
                                                        owner=owner)
            except Organization.DoesNotExist:
                organization = Organization(
                    name=owner.email.split('@')[1].split('.')[0].capitalize(),
                    owner=owner
                )
                organization.save()
            organization_link[item.id] = organization.id
            owner.employee_of_organization = organization
            owner.save()

    except Exception as e:
        result['status'] = "error"
        result['error'] = e

    return result


def create_default_collections() -> dict:
    result = {"status": "success"}
    objects = []
    try:
        for collection_id, organization_id in organization_link.items():
            organization = Organization.objects.get(id=organization_id)
            try:
                collection = Collection.objects.get(
                    name=organization.name,
                    organization=organization
                )
            except Collection.DoesNotExist:
                collection = Collection.objects.create(
                    name=organization.name,
                    organization=organization
                )
                objects.append(collection)
            collections_link[collection_id] = collection.id
        Collection.objects.bulk_create(objects)

    except Exception as e:
        result['status'] = "error"
        result['error'] = e

    return result


def import_customers() -> dict:
    result = {"status": "success"}
    try:
        firebase_items = import_from_firebase(collection="customers")
        objects = []
        for item in firebase_items:
            organization_id = organization_link[item._data.get('organizationId')]
            organization = Organization.objects.get(id=organization_id)
            try:
                customer = Customer.objects.get(
                    email=item._data.get('email'),
                    organization=organization
                )
            except Customer.DoesNotExist:
                customer = Customer(
                    email=item._data.get('email') or None,
                    organization=organization,
                    first_name=item._data.get('firstName'),
                    last_name=item._data.get('lastName'),
                    phone=item._data.get('phoneNumber') or None,
                    language=item._data.get('language'),
                    note=item._data.get('note'),
                )
                objects.append(customer)
            customer_link[item.id] = customer.id
        Customer.objects.bulk_create(objects)

    except Exception as e:
        result['status'] = "error"
        result['error'] = e

    return result


def import_categories() -> dict:
    result = {"status": "success"}
    try:
        firebase_items = import_from_firebase(collection="categories")
        objects = []
        for item in firebase_items:
            organization_id = organization_link[item._data.get('organizationId')]
            organization = Organization.objects.get(id=organization_id)
            try:
                category = Category.objects.get(
                    name=item._data.get('name'),
                    organization=organization
                )
            except Category.DoesNotExist:
                category = Category(
                    name=item._data.get('name'),
                    organization=organization
                )
                objects.append(category)
            categories_link[item.id] = category.id
        Category.objects.bulk_create(objects)

    except Exception as e:
        result['status'] = "error"
        result['error'] = e

    return result


def import_books() -> dict:
    result = {"status": "success"}
    try:
        firebase_items = import_from_firebase(collection="books")
        count = 0
        for item in firebase_items:
            count += 1
            if item._data.get('collectionId') and item._data.get(
                    'collectionId') in collections_link:  # reject old books not linked to a collection
                organization_id = organization_link[item._data.get('collectionId')]
                organization = Organization.objects.get(id=organization_id)
                try:
                    book = Book.objects.get(
                        isbn=item._data.get('isbn'),
                        organization=organization
                    )
                except Book.DoesNotExist:
                    try:
                        book = Book.objects.get(
                            title=item._data.get('title'),
                            organization=organization
                        )
                    except Book.DoesNotExist:
                        collections = [collections_link[item._data.get('collectionId')]]
                        categories = []
                        for category_id in item._data.get('categories', []):
                            if categories_link.get(category_id):
                                categories.append(categories_link.get(category_id))
                            else:
                                categories_errors.append({"book_firebase_id": item.id, "category": category_id })
                                print(f"Category not found {category_id}")

                        picture = download_picture_from_url(item._data.get('picture'))
                        book = Book(
                            title=item._data.get('title'),
                            organization=organization,
                            archived=item._data.get('archived') or False,
                            featured=item._data.get('featured') or False,
                            status=item._data.get('status'),
                            author=item._data.get('author'),
                            isbn=item._data.get('isbn'),
                            publisher=item._data.get('publisher'),
                            lang=item._data.get('lang'),
                            published_year=item._data.get('publishedYear'),
                            description=item._data.get('description'),
                            inventory=item._data.get('inventory'),
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
                collection_errors.append(item._data.get('collectionId'))

            print (f"{count}/{firebase_items.__len__()}")
    except Exception as e:
        print(e)
        result['status'] = "error"
        result['error'] = e

    print(f"Collections_error - {collection_errors.__len__()} {collection_errors}")
    print(f"Pictures_error - {picture_errors.__len__()} {picture_errors}")
    print(f"Categories_error - {categories_errors.__len__()} {categories_errors}")
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
