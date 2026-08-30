"""Importer des ouvrages dans la collection d'une organisation.

Le format de référence est celui du fichier envoyé par le RFNB, le seul qui
ait servi à un import réel complet : ISBN, titre, auteur, année, langue,
catégorie, couverture, description. Un tiers de ses lignes n'avaient AUCUN
ISBN et ont été cataloguées quand même — c'est la règle que ce module tient.

Trois principes en découlent :

1. **Un ouvrage entre toujours.** L'ISBN n'est pas une condition d'entrée :
   il ouvre l'enrichissement (couverture, résumé), son absence ne fait rien
   perdre. Un inventaire de médiathèque saisi au tableur n'en a pas.
2. **Le fichier fait foi.** Ce que la bibliothèque a catalogué prime sur ce
   qu'un catalogue extérieur raconte ; le lookup ne comble que les vides.
   Sans quoi on réécrirait sa collection avec une autre édition.
3. **Rien hors d'une organisation.** Chaque lecture et chaque écriture porte
   `organization_id`, y compris le contrôle de doublon — l'oublier avait
   fait rejeter en silence, en production, tout titre déjà catalogué
   ailleurs.
"""
from django.core.files.base import ContentFile
from django.db import transaction

from src.imports.runner import Importer
from src.items.book_lookup import download_image, find_book_details
from src.items.isbn_resolution import find_isbn, normalize
from src.items.models import Book, Category

COLUMNS = (
    "isbn", "title", "author", "publisher", "published_year", "lang",
    "category", "cover_url", "description",
)


def isbn_key(isbn) -> str:
    """L'ISBN réduit à ses chiffres.

    `978-2-7648-1344-7` et `9782764813447` désignent le même ouvrage : sans
    ça, le même livre entrait deux fois selon la façon dont le tableur avait
    été rempli.
    """
    if not isbn:
        return None
    digits = "".join(character for character in str(isbn) if character.isdigit() or character in "Xx")
    return f"isbn:{digits.lower()}" if digits else None


def title_key(title, author, publisher) -> str:
    """La clé de repli quand l'ISBN manque : titre, auteur et éditeur.

    L'éditeur en fait partie à dessein. Sans lui, deux éditions distinctes
    d'un même titre — « Les misérables » chez Gallimard et au Livre de Poche
    — seraient fondues en une seule et la seconde ligne serait perdue, ce
    qui est exactement le défaut qu'on a payé le 30/08. Avec lui, les
    doublons d'un inventaire saisi à la main restent détectés, puisqu'ils
    répètent le même éditeur.
    """
    if not title:
        return None
    return f"ta:{normalize(title)}|{normalize(author)}|{normalize(publisher)}"


def dedupe_keys(isbn, title, author, publisher) -> list:
    """Les deux façons de reconnaître un ouvrage déjà présent.

    Les deux clés sont produites, pas une seule : un catalogue bâti par
    ISBN et un inventaire sans ISBN doivent se reconnaître mutuellement,
    sinon réimporter l'inventaire duplique tout le catalogue.
    """
    return [key for key in (isbn_key(isbn), title_key(title, author, publisher)) if key]


