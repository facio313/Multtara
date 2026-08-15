from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.users.models import User

STRONG = "correct-horse-battery-12"


class AuthApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient(enforce_csrf_checks=True)

    def csrf(self):
        response = self.client.get("/api/v1/auth/csrf/")
        self.assertEqual(response.status_code, 200)
        token = response.data["csrfToken"]
        self.assertTrue(token)
        return token

    def test_csrf_required_for_login(self):
        self.csrf()
        response = self.client.post(
            "/api/v1/auth/login/",
            {"username": "nobody", "password": STRONG},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_register_login_me_logout(self):
        token = self.csrf()
        created = self.client.post(
            "/api/v1/auth/register/",
            {
                "username": "waveuser",
                "password": STRONG,
                "password_confirm": STRONG,
            },
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["username"], "waveuser")
        self.assertNotIn("password", created.data)
        stored = User.objects.get(username="waveuser")
        self.assertTrue(stored.password.startswith("argon2"))

        me = self.client.get("/api/v1/auth/me/")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.data["username"], "waveuser")

        token = self.csrf()
        logged_out = self.client.post(
            "/api/v1/auth/logout/",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(logged_out.status_code, 204)
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 401)

        token = self.csrf()
        logged_in = self.client.post(
            "/api/v1/auth/login/",
            {"username": "waveuser", "password": STRONG},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(logged_in.status_code, 200)
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 200)

    def test_weak_password_rejected(self):
        token = self.csrf()
        response = self.client.post(
            "/api/v1/auth/register/",
            {
                "username": "waveuser",
                "password": "short",
                "password_confirm": "short",
            },
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 400)

    def test_login_error_is_generic(self):
        token = self.csrf()
        missing = self.client.post(
            "/api/v1/auth/login/",
            {"username": "missinguser", "password": STRONG},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        User.objects.create_user(username="realuser", password=STRONG)
        token = self.csrf()
        wrong = self.client.post(
            "/api/v1/auth/login/",
            {"username": "realuser", "password": "wrong-password-12"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(wrong.status_code, 400)
        self.assertEqual(missing.data["detail"], wrong.data["detail"])

    def test_lockout_after_repeated_failures(self):
        User.objects.create_user(username="lockme", password=STRONG)
        token = self.csrf()
        for _ in range(5):
            failed = self.client.post(
                "/api/v1/auth/login/",
                {"username": "lockme", "password": "wrong-password-12"},
                format="json",
                HTTP_X_CSRFTOKEN=token,
            )
            self.assertEqual(failed.status_code, 400)
        locked = self.client.post(
            "/api/v1/auth/login/",
            {"username": "lockme", "password": STRONG},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(locked.status_code, 429)

    def test_password_change_keeps_session(self):
        User.objects.create_user(username="changer", password=STRONG)
        token = self.csrf()
        self.client.post(
            "/api/v1/auth/login/",
            {"username": "changer", "password": STRONG},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        token = self.csrf()
        changed = self.client.post(
            "/api/v1/auth/password/",
            {
                "current_password": STRONG,
                "new_password": "another-stable-pass-12",
                "new_password_confirm": "another-stable-pass-12",
            },
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 200)

    def test_spots_stay_public(self):
        response = self.client.get("/api/v1/spots/")
        self.assertEqual(response.status_code, 200)
