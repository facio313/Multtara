from pathlib import Path
import tempfile
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config.settings.validation import (
    POSTGRESQL_ENGINE,
    load_production_sso_edge_secret,
    parse_production_cors_allowed_origins,
    parse_production_database_url,
    validate_production_sso_edge_secret,
)


class ProductionSplitSessionSettingsContractTests(SimpleTestCase):
    def test_prod_settings_bind_split_cors_to_csrf_and_secure_cookie_mode(self):
        source = (Path(__file__).parent / "settings" / "prod.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("CSRF_TRUSTED_ORIGINS = list(CORS_ALLOWED_ORIGINS)", source)
        self.assertIn("CORS_ALLOW_CREDENTIALS = bool(CORS_ALLOWED_ORIGINS)", source)
        self.assertIn('SESSION_COOKIE_SAMESITE = "None"', source)
        self.assertIn('CSRF_COOKIE_SAMESITE = "None"', source)

    def test_subpath_and_cookie_isolation_are_explicit(self):
        source = (Path(__file__).parent / "settings" / "prod.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("FORCE_SCRIPT_NAME = APPLICATION_BASE_PATH or None", source)
        self.assertIn('SESSION_COOKIE_NAME = "pongdang_sessionid"', source)
        self.assertIn('CSRF_COOKIE_NAME = "pongdang_csrftoken"', source)
        self.assertIn('SESSION_COOKIE_PATH = f"{APPLICATION_BASE_PATH}/"', source)
        self.assertIn(
            'PONGDANG_SSO_ENABLED = config("PONGDANG_SSO_ENABLED"',
            (Path(__file__).parent / "settings" / "base.py").read_text(
                encoding="utf-8"
            ),
        )
        self.assertIn(
            'PONGDANG_SSO_EDGE_SECRET = config("PONGDANG_SSO_EDGE_SECRET"',
            (Path(__file__).parent / "settings" / "base.py").read_text(
                encoding="utf-8"
            ),
        )
        self.assertIn(
            '"PONGDANG_SSO_EDGE_SECRET_FILE", default=""',
            (Path(__file__).parent / "settings" / "base.py").read_text(
                encoding="utf-8"
            ),
        )

    def test_sso_edge_secret_is_required_only_when_sso_is_enabled(self):
        self.assertEqual(validate_production_sso_edge_secret(False, ""), "")
        secret = "a-unique-private-edge-secret-value-2026"
        self.assertEqual(validate_production_sso_edge_secret(True, secret), secret)
        for invalid in (
            "",
            "short",
            "replace-with-a-private-edge-secret-value",
            "가" * 32,
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ImproperlyConfigured):
                    validate_production_sso_edge_secret(True, invalid)

    def test_mode_0600_secret_file_is_preferred_over_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sso-edge-secret"
            file_secret = "file-backed-private-edge-secret-value-2026"
            path.write_text(f"{file_secret}\n", encoding="utf-8")
            path.chmod(0o600)

            loaded = load_production_sso_edge_secret(
                True,
                "environment-value-is-not-selected",
                str(path),
            )

        self.assertEqual(loaded, file_secret)

    def test_mode_0640_rootless_group_secret_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sso-edge-secret"
            file_secret = "rootless-private-edge-secret-value-2026"
            path.write_text(file_secret, encoding="utf-8")
            path.chmod(0o640)
            metadata = path.lstat()
            root_mapped_metadata = list(metadata)
            root_mapped_metadata[4] = 0
            root_mapped_metadata[5] = 0

            with (
                patch.object(
                    Path,
                    "lstat",
                    return_value=type(metadata)(root_mapped_metadata),
                ),
                patch("config.settings.validation.os.geteuid", return_value=10_001),
                patch("config.settings.validation.os.getegid", return_value=0),
            ):
                loaded = load_production_sso_edge_secret(
                    True,
                    "",
                    str(path),
                )

        self.assertEqual(loaded, file_secret)

    def test_secret_file_rejects_unsafe_kind_mode_and_size_without_echoing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            valid = root / "valid"
            secret = "do-not-echo-private-edge-secret-value-2026"
            valid.write_text(secret, encoding="utf-8")
            valid.chmod(0o600)

            symlink = root / "symlink"
            symlink.symlink_to(valid)
            unsafe_mode = root / "unsafe-mode"
            unsafe_mode.write_text(secret, encoding="utf-8")
            unsafe_mode.chmod(0o644)
            too_small = root / "too-small"
            too_small.write_text("short", encoding="utf-8")
            too_small.chmod(0o600)

            for path in (root, symlink, unsafe_mode, too_small):
                with self.subTest(path=path.name):
                    with self.assertRaises(ImproperlyConfigured) as raised:
                        load_production_sso_edge_secret(True, "", str(path))
                    self.assertNotIn(secret, str(raised.exception))


class ProductionDatabaseSettingsTests(SimpleTestCase):
    def test_complete_postgresql_url_is_accepted(self):
        database = parse_production_database_url(
            "postgresql://pongdang:strong-password@db.internal/pongdang"
        )

        self.assertEqual(database["ENGINE"], POSTGRESQL_ENGINE)
        self.assertEqual(database["NAME"], "pongdang")
        self.assertEqual(database["USER"], "pongdang")
        self.assertEqual(database["PASSWORD"], "strong-password")
        self.assertEqual(database["HOST"], "db.internal")

    def test_non_postgresql_scheme_is_rejected(self):
        with self.assertRaisesMessage(
            ImproperlyConfigured,
            "must use the PostgreSQL engine",
        ):
            parse_production_database_url("sqlite:///:memory:")

    def test_blank_database_password_is_rejected(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "PASSWORD"):
            parse_production_database_url("postgresql://pongdang@db.internal/pongdang")

    def test_blank_database_host_is_rejected(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "HOST"):
            parse_production_database_url(
                "postgresql://pongdang:strong-password@/pongdang"
            )

    def test_blank_database_name_is_rejected(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "NAME"):
            parse_production_database_url(
                "postgresql://pongdang:strong-password@db.internal/"
            )

    def test_blank_database_user_is_rejected(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "USER"):
            parse_production_database_url(
                "postgresql://:strong-password@db.internal/pongdang"
            )

    def test_error_does_not_echo_database_credentials(self):
        secret = "do-not-echo-this-password"

        with self.assertRaises(ImproperlyConfigured) as raised:
            parse_production_database_url(
                f"mysql://pongdang:{secret}@db.internal/pongdang"
            )

        self.assertNotIn(secret, str(raised.exception))


class ProductionCorsSettingsTests(SimpleTestCase):
    def test_blank_value_keeps_same_origin_default(self):
        self.assertEqual(parse_production_cors_allowed_origins(""), [])
        self.assertEqual(parse_production_cors_allowed_origins(" ,  , "), [])

    def test_https_origins_are_normalized_and_deduplicated(self):
        origins = parse_production_cors_allowed_origins(
            "HTTPS://APP.Example.COM:443, https://api.example.com:8443, "
            "https://app.example.com"
        )

        self.assertEqual(
            origins,
            ["https://app.example.com", "https://api.example.com:8443"],
        )

    def test_ipv4_and_ipv6_origins_are_accepted(self):
        origins = parse_production_cors_allowed_origins(
            "https://192.0.2.10,https://[2001:0db8::1]:8443"
        )

        self.assertEqual(
            origins,
            ["https://192.0.2.10", "https://[2001:db8::1]:8443"],
        )

    def test_non_https_and_non_origin_values_are_rejected(self):
        invalid_values = (
            "http://app.example.com",
            "ftp://app.example.com",
            "https://user:password@app.example.com",
            "https://app.example.com/",
            "https://app.example.com/path",
            "https://app.example.com?mode=split",
            "https://app.example.com#fragment",
            "https://*.example.com",
            "https://app_example.com",
            "https://app.example.com:0",
            "https://app.example.com:65536",
            "https://999.999.999.999",
        )

        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(ImproperlyConfigured):
                    parse_production_cors_allowed_origins(value)

    def test_error_does_not_echo_rejected_origin(self):
        rejected = "https://user:do-not-echo@app.example.com"

        with self.assertRaises(ImproperlyConfigured) as raised:
            parse_production_cors_allowed_origins(rejected)

        self.assertNotIn(rejected, str(raised.exception))
