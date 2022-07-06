import datetime
import io

from PIL import Image

from src.accounts.models import Organization, User
from src.customers.models import Customer
from src.items.models import Category, Collection, Lending
from src.payment.models import Subscription


def authenticate_user(self):
    result = self.client.post(
        "/api/users/login/", {"email": self.user.email, "password": "testing"}
    )
    assert result.status_code == 200
    token = result.json().get("token")
    self.client.credentials(HTTP_AUTHORIZATION="Token " + token)


def authenticate_admin(self):
    result = self.client.post(
        "/api/users/login/", {"email": self.admin_user.email, "password": "testing"}
    )
    assert result.status_code == 200
    token = result.json().get("token")
    self.client.credentials(HTTP_AUTHORIZATION="Token " + token)


def create_admin_user():
    admin_user = User.objects.create_superuser(
        first_name="test_admin_user",
        email="test_admin_user@test.com",
        password="testing",
    )
    admin_user.is_verified = True
    admin_user.save()
    return admin_user


def create_user():
    user = User.objects.create_user(
        first_name="testuser", email="testuser@test.com", password="testing"
    )
    user.is_verified = True
    user.save()
    return user


def create_organization(owner):
    organization = Organization.objects.create(name="Test Organization", owner=owner)
    owner.employee_of_organization = organization
    owner.save()
    return organization


def create_subscription(organization, active: bool):
    subscription = Subscription.objects.create(
        plan="Test Plan",
        organization=organization,
        active=active,
        interval="yearly",
        raw_data={},
        stripe_customer_id="dummy-id",
    )
    subscription.save()
    return subscription


def create_collection(organization, slug):
    collection = Collection.objects.create(
        name="Test Collection",
        organization=organization,
        slug=slug,
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
        note="Client de test super sympa",
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
    category = Category.objects.create(
        organization=organization, name="Catégorie de test"
    )
    category.save()
    return category


def generate_photo_file():
    file = io.BytesIO()
    image = Image.new("RGBA", size=(100, 100), color=(155, 0, 0))
    image.save(file, "png")
    file.name = "test.png"
    file.seek(0)
    return file
