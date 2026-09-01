"""Retirer l'adresse courriel des noms d'organisation et de collection.

🔴 Ce que cette migration répare a été PUBLIÉ. Le nom d'attente d'une
organisation valait « <courriel> - default organization », il se propageait au
nom de la collection, et la vitrine publique l'affiche en titre : le
01/09/2026, vingt-deux bibliothèques exposaient l'adresse courriel de leur
direction sur une page ouverte à tous — Alliances françaises, organismes
communautaires, garderies.

Le correctif de code arrête l'hémorragie pour les inscriptions à venir. Il ne
touche pas aux trente et une organisations déjà en base : c'est ce que fait
celle-ci.

⛔ On ne DEVINE aucun nom. On retire ce qui fuit et on pose le nom d'attente,
qui n'annonce rien de faux. Le vrai nom, seule la bibliothèque le connaît, et
elle peut maintenant le saisir dans « Mon compte ».
"""
from django.db import migrations

NOM_PAR_DEFAUT = "Ma bibliothèque"


def sans_courriel(apps, schema_editor):
    Organization = apps.get_model("accounts", "Organization")
    Collection = apps.get_model("items", "Collection")

    for modele in (Organization, Collection):
        # ⚠️ Le filtre porte sur « @ » ET sur « default » : un nom légitime
        # peut contenir l'un — « Café & Livres » n'a pas d'arobase, mais une
        # bibliothèque pourrait s'appeler « Livres@Sud ». Les deux ensemble ne
        # se produisent que sur un nom généré.
        modele.objects.filter(name__contains="@", name__icontains="default").update(
            name=NOM_PAR_DEFAUT
        )
        # Le suffixe seul, sans courriel : « Aynils - default collection ».
        for objet in modele.objects.filter(name__icontains="default collection"):
            objet.name = objet.name.replace(" - default collection", "").strip()
            objet.save(update_fields=["name"])
        for objet in modele.objects.filter(name__icontains="default organization"):
            objet.name = objet.name.replace(" - default organization", "").strip()
            objet.save(update_fields=["name"])


def sans_retour(apps, schema_editor):
    """⛔ Irréversible, et c'est voulu.

    Remettre l'adresse courriel dans un champ public serait rejouer la fuite.
    Les anciens noms n'ont aucune valeur : ils n'ont jamais été choisis par
    personne.
    """


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_paliers_de_relance"),
        ("items", "0019_le_recapitulatif_n_est_plus_borne_au_jour"),
    ]
    operations = [migrations.RunPython(sans_courriel, sans_retour)]
