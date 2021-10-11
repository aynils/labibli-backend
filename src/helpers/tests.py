import datetime

from accounts.models import User, Organization
from customers.models import Customer
from items.models import Collection, Lending, Category


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


def create_organization(owner):
    organization = Organization.objects.create(
        name='Test Organization',
        owner=owner
    )
    owner.employee_of_organization = organization
    owner.save()
    return organization


def create_collection(organization):
    collection = Collection.objects.create(
        name='Test Collection',
        organization=organization
    )
    collection.save()
    return collection


def create_customer(organization):
    collection = Customer.objects.create(
        organization=organization,
        first_name="Jean",
        last_name="Michel",
        email="jean@michel.ca",
        phone="01234566778",
        language="fr",
        note="Client de test super sympa"
    )
    collection.save()
    return collection


def create_lending(organization, customer, book):
    collection = Lending.objects.create(
        organization=organization,
        customer=customer,
        book=book,
        allowance_days=31,
        lent_at=datetime.datetime.now(),
        returned_at=None,
    )
    collection.save()
    return collection


def create_category(organization):
    collection = Category.objects.create(
        organization=organization,
        name="Catégorie de test"
    )
    collection.save()
    return collection
