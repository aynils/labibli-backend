import os
from pathlib import Path

import environ

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent
APPS_DIR = BASE_DIR / "src"

env = environ.Env()

# Set the config base directory
CONFIG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Take environment variables from .env file
environ.Env.read_env(os.path.join(CONFIG_DIR, ".env"))

SECRET_KEY = env("DJANGO_SECRET_KEY")


CORS_ALLOWED_ORIGINS = ["http://localhost:3000"]


DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "authemail",
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
]

LOCAL_APPS = [
    "src.accounts.apps.AccountsConfig",
    "src.labibli.apps.LaBibliConfig",
    "src.customers.apps.CustomersConfig",
    "src.items.apps.ItemsConfig",
    "src.payment.apps.PaymentConfig",
    "src.scripts.apps.ScriptsConfig",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [str(APPS_DIR / "templates")],
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Transactional emails
EMAIL_BACKEND = "postmarker.django.EmailBackend"
DEFAULT_FROM_EMAIL = "no-reply@labibli.com"
POSTMARK = {
    "TOKEN": env("AUTHEMAIL_EMAIL_HOST_USER"),
    "TEST_MODE": False,
    "VERBOSITY": 0,
}


# Password validation
# https://docs.djangoproject.com/en/3.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# User Model
AUTH_USER_MODEL = "accounts.User"

# Internationalization
# https://docs.djangoproject.com/en/3.1/topics/i18n/

LANGUAGE_CODE = "fr-fr"

TIME_ZONE = "UTC"

USE_I18N = True

USE_L10N = True

USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "static/")

MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media/")

# Store images on Digital Ocean S3
DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
AWS_S3_REGION_NAME = env("DIGITAL_OCEAN_REGION_NAME")
AWS_S3_ENDPOINT_URL = f"https://{AWS_S3_REGION_NAME}.digitaloceanspaces.com"
AWS_ACCESS_KEY_ID = env("DIGITAL_OCEAN_KEY_ID")
AWS_SECRET_ACCESS_KEY = env("DIGITAL_OCEAN_SECRET_ACCESS_KEY")
AWS_STORAGE_BUCKET_NAME = env("DIGITAL_OCEAN_STORAGE_BUCKET_NAME")

REST_FRAMEWORK = {
    # Use Django's standard `django.contrib.auth` permissions,
    # or allow read-only access for unauthenticated users.
    "DEFAULT_PERMISSION_CLASSES": [
        # 'rest_framework.permissions.DjangoModelPermissionsOrAnonReadOnly',
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.TokenAuthentication",
    ),
    "DEFAULT_PARSER_CLASSES": (
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ),
    "TEST_REQUEST_DEFAULT_FORMAT": "multipart",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
}

AUTH_EMAIL_VERIFICATION = True

# Email settings
# https://docs.djangoproject.com/en/3.1/topics/email/
# https://docs.djangoproject.com/en/3.1/ref/settings/#email-host

EMAIL_FROM = os.environ.get("AUTHEMAIL_DEFAULT_EMAIL_FROM")
EMAIL_BCC = os.environ.get("AUTHEMAIL_DEFAULT_EMAIL_BCC")

EMAIL_HOST = os.environ.get("AUTHEMAIL_EMAIL_HOST")
EMAIL_PORT = os.environ.get("AUTHEMAIL_EMAIL_PORT")
EMAIL_HOST_USER = os.environ.get("AUTHEMAIL_EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.environ.get("AUTHEMAIL_EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = True
EMAIL_USE_SSL = False
