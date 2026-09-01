"""Rendre la collection d'une organisation sous forme de classeur.

Le site l'écrit au présent : « Dans Livres, l'export vous rend votre
collection en classeur, avec tout ce qu'elle contient ». Ce module est ce
qui rend la phrase vraie.

🔑 **Le format est celui que notre propre import sait relire.** C'est la
seule chose qui distingue « vous partez avec vos données » d'une promesse
décorative : un classeur qu'on ne peut recharger nulle part, pas même chez
nous, n'est pas une sortie, c'est une capture d'écran. Les en-têtes sont
donc ceux que `src/imports/readers.py` reconnaît, et l'aller-retour est
éprouvé par un test (`src/items/test_book_export.py`).

Deux choix qui méritent d'être écrits :

1. **Les ouvrages archivés sont dedans.** Archivé vaut caché dans
   l'interface, pas effacé de la collection. Un export qui les omettrait
   perdrait en silence tout ce qu'une bibliothèque a sorti de la
   circulation — exactement le genre de perte qu'on ne voit qu'une fois le
   logiciel quitté.
2. **La couverture n'est pas exportée.** Les images sont servies par des URL
   signées qui expirent au bout d'une heure : les écrire dans un fichier que
   la bibliothèque garde des années donnerait une colonne de liens morts.
   Mieux vaut une colonne absente qu'une colonne fausse.
"""
from io import BytesIO

import openpyxl
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

from src.items.book_import import CATEGORY_SEPARATOR
from src.items.models import Book

# (champ interne, en-tête écrit dans le classeur).
#
# ⚠️ Chaque en-tête DOIT être reconnu par `readers.COLUMN_LABELS`, sinon la
# colonne est perdue au réimport — silencieusement, puisqu'une colonne
# inconnue est simplement laissée vide. L'ordre est celui qui se lit, pas
# celui de `book_import.COLUMNS` : le placement se fait par en-tête.
COLUMNS = (
    ("title", "Titre"),
    ("author", "Auteurice"),
    ("isbn", "ISBN"),
    ("publisher", "Éditeur"),
    ("published_year", "Année"),
    ("lang", "Langue"),
    ("category", "Catégories"),
    ("location", "Emplacement"),
    ("description", "Description"),
    # Sans cette colonne, « archivé vaut caché, pas effacé » ne tient que dans
    # un sens : une bibliothèque qui exporte, quitte, puis revient perdrait tout
    # son classement — sans être prévenue, puisque l'ouvrage réapparaît, actif.
    ("archived", "Archivé"),
)


def books_of(organization_id):
    """Les ouvrages de CETTE organisation, archivés compris.

    🔴 `organization_id` n'est pas un filtre parmi d'autres : c'est ce qui
    empêche de rendre à une bibliothèque la collection d'une autre. Une
    requête qui l'oublie ne lève rien et rend un fichier plausible.

    `prefetch_related` évite une requête de catégories par ouvrage — sur une
    collection de quatre mille titres, l'export en ferait quatre mille.
    """
    return (
        Book.objects.filter(organization_id=organization_id)
        .prefetch_related("categories")
        .order_by("title")
    )


def clean(value) -> str:
    """La valeur telle qu'openpyxl accepte de l'écrire.

    🔴 Un seul caractère de contrôle fait échouer TOUT l'export, en 500, dès
    l'appel à `append()` — pas à l'enregistrement. Le nettoyage doit donc être
    ici, en amont, et pas plus loin.

    Ce n'est pas une hypothèse d'école : `description` vient de Wikipédia, de
    Google Books, de la BnF et des fichiers que les bibliothèques nous envoient.
    Ce sont exactement les sources qui charrient ce genre de caractère.
    """
    if value in (None, ""):
        return ""
    return ILLEGAL_CHARACTERS_RE.sub("", str(value))


def row(book) -> list:
    values = {
        "title": book.title,
        "author": book.author,
        "isbn": book.isbn,
        "publisher": book.publisher,
        "published_year": book.published_year,
        "lang": book.lang,
        # Le séparateur est celui que l'import sait défaire.
        "category": f"{CATEGORY_SEPARATOR} ".join(
            category.name for category in book.categories.all()
        ),
        "location": book.location,
        "description": book.description,
        # « Oui »/« Non » plutôt que True/False : c'est ce qu'une personne lit
        # dans un tableur, et `is_archived` de l'import sait relire « oui ».
        "archived": "Oui" if book.archived else "Non",
    }
    return [clean(values[field]) for field, _ in COLUMNS]


def build_workbook(books) -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Collection"
    sheet.append([header for _, header in COLUMNS])
    for book in books:
        sheet.append(row(book))
        # 🔴 Forcer le type TEXTE sur la ligne qu'on vient d'écrire.
        #
        # Sans ça, openpyxl écrit un titre commençant par « = » comme une
        # FORMULE. Deux conséquences, toutes deux silencieuses :
        #   1. au réimport, la cellule rend None : l'ouvrage tombe en
        #      « introuvable », sans la moindre erreur ;
        #   2. c'est une injection de formule dans un fichier qu'une personne
        #      bénévole ouvre sur son poste.
        #
        # Le type se pose APRÈS l'écriture, parce qu'openpyxl le déduit de la
        # valeur au moment de l'affectation.
        for cell in sheet[sheet.max_row]:
            cell.data_type = "s"
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def export(organization_id) -> bytes:
    return build_workbook(books_of(organization_id))
