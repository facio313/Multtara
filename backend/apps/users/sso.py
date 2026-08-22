"""Fail-closed portfolio SSO identity binding helpers."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, connection, transaction


User = get_user_model()


@dataclass(frozen=True, slots=True)
class TrustedSsoIdentity:
    subject: str
    email: str
    display_name: str


class SsoIdentityConflict(Exception):
    """The asserted identity cannot be mapped without account ambiguity."""


def has_valid_edge_secret(request) -> bool:
    expected = getattr(settings, "PONGDANG_SSO_EDGE_SECRET", "")
    supplied = request.META.get("HTTP_X_PORTFOLIO_EDGE_SECRET", "")
    if not (
        isinstance(expected, str)
        and expected
        and isinstance(supplied, str)
    ):
        return False
    try:
        return secrets.compare_digest(
            supplied.encode("utf-8"), expected.encode("utf-8")
        )
    except UnicodeError:
        return False


def trusted_sso_identity(request) -> TrustedSsoIdentity | None:
    """Return a normalized identity only from the authenticated private edge."""

    if not has_valid_edge_secret(request):
        return None

    raw_subject = request.META.get("HTTP_REMOTE_USER", "")
    raw_email = request.META.get("HTTP_REMOTE_EMAIL", "")
    raw_display_name = request.META.get("HTTP_REMOTE_NAME", "")
    if not all(
        isinstance(value, str) for value in (raw_subject, raw_email, raw_display_name)
    ):
        return None

    subject = raw_subject.strip()
    email = raw_email.strip().lower()
    display_name = raw_display_name.strip()
    # Do not silently turn a different opaque subject into the stored one.
    if raw_subject != subject or not subject or not email:
        return None
    if any(
        len(value) > 254
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        for value in (subject, email, display_name)
    ):
        return None
    try:
        validate_email(email)
    except ValidationError:
        return None
    return TrustedSsoIdentity(
        subject=subject,
        email=email,
        display_name=display_name,
    )


def request_matches_sso_user(request, user) -> bool:
    """Bind an existing Django session to its current trusted edge subject."""

    if not has_valid_edge_secret(request):
        return False
    raw_subject = request.META.get("HTTP_REMOTE_USER", "")
    return bool(
        isinstance(raw_subject, str) and raw_subject and raw_subject == user.sso_subject
    )


def _acquire_postgresql_identity_locks(identity: TrustedSsoIdentity) -> None:
    """Serialize first-time subject/email bindings, including absent rows."""

    if connection.vendor != "postgresql":
        return
    lock_keys = set()
    for namespace, value in (
        ("subject", identity.subject),
        ("email", identity.email),
        ("username", identity.subject.casefold()),
    ):
        digest = sha256(f"pongdang-sso:{namespace}:{value}".encode()).digest()
        lock_keys.add(int.from_bytes(digest[:8], byteorder="big", signed=True))
    with connection.cursor() as cursor:
        for lock_key in sorted(lock_keys):
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_key])


def _username_is_available(candidate: str) -> bool:
    try:
        UnicodeUsernameValidator()(candidate)
    except ValidationError:
        return False
    return not User.objects.filter(username__iexact=candidate).exists()


def _new_sso_username(subject: str) -> str:
    """Choose a username without ever treating a collision as an identity."""

    max_length = User._meta.get_field("username").max_length
    if len(subject) <= max_length and _username_is_available(subject):
        return subject

    base = re.sub(r"[^\w.@+-]+", "-", subject, flags=re.UNICODE).strip("-.")
    base = base or "sso-user"
    digest = sha256(subject.encode()).hexdigest()
    for attempt in range(100):
        suffix = digest[:12] if attempt == 0 else f"{digest[:9]}-{attempt:02d}"
        candidate = f"{base[: max_length - len(suffix) - 1]}-{suffix}"
        if _username_is_available(candidate):
            return candidate
    raise SsoIdentityConflict


def _resolve_sso_user_once(identity: TrustedSsoIdentity):
    _acquire_postgresql_identity_locks(identity)

    subject_user = (
        User.objects.select_for_update().filter(sso_subject=identity.subject).first()
    )
    email_users = list(
        User.objects.select_for_update()
        .filter(email__iexact=identity.email)
        .order_by("pk")[:3]
    )

    if subject_user is not None:
        if (
            subject_user.email.lower() != identity.email
            or len(email_users) != 1
            or email_users[0].pk != subject_user.pk
        ):
            raise SsoIdentityConflict
        if subject_user.has_usable_password():
            subject_user.set_unusable_password()
            subject_user.save(update_fields=("password",))
        return subject_user

    if len(email_users) > 1:
        raise SsoIdentityConflict
    if len(email_users) == 1:
        user = email_users[0]
        if user.sso_subject is not None:
            raise SsoIdentityConflict
        user.sso_subject = identity.subject
        user.set_unusable_password()
        user.save(update_fields=("sso_subject", "password"))
        return user

    user = User(
        username=_new_sso_username(identity.subject),
        email=identity.email,
        sso_subject=identity.subject,
    )
    if identity.display_name:
        user.first_name = identity.display_name[:150]
    user.set_unusable_password()
    user.save(force_insert=True)
    return user


def resolve_sso_user(identity: TrustedSsoIdentity):
    """Resolve, one-time link, or create an SSO user without fuzzy matching."""

    # A unique subject/username race is retried once so the winner can be
    # resolved and all subject/email conflict checks are applied to it.
    for attempt in range(2):
        try:
            with transaction.atomic():
                return _resolve_sso_user_once(identity)
        except IntegrityError as exc:
            if attempt == 1:
                raise SsoIdentityConflict from exc
    raise SsoIdentityConflict
