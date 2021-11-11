from rest_framework import generics, permissions

from src.accounts.models import Organization, User
from src.accounts.serializers import OrganizationSerializer, UserSerializer
from src.labibli import permissions as custom_permissions


class OrganizationCreate(generics.CreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer

    def perform_create(self, serializer):
        user = self.request.user
        organization = serializer.save(owner=user)
        user.employee_of_organization = organization
        user.save()


class OrganizationDetail(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [custom_permissions.IsOwner]
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer


class UserList(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAdminUser]
    queryset = User.objects.all()
    serializer_class = UserSerializer


class UserDetail(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [custom_permissions.IsSelf]
    queryset = Organization.objects.all()
    serializer_class = UserSerializer
