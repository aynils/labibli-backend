import django.utils.timezone
from django.db import models

from src.accounts.models import Organization


class Subscription(models.Model):
    organization = models.ForeignKey(to=Organization, on_delete=models.CASCADE)
    plan = models.CharField(max_length=255, unique=False, blank=True, null=True)
    interval = models.CharField(max_length=255, unique=False, blank=True, null=True)
    stripe_customer_id = models.CharField(
        max_length=255, unique=True, blank=False, null=False
    )
    active = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=django.utils.timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    raw_data = models.JSONField(blank=False, null=False)
