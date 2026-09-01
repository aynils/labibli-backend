import uuid

from authemail.models import EmailAbstractUser, EmailUserManager
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.dispatch import receiver
from django.utils.timezone import now

from src.helpers.paliers import normaliser_paliers, paliers_par_defaut


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

    # ── Les rappels de retard : DEUX destinataires, DEUX interrupteurs ───
    #
    # 🔑 Ils sont séparés parce qu'ils ne racontent pas la même chose. Écrire
    # aux membres engage la bibliothèque auprès de gens qui ne sont pas nos
    # clients ; écrire à la bibliothécaire ne regarde qu'elle. Une
    # bibliothèque peut très bien vouloir surveiller ses retards sans encore
    # oser en parler à ses membres — c'est même l'ordre naturel des choses, et
    # un interrupteur unique le lui interdirait.
    #
    # ⛔ Les deux sont ÉTEINTS par défaut, et ce défaut n'est pas une prudence
    # de rédaction : dix-sept organisations sont déjà en production, elles ont
    # des prêts en retard depuis des mois, et pas une seule de leurs membres
    # n'a jamais reçu de courriel de La Bibli. Allumer ça pour tout le monde
    # enverrait, à la première nuit, des centaines de courriels au nom de
    # bibliothèques qui n'ont rien demandé. On ne dé-envoie pas un courriel.
    #
    # ⚠️ Les `verbose_name` ne sont pas décoratifs : ce sont les en-têtes des
    # colonnes de l'admin, c'est-à-dire le seul endroit où quelqu'un verra ces
    # deux cases côte à côte, un matin, avant de cocher. Elles doivent dire à
    # QUI chacune écrit, pas « rappels » deux fois.
    member_reminders_enabled = models.BooleanField(
        default=False,
        verbose_name="Rappels de retard aux MEMBRES",
    )

    # Les PALIERS de relance, en jours après l'échéance : [0, 7, 30] veut
    # dire une relance le jour du retard, une septième jour, une trentième —
    # puis PLUS RIEN.
    #
    # 🔴 Ça remplace un intervalle qui se répétait sans fin. Une personne qui
    # ne rendait jamais son livre recevait un courriel toutes les semaines,
    # indéfiniment, au nom de sa bibliothèque. Ce n'était plus une relance,
    # c'était du harcèlement automatisé — et personne ne pouvait répondre à la
    # question « combien de rappels envoie-t-on ? ». La longueur de la liste y
    # répond maintenant.
    #
    # ⚠️ `ArrayField` et non `JSONField` : Postgres refuse lui-même un élément
    # qui n'est pas un entier. Le reste — trié, dédoublonné, borné, non vide —
    # est tenu par `normaliser_paliers`, appelé à la fois par les validateurs
    # (formulaires, API) et par `save()` ci-dessous, qui est la seule barrière
    # que le `manage.py shell` d'un soir de correctif ne contourne pas.
    reminder_schedule_days = ArrayField(
        models.PositiveIntegerField(),
        default=paliers_par_defaut,
        validators=[normaliser_paliers],
        verbose_name="Paliers de relance, en jours après l'échéance (ex. 0, 7, 30)",
    )

    # Le récapitulatif à la bibliothécaire n'a PAS de fréquence, et c'est
    # délibéré — voir la docstring de `src/items/reminders.py`. C'est un état
    # du jour, pas une relance : sa cadence est celle de la tâche planifiée.
    librarian_digest_enabled = models.BooleanField(
        default=False,
        verbose_name="Récapitulatif quotidien des retards à la BIBLIOTHÉCAIRE",
    )

    def save(self, *args, **kwargs):
        """🔴 La normalisation des paliers est ici, pas seulement dans un
        validateur de formulaire.

        Les validateurs de champ ne s'exécutent QUE sur `full_clean()`, donc
        depuis l'admin et depuis l'API. Un `manage.py shell` — c'est-à-dire
        l'outil qu'on prend justement le soir où quelque chose ne va pas —
        poserait « [-3] » sans un mot, et la tâche de 8 h lèverait le
        lendemain, pour les dix-sept organisations d'un coup.
        """
        self.reminder_schedule_days = normaliser_paliers(self.reminder_schedule_days)
        super().save(*args, **kwargs)

    @property
    def is_subscribed(self):
        from src.payment.models import Subscription

        try:
            subscription = Subscription.objects.get(organization=self)
        except Subscription.DoesNotExist:
            return False
        else:
            return subscription.active


# Le nom d'attente, quand l'inscription n'en a pas fourni.
#
# 🔴 Il ne contient PLUS l'adresse courriel. L'ancien — « <courriel> - default
# organization » — se retrouvait dans le nom de la collection, puis en TITRE de
# la vitrine publique : le 01/09/2026, vingt-deux bibliothèques publiaient
# l'adresse de leur direction sur une page ouverte à tous, dont des Alliances
# françaises et des organismes communautaires.
#
# ⛔ Rien de ce qui est saisi à l'inscription — courriel, nom de la personne —
# ne doit entrer dans un champ que la vitrine affiche. Ce sont deux mondes :
# l'un sert à se connecter, l'autre est public.
NOM_PAR_DEFAUT = "Ma bibliothèque"


@receiver(models.signals.post_save, sender=User)
def create_organization(sender, instance, created, **kwargs):
    if created:
        organization = Organization.objects.create(
            name=NOM_PAR_DEFAUT, owner=instance
        )
        instance.employee_of_organization = organization
        instance.save()
        return organization


@receiver(models.signals.post_save, sender=Organization)
def create_collection(sender, instance, created, **kwargs):
    if created:
        from src.items.models import Collection

        # Le nom de la collection SUIT celui de l'organisation, sans suffixe :
        # c'est lui que la vitrine publique affiche en titre, et « Ma
        # bibliothèque - default collection » n'est un nom pour personne.
        name = instance.name
        slug = uuid.uuid4()
        organization = Collection.objects.create(
            name=name, organization=instance, slug=slug
        )
        return organization
