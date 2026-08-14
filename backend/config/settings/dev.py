"""
PongDang (퐁당) — Development settings.
"""

from .base import *  # noqa: F401, F403

DEBUG = True

ALLOWED_HOSTS = ["*"]

CORS_ALLOW_ALL_ORIGINS = True

DATABASES = {
    "default": dj_database_url.config(  # noqa: F405
        default="sqlite:///" + str(BASE_DIR / "db.sqlite3"),  # noqa: F405
        conn_max_age=600,
    ),
}
