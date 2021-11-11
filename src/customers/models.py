from django.db import models
from django.utils.timezone import now

# Create your models here.
from src.accounts.models import Organization


class Customer(models.Model):
    organization = models.ForeignKey(to=Organization, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=now)
    first_name = models.CharField(max_length=255, unique=False, blank=False, null=False)
    last_name = models.CharField(max_length=255, unique=False, blank=False, null=False)
    email = models.EmailField(max_length=255, unique=False, blank=True, null=True)
    phone = models.CharField(max_length=255, unique=False, blank=True, null=True)
    language = models.CharField(max_length=25, unique=False, blank=True, null=True)
    note = models.CharField(max_length=255, unique=False, blank=True, null=True)

    class Meta:
        unique_together = [
            ["organization", "first_name", "last_name", "email"],
            ["organization", "first_name", "last_name", "phone"],
        ]
