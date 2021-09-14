from django.db import models
from django.utils.timezone import now

from customers.models import Customer
# Create your models here.
from accounts.models import Organization


class Category(models.Model):
    organization = models.ForeignKey(to=Organization, on_delete=models.CASCADE)
    name = models.CharField(max_length=255, unique=False, blank=False, null=False)
    archived = models.BooleanField(default=False)

    unique_together = [
        ['name', 'organization'],
    ]


class Collection(models.Model):
    organization = models.ForeignKey(to=Organization, on_delete=models.CASCADE)
    name = models.CharField(max_length=255, unique=False, blank=False, null=False)
    archived = models.BooleanField(default=False)
    public = models.BooleanField(default=True)


class Book(models.Model):
    class Status(models.TextChoices):
        LOST = "lost", ("Lost")
        RESERVED = "reserved", ("Reserved")
        LENT = "lent", ("Prêté")
        AVAILABLE = "available", ("disponible")

    organization = models.ForeignKey(to=Organization, on_delete=models.CASCADE)
    created_at = models.DateTimeField(default=now)
    archived = models.BooleanField(default=False)
    featured = models.BooleanField(default=False)
    status = models.CharField(max_length=255, blank=False, null=False, choices=Status.choices, default=Status.AVAILABLE)
    author = models.CharField(max_length=255, unique=False, blank=False, null=False)
    title = models.CharField(max_length=255, unique=False, blank=False, null=False)
    isbn = models.CharField(max_length=255, unique=False, blank=False, null=False)
    publisher = models.CharField(max_length=255, unique=False, blank=True, null=True)
    picture = models.ImageField(upload_to='pictures',blank=True, null=True)
    lang = models.CharField(max_length=25, unique=False, blank=True, null=True)
    published_year = models.IntegerField(unique=False, blank=True, null=True)
    description = models.TextField(unique=False, blank=True, null=True)
    categories = models.ManyToManyField(Category, blank=True)
    collections = models.ManyToManyField(Collection,blank=True)

    class Meta:
        unique_together = [
            ['isbn', 'organization'],
        ]



class Lending(models.Model):
    organization = models.ForeignKey(to=Organization, on_delete=models.CASCADE)
    customer = models.ForeignKey(to=Customer, on_delete=models.CASCADE)
    book = models.ForeignKey(to=Book, on_delete=models.CASCADE)
    allowance_days = models.IntegerField(unique=False, blank=False, null=False)
    lent_at = models.DateTimeField(default=now)
    returned_at = models.DateTimeField(blank=True, null=True)
