from io import BytesIO

import openpyxl
from django.db import IntegrityError
from rest_framework import permissions, views
from rest_framework.parsers import (
    FileUploadParser,
    FormParser,
    JSONParser,
    MultiPartParser,
)
from rest_framework.response import Response

from src.items.book_lookup import find_book_details
from src.items.models import Book, Collection
from src.scripts.serializers import FileUploadSerializer

# ORGANIZATION_ID = 1
# COLLECTION_ID = 1


class ImportBooksFromISBNS(views.APIView):
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
        ORGANIZATION_ID = request.user.employee_of_organization_id
        COLLECTION_ID = Collection.objects.find(organization_id=ORGANIZATION_ID).first()
        file = request.FILES["file"]
        isbns = read_isbns_from_xls_file(file=file)
        status = {"not_found": [], "duplicates": [], "success": []}
        for index, isbn in enumerate(isbns):
            book = find_book_details(isbn=isbn)
            if book:
                print(f"✅{index + 1}/{len(isbns)} found : {book.title} - {isbn}")
                # books.append(book)
                db_book = Book(
                    organization_id=ORGANIZATION_ID,
                    author=book.author,
                    title=book.title,
                    isbn=book.isbn,
                    publisher=book.publisher,
                    picture=book.author,
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
                else:
                    db_book.collections.set([COLLECTION_ID])
                    status["success"].append(book.isbn)
                    print(f"✅{index + 1}/{len(isbns)} Duccess : {book.title} - {isbn}")
            else:
                print(f"❌{index + 1}/{len(isbns)} Not found : {isbn}")
                status["not_found"].append(isbn)

        return Response(
            {
                "status": status
                | {
                    "not_found_count": len(status["not_found"]),
                    "duplicates_count": len(status["duplicates"]),
                    "success_count": len(status["success"]),
                }
            },
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
