from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.conditions.models import IngestionRun, PipelineHeartbeat
from services.provider_config import ProviderConfig
from services.pipeline_health import TASK_MAX_AGES


class ProviderConfigTests(SimpleTestCase):
    @patch("services.provider_config.config")
    def test_blank_provider_key_falls_back_to_shared_key(self, mock_config):
        values = {
            "DATA_GO_KR_SERVICE_KEY": "shared-key",
            "TOUR_API_KEY": "",
            "KMA_API_KEY": "weather-key",
            "KHOA_API_KEY": "marine-key",
            "MOE_API_KEY": "",
            "ROUTING_MATRIX_URL": "https://routing.example.test",
        }
        mock_config.side_effect = lambda name, default="": values.get(name, default)

        providers = ProviderConfig.from_environment()

        self.assertEqual(providers.tour_api, "shared-key")
        self.assertEqual(providers.moe, "shared-key")
        self.assertEqual(providers.kma, "weather-key")
        self.assertEqual(
            providers.routing_matrix,
            "https://routing.example.test",
        )

    def test_health_endpoints_are_get_only(self):
        self.assertEqual(self.client.post("/api/health/").status_code, 405)
        self.assertEqual(
            self.client.post("/api/health/integrations/").status_code,
            405,
        )
        self.assertEqual(self.client.post("/api/health/safety/").status_code, 405)


class IntegrationHealthTests(TestCase):
    def setUp(self):
        self.config = ProviderConfig(
            data_go_kr="",
            tour_api="",
            kma="",
            khoa="",
            moe="",
        )

    @patch("config.urls.get_provider_status")
    @patch("config.urls.ProviderConfig.from_environment")
    def test_integration_health_fails_closed_before_pipeline_success(
        self, provider_config, public_status
    ):
        provider_config.return_value = self.config
        public_status.return_value = self.config.public_status()

        response = self.client.get("/api/health/integrations/")

        self.assertEqual(response.status_code, 503)
        payload = response.json()
        self.assertEqual(payload["status"], "degraded")
        self.assertEqual(payload["heartbeat"]["state"], "missing")
        self.assertEqual(
            set(payload["configured"]),
            {"tour_api", "weather", "marine", "water_quality", "routing_matrix"},
        )
        self.assertTrue(
            all(isinstance(value, bool) for value in payload["configured"].values())
        )

    @patch("config.urls.get_provider_status")
    @patch("config.urls.ProviderConfig.from_environment")
    def test_integration_health_reports_current_successes_without_credentials(
        self, provider_config, public_status
    ):
        provider_config.return_value = self.config
        public_status.return_value = self.config.public_status()
        at = timezone.now()
        PipelineHeartbeat.objects.create(
            state=PipelineHeartbeat.State.RUNNING,
            last_seen_at=at,
        )
        for task_name in (
            "water-index-general",
            "water-index-family",
            "derive-suitability",
            "daily-forecast",
            "condition-retention",
        ):
            IngestionRun.objects.create(
                task_name=task_name,
                status=IngestionRun.Status.SUCCEEDED,
                started_at=at - timedelta(seconds=1),
                finished_at=at,
                details={"command": "safe-command"},
            )

        response = self.client.get("/api/health/integrations/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertNotIn("credential", response.content.decode())
        self.assertEqual(
            payload["tasks"]["daily-forecast"]["max_age_seconds"],
            int(TASK_MAX_AGES["daily-forecast"].total_seconds()),
        )

    @patch("config.urls.get_provider_status")
    @patch("config.urls.ProviderConfig.from_environment")
    def test_configured_routing_requires_all_three_current_matrix_refreshes(
        self, provider_config, public_status
    ):
        configured = ProviderConfig(
            data_go_kr="",
            tour_api="",
            kma="",
            khoa="",
            moe="",
            routing_matrix="https://routing.example.test",
        )
        provider_config.return_value = configured
        public_status.return_value = configured.public_status()
        at = timezone.now()
        PipelineHeartbeat.objects.create(
            state=PipelineHeartbeat.State.RUNNING,
            last_seen_at=at,
        )
        core_tasks = (
            "water-index-general",
            "water-index-family",
            "derive-suitability",
            "daily-forecast",
            "condition-retention",
        )
        for task_name in core_tasks:
            IngestionRun.objects.create(
                task_name=task_name,
                status=IngestionRun.Status.SUCCEEDED,
                started_at=at - timedelta(seconds=1),
                finished_at=at,
            )

        missing = self.client.get("/api/health/integrations/")

        self.assertEqual(missing.status_code, 503)
        self.assertEqual(
            missing.json()["tasks"]["route-matrix-drive"]["state"],
            "never_succeeded",
        )

        for task_name in (
            "route-matrix-drive",
            "route-matrix-walk",
            "route-matrix-bicycle",
        ):
            IngestionRun.objects.create(
                task_name=task_name,
                status=IngestionRun.Status.SUCCEEDED,
                started_at=at - timedelta(seconds=1),
                finished_at=at,
            )

        current = self.client.get("/api/health/integrations/")

        self.assertEqual(current.status_code, 200)
        self.assertEqual(
            current.json()["manual_integrations"]["routing_matrix"],
            "scheduled",
        )

    def test_safety_health_fails_closed_without_verified_catalog(self):
        response = self.client.get("/api/health/safety/")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "degraded")
        self.assertEqual(response.json()["detail"], "no verified catalog spots")


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