class BookImporter(Importer):
    columns = COLUMNS

    def __init__(self, collection=None, resolve_isbn=True, enrich=True):
        # La résolution et l'enrichissement font chacun des appels réseau par
        # ligne : on doit pouvoir les couper pour rejouer un import à froid.
        self.collection = collection
        self.resolve_isbn = resolve_isbn
        self.enrich = enrich
        # Les catégories sont retenues d'une ligne à l'autre : sans ça,
        # chaque ouvrage relançait une requête pour la même catégorie.
        self.categories = {}

    def label(self, record) -> str:
        return record.get("title") or record.get("isbn") or "(ligne sans titre)"

    def dedupe_keys(self, record) -> list:
        return dedupe_keys(
            record.get("isbn"), record.get("title"),
            record.get("author"), record.get("publisher"),
        )

    def existing_keys(self, organization_id) -> set:
        """Les ouvrages déjà catalogués par CETTE organisation, en une requête."""
        rows = Book.objects.filter(organization_id=organization_id).values_list(
            "isbn", "title", "author", "publisher"
        )
        keys = set()
        for isbn, title, author, publisher in rows:
            keys.update(dedupe_keys(isbn, title, author, publisher))
        return keys

    @transaction.atomic
    def build(self, record, organization_id):
        """Enregistre l'ouvrage, ou rend None s'il reste introuvable.

        Tout se joue dans une seule transaction : si le rattachement à une
        collection ou à une catégorie échoue, l'ouvrage ne doit pas rester
        en base pendant que le compte rendu annonce un échec — la ligne
        serait rejouée et créerait un doublon.
        """
        # Un fichier d'ISBN nus reste valable : c'est le format qui a servi à
        # l'Alliance Française d'Ottawa, et le titre vient alors du lookup.
        if not record.get("title") and not record.get("isbn"):
            return None

        isbn = record.get("isbn") or self.resolve(record)
        details = self.fetch_details(isbn)
        title = record.get("title") or (details.title if details else None)
        if not title:
            return None

        book = Book(
            organization_id=organization_id,
            title=title,
            # `Book.author` est obligatoire : un auteur inconnu vaut la chaîne
            # vide, il ne fait pas perdre l'ouvrage.
            author=record.get("author") or (details.author if details else None) or "",
            # L'ISBN retrouvé est conservé même quand aucun catalogue n'a pu
            # rendre la fiche : c'est la raison d'être de la résolution.
            isbn=isbn,
            publisher=record.get("publisher") or (details.publisher if details else None),
            published_year=record.get("published_year") or (details.published_year if details else None),
            lang=record.get("lang") or (details.language if details else None),
            description=record.get("description") or (details.description if details else None),
            inventory=1,
        )
        book.save()

        if self.collection:
            book.collections.set([self.collection])
        self.attach_category(book, record.get("category"), organization_id)
        self.attach_cover(book, record.get("cover_url"), details)
        return book

    def resolve(self, record):
        """Retrouve l'ISBN par le titre et l'auteur, si on nous y autorise."""
        if not self.resolve_isbn:
            return None
        match = find_isbn(title=record.get("title"), author=record.get("author") or "")
        return match.isbn if match else None

    def fetch_details(self, isbn):
        """Métadonnées extérieures, si on peut en obtenir.

        Un échec de lookup n'est pas un échec d'import : on rend None et
        l'ouvrage entre avec ce que le fichier en dit.
        """
        if not isbn or not self.enrich:
            return None
        try:
            return find_book_details(isbn=isbn)
        except Exception:
            # Un catalogue indisponible ne doit pas coûter la ligne.
            return None

    def attach_category(self, book, name, organization_id):
        """Rattache l'ouvrage à une catégorie de SON organisation.

        Le fichier du RFNB nommait une catégorie sur chacune de ses lignes :
        la perdre à l'import obligerait à recataloguer à la main. La
        catégorie est cherchée dans la seule organisation qui importe — deux
        bibliothèques peuvent nommer une catégorie pareil sans rien
        partager.

        On ne passe pas par `get_or_create` : `Category` déclare bien un
        `unique_together`, mais HORS de sa `Meta` (`src/items/models.py`),
        donc aucune contrainte n'existe en base et les homonymes sont réels
        en production. `get_or_create` y lèverait `MultipleObjectsReturned`.
        """
        if not name:
            return
        cached = self.categories.get((organization_id, name))
        if cached is None:
            cached = Category.objects.filter(
                organization_id=organization_id, name=name
            ).first()
            if cached is None:
                cached = Category.objects.create(
                    organization_id=organization_id, name=name
                )
            self.categories[(organization_id, name)] = cached
        book.categories.add(cached)

    def attach_cover(self, book, cover_url, details):
        url = cover_url or (details.picture if details else None)
        if not url:
            return
        try:
            image = download_image(url=url)
            if image:
                book.picture.save(name=book.title, content=ContentFile(image), save=True)
        except Exception:
            # Une couverture manquante n'invalide pas un ouvrage catalogué.
            pass
