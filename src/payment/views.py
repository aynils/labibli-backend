import logging

from django.shortcuts import redirect
from rest_framework import permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .provider import create_session, parse_webhook

logger = logging.getLogger(__name__)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def create_checkout_session(request):
    price_id = request.POST.get("price_id")
    user_id = request.user.id
    try:
        checkout_session = create_session(price_id=price_id, user_id=user_id)

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

    if event.type == "checkout.session.completed":
        logger.info("checkout.session.completed")
    elif event.type == "invoice.paid":
        logger.info("invoice.paid")
    elif event.type == "invoice.payment_failed":
        logger.info("invoice.payment_failed")
    else:
        logger.error(f"Unhandled event type {event.data}")

    return Response(status=204)
