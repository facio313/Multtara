"""
PongDang (퐁당) — Development settings.
"""

from .base import *  # noqa: F401, F403

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

CORS_ALLOW_ALL_ORIGINS = False

DATABASES = {
    "default": dj_database_url.config(  # noqa: F405
        default="sqlite:///" + str(BASE_DIR / "db.sqlite3"),  # noqa: F405
        conn_max_age=600,
    ),
}
