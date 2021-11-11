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
    if env("DATABASE_URL", None) is None:
        raise Exception("DATABASE_URL environment variable not defined")
    DATABASES = {
        "default": dj_database_url.parse(env("DATABASE_URL")),
    }
    # CACHES = {
    #     "default": {
    #         "BACKEND": "django_redis.cache.RedisCache",
    #         "LOCATION": env("CACHE_URL"),
    #         "OPTIONS": {
    #             "CLIENT_CLASS": "django_redis.client.DefaultClient",
    #         },
    #         "KEY_PREFIX": "production",
    #     }
    # }

# ERRORS LOGGING
sentry_sdk.init(
    dsn="https://73519869467d49c9b719cc3bca1309eb@o572238.ingest.sentry.io/5721358",
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
