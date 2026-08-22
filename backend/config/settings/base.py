"""
PongDang (퐁당) — Shared Django settings.
"""

from pathlib import Path

import dj_database_url
from decouple import config
from django.core.exceptions import ImproperlyConfigured

from config.auth_mode import resolve_portfolio_auth_contract
from config.settings.validation import load_production_sso_edge_secret

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config("SECRET_KEY")

DEBUG = False

ALLOWED_HOSTS = []

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "corsheaders",
    "django_filters",
    # Project apps
    "apps.users",
    "apps.spots",
    "apps.conditions",
    "apps.forecasts",
    "apps.content",
    "apps.trips",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
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
        "DIRS": [],
        "APP_DIRS": True,
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

DATABASES = {
    "default": dj_database_url.config(
        default="sqlite:///" + str(BASE_DIR / "db.sqlite3"),
        conn_max_age=600,
    ),
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTH_USER_MODEL = "users.User"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.users.authentication.PortfolioSessionAuthentication",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "apps.trips.throttles.RemoteAddressAnonRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "120/minute",
        "recommendations": "10/minute",
        "authentication": "10/minute",
    },
}

CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:80",
    "http://localhost",
]

LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Public JSON endpoints accept small structured requests only. Keep an
# application-level bound as well as the reverse proxy limit so development or
# a direct internal request cannot allocate an unbounded request body.
DATA_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1_000

# Session authentication is same-origin by default. Split HTTPS deployments
# must opt into exact origins in prod.py and still send a CSRF token.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"

# Git branch is the authentication source of truth. Local checkouts resolve it
# from Git; packaged runtimes receive both canonical variables explicitly.
_portfolio_environment = {
    name: value
    for name in ("PORTFOLIO_BRANCH", "PORTFOLIO_AUTH_MODE", "GITHUB_REF_NAME")
    if (value := config(name, default=None)) is not None
}
_portfolio_auth = resolve_portfolio_auth_contract(
    base_dir=BASE_DIR,
    environment=_portfolio_environment,
    legacy_sso_name="PONGDANG_SSO_ENABLED",
    legacy_sso_value=config("PONGDANG_SSO_ENABLED", default=None),
    build_mode=config("PORTFOLIO_BUILD_AUTH_MODE", default=None),
    build_contract_path=Path("/etc/portfolio-auth-build"),
)
PORTFOLIO_BRANCH = _portfolio_auth.branch
PORTFOLIO_AUTH_MODE = _portfolio_auth.mode
PONGDANG_SSO_ENABLED = _portfolio_auth.sso_enabled
PONGDANG_RUNTIME_ROLE = config("PONGDANG_RUNTIME_ROLE", default="web").strip()
if PONGDANG_RUNTIME_ROLE not in {"web", "worker"}:
    raise ImproperlyConfigured("PONGDANG_RUNTIME_ROLE must be web or worker.")

PONGDANG_SSO_EDGE_SECRET = config("PONGDANG_SSO_EDGE_SECRET", default="")
PONGDANG_SSO_EDGE_SECRET_FILE = config(
    "PONGDANG_SSO_EDGE_SECRET_FILE", default=""
).strip()
if PONGDANG_RUNTIME_ROLE == "worker":
    if PONGDANG_SSO_EDGE_SECRET or PONGDANG_SSO_EDGE_SECRET_FILE:
        raise ImproperlyConfigured(
            "The worker runtime must not receive the portfolio edge secret."
        )
else:
    PONGDANG_SSO_EDGE_SECRET = load_production_sso_edge_secret(
        PONGDANG_SSO_ENABLED,
        PONGDANG_SSO_EDGE_SECRET,
        PONGDANG_SSO_EDGE_SECRET_FILE,
    )
