from rest_framework import serializers

from src.accounts.models import Organization, User


class OrganizationSerializer(serializers.ModelSerializer):
    owner = serializers.ReadOnlyField(source="owner.email")

    class Meta:
        model = Organization
        fields = ["name", "id", "owner", "is_subscribed"]


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]
