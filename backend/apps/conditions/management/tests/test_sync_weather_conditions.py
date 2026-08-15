from __future__ import annotations

from datetime import datetime
from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.spots.models import WaterSpot
from services.ingestion.weather import KmaMode, WeatherSyncReport


KST = ZoneInfo("Asia/Seoul")
SECRET = "server-only-weather-test-key"
COMMAND_MODULE = "apps.conditions.management.commands.sync_weather_conditions"


class SyncWeatherConditionsCommandTests(TestCase):
    def setUp(self) -> None:
        self.spot = WaterSpot.objects.create(
            type="beach",
            name="경포해수욕장",
            lat=37.8055,
            lng=128.9070,
            region="강원",
            address="강원특별자치도 강릉시",
        )

    @patch(f"{COMMAND_MODULE}.WeatherIngestionService")
    @patch(f"{COMMAND_MODULE}.KmaClient")
    @patch(f"{COMMAND_MODULE}.ProviderConfig.from_environment")
    def test_key_stays_server_side_and_explicit_issue_time_reaches_service(
        self,
        from_environment: MagicMock,
        client_class: MagicMock,
        service_class: MagicMock,
    ) -> None:
        from_environment.return_value = SimpleNamespace(kma=SECRET)
        service = service_class.return_value
        service.sync.return_value = WeatherSyncReport(
            mode=KmaMode.NOWCAST,
            requested_grids=1,
            fetched_values=8,
            normalized_snapshots=1,
            persisted_snapshots=0,
            created_snapshots=0,
            dry_run=True,
        )
        stdout = StringIO()

        call_command(
            "sync_weather_conditions",
            "--dry-run",
            "--spot",
            str(self.spot.pk),
            "--issued-at",
            "2026-08-16T13:00:00+09:00",
            stdout=stdout,
        )

        client_class.assert_called_once_with(SECRET)
        client_class.return_value.close.assert_called_once_with()
        kwargs = service.sync.call_args.kwargs
        self.assertEqual(kwargs["mode"], KmaMode.NOWCAST)
        self.assertEqual(
            kwargs["issued_at"], datetime(2026, 8, 16, 13, tzinfo=KST)
        )
        self.assertEqual(tuple(item.pk for item in kwargs["spots"]), (self.spot.pk,))
        self.assertTrue(kwargs["dry_run"])
        self.assertNotIn(SECRET, stdout.getvalue())

    @patch(f"{COMMAND_MODULE}.KmaClient")
    @patch(f"{COMMAND_MODULE}.ProviderConfig.from_environment")
    def test_missing_key_fails_before_client_creation(
        self, from_environment: MagicMock, client_class: MagicMock
    ) -> None:
        from_environment.return_value = SimpleNamespace(kma="")
        with self.assertRaisesMessage(
            CommandError, "KMA provider credential is not configured"
        ):
            call_command("sync_weather_conditions")
        client_class.assert_not_called()

    def test_naive_issue_time_is_rejected(self) -> None:
        with self.assertRaisesMessage(
            CommandError, "--issued-at must include a timezone offset"
        ):
            call_command(
                "sync_weather_conditions",
                "--issued-at",
                "2026-08-16T13:00:00",
            )
