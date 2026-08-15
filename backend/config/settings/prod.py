"""
PongDang (퐁당) — Production settings.
"""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401, F403

DEBUG = False

SECRET_KEY = config("SECRET_KEY", default="").strip()  # noqa: F405
if (
    len(SECRET_KEY) < 50
    or SECRET_KEY.startswith("django-insecure-")
    or "change" in SECRET_KEY.lower()
):
    raise ImproperlyConfigured(
        "Production requires a random SECRET_KEY of at least 50 characters."
    )

ALLOWED_HOSTS = [  # noqa: F405
    host.strip()
    for host in config("ALLOWED_HOSTS", default="").split(",")  # noqa: F405
    if host.strip()
]
if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "Production requires explicit ALLOWED_HOSTS and does not allow '*'."
    )

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = "DENY"
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)  # noqa: F405
