"""
PongDang (퐁당) — ASGI config.

Exposes the ASGI callable as a module-level variable named ``application``.
"""

import os

from django.core.asgi import get_asgi_application

# Server entry points fail closed when deployment configuration is omitted.
# Local commands use manage.py, which explicitly selects config.settings.dev.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

application = get_asgi_application()
