import uuid

from authemail.models import EmailAbstractUser, EmailUserManager
from django.core.validators import MinValueValidator
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

    # La fréquence : nombre de jours entre deux rappels pour le MÊME prêt.
    # C'est elle qui empêche de harceler un membre en retard de trois mois,
    # et c'est elle, aussi, qui rend la commande rejouable — relancée le même
    # jour, elle ne renvoie rien.
    #
    # ⛔ Jamais 0 : une fréquence nulle voudrait dire « à chaque exécution »,
    # donc autant de courriels que de passages de la tâche planifiée.
    member_reminder_frequency_days = models.PositiveIntegerField(
        default=7,
        validators=[MinValueValidator(1)],
        verbose_name="Jours entre deux rappels au même membre, pour le même prêt",
    )

    # Le récapitulatif à la bibliothécaire n'a PAS de fréquence, et c'est
    # délibéré — voir la docstring de `src/items/reminders.py`. C'est un état
    # du jour, pas une relance : sa cadence est celle de la tâche planifiée.
    librarian_digest_enabled = models.BooleanField(
        default=False,
        verbose_name="Récapitulatif quotidien des retards à la BIBLIOTHÉCAIRE",
    )

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
