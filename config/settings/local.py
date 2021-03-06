import dj_database_url

from .base import *  # noqa
from .base import env

DEBUG = True

DJANGO_ENV = "DEV"

ALLOWED_HOSTS = ["localhost", "432f-134-41-73-182.ngrok.io"]
FRONTEND_URL = "http://localhost:3000"

# CORS_ALLOWED_ORIGINS = [
#     FRONTEND_URL,
#     '*'
# ]


DATABASES = {
    "default": dj_database_url.parse(env("DATABASE_URL")),
}
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": env("DJANGO_LOG_LEVEL", default="INFO"),
            "propagate": False,
        },
    },
}

DEBUG_TOOLBAR_CONFIG = {
    "DISABLE_PANELS": ["debug_toolbar.panels.redirects.RedirectsPanel"],
    "SHOW_TEMPLATE_CONTEXT": True,
}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Store images on Digital Ocean S3
DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
AWS_S3_REGION_NAME = "sfo3"
AWS_S3_ENDPOINT_URL = f"https://{AWS_S3_REGION_NAME}.digitaloceanspaces.com"
AWS_ACCESS_KEY_ID = "BGLZPAXQMT7H2HGFREQI"
AWS_SECRET_ACCESS_KEY = env("DIGITAL_OCEAN_SECRET_ACCESS_KEY")
AWS_STORAGE_BUCKET_NAME = "labibli-s3"


# Auth email config
EMAIL_FROM = "contact@labibli.com"
EMAIL_BCC = "seraphin@aynils.ca"

EMAIL_HOST = "smtp.postmarkapp.com"
EMAIL_PORT = "587"
EMAIL_HOST_USER = env("POSTMARK_API_KEY")
EMAIL_HOST_PASSWORD = env("POSTMARK_API_KEY")
EMAIL_USE_TLS = True
EMAIL_USE_SSL = False
