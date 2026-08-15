"""Credential-free URL projection for public API payloads."""

from __future__ import annotations

import ipaddress
from typing import Any
from urllib.parse import urlsplit, urlunsplit


def public_https_url(value: Any) -> str:
    """Return a query-free public HTTPS URL, or an empty string.

    Provider credentials commonly appear in URL query strings. Public payloads
    do not need those queries, fragments, userinfo, non-standard ports, or local
    network destinations.
    """

    if not isinstance(value, str) or not value.strip() or "\\" in value:
        return ""
    try:
        parsed = urlsplit(value.strip())
        hostname = parsed.hostname or ""
        port = parsed.port
    except ValueError:
        return ""
    if (
        parsed.scheme.lower() != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or _is_local_hostname(hostname)
    ):
        return ""
    display_host = f"[{hostname}]" if ":" in hostname else hostname
    return urlunsplit(("https", display_host, parsed.path or "/", "", ""))


def _is_local_hostname(hostname: str) -> bool:
    canonical = hostname.rstrip(".").casefold()
    if canonical in {"localhost", "localhost.localdomain"} or canonical.endswith(
        (".localhost", ".local", ".internal")
    ):
        return True
    try:
        address = ipaddress.ip_address(canonical)
    except ValueError:
        # Require a qualified DNS name. Official/public hosts used by PongDang
        # all have at least one dot; single-label names are local-network prone.
        return "." not in canonical
    return not address.is_global
