import logging

from django.shortcuts import redirect
from rest_framework import permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import Subscription
from .provider import create_session, parse_webhook

logger = logging.getLogger(__name__)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def create_checkout_session(request):
    price_id = request.POST.get("price_id")
    organization_id = request.user.employee_of_organization.id
    try:
        checkout_session = create_session(
            price_id=price_id, organization_id=organization_id
        )

    except Exception as e:
        logger.error(f"Create checkout failed: {e}")
        return Response(status=500, data={"error": e}, exception=True)

    return redirect(checkout_session.url)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def capture_payment_status(request):
    event = parse_webhook(request)

    if event.error:
        return Response(status=400, data={"error": event.error}, exception=True)

    if event.type in [
        "checkout.session.completed",
        "invoice.paid",
        "invoice.payment_failed",
    ]:
        try:
            create_or_update_subscription(subscription_data=event.data)
            logger.info(f"{event.type} received and saved")

        except Exception as e:
            logger.error(f"Error while treating {event.type}")
            return Response(status=500, data={"error": e}, exception=True)
    else:
        logger.error(f"Unhandled event type {event.data}")

    return Response(status=204)


def create_or_update_subscription(subscription_data: dict):
    organization_id = subscription_data.get("client_reference_id")
    stripe_customer_id = subscription_data.get("customer")
    active = subscription_data.get("status") == "paid"
    items = subscription_data.get("items")
    plan = items.get("data").get("plan").get("id")
    interval = items.get("data").get("plan").get("interval")
    Subscription.objects.create(
        organization_id=organization_id,
        plan=plan,
        interval=interval,
        active=active,
        stripe_customer_id=stripe_customer_id,
        raw_data=subscription_data,
    )
