from unittest.mock import patch

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
