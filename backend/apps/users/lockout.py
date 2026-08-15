"""Account lockout keyed by username and client IP."""

from __future__ import annotations

import hashlib

from django.core.cache import cache

MAX_FAILURES_PAIR = 5
MAX_FAILURES_USER = 10
LOCK_SECONDS = 15 * 60


def client_ip(request) -> str:
    return request.META.get("REMOTE_ADDR") or "0.0.0.0"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _pair_key(username: str, ip: str) -> str:
    return f"auth:fail:pair:{_digest(username.casefold() + '|' + ip)}"


def _user_key(username: str) -> str:
    return f"auth:fail:user:{_digest(username.casefold())}"


def is_locked(username: str, ip: str) -> bool:
    pair = cache.get(_pair_key(username, ip)) or 0
    user = cache.get(_user_key(username)) or 0
    return pair >= MAX_FAILURES_PAIR or user >= MAX_FAILURES_USER


def register_failure(username: str, ip: str) -> None:
    pair_key = _pair_key(username, ip)
    user_key = _user_key(username)
    cache.set(pair_key, (cache.get(pair_key) or 0) + 1, LOCK_SECONDS)
    cache.set(user_key, (cache.get(user_key) or 0) + 1, LOCK_SECONDS)


def clear_failures(username: str, ip: str) -> None:
    cache.delete(_pair_key(username, ip))
    cache.delete(_user_key(username))
