import datetime
import os

import pytz as pytz
from django.conf import settings
from django.db import models
from django.db.models import Count, OuterRef, Subquery
from django.db.models.functions import Coalesce
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


class BookQuerySet(models.QuerySet):
    """Le queryset des ouvrages, avec de quoi éviter une requête par ligne."""

    def with_lending_status(self):
        """Compte les prêts en cours de CHAQUE ouvrage, en une seule requête.

        Sans elle, `Book.status` interroge la table des prêts ouvrage par
        ouvrage : une page de 24 vignettes, ce sont 24 requêtes de plus, pour
        une pastille « disponible / emprunté » que la vitrine publique
        affiche sur chacune.

        ⚠️ Une sous-requête corrélée, et surtout PAS un `Count` joint : la
        liste porte déjà des jointures (le filtre « disponible », le filtre
        par catégorie) et un `Count` de plus compterait les lignes du produit
        cartésien — un chiffre plausible et faux, donc une pastille fausse.

        🔴 Le cloisonnement ne bouge pas : la sous-requête est corrélée sur
        `book=OuterRef("pk")`, elle ne peut voir que les prêts des ouvrages
        déjà retenus par le queryset appelant, lequel est cloisonné par
        organisation.
        """
        lendings_en_cours = (
            Lending.objects.filter(book=OuterRef("pk"), returned_at__isnull=True)
            .order_by()
            .values("book")
            .annotate(total=Count("pk"))
            .values("total")
        )
        return self.annotate(
            active_lendings_count=Coalesce(
                Subquery(lendings_en_cours, output_field=models.IntegerField()), 0
            )
        )


class Book(models.Model):
    objects = BookQuerySet.as_manager()

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
        # `active_lendings_count` est posé par `BookQuerySet.with_lending_status()`
        # quand la vue en sert toute une page d'un coup. Absent, on retombe sur
        # la requête d'origine : un ouvrage seul reste correct.
        is_borrowed_count = getattr(self, "active_lendings_count", None)
        if is_borrowed_count is None:
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


CLIENT = "customer"
LIBRAIRE = "librarian"
DESTINATAIRES = [
    (CLIENT, "Le membre en retard"),
    (LIBRAIRE, "La bibliothécaire"),
]


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
    # Le palier franchi, en jours après l'échéance. C'est LUI qui dit si une
    # relance reste à faire : on n'envoie jamais un palier inférieur ou égal à
    # un palier déjà envoyé.
    step_days = models.PositiveIntegerField(default=0)
    # 🔑 Deux histoires indépendantes dans la même table. La bibliothécaire et
    # le membre suivent les mêmes paliers, mais chacun les franchit pour son
    # propre compte : une bibliothèque qui n'allume que le récapitulatif ne
    # doit pas « consommer » les paliers de ses membres, sans quoi le jour où
    # elle allumerait les rappels, plus personne ne recevrait jamais rien.
    recipient = models.CharField(max_length=16, choices=DESTINATAIRES, default=CLIENT)
    sent_at = models.DateTimeField(default=now)
    sent_on = models.DateField()
    to_email = models.EmailField(max_length=255)
    language = models.CharField(max_length=25, blank=True, null=True)

    class Meta:
        unique_together = [
            ["lending", "step_days", "recipient"],
        ]
        ordering = ["-sent_at"]
        indexes = [
            models.Index(fields=["organization", "sent_at"]),
        ]


class LibrarianDigest(models.Model):
    """La trace des récapitulatifs envoyés — un journal, PAS une garde.

    ⚠️ Elle portait un `unique_together (organization, sent_on)`, « au plus un
    récapitulatif par jour ». Ce garde-fou a été RETIRÉ le 01/09/2026, et
    c'est un test qui l'a exigé : depuis que le récapitulatif suit les paliers,
    la non-répétition est déjà tenue, et bien mieux, par
    `LendingReminder (lending, step_days, recipient)` — un palier ne peut pas
    partir deux fois, jamais, quel que soit le jour. Deux mécanismes pour une
    seule garantie, et c'est le plus faible qui gagnait : il faisait taire une
    relance légitime au seul motif qu'un courriel était déjà parti ce
    matin-là.

    Ce qui reste ici sert à répondre, trois mois plus tard, à « est-ce que le
    récapitulatif du 12 est parti, et à quelle adresse ? ».
    """

    organization = models.ForeignKey(to=Organization, on_delete=models.CASCADE)
    sent_at = models.DateTimeField(default=now)
    sent_on = models.DateField()
    to_email = models.EmailField(max_length=255)
    lendings_count = models.IntegerField(default=0)

    class Meta:
        ordering = ["-sent_at"]
