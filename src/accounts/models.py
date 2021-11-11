from authemail.models import EmailAbstractUser, EmailUserManager
from django.db import models
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
        return True
