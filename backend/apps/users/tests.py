from datetime import timedelta

from django.core.cache import cache
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.users.admin import EcoActionAdmin
from apps.users.models import EcoAction, Passport, User, UserActivity
from apps.spots.models import WaterSpot


class UserModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="useruser", password="testpassword", persona_type="surfer"
        )
        self.spot = WaterSpot.objects.create(
            type="beach",
            name="Test Surf Beach",
            lat=34.0,
            lng=126.0,
            region="Incheon",
            address="654 Test Ln",
        )

    def test_user_creation(self):
        self.assertEqual(self.user.username, "useruser")
        self.assertEqual(self.user.persona_type, "surfer")

    def test_linked_sso_subject_is_unique_and_immutable(self):
        self.user.sso_subject = "portfolio-subject"
        self.user.save(update_fields=("sso_subject",))

        self.user.sso_subject = "replacement-subject"
        with self.assertRaisesMessage(ValidationError, "immutable"):
            self.user.save(update_fields=("sso_subject",))
        self.user.refresh_from_db()
        self.assertEqual(self.user.sso_subject, "portfolio-subject")

        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                User.objects.filter(pk=self.user.pk).update(
                    sso_subject="bulk-replacement-subject"
                )
        self.user.refresh_from_db()
        self.assertEqual(self.user.sso_subject, "portfolio-subject")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.create_user(
                    username="other-sso-user",
                    sso_subject="portfolio-subject",
                )

    def test_user_activity_creation(self):
        activity = UserActivity.objects.create(
            user=self.user,
            spot=self.spot,
            action="visit",
        )
        self.assertEqual(activity.action, "visit")
        self.assertIsNone(activity.rating)

    def test_passport_creation(self):
        passport = Passport.objects.create(
            user=self.user, spot=self.spot, eco_action="picked up trash"
        )
        self.assertEqual(passport.eco_action, "picked up trash")

    def test_passport_evidence_is_public_and_query_free_at_rest(self):
        with self.assertRaises(ValidationError):
            Passport.objects.create(
                user=self.user,
                spot=self.spot,
                evidence_url="http://127.0.0.1/private?token=secret",
            )
        passport = Passport.objects.create(
            user=self.user,
            spot=self.spot,
            evidence_url="https://evidence.example.org/passport?token=secret#private",
        )
        self.assertEqual(
            passport.evidence_url,
            "https://evidence.example.org/passport",
        )


