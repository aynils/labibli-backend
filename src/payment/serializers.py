from rest_framework import serializers

from src.payment.models import Subscription


class SubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = ["plan", "interval", "active", "created_at"]
