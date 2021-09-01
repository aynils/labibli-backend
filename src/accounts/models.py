from authemail.models import EmailUserManager, EmailAbstractUser
from django.db import models
from django.utils.timezone import now

class MyUser(EmailAbstractUser):
    objects = EmailUserManager()

class Organization(models.Model):
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=now)
    name = models.CharField(max_length=255, unique=False, blank=False, null=False)
    owner = models.ForeignKey(to=MyUser, on_delete=models.DO_NOTHING)
