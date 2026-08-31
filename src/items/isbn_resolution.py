"""Retrouver l'ISBN d'un ouvrage à partir de son titre et de son auteur.

Toute la chaîne de `book_lookup` interroge les catalogues par ISBN. Les
collections saisies à la main n'en ont pas : un inventaire de médiathèque tenu au tableur
donne un auteur, un titre, parfois un éditeur et une année. Ce module comble
ce trou en amont — une fois l'ISBN trouvé, `find_book_details` fait le reste.

Deux principes tiennent le module :

1. **La BnF d'abord.** Les collections visées sont francophones, et le dépôt légal
   français est la seule base qui les couvre vraiment. Google Books est un
   repli, pas un socle : interrogé avec la clé du projet, il rend une réponse
   sur deux en 503.
2. **Un appariement se prouve.** Une recherche par titre rend toujours
   quelque chose ; accepter ce « quelque chose » sans le vérifier ferait
   entrer dans le catalogue d'une bibliothèque un livre qu'elle ne possède
   pas. Chaque candidat est donc noté sur le titre ET sur l'auteur, et
   rejeté sous les seuils.
"""
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import requests

from src.items.book_lookup import BNF_NS, BNF_SRU_URL, GOOGLE_BOOKS_API_KEY, GOOGLE_URL, HEADERS, TIMEOUT
from src.helpers.text_matching import (
    author_similarity,
    normalize,
    shares_surname,
    title_similarity,
)

OPEN_LIBRARY_SEARCH_URL = "https://openlibrary.org/search.json"

# Un titre doit se ressembler de près ; un auteur est saisi de mille façons
# (« Nathan littell » pour Jonathan Littell, « atwood » seul, « Pere Castor »),
# et on se contente d'un nom en commun.
TITLE_THRESHOLD = 0.82
AUTHOR_THRESHOLD = 0.34


@dataclass
class IsbnMatch:
    """Un ISBN retrouvé, avec de quoi juger si on lui fait confiance."""

    isbn: str
    source: str
    matched_title: str
    matched_author: str
    title_score: float
    author_score: float

    @property
    def score(self) -> float:
        return round((self.title_score * 2 + self.author_score) / 3, 3)


def isbn13(candidates: list) -> str:
    """Le meilleur ISBN d'une liste : on préfère un ISBN-13."""
    cleaned = [re.sub(r"[^0-9Xx]", "", value or "") for value in candidates]
    cleaned = [value for value in cleaned if len(value) in (10, 13)]
    if not cleaned:
        return None
    return next((value for value in cleaned if len(value) == 13), cleaned[0])


