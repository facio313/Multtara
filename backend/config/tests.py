from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from services.provider_config import ProviderConfig


class ProviderConfigTests(SimpleTestCase):
    @patch("services.provider_config.config")
    def test_blank_provider_key_falls_back_to_shared_key(self, mock_config):
        values = {
            "DATA_GO_KR_SERVICE_KEY": "shared-key",
            "TOUR_API_KEY": "",
            "KMA_API_KEY": "weather-key",
            "KHOA_API_KEY": "marine-key",
            "MOE_API_KEY": "",
        }
        mock_config.side_effect = lambda name, default="": values.get(name, default)

        providers = ProviderConfig.from_environment()

        self.assertEqual(providers.tour_api, "shared-key")
        self.assertEqual(providers.moe, "shared-key")
        self.assertEqual(providers.kma, "weather-key")

    def test_integration_health_exposes_booleans_only(self):
        response = self.client.get("/api/health/integrations/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(
            set(payload["configured"]),
            {"tour_api", "weather", "marine", "water_quality"},
        )
        self.assertTrue(
            all(isinstance(value, bool) for value in payload["configured"].values())
        )

    def test_health_endpoints_are_get_only(self):
        self.assertEqual(self.client.post("/api/health/").status_code, 405)
        self.assertEqual(
            self.client.post("/api/health/integrations/").status_code,
            405,
        )


class ReadinessHealthTests(SimpleTestCase):
    @patch("config.urls.connection")
    def test_readiness_checks_database_without_exposing_details(self, connection):
        context = MagicMock()
        connection.cursor.return_value.__enter__.return_value = context

        response = self.client.get("/api/health/ready/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": "ready", "service": "pongdang-api"},
        )
        context.execute.assert_called_once_with("SELECT 1")
        context.fetchone.assert_called_once_with()

    @patch("config.urls.connection")
    def test_readiness_fails_closed_without_database_error_details(self, connection):
        from django.db import DatabaseError

        connection.cursor.side_effect = DatabaseError("private database host")

        response = self.client.get("/api/health/ready/")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"status": "unavailable", "service": "pongdang-api"},
        )
        self.assertNotIn("private", response.content.decode())

    def test_readiness_is_get_only(self):
        self.assertEqual(self.client.post("/api/health/ready/").status_code, 405)
