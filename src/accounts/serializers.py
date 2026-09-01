from rest_framework import serializers

from src.accounts.models import Organization, User


class OrganizationSerializer(serializers.ModelSerializer):
    owner = serializers.ReadOnlyField(source="owner.email")

    class Meta:
        model = Organization
        # Les trois réglages de rappel sont modifiables par la propriétaire
        # de l'organisation (`OrganizationDetail`, permission `IsOwner`).
        # C'est ce qui permettra à l'interface de proposer l'interrupteur
        # sans nouvel aller-retour côté API.
        fields = [
            "name",
            "id",
            "owner",
            "is_subscribed",
            "member_reminders_enabled",
            "member_reminder_frequency_days",
            "librarian_digest_enabled",
        ]


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]
