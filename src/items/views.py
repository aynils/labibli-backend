import dataclasses
import datetime
from collections import OrderedDict

from django.conf import settings
from django.db.models import Q
from django.http import HttpResponse
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from src.helpers.query_params import is_true
from src.items.book_export import export as export_books
from src.items.book_lookup import download_image, find_book_details
from src.items.models import Book, Category, Collection, Lending
from src.items.serializers import (
    BookSerializer,
    CategorySerializer,
    CollectionSerializer,
    LendingSerializer,
)
from src.labibli import permissions as custom_permissions


class BooksListPagination(PageNumberPagination):
    page_size = settings.DEFAULT_BOOK_PAGE_SIZE
    page_size_query_param = "page_size"
    max_page_size = 1000

    def get_paginated_response(self, data):
        return Response(
            OrderedDict(
                [
                    ("count", self.page.paginator.count),
                    ("next", self.get_next_link()),
                    ("previous", self.get_previous_link()),
                    ("results", data),
                    ("num_pages", self.page.paginator.num_pages),
                ]
            )
        )


class BooksList(generics.ListCreateAPIView):
    permission_classes = [
        permissions.IsAuthenticated,
        custom_permissions.IsEmployeeOfAnOrganization,
    ]
    serializer_class = BookSerializer
    pagination_class = BooksListPagination

    def get_queryset(self):
        user = self.request.user
        query = self.request.query_params.get("query")
        available = self.request.query_params.get("available")
        category_ids = self.request.query_params.getlist("categoryId")
        queryset = Book.objects.filter(
            organization=user.employee_of_organization
        ).order_by("-featured", "-created_at")
        if query:
            queryset = queryset.filter(
                Q(title__unaccent__icontains=query)
                | Q(author__unaccent__icontains=query)
                | Q(isbn__unaccent__icontains=query)
            )
        if is_true(available):
            queryset = queryset.filter(
                Q(lendings__isnull=True) | Q(lendings__returned_at__isnull=False)
            )
        if not is_true(self.request.query_params.get("archived")):
            # Archivé vaut caché : un ouvrage sorti de la circulation n'a pas
            # à encombrer la liste. Il reste atteignable par « archived=true »,
            # sans quoi il deviendrait impossible de le désarchiver.
            queryset = queryset.exclude(archived=True)
        for category_id in category_ids:
            queryset = queryset.filter(categories__in=[category_id])
        return queryset

    def perform_create(self, serializer):
        user = self.request.user
        serializer.save(organization=user.employee_of_organization)


class BooksExport(APIView):
    """Rend la collection en classeur, sans passer par nous.

    Jusqu'ici l'export se faisait à la main, de notre côté, sur demande. Le
    site le décrit pourtant comme un bouton, et c'est la contrepartie de
    tout le discours sur la souveraineté des données : une bibliothèque doit
    pouvoir partir sans nous le demander.

    Le format est celui que `src/imports/readers.py` sait relire — voir
    `src/items/book_export.py`.
    """

    permission_classes = [
        permissions.IsAuthenticated,
        custom_permissions.IsEmployeeOfAnOrganization,
    ]

    def get(self, request):
        # 🔴 L'organisation vient du jeton, jamais d'un paramètre de requête :
        # un identifiant accepté depuis l'URL rendrait la collection de
        # n'importe quelle bibliothèque à n'importe qui.
        organization = request.user.employee_of_organization
        content = export_books(organization_id=organization.id)
        response = HttpResponse(
            content,
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )
        stamp = datetime.date.today().isoformat()
        # Le nom du fichier ne porte pas celui de l'organisation : il peut
        # contenir n'importe quel caractère, et un en-tête HTTP mal formé
        # casse le téléchargement chez le client, pas chez nous.
        response["Content-Disposition"] = (
            f'attachment; filename="collection-labibli-{stamp}.xlsx"'
        )
        return response