class EcoActionVerificationIntegrityTests(TestCase):
    def setUp(self):
        self.submitter = User.objects.create_user(
            username="eco-submitter",
            password="strong-test-password",
        )
        self.operator = User.objects.create_user(
            username="eco-operator",
            password="strong-test-password",
            is_staff=True,
        )
        self.other_operator = User.objects.create_user(
            username="other-eco-operator",
            password="strong-test-password",
            is_staff=True,
        )
        self.spot = WaterSpot.objects.create(
            type="beach",
            name="Eco verification beach",
            lat=37.8,
            lng=128.9,
            region="Gangwon",
            address="Gangneung",
        )
        self.action = EcoAction.objects.create(
            user=self.submitter,
            spot=self.spot,
            action_type=EcoAction.ActionType.CLEANUP,
            occurred_on=timezone.localdate(),
        )
        self.admin = EcoActionAdmin(EcoAction, AdminSite())
        self.request = RequestFactory().post("/admin/users/ecoaction/")
        self.request.user = self.operator

    def test_model_and_database_require_verifier_and_time_to_match_state(self):
        self.action.state = EcoAction.VerificationState.VERIFIED
        with self.assertRaises(ValidationError):
            self.action.full_clean()

        self.action.state = EcoAction.VerificationState.PENDING
        self.action.verified_at = timezone.now()
        self.action.verified_by = self.operator
        with self.assertRaises(ValidationError):
            self.action.full_clean()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                EcoAction.objects.bulk_create(
                    [
                        EcoAction(
                            user=self.submitter,
                            action_type=EcoAction.ActionType.REUSABLE,
                            occurred_on=timezone.localdate(),
                            state=EcoAction.VerificationState.VERIFIED,
                            verified_at=timezone.now(),
                            verified_by=None,
                        )
                    ]
                )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                EcoAction.objects.bulk_create(
                    [
                        EcoAction(
                            user=self.submitter,
                            action_type=EcoAction.ActionType.TRANSIT,
                            occurred_on=timezone.localdate(),
                            state=EcoAction.VerificationState.REJECTED,
                            verified_at=timezone.now(),
                            verified_by=self.operator,
                        )
                    ]
                )

    def test_model_normalizes_public_evidence_and_rejects_private_links(self):
        with self.assertRaises(ValidationError):
            EcoAction.objects.create(
                user=self.submitter,
                action_type=EcoAction.ActionType.CLEANUP,
                evidence_url="http://127.0.0.1/private?token=secret",
                occurred_on=timezone.localdate(),
            )
        action = EcoAction.objects.create(
            user=self.submitter,
            action_type=EcoAction.ActionType.CLEANUP,
            evidence_url="https://evidence.example.org/proof?token=secret#private",
            occurred_on=timezone.localdate(),
        )
        self.assertEqual(
            action.evidence_url,
            "https://evidence.example.org/proof",
        )

    def test_admin_transitions_fill_preserve_and_clear_audit_fields_atomically(self):
        self.action.state = EcoAction.VerificationState.VERIFIED
        self.admin.save_model(self.request, self.action, form=None, change=True)
        self.action.refresh_from_db()
        first_verified_at = self.action.verified_at
        self.assertIsNotNone(first_verified_at)
        self.assertEqual(self.action.verified_by, self.operator)
        self.action.full_clean()

        # An unrelated edit by another operator does not reattribute the
        # original verification event.
        second_request = RequestFactory().post("/admin/users/ecoaction/")
        second_request.user = self.other_operator
        self.action.note = "evidence reviewed again"
        self.admin.save_model(second_request, self.action, form=None, change=True)
        self.action.refresh_from_db()
        self.assertEqual(self.action.verified_at, first_verified_at)
        self.assertEqual(self.action.verified_by, self.operator)

        with self.assertRaises(ProtectedError):
            self.operator.delete()

        self.action.state = EcoAction.VerificationState.REJECTED
        self.admin.save_model(second_request, self.action, form=None, change=True)
        self.action.refresh_from_db()
        self.assertIsNone(self.action.verified_at)
        self.assertIsNone(self.action.verified_by)
        self.action.full_clean()


