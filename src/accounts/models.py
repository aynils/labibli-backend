import uuid

from authemail.models import EmailAbstractUser, EmailUserManager
from django.db import models
from django.dispatch import receiver
from django.utils.timezone import now


class User(EmailAbstractUser):
    objects = EmailUserManager()
    employee_of_organization = models.ForeignKey(
        to="Organization",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
    )


class Organization(models.Model):
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=now)
    name = models.CharField(max_length=255, unique=False, blank=False, null=False)
    owner = models.ForeignKey(to=User, on_delete=models.DO_NOTHING)

    @property
    def is_subscribed(self):
        from src.payment.models import Subscription

        try:
            subscription = Subscription.objects.get(organization=self)
        except Subscription.DoesNotExist:
            return False
        else:
            return subscription.active


@receiver(models.signals.post_save, sender=User)
def create_organization(sender, instance, created, **kwargs):
    if created:
        name = f"{instance.email} - default organization"
        organization = Organization.objects.create(name=name, owner=instance)
        instance.employee_of_organization = organization
        instance.save()
        return organization


@receiver(models.signals.post_save, sender=Organization)
def create_collection(sender, instance, created, **kwargs):
    if created:
        from src.items.models import Collection

        name = f"{instance.name} - default collection"
        slug = uuid.uuid4()
        organization = Collection.objects.create(
            name=name, organization=instance, slug=slug
        )
        return organization
