import sys

import dj_database_url
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

from .base import *  # noqa
from .base import env

DEBUG = True
DJANGO_ENV = "PRODUCTION"

ALLOWED_HOSTS = ["app.qiiro.eu", "webapp-production-9j96q.ondigitalocean.app"]

SMARTDOCS_API_BASE_PATH = "https://api.qiiro.eu"

if (
    len(sys.argv) > 0 and sys.argv[1] != "collectstatic"
):  # do not set cache and DB for static collection job
    DATABASES = {
        "default": dj_database_url.parse(env("DATABASE_URL")),
    }


# ERRORS LOGGING
sentry_sdk.init(
    dsn="https://36ffea1b29ac488ea1992ed6e43eb500@o413315.ingest.sentry.io/5973618",
    integrations=[DjangoIntegration()],
    environment=DJANGO_ENV,
    # Set traces_sample_rate to 1.0 to capture 100%
    # of transactions for performance monitoring.
    # We recommend adjusting this value in production.
    traces_sample_rate=0.01,
    # If you wish to associate users to errors (assuming you are using
    # django.contrib.auth) you may enable sending PII data.
    send_default_pii=True,
)

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

# Store images on Digital Ocean S3
DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
AWS_S3_REGION_NAME = "sfo3"
AWS_S3_ENDPOINT_URL = f"https://{AWS_S3_REGION_NAME}.digitaloceanspaces.com"
AWS_ACCESS_KEY_ID = "BGLZPAXQMT7H2HGFREQI"
AWS_SECRET_ACCESS_KEY = env("DIGITAL_OCEAN_SECRET_ACCESS_KEY")
AWS_STORAGE_BUCKET_NAME = "labibli-s3"


# Transactional emails
EMAIL_BACKEND = "postmarker.django.EmailBackend"
DEFAULT_FROM_EMAIL = "no-reply@labibli.com"
POSTMARK = {
    "TOKEN": env("POSTMARK_API_KEY"),
    "TEST_MODE": False,
    "VERBOSITY": 0,
}


# Auth email config
EMAIL_FROM = "seraphin@aynils.ca"
EMAIL_BCC = "seraphin@aynils.ca"

EMAIL_HOST = "smtp.postmarkapp.com"
EMAIL_PORT = "587"
EMAIL_HOST_USER = env("POSTMARK_API_KEY")
EMAIL_HOST_PASSWORD = env("POSTMARK_API_KEY")
EMAIL_USE_TLS = True
EMAIL_USE_SSL = False