class UserSessionApiTests(TestCase):
    password = "V3ry-Long!Pond-Passphrase-2026"
    sso_edge_secret = "test-only-pongdang-edge-secret-2026"

    def setUp(self):
        cache.clear()
        self.spot = WaterSpot.objects.create(
            type="beach",
            name="계정 테스트 해변",
            lat=37.8,
            lng=128.9,
            region="강릉",
            address="강릉시",
        )

    def _csrf_client(self):
        client = APIClient(enforce_csrf_checks=True)
        response = client.get("/api/v1/users/csrf/")
        self.assertEqual(response.status_code, 200)
        token = response.json()["csrf_token"]
        return client, token

    def _sso_headers(
        self,
        subject="portfolio-owner",
        email="owner@example.test",
        display_name="Portfolio Owner",
    ):
        return {
            "HTTP_REMOTE_USER": subject,
            "HTTP_REMOTE_EMAIL": email,
            "HTTP_REMOTE_NAME": display_name,
            "HTTP_X_PORTFOLIO_EDGE_SECRET": self.sso_edge_secret,
        }

    def test_registration_requires_csrf_and_creates_an_authenticated_session(self):
        client = APIClient(enforce_csrf_checks=True)
        payload = {
            "username": "pond-user",
            "password": self.password,
            "email": "POND@EXAMPLE.COM",
            "preferred_locale": "en",
        }
        rejected = client.post("/api/v1/users/register/", payload, format="json")
        self.assertEqual(rejected.status_code, 403)

        client, token = self._csrf_client()
        created = client.post(
            "/api/v1/users/register/",
            payload,
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(created.status_code, 201)
        self.assertNotIn("password", created.json())
        self.assertEqual(created.json()["email"], "pond@example.com")
        self.assertEqual(client.get("/api/v1/users/me/").status_code, 200)

    @override_settings(
        PONGDANG_SSO_ENABLED=True,
        PONGDANG_SSO_EDGE_SECRET=sso_edge_secret,
    )
    def test_sso_exchange_creates_session_and_disables_local_credentials(self):
        client, token = self._csrf_client()
        missing = client.post(
            "/api/v1/users/sso/",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(missing.status_code, 401)

        exchanged = client.post(
            "/api/v1/users/sso/",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=token,
            **self._sso_headers(),
        )
        self.assertEqual(exchanged.status_code, 200)
        self.assertEqual(exchanged.json()["username"], "portfolio-owner")
        user = User.objects.get(username="portfolio-owner")
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.sso_subject, "portfolio-owner")
        self.assertEqual(
            client.get("/api/v1/users/me/", **self._sso_headers()).status_code,
            200,
        )

        csrf_token = client.cookies["csrftoken"].value
        local_register = client.post(
            "/api/v1/users/register/",
            {
                "username": "other",
                "email": "other@example.test",
                "password": self.password,
            },
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(local_register.status_code, 403)
        self.assertIn("single sign-on", local_register.json()["detail"])
        local_login = client.post(
            "/api/v1/users/login/",
            {"username": "portfolio-owner", "password": self.password},
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(local_login.status_code, 403)
        self.assertIn("single sign-on", local_login.json()["detail"])
        local_password = client.post(
            "/api/v1/users/password/",
            {"current_password": self.password, "new_password": self.password + "-new"},
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
            **self._sso_headers(),
        )
        self.assertEqual(local_password.status_code, 403)
        self.assertIn("single sign-on", local_password.json()["detail"])
        local_delete = client.delete(
            "/api/v1/users/me/",
            {"current_password": self.password},
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
            **self._sso_headers(),
        )
        self.assertEqual(local_delete.status_code, 403)
        self.assertIn("single sign-on", local_delete.json()["detail"])

    @override_settings(
        PONGDANG_SSO_ENABLED=True,
        PONGDANG_SSO_EDGE_SECRET=sso_edge_secret,
    )
    def test_sso_never_claims_a_username_collision(self):
        collision = User.objects.create_user(
            username="portfolio-owner",
            email="different@example.test",
            password=self.password,
        )
        client, token = self._csrf_client()

        exchanged = client.post(
            "/api/v1/users/sso/",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=token,
            **self._sso_headers(),
        )

        self.assertEqual(exchanged.status_code, 200)
        collision.refresh_from_db()
        self.assertIsNone(collision.sso_subject)
        linked = User.objects.get(sso_subject="portfolio-owner")
        self.assertNotEqual(linked.pk, collision.pk)
        self.assertNotEqual(linked.username.lower(), collision.username.lower())
        self.assertEqual(linked.email, "owner@example.test")

    @override_settings(
        PONGDANG_SSO_ENABLED=True,
        PONGDANG_SSO_EDGE_SECRET=sso_edge_secret,
    )
    def test_sso_preserves_an_opaque_subject_with_a_safe_local_username(self):
        subject = "https://identity.example.test/subjects|owner account"
        client, token = self._csrf_client()

        exchanged = client.post(
            "/api/v1/users/sso/",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=token,
            **self._sso_headers(subject=subject),
        )

        self.assertEqual(exchanged.status_code, 200)
        user = User.objects.get(sso_subject=subject)
        self.assertNotEqual(user.username, subject)
        self.assertLessEqual(len(user.username), 150)

    @override_settings(
        PONGDANG_SSO_ENABLED=True,
        PONGDANG_SSO_EDGE_SECRET=sso_edge_secret,
    )
    def test_sso_links_only_one_unambiguous_email_match(self):
        email_owner = User.objects.create_user(
            username="legacy-email-owner",
            email="OWNER@example.test",
            password=self.password,
        )
        username_collision = User.objects.create_user(
            username="portfolio-owner",
            email="someone-else@example.test",
            password=self.password,
        )
        client, token = self._csrf_client()

        exchanged = client.post(
            "/api/v1/users/sso/",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=token,
            **self._sso_headers(),
        )

        self.assertEqual(exchanged.status_code, 200)
        email_owner.refresh_from_db()
        username_collision.refresh_from_db()
        self.assertEqual(email_owner.sso_subject, "portfolio-owner")
        self.assertIsNone(username_collision.sso_subject)
        self.assertEqual(exchanged.json()["username"], "legacy-email-owner")

    @override_settings(
        PONGDANG_SSO_ENABLED=True,
        PONGDANG_SSO_EDGE_SECRET=sso_edge_secret,
    )
    def test_sso_fails_closed_on_email_or_subject_conflicts(self):
        duplicate_one = User.objects.create_user(
            username="duplicate-one",
            email="owner@example.test",
        )
        duplicate_two = User.objects.create_user(
            username="duplicate-two",
            email="OWNER@example.test",
        )
        client, token = self._csrf_client()
        ambiguous = client.post(
            "/api/v1/users/sso/",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=token,
            **self._sso_headers(),
        )
        self.assertEqual(ambiguous.status_code, 409)
        self.assertNotIn("owner@example.test", str(ambiguous.json()))
        duplicate_one.refresh_from_db()
        duplicate_two.refresh_from_db()
        self.assertIsNone(duplicate_one.sso_subject)
        self.assertIsNone(duplicate_two.sso_subject)

        duplicate_two.delete()
        duplicate_one.sso_subject = "different-subject"
        duplicate_one.save(update_fields=("sso_subject",))
        occupied_email = client.post(
            "/api/v1/users/sso/",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
            **self._sso_headers(),
        )
        self.assertEqual(occupied_email.status_code, 409)

        wrong_email = client.post(
            "/api/v1/users/sso/",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
            **self._sso_headers(
                subject="different-subject",
                email="changed@example.test",
            ),
        )
        self.assertEqual(wrong_email.status_code, 409)

    @override_settings(
        PONGDANG_SSO_ENABLED=True,
        PONGDANG_SSO_EDGE_SECRET=sso_edge_secret,
    )
    def test_sso_session_requires_current_subject_and_edge_secret(self):
        client, token = self._csrf_client()
        exchanged = client.post(
            "/api/v1/users/sso/",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=token,
            **self._sso_headers(),
        )
        self.assertEqual(exchanged.status_code, 200)
        self.assertEqual(
            client.get("/api/v1/users/me/", **self._sso_headers()).status_code,
            200,
        )

        rejected = client.get(
            "/api/v1/users/me/",
            HTTP_REMOTE_USER="portfolio-owner",
            HTTP_X_PORTFOLIO_EDGE_SECRET="wrong-secret",
        )
        self.assertEqual(rejected.status_code, 403)
        self.assertEqual(
            client.get("/api/v1/users/me/", **self._sso_headers()).status_code,
            403,
        )

        refreshed = client.post(
            "/api/v1/users/sso/",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
            **self._sso_headers(),
        )
        self.assertEqual(refreshed.status_code, 200)
        switched = client.get(
            "/api/v1/users/me/",
            **self._sso_headers(
                subject="Portfolio-Owner",
                email="owner@example.test",
            ),
        )
        self.assertEqual(switched.status_code, 403)
        new_identity = client.post(
            "/api/v1/users/sso/",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
            **self._sso_headers(
                subject="another-subject",
                email="another@example.test",
            ),
        )
        self.assertEqual(new_identity.status_code, 200)
        self.assertEqual(User.objects.filter(sso_subject="another-subject").count(), 1)

    @override_settings(
        PONGDANG_SSO_ENABLED=True,
        PONGDANG_SSO_EDGE_SECRET=sso_edge_secret,
    )
    def test_sso_exchange_and_logout_require_the_private_edge(self):
        client, token = self._csrf_client()
        missing_edge = client.post(
            "/api/v1/users/sso/",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=token,
            HTTP_REMOTE_USER="portfolio-owner",
            HTTP_REMOTE_EMAIL="owner@example.test",
        )
        self.assertEqual(missing_edge.status_code, 401)
        self.assertFalse(User.objects.filter(sso_subject="portfolio-owner").exists())

        self.assertEqual(
            client.post(
                "/api/v1/users/sso/",
                {},
                format="json",
                HTTP_X_CSRFTOKEN=token,
                **self._sso_headers(),
            ).status_code,
            200,
        )
        logged_out = client.post(
            "/api/v1/users/logout/",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
            **self._sso_headers(),
        )
        self.assertEqual(logged_out.status_code, 204)
        self.assertEqual(
            client.get("/api/v1/users/me/", **self._sso_headers()).status_code,
            403,
        )

    def test_login_profile_password_logout_and_account_delete(self):
        user = User.objects.create_user(
            username="returning-user",
            password=self.password,
        )
        client, token = self._csrf_client()
        login_response = client.post(
            "/api/v1/users/login/",
            {"username": user.username, "password": self.password},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(login_response.status_code, 200)

        token = client.cookies["csrftoken"].value
        patched = client.patch(
            "/api/v1/users/me/",
            {
                "persona_type": "wellness",
                "home_region": " 강릉 ",
                "preferred_locale": "ja",
            },
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(patched.status_code, 200)
        self.assertEqual(patched.json()["home_region"], "강릉")

        changed = client.post(
            "/api/v1/users/password/",
            {
                "current_password": self.password,
                "new_password": "N3w-Very!Long-Pond-Passphrase-2026",
            },
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(changed.status_code, 204)
        self.assertEqual(client.get("/api/v1/users/me/").status_code, 200)

        logged_out = client.post(
            "/api/v1/users/logout/",
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(logged_out.status_code, 204)
        self.assertEqual(client.get("/api/v1/users/me/").status_code, 403)

        client, token = self._csrf_client()
        client.post(
            "/api/v1/users/login/",
            {
                "username": user.username,
                "password": "N3w-Very!Long-Pond-Passphrase-2026",
            },
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        deleted = client.delete(
            "/api/v1/users/me/",
            {"current_password": "N3w-Very!Long-Pond-Passphrase-2026"},
            format="json",
            HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
        )
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(User.objects.filter(pk=user.pk).exists())

    def test_user_data_is_isolated_and_passports_are_read_only(self):
        owner = User.objects.create_user(username="owner", password=self.password)
        other = User.objects.create_user(username="other", password=self.password)
        UserActivity.objects.create(
            user=other,
            spot=self.spot,
            action=UserActivity.Action.SAVE,
        )
        Passport.objects.create(user=owner, spot=self.spot)

        client = APIClient()
        client.force_authenticate(owner)
        activities = client.get("/api/v1/users/activities/").json()["results"]
        passports = client.get("/api/v1/users/passports/").json()["results"]

        self.assertEqual(activities, [])
        self.assertEqual(len(passports), 1)
        self.assertEqual(passports[0]["spot"]["id"], self.spot.pk)
        self.assertEqual(
            client.post(
                "/api/v1/users/passports/",
                {"spot": self.spot.pk},
                format="json",
            ).status_code,
            405,
        )

    def test_reviews_and_eco_actions_have_explicit_verification_semantics(self):
        user = User.objects.create_user(username="eco-user", password=self.password)
        client = APIClient()
        client.force_authenticate(user)

        invalid = client.post(
            "/api/v1/users/activities/",
            {"spot": self.spot.pk, "action": "save", "rating": 5},
            format="json",
        )
        self.assertEqual(invalid.status_code, 400)
        review = client.post(
            "/api/v1/users/activities/",
            {
                "spot": self.spot.pk,
                "action": "review",
                "rating": 5,
                "review_text": " 깨끗했어요 ",
            },
            format="json",
        )
        self.assertEqual(review.status_code, 201)
        self.assertEqual(review.json()["review_text"], "깨끗했어요")

        future = client.post(
            "/api/v1/users/eco-actions/",
            {
                "spot": self.spot.pk,
                "action_type": "cleanup",
                "occurred_on": timezone.localdate() + timedelta(days=1),
            },
            format="json",
        )
        self.assertEqual(future.status_code, 400)
        submitted = client.post(
            "/api/v1/users/eco-actions/",
            {
                "spot": self.spot.pk,
                "action_type": "cleanup",
                "note": "20분 정화",
                "occurred_on": timezone.localdate(),
                "state": "verified",
            },
            format="json",
        )
        self.assertEqual(submitted.status_code, 201)
        self.assertEqual(submitted.json()["state"], "pending")
        action = EcoAction.objects.get()
        self.assertEqual(action.state, "pending")

        operator = User.objects.create_user(
            username="private-staff-login",
            password=self.password,
            is_staff=True,
        )
        action.state = EcoAction.VerificationState.VERIFIED
        action.verified_at = timezone.now()
        action.verified_by = operator
        action.save(update_fields=("state", "verified_at", "verified_by"))
        rendered = client.get("/api/v1/users/eco-actions/").json()["results"][0]
        self.assertEqual(rendered["verified_by"], "operator")
        self.assertNotIn("private-staff-login", str(rendered))

    def test_eco_api_hides_legacy_unsafe_evidence_url(self):
        user = User.objects.create_user(
            username="legacy-eco-url-owner",
            password=self.password,
        )
        action = EcoAction.objects.create(
            user=user,
            spot=self.spot,
            action_type=EcoAction.ActionType.CLEANUP,
            occurred_on=timezone.localdate(),
        )
        EcoAction.objects.filter(pk=action.pk).update(
            evidence_url="https://user:pass@example.org/proof?token=secret",
        )
        client = APIClient()
        client.force_authenticate(user)

        rendered = client.get("/api/v1/users/eco-actions/")

        self.assertEqual(rendered.status_code, 200)
        self.assertEqual(rendered.json()["results"][0]["evidence_url"], "")

    def test_sensitive_account_checks_are_user_throttled(self):
        user = User.objects.create_user(
            username="sensitive-rate-user",
            password=self.password,
        )
        client = APIClient()
        client.force_authenticate(user)

        responses = [
            client.post(
                "/api/v1/users/password/",
                {
                    "current_password": f"wrong-{index}",
                    "new_password": "N3w-Very!Long-Pond-Passphrase-2026",
                },
                format="json",
                HTTP_X_FORWARDED_FOR=f"198.51.100.{index}",
            )
            for index in range(1, 12)
        ]

        self.assertTrue(all(response.status_code == 400 for response in responses[:10]))
        self.assertEqual(responses[10].status_code, 429)

    def test_verification_audit_owner_requires_operator_review_before_deletion(self):
        operator = User.objects.create_user(
            username="retained-verifier",
            password=self.password,
            is_staff=True,
        )
        submitter = User.objects.create_user(
            username="retained-submitter",
            password=self.password,
        )
        EcoAction.objects.create(
            user=submitter,
            spot=self.spot,
            action_type=EcoAction.ActionType.CLEANUP,
            occurred_on=timezone.localdate(),
            state=EcoAction.VerificationState.VERIFIED,
            verified_at=timezone.now(),
            verified_by=operator,
        )
        client = APIClient()
        client.force_authenticate(operator)

        response = client.delete(
            "/api/v1/users/me/",
            {"current_password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "ACCOUNT_RETENTION_REVIEW_REQUIRED")
        self.assertTrue(User.objects.filter(pk=operator.pk).exists())
