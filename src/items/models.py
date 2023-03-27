import datetime
import os

import pytz as pytz
from django.conf import settings
from django.db import models
from django.utils.timezone import now

# Create your models here.
from src.accounts.models import Organization
from src.customers.models import Customer


def path_and_rename(instance, filename):
    upload_to = f"{settings.DJANGO_ENV}-covers"
    ext = filename.split(".")[-1]
    # get filename
    if instance.pk:
        filename = f"{instance.pk}.{ext}"
    else:
        # set filename as random string
        filename = f"{instance.organization_id}-{instance.title}.{ext}"
    # return the whole path to the file
    return os.path.join(upload_to, filename)


class Category(models.Model):
    organization = models.ForeignKey(to=Organization, on_delete=models.CASCADE)
    name = models.CharField(max_length=255, unique=False, blank=False, null=False)
    archived = models.BooleanField(default=False)

    unique_together = [
        ["name", "organization"],
    ]

    class Meta:
        ordering = ["name"]


class Collection(models.Model):
    organization = models.ForeignKey(to=Organization, on_delete=models.CASCADE)
    name = models.CharField(max_length=255, unique=False, blank=False, null=False)
    archived = models.BooleanField(default=False)
    public = models.BooleanField(default=True)
    slug = models.CharField(max_length=255, unique=False, blank=False, null=False)


class Book(models.Model):
    organization = models.ForeignKey(to=Organization, on_delete=models.CASCADE)
    created_at = models.DateTimeField(default=now)
    archived = models.BooleanField(default=False)
    deleted = models.BooleanField(default=False)
    featured = models.BooleanField(default=False)
    author = models.CharField(max_length=255, unique=False, blank=False, null=False)
    title = models.CharField(max_length=255, unique=False, blank=False, null=False)
    isbn = models.CharField(max_length=255, unique=False, blank=True, null=True)
    publisher = models.CharField(max_length=255, unique=False, blank=True, null=True)
    picture = models.ImageField(upload_to=path_and_rename, blank=True, null=True)
    lang = models.CharField(max_length=25, unique=False, blank=True, null=True)
    inventory = models.IntegerField(unique=False, blank=True, null=True)
    published_year = models.CharField(
        max_length=255, unique=False, blank=True, null=True
    )
    location = models.CharField(max_length=255, unique=False, blank=True, null=True)
    description = models.TextField(unique=False, blank=True, null=True)
    categories = models.ManyToManyField(Category, blank=True)
    collections = models.ManyToManyField(Collection, blank=True)

    @property
    def status(self):
        is_borrowed_count = Lending.objects.filter(
            book=self, returned_at__isnull=True
        ).count()
        if is_borrowed_count >= (self.inventory or 1):
            return "borrowed"
        else:
            return "available"

    class Meta:
        unique_together = [
            ["isbn", "organization", "title"],
        ]
        ordering = ["-created_at", "title"]
        indexes = [
            models.Index(fields=["author"]),
            models.Index(fields=["title"]),
            models.Index(fields=["isbn"]),
            models.Index(fields=["organization_id", "author", "title", "isbn"]),
        ]


class Lending(models.Model):
    organization = models.ForeignKey(to=Organization, on_delete=models.CASCADE)
    customer = models.ForeignKey(to=Customer, on_delete=models.CASCADE)
    book = models.ForeignKey(to=Book, on_delete=models.CASCADE, related_name="lendings")
    allowance_days = models.IntegerField(
        unique=False, blank=True, null=False, default=31
    )
    lent_at = models.DateTimeField(default=now)
    returned_at = models.DateTimeField(blank=True, null=True)

    @property
    def due_at(self):
        return self.lent_at + datetime.timedelta(days=self.allowance_days)

    @property
    def is_past_due(self):
        return self.due_at <= datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
