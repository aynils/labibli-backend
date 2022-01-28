import logging
import time

from rest_framework import permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import Subscription
from .provider import create_session, parse_webhook

logger = logging.getLogger(__name__)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def create_checkout_session(request):
    price_id = request.data.get("priceId")
    organization_id = request.user.employee_of_organization.id
    user_email = request.user.email
    try:
        checkout_session = create_session(
            price_id=price_id, organization_id=organization_id, user_email=user_email
        )

    except Exception as e:
        logger.error(f"Create checkout failed: {e}")
        return Response(status=500, data={"error": e}, exception=True)

    return Response(status=200, data={"url": checkout_session.url})


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def capture_payment_status(request):
    event = parse_webhook(request)

    if event.error:
        return Response(status=400, data={"error": event.error}, exception=True)

    if event.type in [
        "checkout.session.completed",
    ]:
        try:
            create_subscription(checkout_data=event.data)
            logger.info(f"{event.type} received and saved")

        except Exception as e:
            logger.error(f"Error while creating subscription for {event.type} - {e}")
            return Response(status=500, data={"error": e}, exception=True)

    elif event.type in [
        "invoice.paid",
        "invoice.payment_failed",
    ]:
        try:
            update_subscription(invoice_data=event.data)
            logger.info(f"{event.type} received and saved")

        except Exception as e:
            logger.error(f"Error while updating subscription for {event.type} - {e}")
            return Response(status=500, data={"error": e}, exception=True)
    else:
        logger.error(f"Unhandled event type {event.data}")

    return Response(status=204)


def create_subscription(checkout_data: dict):
    organization_id = checkout_data.get("client_reference_id")
    stripe_customer_id = checkout_data.get("customer")
    Subscription.objects.create(
        organization_id=organization_id,
        stripe_customer_id=stripe_customer_id,
        raw_data=checkout_data,
    )


def update_subscription(invoice_data: dict):
    stripe_customer_id = invoice_data.get("customer")
    active = invoice_data.get("status") == "paid"
    lines = invoice_data.get("lines")
    plan = lines.get("data")[0].get("plan").get("id")
    interval = lines.get("data")[0].get("plan").get("interval")

    subscription = False
    retry = 0
    while not subscription and retry < 30:
        try:
            subscription = Subscription.objects.get(
                stripe_customer_id=stripe_customer_id
            )
        except Subscription.DoesNotExist:
            retry += 1
            time.sleep(1)

    subscription.plan = plan
    subscription.interval = interval
    subscription.active = active
    subscription.plan = plan
    subscription.raw_data = invoice_data

    subscription.save()
