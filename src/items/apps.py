from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ItemsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "src.items"
    verbose_name = _("Items")
