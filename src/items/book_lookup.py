import logging
import os
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from functools import partial
from urllib.parse import quote

import requests

from src.helpers.text_matching import significant_words

GOOGLE_URL = "https://www.googleapis.com/books/v1/volumes"
OPEN_LIBRARY_URL = "https://openlibrary.org/api/books"
WIKIPEDIA_URL = "https://en.wikipedia.org/api/rest_v1/data/citation/mediawiki/"
WIKIPEDIA_FR_API = "https://fr.wikipedia.org/w/api.php"
WIKIPEDIA_FR_SUMMARY = "https://fr.wikipedia.org/api/rest_v1/page/summary/"
BNF_SRU_URL = "https://catalogue.bnf.fr/api/SRU"

HEADERS = {"User-Agent": "LaBibli/1.0 (https://labibli.com; contact@labibli.com)"}
TIMEOUT = 5

# Google Books alterne les 503 : mesuré à 0 réponse sur 8 au premier appel,
# et 4 sur 8 en réessayant. Sans réessai, la fiche revient vide — ou le livre
# entier reste introuvable, puisque Google porte aussi les descriptions.
# 429 n'y figure pas : il annonce un quota épuisé, que trois tentatives à
# 0,6 s d'intervalle ne rouvriront pas. Sur un import de collection entière,
# insister coûterait 1,2 s par ouvrage pour le même échec.
RETRY_STATUSES = (500, 502, 503, 504)
RETRY_ATTEMPTS = 3
RETRY_PAUSE = 0.6

GOOGLE_BOOKS_API_KEY = os.environ.get("GOOGLE_BOOKS_API_KEY")

logger = logging.getLogger(__name__)

BNF_NS = {
    "srw": "http://www.loc.gov/zing/srw/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
}


@dataclass
class BookDetails:
    isbn: str
    title: str
    picture: str
    author: str
    publisher: str
    published_year: int
    description: str
    page_count: str
    language: str


def get_with_retry(url, params=None, attempts=RETRY_ATTEMPTS):
    """Un GET qui insiste quand le service répond « reviens plus tard ».

    Seuls les codes transitoires sont réessayés : un 404 est une réponse,
    pas une panne.
    """
    for attempt in range(attempts):
        try:
            response = requests.get(url=url, params=params, headers=HEADERS, timeout=TIMEOUT)
        except requests.RequestException:
            return None
        if response.status_code not in RETRY_STATUSES:
            return response
        if attempt < attempts - 1:
            time.sleep(RETRY_PAUSE)
    return None


def get_google_book_information(isbn: str) -> dict or None:
    params = {
        "q": f"isbn:{isbn}",
        "fields": "items/volumeInfo(title,authors,publisher,publishedDate,language,description,pageCount,imageLinks)",
        "maxResults": 1,
    }
    if GOOGLE_BOOKS_API_KEY:
        params["key"] = GOOGLE_BOOKS_API_KEY
    response = get_with_retry(url=GOOGLE_URL, params=params)
    if response is None:
        return None
    if response.status_code == 200 and response.json().get("items"):
        volume = response.json().get("items")[0].get("volumeInfo")
        return {
            "title": volume.get("title"),
            "isbn": isbn,
            "author": ", ".join(volume.get("authors", [])),
            "publisher": volume.get("publisher"),
            "cover": volume.get("imageLinks", {}).get("thumbnail"),
            "published_year": volume.get("publishedDate", "")[:4] or None,
            "description": volume.get("description"),
            "page_count": volume.get("pageCount"),
            "language": volume.get("language"),
        }
    return None


