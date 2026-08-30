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

# Libellés d'en-tête reconnus. Les fichiers reçus sont écrits en français —
# celui du RFNB commence par « isbn ; titre ; auteur » — alors que les
# colonnes internes portent des noms anglais. Sans cette table, la ligne
# d'en-tête était prise pour un ouvrage et chaque import créait une fiche
# fantôme intitulée « Titre ».
HEADER_LABELS = {
    "isbn", "ean", "code", "code barres",
    "titre", "title", "titre du livre",
    "auteur", "auteurs", "auteur s", "author", "authors",
    "editeur", "edition", "publisher",
    "annee", "annee de publication", "annee de publication premiere", "year", "published year",
    "langue", "language", "lang",
    "categorie", "categorie1", "category",
    "couverture", "url couverture", "cover", "cover url", "image",
    "description", "resume", "summary",
    "prenom", "first name", "firstname",
    "nom", "nom de famille", "last name", "lastname",
    "email", "courriel", "mail", "adresse courriel",
    "telephone", "phone", "tel", "numero de telephone",
    "note", "notes", "commentaire",
}


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


def read_rows(file, columns, delimiter=";") -> list:
    """Rend une liste de dictionnaires, une entrée par ligne utile du fichier.

    `columns` donne le nom de chaque colonne dans l'ordre du fichier. Une
    première ligne qui reprend ces noms est traitée comme un en-tête et
    sautée ; sinon elle est lue comme une donnée, parce que la moitié des
    fichiers reçus n'ont pas d'en-tête du tout.
    """
    name = (getattr(file, "name", "") or "").lower()
    size = getattr(file, "size", None)
    if size and size > MAX_UPLOAD_BYTES:
        raise ImportFileError(
            f"Fichier trop volumineux ({size // 1024 // 1024} Mo) : "
            f"maximum {MAX_UPLOAD_BYTES // 1024 // 1024} Mo."
        )
    raw = file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ImportFileError(f"Fichier trop volumineux : maximum {MAX_UPLOAD_BYTES // 1024 // 1024} Mo.")
    if name.endswith(XLSX_SUFFIXES):
        rows = read_xlsx(raw)
    else:
        rows = read_csv(raw, delimiter=delimiter)

    if not rows:
        raise ImportFileError("Le fichier ne contient aucune ligne.")
    if looks_like_header(rows[0], columns):
        rows = rows[1:]

    records = []
    for values in rows:
        record = {}
        for index, column in enumerate(columns):
            value = values[index] if index < len(values) else None
            record[column] = clean(value)
        if any(record.values()):
            records.append(record)
    return records


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
