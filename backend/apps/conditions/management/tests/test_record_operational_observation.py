from __future__ import annotations

from datetime import timedelta
from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone

from apps.conditions.models import ObservationSnapshot
from apps.spots.models import WaterSpot
from services.ingestion.operational import build_operational_observation


class OperationalObservationTests(TestCase):
    def setUp(self):
        self.spot = WaterSpot.objects.create(
            type=WaterSpot.SpotType.BEACH,
            name="운영 검증 해변",
            lat=37.75,
            lng=128.9,
        )

    def temporal_arguments(self):
        now = timezone.now().replace(microsecond=0)
        return {
            "observed_at": now - timedelta(minutes=1),
            "fetched_at": now,
            "valid_until": now + timedelta(minutes=9),
        }

    def test_build_rejects_source_metric_impersonation(self):
        with self.assertRaisesRegex(ValueError, "not approved"):
            build_operational_observation(
                source="KMA_LIGHTNING",
                provider_record_id="kma-20260816-1200",
                source_url="https://www.data.go.kr/data/15058079/openapi.do",
                spatial_scope=f"spot:{self.spot.pk}",
                metric_assignments=("official_entry_status=open",),
                **self.temporal_arguments(),
            )

    def test_build_rejects_non_finite_and_credential_bearing_values(self):
        arguments = self.temporal_arguments()
        with self.assertRaisesRegex(ValueError, "finite"):
            build_operational_observation(
                source="KMA_LIGHTNING",
                provider_record_id="kma-20260816-1200",
                source_url="https://www.data.go.kr/data/15058079/openapi.do",
                spatial_scope=f"spot:{self.spot.pk}",
                metric_assignments=("lightning_clearance_minutes=nan",),
                **arguments,
            )
        with self.assertRaisesRegex(ValueError, "public HTTPS"):
            build_operational_observation(
                source="KMA_LIGHTNING",
                provider_record_id="kma-20260816-1200",
                source_url="https://example.com/status?serviceKey=secret",
                spatial_scope=f"spot:{self.spot.pk}",
                metric_assignments=("lightning_clearance_minutes=31",),
                **arguments,
            )
        with self.assertRaisesRegex(ValueError, "public HTTPS"):
            build_operational_observation(
                source="KMA_LIGHTNING",
                provider_record_id="kma-20260816-1200",
                source_url="https://127.0.0.1/status",
                spatial_scope=f"spot:{self.spot.pk}",
                metric_assignments=("lightning_clearance_minutes=31",),
                **arguments,
            )

    def test_build_rejects_unbounded_or_expired_assertion(self):
        arguments = self.temporal_arguments()
        arguments["valid_until"] = arguments["observed_at"] + timedelta(hours=25)
        with self.assertRaisesRegex(ValueError, "over 24 hours"):
            build_operational_observation(
                source="LOCAL_AUTHORITY",
                provider_record_id="gangneung-ops-42",
                source_url="https://www.gn.go.kr/safety/status",
                spatial_scope=f"spot:{self.spot.pk}",
                metric_assignments=("official_entry_status=open",),
                **arguments,
            )

    def test_official_river_flow_is_typed_as_cubic_metres_per_second(self):
        observation = build_operational_observation(
            source="MOE",
            provider_record_id="MOE-STATION-1",
            source_url="https://www.me.go.kr/public/river-flow",
            spatial_scope=f"spot:{self.spot.pk}",
            metric_assignments=("river_flow_cms=15.5",),
            **self.temporal_arguments(),
        )

        flow = observation.observations.get("river_flow_cms")
        self.assertEqual(flow.value, 15.5)
        self.assertEqual(flow.unit, "m3/s")

    def test_command_persists_idempotent_auditable_snapshot(self):
        now = timezone.now().replace(microsecond=0)
        common = (
            "record_operational_observation",
            "--spot",
            str(self.spot.pk),
            "--source",
            "LOCAL_AUTHORITY",
            "--record-id",
            "gangneung-ops-20260816-1200",
            "--source-url",
            "https://www.gn.go.kr/safety/status",
            "--observed-at",
            (now - timedelta(minutes=1)).isoformat(),
            "--valid-until",
            (now + timedelta(minutes=9)).isoformat(),
            "--metric",
            "official_entry_status=open",
            "--metric",
            "patrol_status=active",
        )
        output = StringIO()
        call_command(*common, stdout=output)
        call_command(*common, stdout=output)

        self.assertEqual(ObservationSnapshot.objects.count(), 1)
        snapshot = ObservationSnapshot.objects.get()
        self.assertEqual(snapshot.provider, "LOCAL_AUTHORITY")
        self.assertEqual(snapshot.metrics.count(), 2)
        self.assertEqual(snapshot.metrics.get(name="official_entry_status").value, "open")
        self.assertNotIn("https://", output.getvalue())
        self.assertNotIn("official_entry_status=open", output.getvalue())

    def test_dry_run_writes_nothing(self):
        now = timezone.now().replace(microsecond=0)
        call_command(
            "record_operational_observation",
            "--spot",
            str(self.spot.pk),
            "--source",
            "MOE",
            "--record-id",
            "moe-quality-20260816",
            "--source-url",
            "https://www.data.go.kr/data/15056705/openapi.do",
            "--observed-at",
            (now - timedelta(minutes=1)).isoformat(),
            "--valid-until",
            (now + timedelta(hours=1)).isoformat(),
            "--metric",
            "water_quality_status=pass",
            "--dry-run",
            stdout=StringIO(),
        )
        self.assertFalse(ObservationSnapshot.objects.exists())
