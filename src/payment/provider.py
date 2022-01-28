import logging
from dataclasses import dataclass

import stripe
from django.conf import settings

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_PRIVATE_KEY
STRIPE_WEBHOOK_KEY = settings.STRIPE_WEBHOOK_KEY


@dataclass
class PaymentEvent:
    type: str
    data: dict
    error: str = ""


def create_session(price_id: str, organization_id: int, user_email: str):
    return stripe.checkout.Session.create(
        line_items=[
            {
                "price": price_id,
                "quantity": 1,
            },
        ],
        mode="subscription",
        success_url=f"{settings.FRONTEND_URL}/account/success",
        cancel_url=f"{settings.FRONTEND_URL}/account/error",
        client_reference_id=organization_id,
        customer_email=user_email,
        allow_promotion_codes=True,
        automatic_tax={"enabled": True},
    )


def parse_webhook(request) -> PaymentEvent:
    signature = request.headers.get("stripe-signature")
    try:
        event = stripe.Webhook.construct_event(
            payload=request.body, sig_header=signature, secret=STRIPE_WEBHOOK_KEY
        )
        data = event["data"]

    except Exception as e:
        logger.error(f"stripe.Webhook.construct_event failed: {e}")
        return PaymentEvent(type="error", error=str(e), data={})

    return PaymentEvent(type=event["type"], data=data["object"])
