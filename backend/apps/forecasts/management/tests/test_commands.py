from __future__ import annotations

from datetime import date
from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.management import CommandError, call_command
from django.test import TestCase

from apps.spots.models import WaterSpot
from services.daily_forecasts import (
    DailyForecastEvaluationReport,
    ForecastEvidenceActivityReport,
    ForecastEvidenceSyncReport,
)
from services.water_index import Activity


SYNC_MODULE = "apps.forecasts.management.commands.sync_forecast_evidence"
EVALUATE_MODULE = "apps.forecasts.management.commands.evaluate_daily_forecasts"


class SyncForecastEvidenceCommandTests(TestCase):
    def setUp(self) -> None:
        self.spot = WaterSpot.objects.create(
            type="beach",
            name="명령 테스트 해변",
            lat=37.8,
            lng=128.9,
            region="강원",
            address="강릉시",
        )

    @patch(f"{SYNC_MODULE}.KhoaForecastEvidenceIngestionService")
    @patch(f"{SYNC_MODULE}.KhoaClient")
    @patch(f"{SYNC_MODULE}.ProviderConfig.from_environment")
    def test_command_uses_one_horizon_service_and_closes_client(
        self,
        config: MagicMock,
        client_class: MagicMock,
        service_class: MagicMock,
    ) -> None:
        config.return_value = SimpleNamespace(khoa="server-only-key")
        service_class.return_value.sync.return_value = ForecastEvidenceSyncReport(
            activities=(
                ForecastEvidenceActivityReport(
                    activity=Activity.SWIM,
                    fetched_records=1,
                    matched_records=1,
                    persisted_records=0,
                    created_snapshots=0,
                    skipped_records=0,
                    provider_failed=False,
                ),
            ),
            dry_run=True,
        )
        output = StringIO()

        call_command(
            "sync_forecast_evidence",
            "--dry-run",
            "--spot",
            str(self.spot.pk),
            "--activity",
            "swim",
            stdout=output,
        )

        client_class.assert_called_once_with("server-only-key")
        client_class.return_value.close.assert_called_once_with()
        kwargs = service_class.return_value.sync.call_args.kwargs
        self.assertEqual(kwargs["activities"], (Activity.SWIM,))
        self.assertEqual(tuple(item.pk for item in kwargs["spots"]), (self.spot.pk,))
        self.assertIs(kwargs["dry_run"], True)
        self.assertNotIn("server-only-key", output.getvalue())

    @patch(f"{SYNC_MODULE}.KhoaClient")
    @patch(f"{SYNC_MODULE}.ProviderConfig.from_environment")
    def test_missing_credential_fails_before_client_creation(
        self,
        config: MagicMock,
        client_class: MagicMock,
    ) -> None:
        config.return_value = SimpleNamespace(khoa="")

        with self.assertRaisesMessage(
            CommandError,
            "KHOA provider credential is not configured",
        ):
            call_command("sync_forecast_evidence")

        client_class.assert_not_called()


class EvaluateDailyForecastCommandTests(TestCase):
    def setUp(self) -> None:
        self.spot = WaterSpot.objects.create(
            type="beach",
            name="평가 명령 해변",
            lat=37.8,
            lng=128.9,
            region="강원",
            address="강릉시",
        )

    @patch(f"{EVALUATE_MODULE}.evaluate_daily_forecasts")
    def test_command_passes_bounded_dates_activities_and_profiles(
        self,
        evaluate: MagicMock,
    ) -> None:
        evaluate.return_value = DailyForecastEvaluationReport(
            requested_dates=3,
            evaluated_projections=3,
            created_projections=3,
            updated_projections=0,
            unavailable_projections=3,
            dry_run=True,
        )
        output = StringIO()

        call_command(
            "evaluate_daily_forecasts",
            "--dry-run",
            "--days",
            "3",
            "--start-date",
            "2026-08-19",
            "--spot",
            str(self.spot.pk),
            "--activity",
            "relax",
            "--profile",
            "general",
            "--participant-skill-level",
            "beginner",
            "--participant-skill-level",
            "intermediate",
            stdout=output,
        )

        kwargs = evaluate.call_args.kwargs
        self.assertEqual(kwargs["start_date"], date(2026, 8, 19))
        self.assertEqual(kwargs["days"], 3)
        self.assertEqual(kwargs["activities"], (Activity.RELAX,))
        self.assertEqual(kwargs["profiles"], ("general",))
        self.assertEqual(kwargs["skill_levels"], ("beginner", "intermediate"))
        self.assertIs(kwargs["dry_run"], True)
        self.assertIn("dates=3", output.getvalue())

    def test_invalid_horizon_is_rejected(self) -> None:
        for value in ("0", "8", "not-a-number"):
            with self.subTest(value=value), self.assertRaises(CommandError):
                call_command("evaluate_daily_forecasts", "--days", value)
