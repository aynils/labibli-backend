from rest_framework import generics, permissions

from customers.models import Customer
from customers.serializers import CustomerSerializer
from labibli import permissions as custom_permissions


class CustomerDetail(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated, custom_permissions.IsEmployeeOfOrganization]
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer

    def perform_create(self, serializer):
        serializer.save(
            owner=self.request.user,
            organization=self.request.user.employee_of_organization
        )


class CustomersList(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated, custom_permissions.IsEmployeeOfOrganization]
    serializer_class = CustomerSerializer

    def get_queryset(self):
        user = self.request.user
        return Customer.objects.filter(organization=user.employee_of_organization)

    def perform_create(self, serializer):
        user = self.request.user
        serializer.save(organization=user.employee_of_organization)
