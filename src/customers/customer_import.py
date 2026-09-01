"""Importer des membres dans une organisation.

Le second usage du socle d'import, et celui qui l'a fait exister : la liste
des membres de l'Alliance Française d'Ottawa est arrivée en CSV
point-virgule sans en-tête, et a été chargée à la main faute de code pour le
faire.

Le dédoublonnage suit `Customer.Meta.unique_together`, qui reconnaît un
membre par son courriel OU par son téléphone : deux clés, pas une, sinon
réimporter une liste corrigée crée un second exemplaire de chaque personne.
"""
from src.customers.membership import find_removed
from src.customers.models import Customer
from src.imports.runner import Importer
from src.helpers.text_matching import normalize

COLUMNS = ("first_name", "last_name", "email", "phone", "language", "note")


def name_key(first_name, last_name, value, kind) -> str:
    if not value:
        return None
    return f"{kind}:{normalize(first_name)}|{normalize(last_name)}|{normalize(value)}"


def keys_for(first_name, last_name, email, phone) -> list:
    """Toutes les façons de reconnaître un membre déjà inscrit.

    Le courriel et le téléphone d'abord, comme `unique_together`. Mais une
    liste de membres en comporte toujours sans l'un ni l'autre : sans clé de
    repli, ceux-là n'étaient JAMAIS vus comme doublons, et réimporter le
    même fichier les inscrivait une seconde fois — `unique_together` ne
    l'arrête pas non plus, deux NULL étant distincts en Postgres.
    """
    keys = [
        name_key(first_name, last_name, email, "email"),
        name_key(first_name, last_name, phone, "phone"),
    ]
    keys = [key for key in keys if key]
    if not keys and (first_name or last_name):
        keys.append(f"nom:{normalize(first_name)}|{normalize(last_name)}")
    return keys


class CustomerImporter(Importer):
    columns = COLUMNS

    def __init__(self):
        # Index des fiches RETIRÉES, chargé une fois avant la boucle.
        # `find_removed` appelé par ligne coûtait un à deux SELECT par
        # membre créé — 601 requêtes pour 200 lignes contre 201 avant. C'est
        # le même défaut que `existing_keys` a été écrit pour éviter.
        self.removed = {}
        # L'organisation pour laquelle l'index a été bâti. 🔴 Sans cette
        # garde, un importateur réutilisé d'une organisation à l'autre
        # réinscrirait le membre du voisin — l'index, lui, ne porte plus de
        # trace de son origine.
        self.removed_for = None

    def label(self, record) -> str:
        name = " ".join(filter(None, [record.get("first_name"), record.get("last_name")]))
        return name or record.get("email") or "(ligne sans nom)"

    def dedupe_keys(self, record) -> list:
        return keys_for(
            record.get("first_name"), record.get("last_name"),
            record.get("email"), record.get("phone"),
        )

    def existing_keys(self, organization_id) -> set:
        """Les membres déjà inscrits dans CETTE organisation, en une requête.

        Les fiches RETIRÉES en sont exclues à dessein. Les compter comme
        doublons ferait qu'une bibliothèque ayant retiré quelqu'un par
        erreur, puis réimportant sa liste, verrait la personne rangée en
        « doublon » et rester invisible — une perte silencieuse de plus.
        `build` s'occupe de la réinscrire.
        """
        rows = Customer.objects.filter(
            organization_id=organization_id, is_active=True
        ).values_list(
            "first_name", "last_name", "email", "phone"
        )
        keys = set()
        for first_name, last_name, email, phone in rows:
            keys.update(keys_for(first_name, last_name, email, phone))
        self.load_removed(organization_id)
        return keys

    def load_removed(self, organization_id) -> None:
        """Les fiches retirées de CETTE organisation, en une requête."""
        self.removed = {}
        self.removed_for = organization_id
        for customer in Customer.objects.filter(
            organization_id=organization_id, is_active=False
        ):
            for key in keys_for(
                customer.first_name, customer.last_name, customer.email, customer.phone
            ):
                self.removed.setdefault(key, customer)

    def take_removed(self, record, organization_id):
        """La fiche retirée que cette ligne désigne, ôtée de l'index.

        Ôtée, parce qu'une fiche ne se réinscrit qu'une fois : deux lignes
        d'un même fichier désignant la même personne se partageraient sinon
        l'objet, et la seconde écraserait la première sans rien créer.
        """
        if self.removed_for != organization_id:
            # L'index n'est pas celui de cette organisation : on ne devine
            # pas, on requête.
            return find_removed(
                organization_id=organization_id,
                first_name=record.get("first_name"),
                last_name=record.get("last_name"),
                email=record.get("email"),
                phone=record.get("phone"),
            )
        for key in self.dedupe_keys(record):
            customer = self.removed.get(key)
            if customer is None:
                continue
            for other in keys_for(
                customer.first_name, customer.last_name, customer.email, customer.phone
            ):
                self.removed.pop(other, None)
            return customer
        return None

    def build(self, record, organization_id):
        # Un membre sans nom n'est pas rattrapable : ni identifiable, ni
        # dédoublonnable, et `Customer` refuse les deux champs vides.
        if not record.get("first_name") or not record.get("last_name"):
            return None
        # Une fiche retirée occupe encore sa place au regard de
        # `unique_together` : la réinscrire est la seule issue qui ne rende
        # pas une erreur d'unicité Postgres à la bibliothèque.
        customer = self.take_removed(record, organization_id) or Customer(
            organization_id=organization_id
        )
        customer.is_active = True
        customer.first_name = record["first_name"]
        customer.last_name = record["last_name"]
        customer.email = record.get("email")
        customer.phone = record.get("phone")
        customer.language = record.get("language")
        customer.note = record.get("note")
        customer.save()
        return customer
