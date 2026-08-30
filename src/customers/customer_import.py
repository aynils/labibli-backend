"""Importer des membres dans une organisation.

Le second usage du socle d'import, et celui qui l'a fait exister : la liste
des membres de l'Alliance Française d'Ottawa est arrivée en CSV
point-virgule sans en-tête, et a été chargée à la main faute de code pour le
faire.

Le dédoublonnage suit `Customer.Meta.unique_together`, qui reconnaît un
membre par son courriel OU par son téléphone : deux clés, pas une, sinon
réimporter une liste corrigée crée un second exemplaire de chaque personne.
"""
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

    def label(self, record) -> str:
        name = " ".join(filter(None, [record.get("first_name"), record.get("last_name")]))
        return name or record.get("email") or "(ligne sans nom)"

    def dedupe_keys(self, record) -> list:
        return keys_for(
            record.get("first_name"), record.get("last_name"),
            record.get("email"), record.get("phone"),
        )

    def existing_keys(self, organization_id) -> set:
        """Les membres déjà inscrits dans CETTE organisation, en une requête."""
        rows = Customer.objects.filter(organization_id=organization_id).values_list(
            "first_name", "last_name", "email", "phone"
        )
        keys = set()
        for first_name, last_name, email, phone in rows:
            keys.update(keys_for(first_name, last_name, email, phone))
        return keys

    def build(self, record, organization_id):
        # Un membre sans nom n'est pas rattrapable : ni identifiable, ni
        # dédoublonnable, et `Customer` refuse les deux champs vides.
        if not record.get("first_name") or not record.get("last_name"):
            return None
        customer = Customer(
            organization_id=organization_id,
            first_name=record["first_name"],
            last_name=record["last_name"],
            email=record.get("email"),
            phone=record.get("phone"),
            language=record.get("language"),
            note=record.get("note"),
        )
        customer.save()
        return customer
