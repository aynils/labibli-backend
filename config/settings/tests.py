"""
With these settings, tests run faster.
"""
import dj_database_url

from .base import *  # noqa
from .base import env

ALLOWED_HOSTS = ["localhost"]

# GENERAL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#secret-key
SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    default="9227ThkXUGW0hRcjLwZ1QriubUgCvjbRQeu15zFV8HEeJ7Dm6sipUA9xQgOb02Hb",
)
# https://docs.djangoproject.com/en/dev/ref/settings/#test-runner
TEST_RUNNER = "django.test.runner.DiscoverRunner"

# PASSWORDS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#password-hashers
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# TEMPLATES
# ------------------------------------------------------------------------------
TEMPLATES[-1]["OPTIONS"]["loaders"] = [  # type: ignore[index] # noqa F405
    (
        "django.template.loaders.cached.Loader",
        [
            "django.template.loaders.filesystem.Loader",
            "django.template.loaders.app_directories.Loader",
        ],
    )
]

# EMAIL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#email-backend
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# `local.py` et `production.py` la définissent déjà ; `base.py`, non. Sans
# elle, tout envoi de courriel lève une AttributeError en test — donc les
# rappels de retard étaient intestables.
EMAIL_FROM = "contact@labibli.com"

# `path_and_rename` (src/items/models.py) nomme le dossier des couvertures à
# partir de cette valeur. Sans elle, TOUT enregistrement d'image lève une
# AttributeError en test — ce qui rendait intestable la moitié de ce qui
# touche aux couvertures.
DJANGO_ENV = "TEST"

# DATABASE
# ------------------------------------------------------------------------------
DATABASES = {
    "default": dj_database_url.parse(env("DATABASE_URL")),
}
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
}
