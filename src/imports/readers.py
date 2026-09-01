"""Lire un fichier d'import et en tirer des lignes nommées.

Les fichiers que les bibliothèques envoient ne se ressemblent pas : la
collection du RFNB est un tableur à dix colonnes avec en-tête, la liste des membres de
l'Alliance Française d'Ottawa un CSV point-virgule sans en-tête, l'inventaire
de Siem Reap un export de traitement de texte. Ce module ramène tout ça à une
liste de dictionnaires ; ce qu'on en fait ensuite ne le regarde pas.
"""
import csv
from io import BytesIO, StringIO

import openpyxl

from src.helpers.text_matching import normalize

XLSX_SUFFIXES = (".xlsx", ".xlsm")

# Taille maximale d'un téléversement. Les instances tournent à 512 Mo avec
# trois workers : sans plafond, un classeur suffit à en faire tomber un.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

# Sentinelle : une valeur par défaut d'argument est figée à la définition de
# la fonction. Écrire `max_bytes=MAX_UPLOAD_BYTES` dans la signature rendrait
# la constante impossible à changer après coup, y compris pour un test.
DEFAULT_CAP = object()

# Ce que chaque libellé désigne. La table sert deux fois : à reconnaître une
# ligne d'en-tête, et — depuis le 31/08/2026 — à SAVOIR QUELLE COLONNE elle
# nomme. Auparavant l'en-tête n'était que sauté, et les colonnes étaient lues
# dans l'ordre de `columns` : un fichier commençant par « Titre » chargeait le
# titre dans l'ISBN et l'auteur dans le titre, sans le moindre message. Trente-
# deux fiches à supprimer, et rien dans les journaux pour dire pourquoi.
COLUMN_LABELS = {
    "isbn": ("isbn", "ean", "code", "code barres"),
    "title": ("titre", "title", "titre du livre"),
    "author": ("auteur", "auteurs", "auteur s", "author", "authors", "auteurice", "auteurices"),
    "publisher": ("editeur", "edition", "publisher"),
    "published_year": (
        "annee", "annee de publication", "annee de publication premiere",
        "year", "published year",
    ),
    "lang": ("langue", "language", "lang"),
    # Les membres nomment la même chose « language » (customer_import.COLUMNS).
    # Deux clés pour un seul libellé : le résolveur n'en voit qu'une à la fois,
    # puisqu'il est construit à partir des colonnes réellement demandées.
    "language": ("langue", "language", "lang"),
    "category": ("categorie", "categorie1", "category", "categories"),
    # Ajouté le 31/08/2026 avec l'export en libre-service : le site promet
    # que le classeur rendu contient les emplacements, et un export que
    # notre propre import ne sait pas relire ne rend pas la collection.
    "location": ("emplacement", "localisation", "location", "rayon", "cote"),
    "cover_url": ("couverture", "url couverture", "cover", "cover url", "image"),
    "description": ("description", "resume", "summary"),
    "archived": ("archive", "archivee", "archived", "statut"),
    "first_name": ("prenom", "first name", "firstname"),
    "last_name": ("nom", "nom de famille", "last name", "lastname"),
    "email": ("email", "courriel", "mail", "adresse courriel"),
    "phone": ("telephone", "phone", "tel", "numero de telephone"),
    "note": ("note", "notes", "commentaire"),
}

LABEL_TO_COLUMN = {
    label: column for column, labels in COLUMN_LABELS.items() for label in labels
}

HEADER_LABELS = set(LABEL_TO_COLUMN)


class ImportFileError(Exception):
    """Le fichier ne peut pas être lu : format, feuille vide, colonnes absentes."""


def looks_like_header(values, columns) -> bool:
    """Vrai si la première ligne nomme des colonnes plutôt qu'un ouvrage.

    On accepte les libellés français comme les noms internes anglais. Le
    seuil est de deux cellules reconnues : un ouvrage réel dont le titre
    serait « Note » ou « Code » ne suffit pas à faire prendre sa ligne pour
    un en-tête.
    """
    known = HEADER_LABELS | {normalize(column) for column in columns}
    recognized = sum(1 for value in values if value and normalize(value) in known)
    return recognized >= 2


