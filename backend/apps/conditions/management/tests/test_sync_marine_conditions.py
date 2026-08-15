from __future__ import annotations

from datetime import date
from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.spots.models import WaterSpot
from services.ingestion.marine import SyncActivityReport, SyncReport
from services.providers.base import ProviderTransportError
from services.water_index import Activity


SECRET = "server-only-test-key"
COMMAND_MODULE = "apps.conditions.management.commands.sync_marine_conditions"


def report(*, dry_run: bool) -> SyncReport:
    return SyncReport(
        activities=(
            SyncActivityReport(
                activity=Activity.SWIM,
                fetched_records=1,
                matched_records=1,
                persisted_records=0 if dry_run else 1,
                created_snapshots=0 if dry_run else 1,
                created_scores=0 if dry_run else 1,
                skipped_records=0,
                unknown_results=1,
            ),
        ),
        dry_run=dry_run,
    )


class SyncMarineConditionsCommandTests(TestCase):
    def setUp(self) -> None:
        self.spot = WaterSpot.objects.create(
            type="beach",
            name="경포해수욕장",
            lat=37.8055,
            lng=128.9070,
            region="강원",
            address="강원특별자치도 강릉시",
        )

    @patch(f"{COMMAND_MODULE}.MarineIngestionService")
    @patch(f"{COMMAND_MODULE}.KhoaClient")
    @patch(f"{COMMAND_MODULE}.ProviderConfig.from_environment")
    def test_options_use_environment_key_and_dry_run_without_network(
        self,
        from_environment: MagicMock,
        client_class: MagicMock,
        service_class: MagicMock,
    ) -> None:
        from_environment.return_value = SimpleNamespace(khoa=SECRET)
        client = client_class.return_value
        service = service_class.return_value
        service.sync.return_value = report(dry_run=True)
        stdout = StringIO()

        call_command(
            "sync_marine_conditions",
            "--dry-run",
            "--spot",
            str(self.spot.pk),
            "--activity",
            "swim",
            "--date",
            "2026-08-16",
            stdout=stdout,
        )

        client_class.assert_called_once_with(SECRET)
        client.close.assert_called_once_with()
        kwargs = service.sync.call_args.kwargs
        self.assertEqual(kwargs["activities"], (Activity.SWIM,))
        self.assertEqual(kwargs["request_date"], date(2026, 8, 16))
        self.assertEqual(tuple(spot.pk for spot in kwargs["spots"]), (self.spot.pk,))
        self.assertIs(kwargs["dry_run"], True)
        self.assertIn("dry-run", stdout.getvalue())
        self.assertNotIn(SECRET, stdout.getvalue())

    @patch(f"{COMMAND_MODULE}.KhoaClient")
    @patch(f"{COMMAND_MODULE}.ProviderConfig.from_environment")
    def test_missing_key_fails_before_client_creation(
        self, from_environment: MagicMock, client_class: MagicMock
    ) -> None:
        from_environment.return_value = SimpleNamespace(khoa="")

        with self.assertRaisesMessage(
            CommandError, "KHOA provider credential is not configured"
        ):
            call_command("sync_marine_conditions")

        client_class.assert_not_called()

    @patch(f"{COMMAND_MODULE}.MarineIngestionService")
    @patch(f"{COMMAND_MODULE}.KhoaClient")
    @patch(f"{COMMAND_MODULE}.ProviderConfig.from_environment")
    def test_provider_and_unexpected_failures_never_echo_secret(
        self,
        from_environment: MagicMock,
        client_class: MagicMock,
        service_class: MagicMock,
    ) -> None:
        from_environment.return_value = SimpleNamespace(khoa=SECRET)
        service = service_class.return_value
        service.sync.side_effect = ProviderTransportError("KHOA", status_code=503)

        with self.assertRaises(CommandError) as raised:
            call_command("sync_marine_conditions")
        self.assertIn("HTTP 503", str(raised.exception))
        self.assertNotIn(SECRET, str(raised.exception))

        service.sync.side_effect = RuntimeError(f"prepared URL serviceKey={SECRET}")
        with self.assertRaises(CommandError) as raised_unexpected:
            call_command("sync_marine_conditions")
        self.assertEqual(
            str(raised_unexpected.exception),
            "Marine condition synchronization failed internally",
        )
        self.assertNotIn(SECRET, str(raised_unexpected.exception))

    def test_invalid_date_is_rejected_before_handle(self) -> None:
        with self.assertRaisesMessage(
            CommandError, "--date must use YYYY-MM-DD or YYYYMMDD"
        ):
            call_command("sync_marine_conditions", "--date", "2026-99-99")
