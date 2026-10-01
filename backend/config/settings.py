"""Django settings. Environment-specific values come from environment variables (see .env.example)."""

from datetime import timedelta
from pathlib import Path

import dj_database_url

from config.env import env_bool, env_list, env_str

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = env_bool("DJANGO_DEBUG", default=False)
SECRET_KEY = env_str("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "apps.core",
    "apps.accounts",
    "apps.catalog",
    "apps.requests_desk",
]

AUTH_USER_MODEL = "accounts.User"

# Argon2id first (OWASP's recommendation). Older PBKDF2 hashes still verify and are re-hashed
# with Argon2id on the next successful login.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

# Applied to new and changed passwords. The seeded demo accounts are created directly, and never in
# production.
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

MIDDLEWARE = [
    "apps.core.middleware.RequestLoggingMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    # Protects any non-API form view. DRF views are exempt by design; the cookie endpoints have their own
    # cross-site check (apps.accounts.views.PublicAuthView).
    "django.middleware.csrf.CsrfViewMiddleware",
]

ROOT_URLCONF = "config.urls"

# Only used to render the Swagger UI page.
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "APP_DIRS": True}]
WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": dj_database_url.parse(
        env_str("DATABASE_URL"),
        conn_max_age=60,
        conn_health_checks=True,
    )
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# One JSON object per line on stdout; the hosting platform collects and indexes it.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"()": "apps.core.logging.JsonFormatter"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json"}},
    "root": {"handlers": ["console"], "level": env_str("LOG_LEVEL", default="INFO")},
    "loggers": {
        # The access log already records every 4xx/5xx; Django's own logger only adds unhandled errors.
        "django.request": {"level": "ERROR"},
    },
}

# API: JSON only, authentication required unless a view opts out (docs/security.md §4).
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.accounts.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.DefaultPagination",
    # Proxies in front of the API (e.g. the hosting load balancer): needed to find the real client IP for
    # throttling. 0 locally, where clients connect directly.
    "NUM_PROXIES": int(env_str("TRUSTED_PROXY_COUNT", default="0")),
}

# Shared by all workers and containers: login throttling counters must not be per process.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache",
    }
}

# Tokens (docs/security.md §3): short-lived access token, rotated refresh token in an HttpOnly cookie.
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=10),
    "REFRESH_TOKEN_LIFETIME": timedelta(hours=12),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": env_str("JWT_SIGNING_KEY"),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}
# Browsers accept Secure cookies on http://localhost, so this stays on everywhere unless explicitly disabled.
AUTH_COOKIE_SECURE = env_bool("AUTH_COOKIE_SECURE", default=True)

# OpenAPI docs at /api/docs/. On by default only in DEBUG: production doesn't publish a map of the API.
API_DOCS_ENABLED = env_bool("API_DOCS_ENABLED", default=DEBUG)
SPECTACULAR_SETTINGS = {
    "TITLE": "Dataset Request Desk API",
    "DESCRIPTION": "Internal API for dataset requests, episodes and fulfilment.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    # One schema name for choice sets used by several fields.
    "ENUM_NAME_OVERRIDES": {"RequestStatus": "apps.requests_desk.models.RequestStatus"},
}

# Episode import uploads (docs/security.md section 2): bounded size, CSV only.
IMPORT_MAX_UPLOAD_BYTES = int(env_str("IMPORT_MAX_UPLOAD_BYTES", default=str(20 * 1024 * 1024)))
