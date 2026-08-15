"""Fail-fast validation for production-only settings."""

from __future__ import annotations

import ipaddress
import re
from typing import Any

import dj_database_url
from django.core.exceptions import ImproperlyConfigured


POSTGRESQL_ENGINE = "django.db.backends.postgresql"
_REQUIRED_DATABASE_FIELDS = ("NAME", "USER", "PASSWORD", "HOST")
_HTTPS_ORIGIN_PATTERN = re.compile(
    r"^https://(?P<host>\[[0-9a-f:.]+\]|[a-z0-9.-]+)"
    r"(?::(?P<port>[1-9][0-9]{0,4}))?$",
    re.IGNORECASE,
)


def parse_production_database_url(database_url: str) -> dict[str, Any]:
    """Return a complete PostgreSQL config without exposing credential values."""

    if not isinstance(database_url, str) or not database_url.strip():
        raise ImproperlyConfigured("Production requires DATABASE_URL.")
    try:
        database = dj_database_url.parse(database_url.strip(), conn_max_age=600)
    except (TypeError, ValueError) as exc:
        raise ImproperlyConfigured(
            "Production DATABASE_URL must be a valid PostgreSQL URL."
        ) from exc

    if database.get("ENGINE") != POSTGRESQL_ENGINE:
        raise ImproperlyConfigured(
            "Production DATABASE_URL must use the PostgreSQL engine."
        )
    missing = tuple(
        field
        for field in _REQUIRED_DATABASE_FIELDS
        if not isinstance(database.get(field), str) or not database[field].strip()
    )
    if missing:
        raise ImproperlyConfigured(
            "Production database configuration requires " + ", ".join(missing) + "."
        )
    return database


def parse_production_cors_allowed_origins(value: str) -> list[str]:
    """Return canonical HTTPS origins for an optional split deployment.

    A same-origin deployment supplies an empty value and therefore permits no
    cross-origin browser callers. Error messages intentionally omit rejected
    values so embedded credentials cannot be echoed to logs.
    """

    if not isinstance(value, str):
        raise ImproperlyConfigured(
            "Production CORS_ALLOWED_ORIGINS must be a comma-separated string."
        )

    origins: list[str] = []
    for raw_origin in value.split(","):
        origin = raw_origin.strip()
        if not origin:
            continue

        match = _HTTPS_ORIGIN_PATTERN.fullmatch(origin)
        if match is None:
            raise ImproperlyConfigured(
                "Production CORS_ALLOWED_ORIGINS entries must be canonical HTTPS "
                "origins without credentials, paths, query strings, or fragments."
            )

        raw_host = match.group("host")
        port_text = match.group("port")
        if port_text is not None and int(port_text) > 65_535:
            raise ImproperlyConfigured(
                "Production CORS_ALLOWED_ORIGINS contains an invalid port."
            )

        if raw_host.startswith("["):
            try:
                address = ipaddress.ip_address(raw_host[1:-1])
            except ValueError as exc:
                raise ImproperlyConfigured(
                    "Production CORS_ALLOWED_ORIGINS contains an invalid host."
                ) from exc
            if address.version != 6:
                raise ImproperlyConfigured(
                    "Production CORS_ALLOWED_ORIGINS contains an invalid host."
                )
            canonical_host = f"[{address.compressed}]"
        else:
            host = raw_host.lower()
            if re.fullmatch(r"[0-9.]+", host):
                try:
                    address = ipaddress.ip_address(host)
                except ValueError as exc:
                    raise ImproperlyConfigured(
                        "Production CORS_ALLOWED_ORIGINS contains an invalid host."
                    ) from exc
                if address.version != 4:
                    raise ImproperlyConfigured(
                        "Production CORS_ALLOWED_ORIGINS contains an invalid host."
                    )
                canonical_host = str(address)
            else:
                labels = host.split(".")
                if (
                    len(host) > 253
                    or any(
                        not label
                        or len(label) > 63
                        or label.startswith("-")
                        or label.endswith("-")
                        for label in labels
                    )
                ):
                    raise ImproperlyConfigured(
                        "Production CORS_ALLOWED_ORIGINS contains an invalid host."
                    )
                canonical_host = host

        canonical_port = (
            f":{port_text}" if port_text is not None and port_text != "443" else ""
        )
        canonical_origin = f"https://{canonical_host}{canonical_port}"
        if canonical_origin not in origins:
            origins.append(canonical_origin)

    return origins