def read_rows(file, columns, delimiter=";", max_bytes=DEFAULT_CAP) -> list:
    """Rend une liste de dictionnaires, une entrée par ligne utile du fichier.

    `max_bytes` borne la taille acceptée ; le passer à None lève la borne,
    ce que fait la commande de gestion : le plafond protège le service web de
    ses téléversements, il n'a pas à refuser un fichier local que la commande
    existe justement pour charger.

    `columns` donne le nom de chaque colonne dans l'ordre du fichier. Une
    première ligne qui reprend ces noms est traitée comme un en-tête et
    sautée ; sinon elle est lue comme une donnée, parce que la moitié des
    fichiers reçus n'ont pas d'en-tête du tout.
    """
    if max_bytes is DEFAULT_CAP:
        max_bytes = MAX_UPLOAD_BYTES
    name = (getattr(file, "name", "") or "").lower()
    if max_bytes is not None:
        size = getattr(file, "size", None)
        if size and size > max_bytes:
            raise ImportFileError(
                f"Fichier trop volumineux ({size // 1024 // 1024} Mo) : "
                f"maximum {max_bytes // 1024 // 1024} Mo."
            )
        raw = file.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise ImportFileError(f"Fichier trop volumineux : maximum {max_bytes // 1024 // 1024} Mo.")
    else:
        raw = file.read()
    if name.endswith(XLSX_SUFFIXES):
        rows = read_xlsx(raw)
    else:
        rows = read_csv(raw, delimiter=delimiter)

    if not rows:
        raise ImportFileError("Le fichier ne contient aucune ligne.")

    # Un en-tête qui nomme ses colonnes fait foi ; sans en-tête — la moitié
    # des fichiers reçus n'en ont pas — on lit dans l'ordre de `columns`.
    placement = None
    if looks_like_header(rows[0], columns):
        placement = header_placement(rows[0], columns)
        rows = rows[1:]
    if placement is None:
        placement = {index: column for index, column in enumerate(columns)}

    records = []
    for values in rows:
        record = {column: None for column in columns}
        for index, column in placement.items():
            value = values[index] if index < len(values) else None
            record[column] = clean(value)
        if any(record.values()):
            records.append(record)
    return records


def label_resolver(columns) -> dict:
    """Libellé normalisé → colonne interne, pour CE jeu de colonnes.

    Construit à partir de `columns` et non de la table globale : c'est ce
    qui permet à « Langue » de désigner `lang` dans un import d'ouvrages et
    `language` dans un import de membres. Le nom interne lui-même est
    accepté, pour qu'un en-tête écrit en anglais exact fonctionne aussi —
    c'est le repli que `looks_like_header` utilisait déjà et que le placement
    avait oublié, ce qui perdait la langue des membres en silence.
    """
    resolver = {normalize(column): column for column in columns}
    for column in columns:
        for label in COLUMN_LABELS.get(column, ()):
            resolver.setdefault(label, column)
    return resolver


def header_placement(header, columns):
    """Rend {indice de colonne du fichier: nom interne}, ou None.

    Trois cas, et c'est la distinction qui compte :

    1. **Aucun libellé reconnu** — l'en-tête n'apprend rien, on rend None et
       l'appelant reprend l'ordre positionnel.
    2. **Tout ce qui est reconnu est déjà à sa place** — le fichier suit
       l'ordre attendu, il nomme simplement ses colonnes autrement
       (« Maison d'édition », « Rayon »). On rend l'ordre positionnel COMPLET,
       donc les colonnes non reconnues sont lues elles aussi. Les abandonner
       perdait l'éditeur et la catégorie sur un en-tête français parfaitement
       ordinaire.
    3. **Au moins une colonne est ailleurs qu'attendu** — le fichier est
       permuté. Seul ce que l'en-tête nomme est lu, et une colonne inconnue
       reste vide : sa position ne veut plus rien dire, et la remplir avec le
       contenu du voisin est exactement la panne du 31/08/2026.
    """
    resolver = label_resolver(columns)
    reconnues = {}
    for index, value in enumerate(header):
        if not value:
            continue
        column = resolver.get(normalize(value))
        # Le premier gagne : un fichier qui répète « Note » deux fois ne doit
        # pas voir la seconde écraser la première.
        if column and column not in reconnues.values():
            reconnues[index] = column
    if not reconnues:
        return None
    positionnel = {index: column for index, column in enumerate(columns)}
    if all(positionnel.get(index) == column for index, column in reconnues.items()):
        return positionnel
    return reconnues


def read_xlsx(raw) -> list:
    try:
        workbook = openpyxl.load_workbook(filename=BytesIO(raw), read_only=True, data_only=True)
    except Exception as error:
        raise ImportFileError(f"Classeur illisible : {error}")
    if not workbook.worksheets:
        raise ImportFileError("Le classeur ne contient aucune feuille.")
    return [list(values) for values in workbook.worksheets[0].iter_rows(values_only=True)]


def read_csv(raw, delimiter) -> list:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ImportFileError("Encodage du fichier non reconnu.")
    return [row for row in csv.reader(StringIO(text), delimiter=delimiter)]


def clean(value):
    """Une cellule vide, quel que soit son déguisement, vaut None."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None
