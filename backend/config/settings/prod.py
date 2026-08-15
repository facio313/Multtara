"""
PongDang (퐁당) — Production settings.
"""

from decouple import config
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401, F403
from .validation import (
    parse_production_cors_allowed_origins,
    parse_production_database_url,
)

DEBUG = False

SECRET_KEY = config("SECRET_KEY", default="").strip()
if (
    len(SECRET_KEY) < 50
    or SECRET_KEY.startswith("django-insecure-")
    or "change" in SECRET_KEY.lower()
):
    raise ImproperlyConfigured(
        "Production requires a random SECRET_KEY of at least 50 characters."
    )

DATABASE_URL = config("DATABASE_URL", default="").strip()
DATABASES = {
    "default": parse_production_database_url(DATABASE_URL),
}

ALLOWED_HOSTS = [  # noqa: F405
    host.strip()
    for host in config("ALLOWED_HOSTS", default="").split(",")
    if host.strip()
]
if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "Production requires explicit ALLOWED_HOSTS and does not allow '*'."
    )

# Same-origin is the production default. Split deployments must opt in with
# exact HTTPS origins; the parser rejects URL components that are not origins.
CORS_ALLOWED_ORIGINS = parse_production_cors_allowed_origins(
    config("CORS_ALLOWED_ORIGINS", default="")
)

# This table predates the evidence-backed condition pipeline and may contain
# seed/demo values. Keep its public API closed in production even when rows
# remain available to development, tests, or the Django admin.
PUBLIC_LEGACY_WATER_FORECASTS = False

MIDDLEWARE.insert(  # noqa: F405
    MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1,  # noqa: F405
    "whitenoise.middleware.WhiteNoiseMiddleware",
)

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = "DENY"
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
