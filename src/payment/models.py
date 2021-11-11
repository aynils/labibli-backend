from django.db import models

from src.accounts.models import Organization
from src.customers.models import Customer


class Subscription(models.Model):
    organization = models.ForeignKey(to=Organization, on_delete=models.CASCADE)
    customer = models.ForeignKey(to=Customer, on_delete=models.CASCADE)
    plan = models.CharField(max_length=255, unique=False, blank=False, null=False)
    interval = models.CharField(max_length=255, unique=False, blank=False, null=False)
    active = models.BooleanField(default=False)
    created_at = models.DateTimeField(blank=False, null=False)
    raw_data = models.JSONField(blank=False, null=False)
