"""
PongDang (퐁당) — Production settings.
"""

import re

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

APPLICATION_BASE_PATH = config("APPLICATION_BASE_PATH", default="").strip()
if APPLICATION_BASE_PATH and not re.fullmatch(
    r"/[A-Za-z0-9._~-]+(?:/[A-Za-z0-9._~-]+)*", APPLICATION_BASE_PATH
):
    raise ImproperlyConfigured(
        "APPLICATION_BASE_PATH must be empty or an absolute URL path without a trailing slash."
    )
FORCE_SCRIPT_NAME = APPLICATION_BASE_PATH or None
STATIC_URL = f"{APPLICATION_BASE_PATH}/static/"

# Unique names avoid collisions with other Django applications on the shared
# bonifacio.work origin. Restrict both cookies to this application's subpath.
SESSION_COOKIE_NAME = "pongdang_sessionid"
CSRF_COOKIE_NAME = "pongdang_csrftoken"
SESSION_COOKIE_PATH = f"{APPLICATION_BASE_PATH}/" if APPLICATION_BASE_PATH else "/"
CSRF_COOKIE_PATH = SESSION_COOKIE_PATH

# Same-origin is the production default. Split deployments must opt in with
# exact HTTPS origins; the parser rejects URL components that are not origins.
CORS_ALLOWED_ORIGINS = parse_production_cors_allowed_origins(
    config("CORS_ALLOWED_ORIGINS", default="")
)
# Exact split-deployment origins may use the same session/CSRF contract as the
# same-origin SPA. Secure cookies and explicit trusted origins are all required;
# configuring CORS alone would otherwise yield a login flow that appears to
# succeed but cannot retain or submit the session cross-site.
CSRF_TRUSTED_ORIGINS = list(CORS_ALLOWED_ORIGINS)
CORS_ALLOW_CREDENTIALS = bool(CORS_ALLOWED_ORIGINS)
if CORS_ALLOWED_ORIGINS:
    SESSION_COOKIE_SAMESITE = "None"
    CSRF_COOKIE_SAMESITE = "None"

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
