import json

from django.apps import apps
from django.conf import settings
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import UNUSABLE_PASSWORD_PREFIX
from django.contrib.sessions.models import Session
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.models import Q


User = get_user_model()

OWNERSHIP_FIELDS = (
    ("content.TripMemory", "user"),
    ("users.UserActivity", "user"),
    ("users.Passport", "user"),
    ("users.EcoAction", "user"),
    ("users.EcoAction", "verified_by"),
    ("trips.Itinerary", "user"),
    ("trips.SafetyCard", "user"),
)
PROJECTION_FIELDS = OWNERSHIP_FIELDS
SYSTEM_USER_RELATIONS = {"admin.LogEntry.user"}
FORBIDDEN_OAUTH_APP_ROOTS = {
    "allauth",
    "oauth2_provider",
    "social_django",
}


def _oauth_apps():
    return sorted(
        app
        for app in settings.INSTALLED_APPS
        if app.split(".", 1)[0] in FORBIDDEN_OAUTH_APP_ROOTS
    )


def _ownership_inventory(*, canonical_user, legacy_user_ids):
    ownership = {}
    rows_to_reassign = {"domain": 0, "audit": 0}
    for model_label, field_name in PROJECTION_FIELDS:
        model = apps.get_model(model_label)
        manager = model._base_manager
        legacy_rows = manager.filter(
            **{f"{field_name}_id__in": legacy_user_ids}
        ).count()
        category = "domain" if (model_label, field_name) in OWNERSHIP_FIELDS else "audit"
        rows_to_reassign[category] += legacy_rows
        ownership[f"{model_label}.{field_name}"] = {
            "total_rows": manager.count(),
            "linked_subject_rows": manager.filter(
                **{f"{field_name}__sso_subject__isnull": False}
            ).count(),
            "canonical_subject_rows": manager.filter(
                **{f"{field_name}_id": canonical_user.pk}
            ).count(),
            "legacy_rows_to_reassign": legacy_rows,
        }
    return ownership, rows_to_reassign


def _unclassified_legacy_relations(legacy_user_ids):
    classified = {
        f"{model_label}.{field_name}" for model_label, field_name in PROJECTION_FIELDS
    } | SYSTEM_USER_RELATIONS
    found = {}
    for relation in User._meta.related_objects:
        if relation.many_to_many or relation.related_model._meta.auto_created:
            continue
        key = f"{relation.related_model._meta.label}.{relation.field.name}"
        if key in classified:
            continue
        count = relation.related_model._base_manager.filter(
            **{f"{relation.field.name}_id__in": legacy_user_ids}
        ).count()
        if count:
            found[key] = count
    return dict(sorted(found.items()))


def build_inventory(*, canonical_user):
    legacy_users = User._base_manager.filter(sso_subject__isnull=True)
    legacy_user_ids = legacy_users.values_list("pk", flat=True)
    ownership, rows_to_reassign = _ownership_inventory(
        canonical_user=canonical_user,
        legacy_user_ids=legacy_user_ids,
    )
    unclassified = _unclassified_legacy_relations(legacy_user_ids)
    usable_passwords = User._base_manager.exclude(
        password__startswith=UNUSABLE_PASSWORD_PREFIX
    ).count()
    staff_flags = User._base_manager.filter(
        Q(is_staff=True) | Q(is_superuser=True)
    ).count()
    oauth_apps = _oauth_apps()
    inventory = {
        "users": {
            "total": User._base_manager.count(),
            "linked_subjects": User._base_manager.filter(
                sso_subject__isnull=False
            ).count(),
            "legacy_unlinked": legacy_users.count(),
            "legacy_deletion_candidates_after_projection": legacy_users.count()
            if not unclassified
            else 0,
        },
        "local_auth": {
            "usable_passwords": usable_passwords,
            "staff_or_superuser_flags": staff_flags,
            "group_memberships": User.groups.through.objects.count(),
            "direct_permission_grants": User.user_permissions.through.objects.count(),
            "django_sessions": Session.objects.count(),
            "django_admin_log_entries": LogEntry.objects.count(),
            "oauth_provider_apps": oauth_apps,
            "oauth_credential_rows": 0 if not oauth_apps else None,
        },
        "ownership_projection": ownership,
        "migration": {
            "legacy_users_to_delete": legacy_users.count(),
            "domain_rows_to_reassign": rows_to_reassign["domain"],
            "audit_rows_to_reassign": rows_to_reassign["audit"],
            "unclassified_legacy_relations": unclassified,
        },
    }
    inventory["ready"] = not any(
        (
            inventory["users"]["legacy_unlinked"],
            usable_passwords,
            staff_flags,
            inventory["local_auth"]["group_memberships"],
            inventory["local_auth"]["direct_permission_grants"],
            inventory["local_auth"]["django_sessions"],
            inventory["local_auth"]["django_admin_log_entries"],
            oauth_apps,
            unclassified,
        )
    )
    return inventory


def _lock_and_reassign_ownership(*, canonical_user, legacy_user_ids):
    updated = {}
    for model_label, field_name in PROJECTION_FIELDS:
        model = apps.get_model(model_label)
        queryset = model._base_manager.filter(
            **{f"{field_name}_id__in": legacy_user_ids}
        )
        list(queryset.select_for_update().values_list("pk", flat=True))
        updated[f"{model_label}.{field_name}"] = queryset.update(
            **{f"{field_name}_id": canonical_user.pk}
        )
    return updated


