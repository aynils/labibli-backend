import json
from io import BytesIO

import openpyxl
from django.core.files.base import ContentFile
from django.db import IntegrityError
from rest_framework import permissions, views
from rest_framework.parsers import (
    FileUploadParser,
    FormParser,
    JSONParser,
    MultiPartParser,
)
from rest_framework.response import Response

from src.items.book_lookup import download_image, find_book_details
from src.items.models import Book, Collection
from src.scripts.serializers import FileUploadSerializer

ORGANIZATION_ID = 1
COLLECTION_ID = 1

LOCAL_RUN = False


class ImportBooksFromISBNS(views.APIView):
    if not LOCAL_RUN:
        permission_classes = [permissions.IsAuthenticated]
    """
    Curl example request :
    curl -F file=@ISBN_test.xlsx http://localhost:8000/scripts/import/
    -H "Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    -H 'Content-Disposition: attachment;filename="ISBN_test.xlsx"'
    """
    serializer = FileUploadSerializer
    parser_classes = (MultiPartParser, FormParser, JSONParser, FileUploadParser)

    def post(self, request):
        if not LOCAL_RUN:
            ORGANIZATION_ID = request.user.employee_of_organization_id
            COLLECTION_ID = Collection.objects.find(
                organization_id=ORGANIZATION_ID
            ).first()
        file = request.FILES["file"]
        isbns = read_isbns_from_xls_file(file=file)
        status = {"not_found": [], "duplicates": [], "success": [], "error": []}
        for index, isbn in enumerate(isbns):
            book_already_in_DB = Book.objects.filter(isbn=isbn).exists()
            if book_already_in_DB:
                status["duplicates"].append(isbn)
                print(f"⚠️{index + 1}/{len(isbns)} Duplicate : {isbn}")
            else:
                try:
                    book = find_book_details(isbn=isbn)
                except Exception as e:
                    print(f"❌{index + 1}/{len(isbns)} Lookup Error : {e}")
                    status["error"].append(isbn)
                else:
                    if book:
                        print(
                            f"✅{index + 1}/{len(isbns)} found : {book.title} - {isbn}"
                        )
                        db_book = Book(
                            organization_id=ORGANIZATION_ID,
                            author=book.author,
                            title=book.title,
                            isbn=book.isbn,
                            publisher=book.publisher,
                            # Todo : fix picture
                            # picture=book.author,
                            lang=book.language,
                            inventory=1,
                            published_year=book.published_year,
                            description=book.description,
                        )
                        try:
                            db_book.save()
                        except IntegrityError:
                            status["duplicates"].append(book.isbn)
                            print(f"⚠️{index + 1}/{len(isbns)} Duplicate : {isbn}")
                        except Exception as e:
                            print(f"❌{index + 1}/{len(isbns)} Saving Error : {e}")
                            status["error"].append(isbn)
                        else:
                            db_book.collections.set([COLLECTION_ID])
                            status["success"].append(book.isbn)
                            print(
                                f"✅{index + 1}/{len(isbns)} Success : {book.title} - {isbn}"
                            )
                        try:
                            image = download_image(url=book.picture)
                            if image:
                                db_book.picture.save(
                                    name=book.title,
                                    content=ContentFile(image),
                                    save=True,
                                )
                        except Exception as e:
                            print(
                                f"⚠️{index + 1}/{len(isbns)} No picture : {isbn} - {e}"
                            )

                    else:
                        print(f"❌{index + 1}/{len(isbns)} Not found : {isbn}")
                        status["not_found"].append(isbn)

        status |= {
            "not_found_count": len(status["not_found"]),
            "duplicates_count": len(status["duplicates"]),
            "success_count": len(status["success"]),
            "error": len(status["error"]),
        }

        with open("import_log.json", "w") as file:
            json.dump(status, file)

        return Response(
            {"status": status},
            status=200,
        )


def read_isbns_from_xls_file(file) -> list:
    reader = openpyxl.load_workbook(filename=BytesIO(file.read()), read_only=True)
    isbns = []
    if reader.worksheets:
        rows = reader.worksheets[0].iter_rows(min_row=2)
        for row in rows:
            isbns.append(row[0].value)
    return isbns
