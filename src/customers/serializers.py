from rest_framework import serializers

from customers.models import Customer


class CustomerSerializer(serializers.ModelSerializer):
    organization = serializers.ReadOnlyField(source='organization.name')

    class Meta:
        model = Customer
        fields = [
            "organization",
            "is_active",
            "first_name",
            "last_name",
            "email",
            "phone",
            "language",
            "note",
        ]
