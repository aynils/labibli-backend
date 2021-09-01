from rest_framework import generics

from accounts.models import Organization
from accounts.serializers import OrganizationSerializer


class OrganizationList(generics.ListCreateAPIView):
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer


class OrganizationDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer

# class UserViewSet(APIView):
#     queryset = MyUser.objects.all()
#     serializer_class = UserSerializer
