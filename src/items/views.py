from rest_framework import generics, permissions

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


class LendingsList(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated, custom_permissions.IsEmployeeOfAnOrganization]
    serializer_class = LendingSerializer

    def get_queryset(self):
        user = self.request.user
        return Lending.objects.filter(organization=user.employee_of_organization)

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
