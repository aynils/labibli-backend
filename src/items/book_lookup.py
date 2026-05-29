import os
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import requests

GOOGLE_URL = "https://www.googleapis.com/books/v1/volumes"
OPEN_LIBRARY_URL = "https://openlibrary.org/api/books"
WIKIPEDIA_URL = "https://en.wikipedia.org/api/rest_v1/data/citation/mediawiki/"
BNF_SRU_URL = "https://catalogue.bnf.fr/api/SRU"

HEADERS = {"User-Agent": "LaBibli/1.0 (https://labibli.com; contact@labibli.com)"}
TIMEOUT = 5

GOOGLE_BOOKS_API_KEY = os.environ.get("GOOGLE_BOOKS_API_KEY")

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


def get_google_book_information(isbn: str) -> dict or None:
    params = {
        "q": f"isbn:{isbn}",
        "fields": "items/volumeInfo(title,authors,publisher,publishedDate,language,description,pageCount,imageLinks)",
        "maxResults": 1,
    }
    if GOOGLE_BOOKS_API_KEY:
        params["key"] = GOOGLE_BOOKS_API_KEY
    try:
        response = requests.get(url=GOOGLE_URL, params=params, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException:
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

    return {
        "title": title,
        "isbn": isbn,
        "author": ", ".join(authors) if authors else None,
        "publisher": publisher,
        "cover": None,
        "published_year": (date or "")[:4] or None,
        "description": None,  # BnF descriptions are catalog notes, not synopses
        "page_count": None,
        "language": language,
    }


def get_open_library_cover(isbn: str) -> str:
    url = f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg?default=false"
    try:
        response = requests.get(url=url, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException:
        return None
    if response.status_code == 200:
        return url


def get_les_librairies_cover(isbn: str) -> str:
    url = f"https://images.leslibraires.ca/books/{isbn}/front/{isbn}_large.jpg"
    try:
        response = requests.get(url=url, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException:
        return None
    if response.status_code == 200:
        return url


def get_cover(isbn: str) -> str:
    sources = [get_open_library_cover, get_les_librairies_cover]
    with ThreadPoolExecutor(max_workers=len(sources)) as executor:
        futures = {executor.submit(fn, isbn): fn for fn in sources}
        for future in as_completed(futures):
            result = future.result()
            if result:
                return result
    return None


def get_book_information(isbn: str):
    wikipedia_book = get_wikipedia_book_information(isbn=isbn)
    if wikipedia_book:
        if not wikipedia_book.get("description"):
            google_book = get_google_book_information(isbn=isbn)
            if google_book:
                wikipedia_book["description"] = google_book.get("description")
        return wikipedia_book

    google_book = get_google_book_information(isbn=isbn)
    if google_book:
        return google_book

    bnf_book = get_bnf_book_information(isbn=isbn)
    if bnf_book:
        google_book = get_google_book_information(isbn=isbn)
        if google_book:
            bnf_book["description"] = google_book.get("description")
        return bnf_book

    return get_open_library_book_information(isbn=isbn)


def find_book_details(isbn: str) -> BookDetails:
    book = get_book_information(isbn=isbn)
    if not book:
        return None

    cover = get_cover(isbn=isbn) or book.get("cover")
    return BookDetails(
        isbn=isbn,
        title=book.get("title"),
        picture=cover,
        author=book.get("author"),
        publisher=book.get("publisher"),
        published_year=book.get("published_year"),
        description=book.get("description"),
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
