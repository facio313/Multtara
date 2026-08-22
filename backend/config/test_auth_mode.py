import importlib
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase
from django.urls import clear_url_caches

from config.auth_mode import resolve_portfolio_auth_contract


class PortfolioAuthModeTests(SimpleTestCase):
    base_dir = Path(__file__).resolve().parent.parent

    def resolve(self, branch, mode, legacy=None, build_mode=None):
        return resolve_portfolio_auth_contract(
            base_dir=self.base_dir,
            environment={
                "PORTFOLIO_BRANCH": branch,
                "PORTFOLIO_AUTH_MODE": mode,
            },
            legacy_sso_name="PONGDANG_SSO_ENABLED",
            legacy_sso_value=legacy,
            build_mode=build_mode,
        )

    def test_main_and_dev_resolve_to_sso(self):
        for branch in ("main", "dev", "refs/heads/main", "refs/heads/dev"):
            with self.subTest(branch=branch):
                contract = self.resolve(branch, "sso", legacy="true")
                self.assertEqual(contract.mode, "sso")
                self.assertTrue(contract.sso_enabled)

    def test_every_other_branch_resolves_to_local(self):
        contract = self.resolve("codex-auth-contract", "local", legacy="false")
        self.assertEqual(contract.mode, "local")
        self.assertFalse(contract.sso_enabled)

    def test_explicit_mode_and_legacy_mismatches_fail_closed(self):
        with self.assertRaises(ImproperlyConfigured):
            self.resolve("main", "local")
        with self.assertRaises(ImproperlyConfigured):
            self.resolve("main", "sso", legacy="false")
        with self.assertRaises(ImproperlyConfigured):
            self.resolve("topic", "local", legacy="true")

    def test_runtime_cannot_change_the_image_build_mode(self):
        with self.assertRaises(ImproperlyConfigured):
            self.resolve("topic", "local", build_mode="sso")

    def test_packaged_runtime_requires_branch_and_mode(self):
        with patch("config.auth_mode._resolver_path", return_value=None):
            with self.assertRaisesRegex(
                ImproperlyConfigured,
                "PORTFOLIO_BRANCH",
            ):
                resolve_portfolio_auth_contract(
                    base_dir=self.base_dir,
                    environment={},
                    legacy_sso_name="PONGDANG_SSO_ENABLED",
                    legacy_sso_value=None,
                )
            with self.assertRaisesRegex(
                ImproperlyConfigured,
                "PORTFOLIO_AUTH_MODE",
            ):
                resolve_portfolio_auth_contract(
                    base_dir=self.base_dir,
                    environment={"PORTFOLIO_BRANCH": "main"},
                    legacy_sso_name="PONGDANG_SSO_ENABLED",
                    legacy_sso_value=None,
                )

    def test_packaged_runtime_matches_immutable_build_contract(self):
        with TemporaryDirectory() as directory:
            contract_path = Path(directory) / "portfolio-auth-build"
            contract_path.write_text("main\nsso\n", encoding="utf-8")
            contract_path.chmod(0o444)
            with patch("config.auth_mode._resolver_path", return_value=None):
                contract = resolve_portfolio_auth_contract(
                    base_dir=self.base_dir,
                    environment={
                        "PORTFOLIO_BRANCH": "refs/heads/main",
                        "PORTFOLIO_AUTH_MODE": "sso",
                    },
                    legacy_sso_name="PONGDANG_SSO_ENABLED",
                    legacy_sso_value="true",
                    build_contract_path=contract_path,
                )
                self.assertEqual(contract.branch, "main")

                contract_path.chmod(0o644)
                contract_path.write_text("dev\nsso\n", encoding="utf-8")
                contract_path.chmod(0o444)
                with self.assertRaisesRegex(ImproperlyConfigured, "image build"):
                    resolve_portfolio_auth_contract(
                        base_dir=self.base_dir,
                        environment={
                            "PORTFOLIO_BRANCH": "main",
                            "PORTFOLIO_AUTH_MODE": "sso",
                        },
                        legacy_sso_name="PONGDANG_SSO_ENABLED",
                        legacy_sso_value="true",
                        build_contract_path=contract_path,
                    )


class AdminRouteModeTests(SimpleTestCase):
    @staticmethod
    def reload_urlconf():
        module = importlib.import_module("config.urls")
        clear_url_caches()
        importlib.reload(module)
        clear_url_caches()

    def test_admin_route_exists_only_in_local_mode(self):
        try:
            with self.settings(PONGDANG_SSO_ENABLED=True):
                self.reload_urlconf()
                self.assertEqual(self.client.get("/admin/login/").status_code, 404)
            with self.settings(PONGDANG_SSO_ENABLED=False):
                self.reload_urlconf()
                self.assertEqual(self.client.get("/admin/login/").status_code, 200)
        finally:
            self.reload_urlconf()
