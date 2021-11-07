import datetime
import dataclasses

from django.http import HttpResponse

from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView

from items.book_lookup import find_book_details, download_image
from items.models import Book, Collection, Lending, Category
from items.serializers import BookSerializer, CollectionSerializer, LendingSerializer, CategorySerializer
from labibli import permissions as custom_permissions


class BooksList(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated, custom_permissions.IsEmployeeOfAnOrganization]
    serializer_class = BookSerializer

    def get_queryset(self):
        user = self.request.user
        return Book.objects.filter(organization=user.employee_of_organization)

    def perform_create(self, serializer):
        user = self.request.user
        serializer.save(organization=user.employee_of_organization)


class BookDetail(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [custom_permissions.IsEmployeeOfOrganization]
    queryset = Book.objects.all()
    serializer_class = BookSerializer

    def perform_create(self, serializer):
        serializer.save(
            organization=self.request.user.employee_of_organization
        )


class CollectionDetail(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [custom_permissions.AllowSafeOrEmployeeOfOrganization]
    queryset = Collection.objects.all()
    serializer_class = CollectionSerializer

    def perform_create(self, serializer):
        serializer.save(
            owner=self.request.user,
            organization=self.request.user.employee_of_organization
        )


class CollectionsList(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated, custom_permissions.IsEmployeeOfAnOrganization]
    serializer_class = CollectionSerializer

    def get_queryset(self):
        user = self.request.user
        return Collection.objects.filter(organization=user.employee_of_organization)

    def perform_create(self, serializer):
        user = self.request.user
        serializer.save(organization=user.employee_of_organization)


class LendingDetail(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated, custom_permissions.IsEmployeeOfOrganization]
    queryset = Lending.objects.all()
    serializer_class = LendingSerializer

    def perform_create(self, serializer):
        serializer.save(
            owner=self.request.user,
            organization=self.request.user.employee_of_organization
        )


class ReturnLending(APIView):
    permission_classes = [permissions.IsAuthenticated, custom_permissions.IsEmployeeOfOrganization]
    queryset = Lending.objects.all()

    def post(self, request, pk):
        lending = Lending.objects.get(id=pk)
        serializer = LendingSerializer()
        today = datetime.datetime.today()
        updated_lending = serializer.return_book(lending, returned_at=today)
        return Response(updated_lending, status.HTTP_200_OK)


class LendingsList(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated, custom_permissions.IsEmployeeOfAnOrganization]
    serializer_class = LendingSerializer

    def get_queryset(self):
        user = self.request.user
        return Lending.objects.filter(organization=user.employee_of_organization, returned_at__isnull=True)

    def perform_create(self, serializer):
        user = self.request.user
        serializer.save(organization=user.employee_of_organization)


class CategoryDetail(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated, custom_permissions.IsEmployeeOfOrganization]
    queryset = Category.objects.all()
    serializer_class = CategorySerializer

    def perform_create(self, serializer):
        serializer.save(
            owner=self.request.user,
            organization=self.request.user.employee_of_organization
        )


class CategoriesList(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated, custom_permissions.IsEmployeeOfAnOrganization]
    serializer_class = CategorySerializer

    def get_queryset(self):
        user = self.request.user
        return Category.objects.filter(organization=user.employee_of_organization)

    def perform_create(self, serializer):
        user = self.request.user
        serializer.save(organization=user.employee_of_organization)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def book_lookup(request):
    isbn = request.GET.get('isbn')
    if isbn:
        result = find_book_details(isbn=isbn)
        if result:
            return Response(dataclasses.asdict(result), status.HTTP_200_OK)
        else:
            return Response(status=404)
    else:
        return Response({"error": "missing ISBN"},status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def fetch_image(request):
    url = request.GET.get('image_url')
    if url:
        result = download_image(url=url)
        if result:
            # return Response(result, status.HTTP_200_OK)
            return HttpResponse(result, content_type="image/png")
        else:
            return Response(status=404)
    else:
        return Response({"error": "missing url"},status.HTTP_400_BAD_REQUEST)
