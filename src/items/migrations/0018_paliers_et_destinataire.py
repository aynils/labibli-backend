"""La trace apprend QUEL palier, et POUR QUI.

Deux ajouts et un déplacement de contrainte :

  * `step_days` — le palier franchi. C'est lui qui répond à « reste-t-il une
    relance à faire ? » ;
  * `recipient` — le membre ou la bibliothécaire. Deux histoires
    indépendantes dans la même table : une bibliothèque qui n'allume que le
    récapitulatif ne doit pas consommer les paliers de ses membres ;
  * l'unicité passe de `(prêt, jour)` à `(prêt, palier, destinataire)`. La
    nouvelle est strictement plus forte pour ce qui compte : elle interdit
    qu'un palier parte deux fois, quel que soit le jour, alors que l'ancienne
    n'interdisait que deux envois le même jour.

⚠️ La table est VIDE en production — les deux commutateurs sont éteints
partout depuis la mise en ligne du 01/09/2026, donc rien n'a jamais été
envoyé. Les valeurs par défaut (`0`, « customer ») ne servent donc qu'à rendre
la migration jouable sur une base de développement.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("items", "0017_trace_des_rappels"),
    ]

    operations = [
        migrations.AddField(
            model_name="lendingreminder",
            name="step_days",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="lendingreminder",
            name="recipient",
            field=models.CharField(
                choices=[
                    ("customer", "Le membre en retard"),
                    ("librarian", "La bibliothécaire"),
                ],
                default="customer",
                max_length=16,
            ),
        ),
        migrations.AlterUniqueTogether(
            name="lendingreminder",
            unique_together={("lending", "step_days", "recipient")},
        ),
    ]
