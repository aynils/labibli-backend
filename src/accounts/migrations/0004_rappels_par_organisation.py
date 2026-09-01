"""Les trois réglages de rappel, par organisation.

⚠️ Les DEUX interrupteurs arrivent à `False`, et ils doivent y rester à la
migration : les dix-sept organisations déjà en production les reçoivent
éteints. Un `default=True` sur l'un ou l'autre enverrait, dès la première
tâche planifiée, des centaines de courriels au nom de bibliothèques qui n'ont
rien demandé.

  * `member_reminders_enabled`   → écrit aux MEMBRES en retard ;
  * `librarian_digest_enabled`   → écrit à la BIBLIOTHÉCAIRE, un récapitulatif.

Ils sont indépendants : allumer l'un n'allume pas l'autre, et c'est le point.

`member_reminder_frequency_days` : jours entre deux rappels pour le même prêt.
Sept par défaut — assez pour ne pas harceler, assez peu pour que le rappel
serve à quelque chose. Le récapitulatif, lui, n'a pas de fréquence : sa
cadence est celle de la tâche planifiée.
"""

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_auto_20211111_1827'),
    ]

    operations = [
        migrations.AddField(
            model_name='organization',
            name='librarian_digest_enabled',
            field=models.BooleanField(default=False, verbose_name='Récapitulatif quotidien des retards à la BIBLIOTHÉCAIRE'),
        ),
        migrations.AddField(
            model_name='organization',
            name='member_reminder_frequency_days',
            field=models.PositiveIntegerField(default=7, validators=[django.core.validators.MinValueValidator(1)], verbose_name='Jours entre deux rappels au même membre, pour le même prêt'),
        ),
        migrations.AddField(
            model_name='organization',
            name='member_reminders_enabled',
            field=models.BooleanField(default=False, verbose_name='Rappels de retard aux MEMBRES'),
        ),
    ]
