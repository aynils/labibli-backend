from rest_framework import generics, permissions

from src.accounts.models import Organization, User
from src.accounts.serializers import OrganizationSerializer, UserSerializer
from src.labibli import permissions as custom_permissions
from src.payment.models import Subscription
from src.payment.serializers import SubscriptionSerializer


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


class OrganizationCurrent(generics.RetrieveAPIView):
    permission_classes = [custom_permissions.IsOwner]
    serializer_class = OrganizationSerializer

    def get_object(self):
        return self.request.user.employee_of_organization


class SubscriptionCurrent(generics.RetrieveAPIView):
    permission_classes = [custom_permissions.IsEmployeeOfOrganization]
    serializer_class = SubscriptionSerializer

    def get_object(self):
        organization = self.request.user.employee_of_organization
        return (
            Subscription.objects.filter(organization=organization)
            .order_by("-created_at")
            .first()
        )


class UserList(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAdminUser]
    queryset = User.objects.all()
    serializer_class = UserSerializer


class UserDetail(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [custom_permissions.IsSelf]
    queryset = Organization.objects.all()
    serializer_class = UserSerializer
