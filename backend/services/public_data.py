"""
Shared data.go.kr HTTP client.

Service keys may already be URL-encoded. They are unquoted once, then
requests encodes them a single time.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import unquote

import requests
from decouple import Config, RepositoryEnv, config as fallback_config
from django.core.cache import cache

DEFAULT_TIMEOUT = 12

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_ENV_CANDIDATES = (_BACKEND_DIR / ".env", _BACKEND_DIR.parent / ".env")


def _env_config():
    for candidate in _ENV_CANDIDATES:
        if candidate.exists():
            return Config(RepositoryEnv(str(candidate)))
    return fallback_config


config = _env_config()


class PublicDataError(Exception):
    """Raised when a public API is missing a key, HTTP fails, or the payload is unusable."""


def resolve_service_key(*env_names: str) -> str:
    names = env_names + ("DATA_GO_KR_SERVICE_KEY",)
    for name in names:
        raw = config(name, default="").strip()
        if raw:
            return unquote(raw)
    return ""


def require_service_key(*env_names: str) -> str:
    key = resolve_service_key(*env_names)
    if not key:
        joined = ", ".join(env_names) or "DATA_GO_KR_SERVICE_KEY"
        raise PublicDataError(f"Missing API key ({joined} or DATA_GO_KR_SERVICE_KEY).")
    return key


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


SUCCESS_CODES = {"00", "0000", "0", "NORMAL", "NORMAL_SERVICE"}
HINTS = {
    "12": "오픈API 서비스가 없거나 폐기되었습니다. TourAPI는 KorService2를 사용합니다.",
    "30": "data.go.kr에서 해당 API 활용신청이 되어 있지 않습니다.",
    "41": "해당 관측 항목이 일시적으로 없습니다.",
}


def _header_from(payload: dict) -> dict:
    openapi = payload.get("OpenAPI_ServiceResponse")
    if isinstance(openapi, dict) and isinstance(openapi.get("cmmMsgHeader"), dict):
        return openapi["cmmMsgHeader"]
    response = payload.get("response")
    if isinstance(response, dict) and isinstance(response.get("header"), dict):
        return response["header"]
    if isinstance(payload.get("header"), dict):
        return payload["header"]
    return {}


def _rows_from_body(body: Any) -> list[dict]:
    if not isinstance(body, dict):
        return []
    items = body.get("items")
    if isinstance(items, dict):
        return [row for row in _as_list(items.get("item")) if isinstance(row, dict)]
    if isinstance(items, list):
        return [row for row in items if isinstance(row, dict)]
    return []


def _header_message(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    header = _header_from(payload)
    return str(
        header.get("returnAuthMsg")
        or header.get("resultMsg")
        or header.get("errMsg")
        or payload.get("resultMsg")
        or payload.get("errMsg")
        or ""
    )


def result_code(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    header = _header_from(payload)
    code = (
        header.get("returnReasonCode")
        or header.get("resultCode")
        or header.get("returnAuthMsg")
    )
    if code is not None:
        return str(code)
    if payload.get("resultCode") is not None:
        return str(payload.get("resultCode"))
    result = payload.get("result")
    if isinstance(result, dict) and result.get("resultCode") is not None:
        return str(result.get("resultCode"))
    return None


def iter_records(payload: Any) -> list[dict]:
    """Pull item/data rows out of KMA, TourAPI, and KHOA envelopes."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []

    response = payload.get("response")
    if isinstance(response, dict):
        rows = _rows_from_body(response.get("body"))
        if rows:
            return rows

    rows = _rows_from_body(payload.get("body"))
    if rows:
        return rows

    result = payload.get("result")
    if isinstance(result, dict):
        data = result.get("data") or result.get("item") or result.get("items")
        rows = [row for row in _as_list(data) if isinstance(row, dict)]
        if rows:
            return rows

    for key in ("data", "item", "items"):
        if key in payload:
            value = payload.get(key)
            if isinstance(value, dict) and "item" in value:
                rows = [row for row in _as_list(value.get("item")) if isinstance(row, dict)]
            else:
                rows = [row for row in _as_list(value) if isinstance(row, dict)]
            if rows:
                return rows

    return []


def get_json(
    url: str,
    params: dict[str, Any],
    *,
    service_key: str,
    cache_key: str | None = None,
    ttl: int | None = None,
    extra_params: dict[str, Any] | None = None,
) -> Any:
    if cache_key and ttl:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    query = dict(params)
    if extra_params:
        query.update(extra_params)
    query["serviceKey"] = service_key

    try:
        response = requests.get(url, params=query, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as exc:
        raise PublicDataError(f"HTTP error for {url}: {exc}") from exc

    payload: Any = None
    try:
        payload = response.json()
    except ValueError:
        payload = None

    code = result_code(payload) if payload is not None else None
    if code and code not in SUCCESS_CODES:
        message = _header_message(payload)
        hint = HINTS.get(code, "")
        raise PublicDataError(
            f"API error {code} for {url}: {message} {hint}".strip()
        )

    if payload is None:
        snippet = response.text[:180].replace("\n", " ")
        if not response.ok:
            raise PublicDataError(f"HTTP {response.status_code} for {url}: {snippet}")
        raise PublicDataError(f"Non-JSON response from {url}: {snippet}")

    if not response.ok:
        raise PublicDataError(f"HTTP {response.status_code} for {url}")

    if cache_key and ttl:
        cache.set(cache_key, payload, ttl)
    return payload