def _lock_cleanup_tables():
    if connection.vendor != "postgresql":
        return
    models = {
        User,
        User.groups.through,
        User.user_permissions.through,
        Session,
        LogEntry,
    }
    models.update(apps.get_model(model_label) for model_label, _ in PROJECTION_FIELDS)
    models.update(
        relation.related_model
        for relation in User._meta.related_objects
        if not relation.related_model._meta.auto_created
    )
    quote_name = connection.ops.quote_name
    with connection.cursor() as cursor:
        for table_name in sorted(model._meta.db_table for model in models):
            cursor.execute(
                f"LOCK TABLE {quote_name(table_name)} IN SHARE ROW EXCLUSIVE MODE"
            )


def _remove_local_auth_state():
    password_users = list(
        User._base_manager.exclude(
            password__startswith=UNUSABLE_PASSWORD_PREFIX
        ).only("pk", "password")
    )
    for user in password_users:
        user.set_unusable_password()
    if password_users:
        User._base_manager.bulk_update(password_users, ("password",), batch_size=500)
    User._base_manager.filter(
        Q(is_staff=True) | Q(is_superuser=True)
    ).update(is_staff=False, is_superuser=False)
    User.groups.through.objects.all().delete()
    User.user_permissions.through.objects.all().delete()
    Session.objects.all().delete()
    admin_log_entries_deleted = LogEntry.objects.count()
    LogEntry.objects.all().delete()
    return {"django_admin_log_entries_deleted": admin_log_entries_deleted}


class Command(BaseCommand):
    help = (
        "Inventory or transactionally project legacy ownership onto one SSO "
        "subject and remove app-local authentication state."
    )

    def add_arguments(self, parser):
        parser.add_argument("--canonical-subject", required=True)
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply the reviewed projection and cleanup transaction.",
        )
        parser.add_argument(
            "--check",
            action="store_true",
            help="Exit non-zero unless no legacy identity or auth state remains.",
        )
        parser.add_argument("--expected-legacy-users", type=int)
        parser.add_argument("--expected-domain-rows", type=int)

    def handle(self, *args, **options):
        if options["apply"] and options["check"]:
            raise CommandError("--apply and --check are mutually exclusive.")
        if options["apply"] and (
            options["expected_legacy_users"] is None
            or options["expected_domain_rows"] is None
        ):
            raise CommandError(
                "--apply requires --expected-legacy-users and --expected-domain-rows."
            )
        if any(
            value is not None and value < 0
            for value in (
                options["expected_legacy_users"],
                options["expected_domain_rows"],
            )
        ):
            raise CommandError("Expected counts must be non-negative.")
        if not settings.PONGDANG_SSO_ENABLED:
            raise CommandError("This command is available only in portfolio SSO mode.")
        if _oauth_apps():
            raise CommandError(
                "An app-local OAuth provider is installed; cleanup is intentionally blocked."
            )

        subject = options["canonical_subject"]
        canonical = User._base_manager.filter(sso_subject=subject).first()
        if canonical is None:
            raise CommandError("The canonical SSO subject does not identify a user.")

        before = build_inventory(canonical_user=canonical)
        if options["check"]:
            self.stdout.write(json.dumps(before, sort_keys=True))
            if not before["ready"]:
                raise CommandError("Legacy app-local authentication state remains.")
            return
        if not options["apply"]:
            self.stdout.write(json.dumps(before, sort_keys=True))
            return

        if before["migration"]["unclassified_legacy_relations"]:
            raise CommandError(
                "Unclassified legacy ownership exists; no cleanup was applied."
            )
        if (
            before["migration"]["legacy_users_to_delete"]
            != options["expected_legacy_users"]
            or before["migration"]["domain_rows_to_reassign"]
            != options["expected_domain_rows"]
        ):
            raise CommandError("The reviewed aggregate no longer matches the database.")

        with transaction.atomic():
            _lock_cleanup_tables()
            canonical = User._base_manager.select_for_update().get(
                sso_subject=subject
            )
            locked_before = build_inventory(canonical_user=canonical)
            if (
                locked_before["migration"]["legacy_users_to_delete"]
                != options["expected_legacy_users"]
                or locked_before["migration"]["domain_rows_to_reassign"]
                != options["expected_domain_rows"]
                or locked_before["migration"]["unclassified_legacy_relations"]
            ):
                raise CommandError(
                    "The locked aggregate differs from the reviewed aggregate; "
                    "no cleanup was applied."
                )
            legacy_user_ids = list(
                User._base_manager.select_for_update()
                .filter(sso_subject__isnull=True)
                .values_list("pk", flat=True)
            )
            unclassified = _unclassified_legacy_relations(legacy_user_ids)
            if unclassified:
                raise CommandError(
                    "Unclassified legacy ownership appeared; no cleanup was applied."
                )
            updated = _lock_and_reassign_ownership(
                canonical_user=canonical,
                legacy_user_ids=legacy_user_ids,
            )
            local_auth_deleted = _remove_local_auth_state()
            deleted_objects = User._base_manager.filter(
                pk__in=legacy_user_ids,
                sso_subject__isnull=True,
            ).delete()[0]

        after = build_inventory(canonical_user=canonical)
        domain_keys = {
            f"{model_label}.{field_name}"
            for model_label, field_name in OWNERSHIP_FIELDS
        }
        self.stdout.write(
            json.dumps(
                {
                    "applied": True,
                    "before": before,
                    "locked_before": locked_before,
                    "after": after,
                    "domain_rows_reassigned": {
                        key: count for key, count in updated.items() if key in domain_keys
                    },
                    "audit_rows_reassigned": {
                        key: count for key, count in updated.items() if key not in domain_keys
                    },
                    "local_auth_deleted": local_auth_deleted,
                    "deleted_objects": deleted_objects,
                    "legacy_users_deleted": len(legacy_user_ids),
                },
                sort_keys=True,
            )
        )
