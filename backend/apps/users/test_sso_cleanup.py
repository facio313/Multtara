import io
import json
from datetime import timedelta

from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Group
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.spots.models import WaterSpot
from apps.users.models import EcoAction, User, UserActivity
from apps.users.permissions import IsPortfolioAdmin, IsPortfolioDeveloper
from apps.users.sso import TrustedSsoIdentity


@override_settings(PONGDANG_SSO_ENABLED=True)
class PortfolioRolePermissionTests(TestCase):
    def _request(self, *, role, groups, is_staff=False, is_superuser=False):
        index = User.objects.count()
        user = User.objects.create_user(
            username=f"role-{role}-{index}",
            email=f"role-{index}@example.test",
            password=None,
            is_staff=is_staff,
            is_superuser=is_superuser,
            sso_subject=f"subject-{index}",
        )
        request = APIRequestFactory().get("/")
        force_authenticate(request, user=user)
        request.user = user
        request.portfolio_sso_identity = TrustedSsoIdentity(
            subject=user.sso_subject,
            email=user.email,
            display_name="",
            groups=groups,
            role=role,
        )
        return request

    def test_central_roles_are_hierarchical_and_ignore_local_staff_flags(self):
        developer = self._request(
            role="developer", groups=("user", "developer")
        )
        self.assertTrue(IsPortfolioDeveloper().has_permission(developer, None))
        self.assertFalse(IsPortfolioAdmin().has_permission(developer, None))

        user_with_legacy_staff = self._request(
            role="user",
            groups=("user",),
            is_staff=True,
            is_superuser=True,
        )
        self.assertFalse(
            IsPortfolioDeveloper().has_permission(user_with_legacy_staff, None)
        )

    @override_settings(PONGDANG_SSO_ENABLED=False)
    def test_local_branch_retains_django_staff_and_superuser_mapping(self):
        local_staff = self._request(
            role="user",
            groups=("user",),
            is_staff=True,
        )
        local_admin = self._request(
            role="user",
            groups=("user",),
            is_staff=True,
            is_superuser=True,
        )
        self.assertTrue(IsPortfolioDeveloper().has_permission(local_staff, None))
        self.assertFalse(IsPortfolioAdmin().has_permission(local_staff, None))
        self.assertTrue(IsPortfolioAdmin().has_permission(local_admin, None))


@override_settings(PONGDANG_SSO_ENABLED=True)
class SsoLegacyCleanupCommandTests(TestCase):
    canonical_subject = "cks"

    def setUp(self):
        self.canonical = User.objects.create_user(
            username="canonical",
            email="canonical@example.test",
            password="legacy-password",
            sso_subject=self.canonical_subject,
            is_staff=True,
            is_superuser=True,
        )
        self.legacy = User.objects.create_user(
            username="legacy",
            email="legacy@example.test",
            password="legacy-password",
        )
        Group.objects.create(name="local-operator").user_set.add(self.canonical)
        self.spot = WaterSpot.objects.create(
            type="beach",
            name="Cleanup beach",
            lat=37.8,
            lng=128.9,
            region="Gangwon",
            address="Gangneung",
        )
        UserActivity.objects.create(
            user=self.legacy,
            spot=self.spot,
            action=UserActivity.Action.VISIT,
        )
        EcoAction.objects.create(
            user=self.canonical,
            spot=self.spot,
            action_type=EcoAction.ActionType.CLEANUP,
            occurred_on=timezone.localdate(),
            state=EcoAction.VerificationState.VERIFIED,
            verified_at=timezone.now(),
            verified_by=self.legacy,
        )
        LogEntry.objects.create(
            user=self.legacy,
            content_type=None,
            object_id="",
            object_repr="retained audit",
            action_flag=1,
            change_message="",
        )
        Session.objects.create(
            session_key="legacy-session",
            session_data="",
            expire_date=timezone.now() + timedelta(days=1),
        )

    def _command(self, *arguments):
        output = io.StringIO()
        call_command(
            "cleanup_sso_legacy_auth",
            "--canonical-subject",
            self.canonical_subject,
            *arguments,
            stdout=output,
            verbosity=0,
        )
        return json.loads(output.getvalue())

    def test_default_is_aggregate_dry_run(self):
        report = self._command()
        self.assertEqual(report["users"]["legacy_unlinked"], 1)
        self.assertEqual(report["migration"]["domain_rows_to_reassign"], 2)
        self.assertEqual(report["migration"]["audit_rows_to_reassign"], 0)
        self.assertEqual(
            report["ownership_projection"]["users.UserActivity.user"][
                "legacy_rows_to_reassign"
            ],
            1,
        )
        self.assertTrue(User.objects.filter(pk=self.legacy.pk).exists())
        self.assertEqual(UserActivity.objects.get().user_id, self.legacy.pk)

    def test_apply_is_atomic_idempotent_and_preserves_subject_ownership(self):
        applied = self._command(
            "--apply",
            "--expected-legacy-users",
            "1",
            "--expected-domain-rows",
            "2",
        )
        self.assertTrue(applied["applied"])
        self.assertEqual(
            applied["locked_before"]["migration"]["legacy_users_to_delete"], 1
        )
        self.assertEqual(applied["legacy_users_deleted"], 1)
        self.assertEqual(
            applied["domain_rows_reassigned"]["users.UserActivity.user"], 1
        )
        self.assertEqual(
            applied["domain_rows_reassigned"]["users.EcoAction.verified_by"], 1
        )
        self.assertEqual(applied["audit_rows_reassigned"], {})
        self.assertEqual(
            applied["local_auth_deleted"]["django_admin_log_entries_deleted"],
            1,
        )
        self.assertFalse(User.objects.filter(pk=self.legacy.pk).exists())
        self.canonical.refresh_from_db()
        self.assertFalse(self.canonical.has_usable_password())
        self.assertFalse(self.canonical.is_staff)
        self.assertFalse(self.canonical.is_superuser)
        activity = UserActivity.objects.get()
        self.assertEqual(activity.user_id, self.canonical.pk)
        self.assertEqual(activity.user.ownership_subject, self.canonical_subject)
        eco_action = EcoAction.objects.get()
        self.assertEqual(eco_action.verified_by_id, self.canonical.pk)
        eco_action.full_clean()
        self.assertFalse(LogEntry.objects.exists())

        repeated = self._command(
            "--apply",
            "--expected-legacy-users",
            "0",
            "--expected-domain-rows",
            "0",
        )
        self.assertEqual(repeated["before"]["users"]["legacy_unlinked"], 0)
        self.assertEqual(repeated["after"]["migration"]["domain_rows_to_reassign"], 0)
        self._command("--check")

    def test_apply_requires_the_reviewed_aggregate_counts(self):
        with self.assertRaises(CommandError):
            self._command("--apply")
        with self.assertRaises(CommandError):
            self._command(
                "--apply",
                "--expected-legacy-users",
                "1",
                "--expected-domain-rows",
                "999",
            )
        self.assertTrue(User.objects.filter(pk=self.legacy.pk).exists())
        self.assertEqual(UserActivity.objects.get().user_id, self.legacy.pk)

    @override_settings(PONGDANG_SSO_ENABLED=False)
    def test_cleanup_is_never_available_in_local_mode(self):
        with self.assertRaises(CommandError):
            self._command()