def get_open_library_book_information(isbn: str) -> dict or None:
    params = {
        "bibkeys": f"ISBN:{isbn}",
        "jscmd": "details",
        "format": "json",
    }
    try:
        response = requests.get(url=OPEN_LIBRARY_URL, params=params, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException:
        return None
    if response.status_code == 200 and response.json():
        volume = response.json().get(f"ISBN:{isbn}", {}).get("details")
        if volume:
            authors = [author.get("name") for author in volume.get("authors", [])]
            publishers = [publisher for publisher in volume.get("publishers", [])]
            cover_id = volume.get("covers", [None])[0]
            cover_url = (
                f"https://covers.openlibrary.org/b/id/{cover_id}.jpg"
                if cover_id
                else None
            )
            return {
                "title": volume.get("title"),
                "isbn": isbn,
                "author": ", ".join(authors),
                "publisher": ", ".join(publishers),
                "cover": cover_url,
                "published_year": volume.get("publish_date"),
                "description": volume.get("description"),
            }
    return None


def get_wikipedia_book_information(isbn: str) -> dict or None:
    url = f"{WIKIPEDIA_URL}{isbn}"
    try:
        response = requests.get(url=url, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException:
        return None
    if response.status_code == 200 and response.json():
        volume = response.json()[0]
        if volume:
            authors = [
                f"{author[0]} {author[1]}"
                for author in volume.get("author", [])
                if isinstance(author, (list, tuple)) and len(author) >= 2
            ]
            return {
                "title": volume.get("title"),
                "isbn": isbn,
                "author": ", ".join(authors),
                "publisher": volume.get("publisher"),
                "cover": None,
                "published_year": volume.get("date"),
                "description": volume.get("abstractNote"),
                "page_count": volume.get("numPages"),
                "language": volume.get("language"),
            }
    return None


def get_bnf_book_information(isbn: str) -> dict or None:
    params = {
        "version": "1.2",
        "operation": "searchRetrieve",
        "query": f'bib.isbn adj "{isbn}"',
        "recordSchema": "dublincore",
        "maximumRecords": 1,
    }
    try:
        response = requests.get(url=BNF_SRU_URL, params=params, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    try:
        root = ET.fromstring(response.content)
    except ET.ParseError:
        return None

    num_records_el = root.find("srw:numberOfRecords", BNF_NS)
    try:
        if not num_records_el or int(num_records_el.text) == 0:
            return None
    except (ValueError, TypeError):
        return None

    record_data = root.find(".//srw:recordData/oai_dc:dc", BNF_NS)
    if record_data is None:
        return None

    title_raw = record_data.findtext("dc:title", namespaces=BNF_NS)
    if not title_raw:
        return None

    # "Mon amie Flicka / Mary O'Hara ; traduit..." → "Mon amie Flicka"
    title = title_raw.split(" / ")[0].strip()

    creators = [el.text for el in record_data.findall("dc:creator", BNF_NS) if el.text]
    # "O'Hara, Mary (1885-1980). Auteur du texte" → "O'Hara, Mary"
    authors = [c.split(" (")[0].strip() for c in creators]

    publisher_raw = record_data.findtext("dc:publisher", namespaces=BNF_NS)
    # "Gallimard-Jeunesse (Paris)" → "Gallimard-Jeunesse"
    publisher = publisher_raw.split(" (")[0].strip() if publisher_raw else None

    date = record_data.findtext("dc:date", namespaces=BNF_NS)
    language = record_data.findtext("dc:language", namespaces=BNF_NS)

    ark_id = next(
        (el.text for el in record_data.findall("dc:identifier", BNF_NS)
         if el.text and el.text.startswith("ark:")),
        None,
    )
    cover = None
    if ark_id:
        cover_url = f"https://catalogue.bnf.fr/couverture?appName=NE&idArk={ark_id}&couverture=1"
        try:
            if requests.get(url=cover_url, headers=HEADERS, timeout=TIMEOUT).status_code == 200:
                cover = cover_url
        except requests.RequestException:
            pass

    return {
        "title": title,
        "isbn": isbn,
        "author": ", ".join(authors) if authors else None,
        "publisher": publisher,
        "cover": cover,
        "published_year": (date or "")[:4] or None,
        "description": None,  # BnF descriptions are catalog notes, not synopses
        "page_count": None,
        "language": language,
    }


def search_wikipedia_fr_articles(title: str, author: str, limit: int = 3) -> list:
    """Titres d'articles de Wikipédia FR susceptibles de parler de ce livre.

    L'article ne porte pas toujours le titre du livre : « Si c'était à
    refaire » y est « Si c'était à refaire (roman) ». On passe donc par la
    recherche plutôt que de deviner l'adresse.
    """
    query = f'intitle:"{title}"'
    if author:
        query += f" {author}"
    params = {
        "action": "query", "list": "search", "srsearch": query,
        "srlimit": limit, "format": "json",
    }
    try:
        response = requests.get(url=WIKIPEDIA_FR_API, params=params, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException:
        return []
    if response.status_code != 200:
        return []
    try:
        results = response.json().get("query", {}).get("search", [])
    except ValueError:
        return []
    return [result["title"] for result in results if result.get("title")]


def get_wikipedia_fr_summary(title: str, author: str) -> str:
    """Le résumé d'un livre sur Wikipédia FR, ou None si rien ne se prouve.

    Deux garde-fous, parce qu'un résumé faux sur une fiche de bibliothèque
    est pire qu'une fiche sans résumé :

    - les pages d'homonymie sont écartées (« Anges et démons » en est une) ;
    - le nom de l'auteur doit apparaître dans l'extrait, sinon rien ne dit
      que l'article parle du bon ouvrage.

    Cette source ne demande ni clé ni quota, contrairement à Google Books
    qui alterne les 503 et laissait les résumés vides.
    """
    if not title:
        return None
    author_words = significant_words(author)
    for article in search_wikipedia_fr_articles(title=title, author=author):
        try:
            response = requests.get(
                url=f"{WIKIPEDIA_FR_SUMMARY}{quote(article, safe='')}",
                headers=HEADERS, timeout=TIMEOUT,
            )
        except requests.RequestException:
            continue
        if response.status_code != 200:
            continue
        try:
            page = response.json()
        except ValueError:
            continue
        if page.get("type") != "standard":
            continue
        extract = (page.get("extract") or "").strip()
        if not extract:
            continue
        # Sans auteur connu, on ne peut rien prouver : on s'abstient.
        if not author_words:
            return None
        if author_words & significant_words(extract):
            return extract
    return None


def get_cover(isbn: str) -> str:
    url = f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg?default=false"
    try:
        response = requests.get(url=url, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException:
        return None
    if response.status_code == 200:
        return url
    return None


def fetch_in_parallel(tasks: dict) -> dict:
    """Lance des appels réseau de front et rend leurs résultats par nom.

    Les catalogues ne se parlent pas : les interroger l'un après l'autre
    faisait payer à la bibliothécaire la somme de leurs délais alors qu'elle
    n'attend, en vérité, que le plus lent. Le choix de la source reste au
    dessus de cette fonction : ici on récolte tout, on ne préfère rien.

    Une source qui lève ne doit jamais emporter les autres — une fiche
    partielle vaut mieux qu'un scan qui échoue —, donc son résultat vaut
    None et le reste continue.
    """
    results = {name: None for name in tasks}
    if not tasks:
        return results
    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        futures = {executor.submit(task): name for name, task in tasks.items()}
        for future in as_completed(futures):
            source = futures[future]
            try:
                results[source] = future.result()
            except Exception as error:
                # Isoler ne doit pas vouloir dire taire : si une source change
                # de format, la panne serait sinon une dégradation silencieuse
                # des métadonnées, identique chez les 17 organisations et
                # invisible dans tout message.
                logger.warning("Source %s indisponible : %s", source, error)
                results[source] = None
    return results


def get_book_information(isbn: str):
    """La meilleure notice disponible pour cet ISBN.

    L'ordre de préférence — Wikipédia, Google, BnF, OpenLibrary — encode une
    qualité de notice, pas une commodité d'appel : la BnF est la meilleure
    source du francophone, Google la plus large. Les quatre partent donc
    ensemble, et c'est au dépouillement que la hiérarchie s'applique,
    exactement comme du temps de la cascade.
    """
    catalogs = fetch_in_parallel({
        "wikipedia": partial(get_wikipedia_book_information, isbn=isbn),
        "google": partial(get_google_book_information, isbn=isbn),
        "bnf": partial(get_bnf_book_information, isbn=isbn),
        "open_library": partial(get_open_library_book_information, isbn=isbn),
    })
    google_book = catalogs["google"]

    wikipedia_book = catalogs["wikipedia"]
    if wikipedia_book:
        if not wikipedia_book.get("description") and google_book:
            wikipedia_book["description"] = google_book.get("description")
        return wikipedia_book

    if google_book:
        return google_book

    bnf_book = catalogs["bnf"]
    if bnf_book:
        if google_book is None:
            # La cascade laissait ici une seconde chance à Google, qui alterne
            # les 503 : on la garde, car une notice BnF n'a pas de résumé et
            # Google est le seul à pouvoir le fournir. Elle passe par la même
            # récolte que les autres pour hériter de la même isolation : une
            # notice BnF ne doit pas se perdre parce que Google a déraillé.
            google_book = fetch_in_parallel(
                {"google": partial(get_google_book_information, isbn=isbn)}
            )["google"]
        if google_book:
            bnf_book["description"] = google_book.get("description")
        return bnf_book

    return catalogs["open_library"]


def find_book_details(isbn: str) -> BookDetails:
    # La couverture ne dépend que de l'ISBN : la chercher pendant que les
    # catalogues répondent l'efface du temps d'attente. Le prix est une
    # requête de couverture même quand aucune notice ne sort — c'est un appel
    # de plus contre plusieurs secondes de moins devant la douchette.
    fetched = fetch_in_parallel({
        "book": partial(get_book_information, isbn=isbn),
        "cover": partial(get_cover, isbn=isbn),
    })
    book = fetched["book"]
    if not book:
        return None

    cover = fetched["cover"] or book.get("cover")
    description = book.get("description")
    if not description:
        # Aucune des sources par ISBN ne rend de résumé fiable : Wikipédia
        # en donne un, gratuitement et sans quota.
        description = get_wikipedia_fr_summary(
            title=book.get("title"), author=book.get("author")
        )
    return BookDetails(
        isbn=isbn,
        title=book.get("title"),
        picture=cover,
        author=book.get("author"),
        publisher=book.get("publisher"),
        published_year=book.get("published_year"),
        description=description,
        page_count=book.get("page_count"),
        language=book.get("language"),
    )


def download_image(url: str):
    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException:
        return None
    if response.status_code == 200:
        return response.content
