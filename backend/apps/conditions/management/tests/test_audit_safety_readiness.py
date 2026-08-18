from __future__ import annotations

from datetime import timedelta
from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone

from apps.conditions.models import ConditionScore, ObservationMetric, ObservationSnapshot
from apps.spots.models import WaterSpot


class AuditSafetyReadinessCommandTests(TestCase):
    def setUp(self):
        self.spot = WaterSpot.objects.create(
            name="Verified Spa",
            type=WaterSpot.SpotType.HOTSPRING,
            lat=37.0,
            lng=128.0,
            region="Gangwon",
            address="Public address",
            catalog_verification=WaterSpot.VerificationState.VERIFIED,
        )

    def test_missing_evaluations_are_unknown_and_can_fail_monitor(self):
        output = StringIO()
        call_command("audit_safety_readiness", "--json", stdout=output)
        rendered = output.getvalue()
        self.assertIn('"status": "degraded"', rendered)
        self.assertIn("EVALUATION_MISSING", rendered)

        with self.assertRaisesRegex(CommandError, "No audited evaluation"):
            call_command("audit_safety_readiness", "--require-current-clear")

    def test_current_clear_requires_current_required_evidence(self):
        now = timezone.now()
        snapshot = ObservationSnapshot.objects.create(
            spot=self.spot,
            provider="PONGDANG_FUSION",
            provider_record_id="readiness-current",
            state=ObservationSnapshot.SourceState.LIVE,
            observed_at=now - timedelta(minutes=1),
            fetched_at=now,
            valid_from=now - timedelta(minutes=1),
            valid_until=now + timedelta(minutes=10),
            spatial_scope=f"spot:{self.spot.pk}",
            ingestion_version="observation-fusion-v4",
        )
        for name, value_type, value in (
            ("facility_status", "text", "open"),
            ("facility_hygiene_status", "text", "clear"),
            ("hot_tub_temperature_c", "number", 38.0),
        ):
            values = {
                "text_value": value if value_type == "text" else None,
                "numeric_value": value if value_type == "number" else None,
            }
            ObservationMetric.objects.create(
                snapshot=snapshot,
                name=name,
                value_type=value_type,
                unit="canonical",
                mode=ObservationMetric.Mode.OBSERVED,
                state=ObservationMetric.State.VALID,
                confidence=1.0,
                source="LOCAL_AUTHORITY",
                spatial_scope=f"spot:{self.spot.pk}",
                observed_at=now - timedelta(minutes=1),
                fetched_at=now,
                valid_from=now - timedelta(minutes=1),
                valid_until=now + timedelta(minutes=10),
                **values,
            )
        ConditionScore.objects.create(
            spot=self.spot,
            snapshot=snapshot,
            activity="onsen",
            participant_profile="general",
            score=80,
            safety_status=ConditionScore.SafetyStatus.CLEAR,
            decision=ConditionScore.Decision.RECOMMENDED,
            confidence=1.0,
            coverage=1.0,
            score_range=[80, 80],
            methodology_version="water-index-v1.0.0",
            evaluated_at=now,
        )

        output = StringIO()
        call_command(
            "audit_safety_readiness",
            "--profile",
            "general",
            "--json",
            stdout=output,
        )

        self.assertIn('"clear": 1', output.getvalue())
        self.assertIn('"unknown": 0', output.getvalue())
