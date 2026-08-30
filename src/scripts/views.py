"""Point d'entrée HTTP des imports en masse.

La vue ne fait que trois choses : établir dans quelle organisation on
importe, lire le fichier, et rendre le compte rendu. Tout ce qui touche aux
ouvrages ou aux membres vit dans `src/items/book_import.py` et
`src/customers/customer_import.py`, au-dessus du socle `src/imports/` — la
mécanique d'un import ne doit exister qu'une fois.
"""
from rest_framework import permissions, views
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from src.customers.customer_import import COLUMNS as CUSTOMER_COLUMNS
from src.customers.customer_import import CustomerImporter
from src.imports.readers import ImportFileError, read_rows
from src.imports.runner import run_import
from src.items.book_import import COLUMNS as BOOK_COLUMNS
from src.items.book_import import BookImporter
from src.items.models import Collection
from src.labibli.permissions import IsEmployeeOfAnOrganization

KINDS = {
    "books": (BOOK_COLUMNS, "ouvrages"),
    "customers": (CUSTOMER_COLUMNS, "membres"),
}


class ImportFromFile(views.APIView):
    """Importe des ouvrages ou des membres depuis un tableur ou un CSV.

    curl -F file=@collection.xlsx -F kind=books http://localhost:8000/scripts/import/
    """

    # Les deux, comme partout ailleurs dans le dépôt : sans
    # `IsAuthenticated`, un anonyme atteint `IsEmployeeOfAnOrganization` qui
    # lit `request.user.employee_of_organization` et rend un 500 au lieu
    # d'un 401.
    permission_classes = [permissions.IsAuthenticated, IsEmployeeOfAnOrganization]
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        organization_id = request.user.employee_of_organization_id
        kind = request.data.get("kind", "books")
        if kind not in KINDS:
            return Response(
                {"detail": f"Type d'import inconnu : {kind}. Attendu : {', '.join(KINDS)}."},
                status=400,
            )
        uploaded = request.FILES.get("file")
        if not uploaded:
            return Response({"detail": "Aucun fichier reçu sous le champ « file »."}, status=400)

        columns, noun = KINDS[kind]
        try:
            records = read_rows(file=uploaded, columns=columns)
        except ImportFileError as error:
            return Response({"detail": str(error)}, status=400)

        if kind == "books":
            # La collection sert de rangement par défaut aux ouvrages
            # importés ; une organisation qui n'en a pas encore importe
            # quand même.
            collection = Collection.objects.filter(organization_id=organization_id).first()
            importer = BookImporter(collection=collection)
        else:
            importer = CustomerImporter()

        report = run_import(
            records=records, importer=importer, organization_id=organization_id
        )
        return Response({"kind": kind, "noun": noun, "status": report.as_dict()}, status=200)
