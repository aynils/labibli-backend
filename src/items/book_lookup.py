from dataclasses import dataclass

import requests

GOOGLE_URL = "https://www.googleapis.com/books/v1/volumes"
OPEN_LIBRARY_URL = "https://openlibrary.org/api/books"
WIKIPEDIA_URL = "https://en.wikipedia.org/api/rest_v1/data/citation/mediawiki/"


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
        "q": "isbn:${isbn}",
        "fields": "items/volumeInfo(title,authors,publisher,publishedDate,language,description,pageCount,imageLinks)",
        "maxResults": 1,
    }
    response = requests.get(url=GOOGLE_URL, params=params)
    if response.status_code == 200 and response.json().get("items"):
        volume = response.json().get("items")[0].get("volumeInfo")
        return {
            "title": volume.get("title"),
            "isbn": isbn,
            "author": ", ".join(volume.get("authors", [])),
            "publisher": volume.get("publisher"),
            "cover": volume.imageLinks if volume.get("imageLinks.thumbnail") else None,
            "published_year": volume.publishedDate[0:4]
            if volume.get("publishedDate")
            else None,
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
    response = requests.get(url=OPEN_LIBRARY_URL, params=params)
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
    params = {}
    url = f"{WIKIPEDIA_URL}{isbn}"
    response = requests.get(url=url, params=params)
    if response.status_code == 200 and response.json():
        volume = response.json()[0]
        if volume:
            authors = [
                f"{author[0]} {author[1]}" for author in volume.get("author", [])
            ]
            publishers = [volume.get("publishers", "")] or [
                publisher.name for publisher in volume.get("publishers", [])
            ]
            # cover_id = volume.get('covers', [])[0]
            return {
                "title": volume.get("title"),
                "isbn": isbn,
                "author": ", ".join(authors),
                "publisher": ", ".join(publishers),
                "cover": None,
                "published_year": volume.get("date"),
                "description": volume.get("abstractNote"),
                "page_count": volume.get("numPages"),
                "language": volume.get("language"),
            }
    return None


def get_open_library_cover(isbn: str) -> str:
    url = f"http://covers.openlibrary.org/b/isbn/{isbn}-L.jpg?default=false"
    response = requests.get(url=url)
    if response.status_code == 200:
        return url


def get_les_librairies_cover(isbn: str) -> str:
    url = f"https://images.leslibraires.ca/books/{isbn}/front/{isbn}_large.jpg"
    response = requests.get(url=url)
    if response.status_code == 200:
        return url


def get_cover(isbn: str) -> str:
    open_library_cover = get_open_library_cover(isbn=isbn)
    if open_library_cover:
        return open_library_cover
    return get_les_librairies_cover(isbn=isbn)


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
    return get_open_library_book_information(isbn=isbn)


def find_book_details(isbn: str) -> BookDetails:
    book = get_book_information(isbn=isbn)
    cover = get_cover(isbn=isbn)

    if book:
        return BookDetails(
            isbn=isbn,
            title=book.get("title"),
            picture=cover or book.get("cover"),
            author=book.get("author"),
            publisher=book.get("publisher"),
            published_year=book.get("published_year"),
            description=book.get("description"),
            page_count=book.get("page_count"),
            language=book.get("language"),
        )


def download_image(url: str):
    response = requests.get(url)
    if response.status_code == 200:
        return response.content
