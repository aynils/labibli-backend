from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ScriptsConfig(AppConfig):
    name = "src.scripts"
    verbose_name = _("Scripts")
