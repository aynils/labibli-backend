"""L'intervalle sans fin devient une suite de paliers qui, elle, s'arrête.

⛔ Django génère volontiers « on retire un champ, on en ajoute un autre ».
Ici ça effacerait le réglage de chaque bibliothèque sans rien dire. Trois
temps, donc, comme pour `customers.0005` : on ajoute, on convertit, on retire.
Et la conversion existe dans les DEUX sens, sinon un retour en arrière ferait
la perte qu'on cherche à éviter.

La traduction, et pourquoi elle est ce qu'elle est :

  * `7`, la valeur par défaut qu'aucune organisation n'a changée, devient le
    nouveau défaut `[0, 7, 30]`. Vérifié en base le 01/09/2026 : les dix-sept
    organisations ont les deux commutateurs éteints et la fréquence d'origine.
    Aucune n'a donc de préférence à préserver ;
  * toute AUTRE valeur `f` devient `[0, f, 2f]` — l'espacement que la
    bibliothèque avait choisi, borné à trois relances. On ne devine pas mieux
    que ça, et on ne jette pas son choix.

Le retour arrière reprend le deuxième palier comme intervalle, ce qui rend
bien `7` pour `[0, 7, 30]`.
"""
import django.contrib.postgres.fields
from django.db import migrations, models

import src.helpers.paliers


def vers_paliers(apps, schema_editor):
    Organization = apps.get_model("accounts", "Organization")
    for organization in Organization.objects.all():
        frequence = organization.member_reminder_frequency_days or 7
        if frequence == 7:
            paliers = [0, 7, 30]
        else:
            paliers = sorted({0, frequence, frequence * 2})
        Organization.objects.filter(pk=organization.pk).update(
            reminder_schedule_days=paliers
        )


def vers_frequence(apps, schema_editor):
    Organization = apps.get_model("accounts", "Organization")
    for organization in Organization.objects.all():
        paliers = organization.reminder_schedule_days or [0, 7, 30]
        frequence = paliers[1] if len(paliers) > 1 else 7
        Organization.objects.filter(pk=organization.pk).update(
            member_reminder_frequency_days=max(frequence, 1)
        )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_rappels_par_organisation"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="reminder_schedule_days",
            field=django.contrib.postgres.fields.ArrayField(
                base_field=models.PositiveIntegerField(),
                default=src.helpers.paliers.paliers_par_defaut,
                size=None,
                validators=[src.helpers.paliers.normaliser_paliers],
                verbose_name="Paliers de relance, en jours après l'échéance (ex. 0, 7, 30)",
            ),
        ),
        migrations.RunPython(vers_paliers, vers_frequence),
        migrations.RemoveField(
            model_name="organization",
            name="member_reminder_frequency_days",
        ),
    ]
