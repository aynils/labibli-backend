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


class LendingReminder(models.Model):
    """La trace d'un rappel réellement envoyé — la seule qui existe.

    Sans elle, rien n'empêche la tâche planifiée de renvoyer le même rappel à
    chaque passage. Ce n'est pas une hypothèse : la commande est faite pour
    tourner toutes les nuits, et une bibliothèque qui a trois prêts en retard
    depuis six mois enverrait à ses membres cent quatre-vingts courriels
    identiques. Un membre qui reçoit ça se désabonne — et il n'y a pas de
    désabonnement, il y a le bouton « courrier indésirable », qui coûte la
    réputation d'envoi de TOUTES les bibliothèques à la fois.

    Trois choses qu'on garde, et pourquoi :

    * `sent_on`, la date seule, porte la garantie forte. Avec
      `unique_together`, la BASE refuse un second rappel pour le même prêt le
      même jour, même si deux exécutions se croisent, même si quelqu'un règle
      la fréquence à un jour, même si la commande est relancée à la main
      après une coupure. La fréquence de l'organisation est un réglage ; ceci
      est un plancher ;
    * `to_email` dit à QUELLE adresse c'est parti. Le courriel d'un membre
      change ; sans ça, la trace mentirait rétroactivement sur ce qui a été
      envoyé, et c'est précisément la question qu'on pose quand quelqu'un se
      plaint de ne rien avoir reçu ;
    * `organization` est redondant — `lending` la porte déjà — et il reste.
      C'est ce qui permet d'interroger la trace d'une bibliothèque sans
      passer par une jointure qu'on peut oublier de cloisonner.
    """

    organization = models.ForeignKey(to=Organization, on_delete=models.CASCADE)
    lending = models.ForeignKey(
        to=Lending, on_delete=models.CASCADE, related_name="reminders"
    )
    sent_at = models.DateTimeField(default=now)
    sent_on = models.DateField()
    to_email = models.EmailField(max_length=255)
    language = models.CharField(max_length=25, blank=True, null=True)

    class Meta:
        unique_together = [
            ["lending", "sent_on"],
        ]
        ordering = ["-sent_at"]
        indexes = [
            models.Index(fields=["organization", "sent_at"]),
        ]


class LibrarianDigest(models.Model):
    """La trace du récapitulatif quotidien envoyé à la bibliothécaire.

    Le `unique_together ('organization', 'sent_on')` est la garantie, et elle
    est dans la BASE : une organisation reçoit au plus UN récapitulatif par
    jour. Ça tient si la tâche planifiée repasse, si quelqu'un relance la
    commande à la main après une coupure, ou si deux exécutions se croisent —
    et c'est exactement ce qui arrive un matin où le déploiement de 8 h a
    échoué et où on rejoue la commande à 8 h 10.

    ⚠️ Il n'y a PAS de réglage de fréquence en face de cette trace, à la
    différence de `LendingReminder`. Un récapitulatif n'est pas une relance :
    c'est l'état des retards du jour. Sa cadence est celle de la tâche
    planifiée, et un second réglage qui dirait autre chose que le `cron`
    finirait par le contredire en silence.

    `lendings_count` est gardé pour qu'on puisse répondre, trois mois plus
    tard, à « est-ce que le récapitulatif du 12 était vide ou est-ce qu'il
    n'est jamais parti ? ». Sans lui, la trace ne distingue pas les deux.
    """

    organization = models.ForeignKey(to=Organization, on_delete=models.CASCADE)
    sent_at = models.DateTimeField(default=now)
    sent_on = models.DateField()
    to_email = models.EmailField(max_length=255)
    lendings_count = models.IntegerField(default=0)

    class Meta:
        unique_together = [
            ["organization", "sent_on"],
        ]
        ordering = ["-sent_at"]