class BookDetail(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [custom_permissions.IsEmployeeOfOrganization]
    queryset = Book.objects.all()
    serializer_class = BookSerializer

    def perform_create(self, serializer):
        serializer.save(organization=self.request.user.employee_of_organization)


class CollectionDetail(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [
        permissions.IsAuthenticated,
        custom_permissions.IsEmployeeOfOrganization,
    ]
    queryset = Collection.objects.all()
    serializer_class = CollectionSerializer

    def perform_create(self, serializer):
        serializer.save(
            owner=self.request.user,
            organization=self.request.user.employee_of_organization,
        )


class CollectionShared(generics.RetrieveAPIView):
    permission_classes = [permissions.AllowAny]
    lookup_field = "slug"
    queryset = Collection.objects.all()
    serializer_class = CollectionSerializer

    def get_serializer_context(self):
        """Signale au sérialiseur qu'il travaille pour la vitrine publique.

        Le même sérialiseur sert les écrans de la bibliothèque, où les
        ouvrages archivés doivent rester visibles : seul ce drapeau les
        retire, et seulement ici.
        """
        context = super().get_serializer_context()
        context["public"] = True
        return context


class CollectionsList(generics.ListCreateAPIView):
    permission_classes = [
        permissions.IsAuthenticated,
        custom_permissions.IsEmployeeOfAnOrganization,
    ]
    serializer_class = CollectionSerializer

    def get_queryset(self):
        user = self.request.user
        return Collection.objects.filter(organization=user.employee_of_organization)

    def perform_create(self, serializer):
        user = self.request.user
        serializer.save(organization=user.employee_of_organization)


class LendingDetail(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [
        permissions.IsAuthenticated,
        custom_permissions.IsEmployeeOfOrganization,
    ]
    queryset = Lending.objects.all()
    serializer_class = LendingSerializer

    def perform_create(self, serializer):
        serializer.save(
            owner=self.request.user,
            organization=self.request.user.employee_of_organization,
        )


class ReturnLending(APIView):
    permission_classes = [
        permissions.IsAuthenticated,
        custom_permissions.IsEmployeeOfOrganization,
    ]
    queryset = Lending.objects.all()

    def post(self, request, pk):
        lending = Lending.objects.get(id=pk)
        serializer = LendingSerializer()
        today = datetime.datetime.today()
        updated_lending = serializer.return_book(lending, returned_at=today)
        return Response(updated_lending, status.HTTP_200_OK)


class LendingsList(generics.ListCreateAPIView):
    permission_classes = [
        permissions.IsAuthenticated,
        custom_permissions.IsEmployeeOfAnOrganization,
    ]
    serializer_class = LendingSerializer

    def get_queryset(self):
        user = self.request.user
        return Lending.objects.filter(
            organization=user.employee_of_organization, returned_at__isnull=True
        )

    def perform_create(self, serializer):
        user = self.request.user
        serializer.save(organization=user.employee_of_organization)


class CategoryDetail(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [
        permissions.IsAuthenticated,
        custom_permissions.IsEmployeeOfOrganization,
    ]
    queryset = Category.objects.all()
    serializer_class = CategorySerializer

    def perform_create(self, serializer):
        serializer.save(
            owner=self.request.user,
            organization=self.request.user.employee_of_organization,
        )


class CategoriesList(generics.ListCreateAPIView):
    permission_classes = [
        permissions.IsAuthenticated,
        custom_permissions.IsEmployeeOfAnOrganization,
    ]
    serializer_class = CategorySerializer

    def get_queryset(self):
        user = self.request.user
        return Category.objects.filter(organization=user.employee_of_organization)

    def perform_create(self, serializer):
        user = self.request.user
        serializer.save(organization=user.employee_of_organization)


class CategoriesShared(generics.ListCreateAPIView):
    permission_classes = [
        permissions.AllowAny,
    ]
    serializer_class = CategorySerializer

    def get_queryset(self):
        slug = self.kwargs["slug"]
        collection = Collection.objects.get(slug=slug)
        organization = collection.organization
        return Category.objects.filter(organization=organization)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def book_lookup(request):
    isbn = request.GET.get("isbn")
    if isbn:
        result = find_book_details(isbn=isbn)
        if result:
            return Response(dataclasses.asdict(result), status.HTTP_200_OK)
        else:
            return Response(status=404)
    else:
        return Response({"error": "missing ISBN"}, status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def fetch_image(request):
    url = request.GET.get("image_url")
    if url:
        result = download_image(url=url)
        if result:
            return HttpResponse(result, content_type="image/png")
        else:
            return Response(status=404)
    else:
        return Response({"error": "missing url"}, status.HTTP_400_BAD_REQUEST)
