from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from src.payment import views

urlpatterns = [
    path(
        r"create/",
        views.create_checkout_session,
        name="post_create_checkout_session",
    ),
    path(
        r"status/",
        views.capture_payment_status,
        name="post_payment_status",
    ),
]

urlpatterns = format_suffix_patterns(urlpatterns)
