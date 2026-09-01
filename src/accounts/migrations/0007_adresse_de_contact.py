"""L'adresse de contact PUBLIQUE de la bibliothèque, distincte de celle du compte.

La vitrine dit « pour emprunter, adressez-vous à la bibliothèque » et donnait
jusqu'ici l'adresse de connexion de la propriétaire — son adresse personnelle,
lisible par quiconque appelle l'API publique. Les deux servent à des choses
opposées : l'une identifie une personne, l'autre est faite pour être lue par
des inconnus.
"""
from django.db import migrations, models


def depuis_la_proprietaire(apps, schema_editor):
    """Chaque bibliothèque part avec l'adresse qui lui servait déjà de contact.

    ⚠️ Ce n'est PAS un correctif de la fuite, et il ne faut pas le lire comme
    tel : l'adresse personnelle de la propriétaire reste publiée tant qu'une
    bibliothèque n'en choisit pas une autre. Ce que ça change, c'est qu'elle
    devient un champ NOMMÉ, visible dans « Mon compte », et modifiable.

    ⛔ L'alternative — laisser vide — aurait cassé l'emprunt sur les trente et
    une vitrines jusqu'à ce que chaque bibliothèque agisse. Une vitrine qui ne
    dit plus à qui s'adresser ne sert à rien.
    """
    Organization = apps.get_model("accounts", "Organization")
    for organisation in Organization.objects.select_related("owner"):
        if not organisation.contact_email and organisation.owner_id:
            organisation.contact_email = organisation.owner.email
            organisation.save(update_fields=["contact_email"])


def sans_retour(apps, schema_editor):
    """Rien à défaire : la colonne disparaît avec le champ."""


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0006_noms_sans_courriel"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="contact_email",
            field=models.EmailField(blank=True, max_length=255, null=True),
        ),
        migrations.RunPython(depuis_la_proprietaire, sans_retour),
    ]
