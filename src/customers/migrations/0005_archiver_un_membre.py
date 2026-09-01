"""« is_active » devient « archived », et la polarité s'inverse.

⛔ La migration générée par Django supprimait le champ puis en ajoutait un
autre. Elle aurait donc PERDU l'information : tout membre archivé serait
revenu actif, dans les listes et dans les prêts possibles, sans que rien ne
l'annonce. C'est pour ça que celle-ci est écrite à la main.

Trois temps : on ajoute, on convertit, on retire. Et la conversion existe dans
les DEUX sens, sans quoi un retour en arrière ferait la même perte que ce
qu'on cherche à éviter.
"""
from django.db import migrations, models


def vers_archived(apps, schema_editor):
    """`is_active = False` devient `archived = True`."""
    Customer = apps.get_model("customers", "Customer")
    Customer.objects.filter(is_active=False).update(archived=True)


def vers_is_active(apps, schema_editor):
    """Le chemin inverse, pour que la migration soit réversible."""
    Customer = apps.get_model("customers", "Customer")
    Customer.objects.filter(archived=True).update(is_active=False)


class Migration(migrations.Migration):

    dependencies = [
        ("customers", "0004_alter_customer_options"),
    ]

    operations = [
        migrations.AddField(
            model_name="customer",
            name="archived",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(vers_archived, vers_is_active),
        migrations.RemoveField(
            model_name="customer",
            name="is_active",
        ),
    ]
