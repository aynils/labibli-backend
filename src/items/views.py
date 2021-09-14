from rest_framework import generics, permissions
from labibli import permissions as custom_permissions

from items.models import Book, Collection, Category
from items.serializers import BookSerializer, CollectionSerializer, CategorySerializer


class BooksList(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated, custom_permissions.IsEmployeeOfAnOrganization]
    serializer_class = BookSerializer

    def get_queryset(self):
        user = self.request.user
        return Book.objects.filter(organization = user.employee_of_organization)

    def perform_create(self, serializer):
        user = self.request.user
        organization = serializer.save(organization=user.employee_of_organization)



class BookDetail(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [custom_permissions.IsEmployeeOfOrganization]
    queryset = Book.objects.all()
    serializer_class = BookSerializer


class CollectionDetail(generics.RetrieveAPIView):
    permission_classes = [permissions.AllowAny]
    queryset = Collection.objects.all()
    serializer_class = CollectionSerializer

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
