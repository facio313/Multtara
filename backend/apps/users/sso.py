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
PORTFOLIO_ROLE_ORDER = ("user", "admin", "chief-admin")
PORTFOLIO_ROLE_RANK = {
    role: rank for rank, role in enumerate(PORTFOLIO_ROLE_ORDER)
}
PORTFOLIO_GRANT_ORDER = (
    "access-react",
    "access-vue",
    "access-dukkeobi",
    "access-ddit-finalproject",
    "access-monitor",
    "access-pilgrimage",
    "access-multtara",
    "access-feelmyrythm",
    "access-garak",
)
PORTFOLIO_V2_MARKER = "portfolio-v2"
MULTTARA_GRANT = "access-multtara"
PORTFOLIO_GROUP_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
SSO_SESSION_SUBJECT_KEY = "portfolio_sso_subject"
SSO_SESSION_ROLE_KEY = "portfolio_sso_role"
SSO_SESSION_APP_ACCESS_KEY = "portfolio_sso_multtara_access"
SSO_LEGACY_SESSION_GROUPS_KEY = "portfolio_sso_groups"


@dataclass(frozen=True, slots=True)
class TrustedSsoIdentity:
    subject: str
    email: str
    display_name: str
    groups: tuple[str, ...]
    grants: tuple[str, ...]
    role: str
    has_app_access: bool


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


def _parse_portfolio_groups(
    raw_groups: str,
) -> tuple[tuple[str, ...], tuple[str, ...], str] | None:
    """Parse exact transitional v1 or canonical app-entitled v2 groups."""

    if raw_groups in {"user", "user,developer"}:
        return (
            ("user", PORTFOLIO_V2_MARKER, MULTTARA_GRANT),
            (MULTTARA_GRANT,),
            "user",
        )
    if raw_groups == "user,developer,admin":
        return (
            ("user", "admin", "chief-admin", PORTFOLIO_V2_MARKER),
            (),
            "chief-admin",
        )

    groups = raw_groups.split(",")
    if (
        any(
            not group or PORTFOLIO_GROUP_PATTERN.fullmatch(group) is None
            for group in groups
        )
        or len(set(groups)) != len(groups)
        or not groups
        or groups[0] != "user"
    ):
        return None

    cursor = 1
    role = "user"
    if cursor < len(groups) and groups[cursor] == "admin":
        role = "admin"
        cursor += 1
        if cursor < len(groups) and groups[cursor] == "chief-admin":
            role = "chief-admin"
            cursor += 1
    if cursor >= len(groups) or groups[cursor] != PORTFOLIO_V2_MARKER:
        return None
    cursor += 1

    raw_grants = groups[cursor:]
    if role == "chief-admin":
        if raw_grants:
            return None
        return tuple(groups), (), role

    grant_indexes = {grant: index for index, grant in enumerate(PORTFOLIO_GRANT_ORDER)}
    previous_index = -1
    grants = []
    for grant in raw_grants:
        grant_index = grant_indexes.get(grant)
        if grant_index is None or grant_index <= previous_index:
            return None
        previous_index = grant_index
        grants.append(grant)
    if MULTTARA_GRANT not in grants:
        return None
    return tuple(groups), tuple(grants), role


def trusted_sso_identity(request) -> TrustedSsoIdentity | None:
    """Return a normalized identity only from the authenticated private edge."""

    if not has_valid_edge_secret(request):
        return None

    raw_subject = request.META.get("HTTP_REMOTE_USER", "")
    raw_email = request.META.get("HTTP_REMOTE_EMAIL", "")
    raw_display_name = request.META.get("HTTP_REMOTE_NAME", "")
    raw_groups = request.META.get("HTTP_REMOTE_GROUPS", "")
    if not all(
        isinstance(value, str)
        for value in (raw_subject, raw_email, raw_display_name, raw_groups)
    ):
        return None

    subject = raw_subject.strip()
    email = raw_email.strip().lower()
    display_name = raw_display_name.strip()
    # Do not silently turn a different opaque subject into the stored one.
    if raw_subject != subject or not subject or not email:
        return None
    if (
        len(raw_groups) > 1024
        or any(ord(character) < 32 or ord(character) == 127 for character in raw_groups)
        or any(
            len(value) > 254
            or any(
                ord(character) < 32 or ord(character) == 127
                for character in value
            )
            for value in (subject, email, display_name)
        )
    ):
        return None
    parsed_groups = _parse_portfolio_groups(raw_groups)
    if parsed_groups is None:
        return None
    groups, grants, role = parsed_groups
    try:
        validate_email(email)
    except ValidationError:
        return None
    return TrustedSsoIdentity(
        subject=subject,
        email=email,
        display_name=display_name,
        groups=groups,
        grants=grants,
        role=role,
        has_app_access=True,
    )


def bind_sso_session(request, identity: TrustedSsoIdentity) -> None:
    request.session.pop(SSO_LEGACY_SESSION_GROUPS_KEY, None)
    request.session[SSO_SESSION_SUBJECT_KEY] = identity.subject
    request.session[SSO_SESSION_ROLE_KEY] = identity.role
    request.session[SSO_SESSION_APP_ACCESS_KEY] = identity.has_app_access


def trusted_session_identity(request, user) -> TrustedSsoIdentity | None:
    """Bind a native session to the current edge subject and central roles."""

    identity = trusted_sso_identity(request)
    if identity is None or identity.subject != user.sso_subject:
        return None
    if request.session.get(SSO_SESSION_SUBJECT_KEY) != identity.subject:
        return None
    if request.session.get(SSO_SESSION_ROLE_KEY) != identity.role:
        return None
    if (
        request.session.get(SSO_SESSION_APP_ACCESS_KEY)
        != identity.has_app_access
    ):
        return None
    return identity


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
