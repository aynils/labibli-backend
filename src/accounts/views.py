from rest_framework import generics, permissions
from labibli import permissions as custom_permissions

from accounts.models import Organization, User
from accounts.serializers import OrganizationSerializer, UserSerializer


class OrganizationList(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAdminUser]
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer

    def perform_create(self, serializer):
        user = self.request.user
        organization = serializer.save(owner=user)
        print(organization)
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