def search_bnf(title: str, author: str, limit: int = 5) -> list:
    """Candidats de la BnF : la meilleure base pour une collection francophone."""
    query = f'bib.title all "{sanitize(title)}"'
    if author:
        query += f' and bib.author all "{sanitize(author)}"'
    params = {
        "version": "1.2",
        "operation": "searchRetrieve",
        "query": query,
        "recordSchema": "dublincore",
        "maximumRecords": limit,
    }
    try:
        response = requests.get(url=BNF_SRU_URL, params=params, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException:
        return []
    if response.status_code != 200:
        return []
    try:
        root = ET.fromstring(response.content)
    except ET.ParseError:
        return []

    candidates = []
    for record in root.findall(".//srw:recordData/oai_dc:dc", BNF_NS):
        raw_title = record.findtext("dc:title", namespaces=BNF_NS)
        if not raw_title:
            continue
        # « Mon amie Flicka / Mary O'Hara ; traduit… » → titre, puis auteurs.
        candidate_title = raw_title.split(" / ")[0].strip()
        creators = [el.text for el in record.findall("dc:creator", BNF_NS) if el.text]
        # « O'Hara, Mary (1885-1980). Auteur du texte » → « O'Hara, Mary »
        candidate_author = ", ".join(creator.split(" (")[0].strip() for creator in creators)
        identifiers = [el.text for el in record.findall("dc:identifier", BNF_NS) if el.text]
        # « ISBN 9782875681362 »
        isbns = [value.replace("ISBN", "").strip() for value in identifiers if "ISBN" in value]
        found = isbn13(isbns)
        if found:
            candidates.append((found, candidate_title, candidate_author))
    return candidates


def search_google(title: str, author: str, limit: int = 5) -> list:
    """Candidats de Google Books, en repli : large, mais rend souvent 503."""
    query = f'intitle:"{sanitize(title)}"'
    if author:
        query += f' inauthor:"{sanitize(author)}"'
    params = {
        "q": query,
        "fields": "items/volumeInfo(title,authors,industryIdentifiers)",
        "maxResults": limit,
    }
    if GOOGLE_BOOKS_API_KEY:
        params["key"] = GOOGLE_BOOKS_API_KEY
    try:
        response = requests.get(url=GOOGLE_URL, params=params, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException:
        return []
    if response.status_code != 200:
        return []
    candidates = []
    for item in response.json().get("items", []):
        volume = item.get("volumeInfo", {})
        found = isbn13([i.get("identifier") for i in volume.get("industryIdentifiers", [])])
        if found and volume.get("title"):
            candidates.append((found, volume["title"], ", ".join(volume.get("authors", []))))
    return candidates


def search_open_library(title: str, author: str, limit: int = 5) -> list:
    """Candidats d'OpenLibrary, dernier repli : faible en français."""
    params = {"title": sanitize(title), "limit": limit, "fields": "title,author_name,isbn"}
    if author:
        params["author"] = sanitize(author)
    try:
        response = requests.get(url=OPEN_LIBRARY_SEARCH_URL, params=params, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException:
        return []
    if response.status_code != 200:
        return []
    candidates = []
    for doc in response.json().get("docs", []):
        found = isbn13(doc.get("isbn", []))
        if found and doc.get("title"):
            candidates.append((found, doc["title"], ", ".join(doc.get("author_name", []))))
    return candidates


def sanitize(text: str) -> str:
    """Retire ce qui casserait la requête d'un catalogue (guillemets, etc.)."""
    return re.sub(r'["\\]', " ", text or "").strip()


SOURCES = (("bnf", search_bnf), ("google", search_google), ("openlibrary", search_open_library))

# « Thorgal 21 - La couronne d'Ogotaï », « 421, Les enfants de la porte (6) » :
# un inventaire écrit la série et le tome dans le titre, les catalogues non.
SERIES_PREFIX = re.compile(r"^.{2,40}?[\s,]*\d{1,3}\s*[-–—:]\s*(?P<rest>.{4,})$")
SERIES_SUFFIX = re.compile(r"^(?P<rest>.{4,}?)\s*[\(\[]?\d{1,3}[\)\]]?\s*$")
SUBTITLE = re.compile(r"^(?P<rest>[^;:]{6,}?)\s*[;:]\s*.+$")


# Le numéro de tome, sous les formes qu'un inventaire tenu à la main emploie.
# L'ordre compte : « tome 2 » est explicite, « (6) » l'est presque, un nombre
# collé à un tiret ne l'est qu'en dernier recours.
VOLUME_PATTERNS = (
    re.compile(r"\b(?:tomes?|t\.|vol\.?|volumes?)\s*(\d{1,3})\b", re.IGNORECASE),
    re.compile(r"[\(\[](\d{1,3})[\)\]]\s*$"),
    re.compile(r"\s(\d{1,3})\s*[-–—:]"),
)


def volume_number(title: str) -> str:
    """Le numéro de tome porté par un titre, s'il en porte un."""
    if not title:
        return None
    for pattern in VOLUME_PATTERNS:
        found = pattern.search(title)
        if found:
            return found.group(1).lstrip("0") or "0"
    return None


def volume_numbers(title: str) -> set:
    """TOUS les numéros de tome cités par un titre.

    Sert à reconnaître les recueils : la BnF publie « Vernon Subutex. Tome 1,
    tome 2, tome 3 » pour l'intégrale des trois volumes.
    """
    if not title:
        return set()
    numbers = set()
    for pattern in VOLUME_PATTERNS:
        for found in pattern.finditer(title):
            numbers.add(found.group(1).lstrip("0") or "0")
    return numbers


def same_volume(wanted: str, candidate: str) -> bool:
    """Vrai si le candidat ne contredit pas le tome demandé.

    Un titre sans tome n'impose rien. Un titre qui en porte un exige que le
    candidat porte le même : sans ce contrôle, « Vernon subutex tome 2 » et
    « tome 3 » recevaient le MÊME ISBN, donc la même couverture et le même
    résumé — constaté en production le 31/08/2026.
    """
    number = volume_number(wanted)
    if number is None:
        return True
    # Un recueil n'est pas le tome qu'on cherche. « Vernon Subutex. Tome 1,
    # tome 2, tome 3 » est l'intégrale : elle contient bien le tome demandé,
    # mais lui attribuer cet ISBN donnerait à deux fiches distinctes la même
    # couverture et le même résumé. Mieux vaut aucun ISBN qu'un ISBN commun.
    if len(volume_numbers(candidate)) > 1:
        return False
    if volume_number(candidate) == number:
        return True
    return number in normalize(candidate).split()


def title_variants(title: str) -> list:
    """Le titre, puis ses réécritures probables, sans doublon.

    Chaque entrée est un couple (libellé, exiger_le_tome). La distinction
    compte : « Thorgal 21 - La couronne d'Ogotaï » se retrouve sous le seul
    titre de l'album, distinctif, qui n'a pas à porter le numéro ; mais
    « Vernon subutex tome 2 » réduit à « Vernon subutex » désigne la série
    entière, et accepter un candidat sans numéro donnerait le même ISBN à
    tous les tomes.
    """
    variants = [(title, True)]
    seen = {normalize(title)}

    def add(candidate, require_volume):
        cleaned = candidate.strip(" -–—,;:")
        if cleaned and normalize(cleaned) not in seen:
            seen.add(normalize(cleaned))
            variants.append((cleaned, require_volume))

    found = SERIES_PREFIX.match(title.strip())
    if found:
        # Ce qui suit le numéro est le titre propre de l'ouvrage.
        add(found.group("rest"), False)
    for pattern in (SUBTITLE, SERIES_SUFFIX):
        found = pattern.match(title.strip())
        if found:
            add(found.group("rest"), True)
    return variants


def find_isbn(title: str, author: str = "") -> IsbnMatch:
    """Retrouve l'ISBN d'un ouvrage, ou rend None si rien ne se prouve.

    Les sources sont interrogées dans l'ordre et on s'arrête à la première
    qui rend un candidat au-dessus des seuils : la BnF répond pour
    l'essentiel d'une collection francophone, et chaque source de plus est un
    aller-retour réseau par ligne d'inventaire.
    """
    if not title:
        return None
    for variant, require_volume in title_variants(title):
        # Le titre d'origine reste la référence pour juger le tome, mais
        # seulement quand la réécriture n'a pas extrait un titre distinct.
        match = search_all_sources(
            variant, author, wanted_title=title if require_volume else None
        )
        if match:
            return match
    return None


def search_all_sources(title: str, author: str, wanted_title: str = None) -> IsbnMatch:
    """Interroge les catalogues dans l'ordre pour un libellé de titre donné.

    `wanted_title` porte le titre d'origine quand le numéro de tome doit être
    respecté, et None quand la réécriture a extrait un titre distinct.
    """
    for name, search in SOURCES:
        best = None
        for isbn, candidate_title, candidate_author in search(title, author):
            title_score = title_similarity(title, candidate_title)
            author_score = author_similarity(author, candidate_author) if author else 1.0
            if title_score < TITLE_THRESHOLD or author_score < AUTHOR_THRESHOLD:
                continue
            # Un seuil ne suffit pas : « Jean Anouilh » et « Jean Racine »
            # partagent la moitié de leurs mots. Le nom de famille tranche.
            if author and not shares_surname(author, candidate_author):
                continue
            # Le numéro de tome est la seule chose qui sépare deux volumes
            # d'une même série : un candidat qui ne le porte pas est un autre
            # ouvrage.
            if wanted_title and not same_volume(wanted_title, candidate_title):
                continue
            match = IsbnMatch(
                isbn=isbn,
                source=name,
                matched_title=candidate_title,
                matched_author=candidate_author,
                title_score=round(title_score, 3),
                author_score=round(author_score, 3),
            )
            if best is None or match.score > best.score:
                best = match
        if best:
            return best
    return None
