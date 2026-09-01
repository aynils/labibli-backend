"""Archiver un membre, et le réactiver s'il revient.

Archiver un membre ne le supprime PAS de la base, et c'est le seul point de
ce module qui compte : `Lending.customer` porte `on_delete=CASCADE`
(`src/items/models.py`), donc un `DELETE` réel emporterait tout l'historique
des prêts de la personne. La documentation promet le contraire noir sur
blanc — « retirer un membre ne supprime pas l'historique de ses prêts » — et
un historique de prêts effacé ne se reconstitue pas.

Archiver un membre pose donc `archived = True` : la personne sort des listes,
ses prêts restent, et le geste est réversible.

🔑 « archivé », le même mot que pour un livre. Un ouvrage retiré de la
circulation est archivé, une personne qui n'emprunte plus l'est aussi : deux
mots pour un même geste feraient diverger l'interface et la documentation.

⚠️ Conséquence qu'il faut traiter ici et nulle part ailleurs : `Customer`
déclare `unique_together` sur (organisation, prénom, nom, courriel) et
(organisation, prénom, nom, téléphone). Une fiche archivée occupe donc encore
sa place. Sans `find_archived`, une bibliothèque qui archive un membre par
erreur puis le rajoute reçoit le texte brut d'une erreur d'unicité Postgres,
sans aucun moyen de comprendre que la fiche est simplement masquée.
"""
from django.db.models import Q

from src.customers.models import Customer


def find_archived(organization_id, first_name, last_name, email=None, phone=None):
    """La fiche RETIRÉE que cette identité désigne, dans CETTE organisation.

    Les critères suivent `Customer.Meta.unique_together` — courriel OU
    téléphone, à noms égaux — plus le repli sans contact de
    `customer_import.keys_for`. Chercher plus large réinscrirait un homonyme
    à la place de la personne (un téléphone de foyer est partagé) ; chercher
    moins large laisserait passer soit une erreur d'unicité, soit une fiche
    en double.

    Le prénom et le nom sont exigés dans TOUS les cas : ce sont eux qui font
    la personne. Sans eux, un téléphone partagé suffirait à réinscrire
    quelqu'un d'autre.

    🔴 `organization_id` est obligatoire, et non un filtre parmi d'autres :
    sans lui, une bibliothèque réinscrirait le membre d'une autre.
    """
    if not organization_id or not first_name or not last_name:
        return None
    same_name = Customer.objects.filter(
        organization_id=organization_id,
        archived=True,
        first_name=first_name,
        last_name=last_name,
    )
    for field, value in (("email", email), ("phone", phone)):
        if value:
            found = same_name.filter(**{field: value}).first()
            if found:
                return found
    # Le repli sans contact, aligné sur `customer_import.keys_for`.
    #
    # C'est ici que `unique_together` ne dit RIEN : deux NULL sont distincts
    # en Postgres, donc rien n'empêche l'écriture. Sans ce repli, un membre
    # sans courriel ni téléphone — et une liste de membres en compte
    # toujours, `keys_for` le dit lui-même — retiré puis rajouté produisait
    # une SECONDE fiche : la personne redevenait visible, et son historique
    # de prêts restait accroché à la fiche cachée. Aucune erreur, aucun
    # message, un historique perdu de vue.
    #
    # Le repli ne joue QUE si la ligne entrante n'a elle-même ni courriel ni
    # téléphone : sinon deux homonymes sans contact et un homonyme joignable
    # seraient confondus.
    if not email and not phone:
        return (
            same_name.filter(Q(email__isnull=True) | Q(email=""))
            .filter(Q(phone__isnull=True) | Q(phone=""))
            .first()
        )
    return None


def archive(customer) -> None:
    """Retire le membre sans toucher à ses prêts."""
    customer.archived = True
    customer.save(update_fields=["archived"])
