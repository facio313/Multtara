from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.conditions.models import ConditionScore, ObservationSnapshot
from apps.spots.models import WaterSpot


class EvaluateWaterConditionsCommandTests(TestCase):
    def setUp(self) -> None:
        self.spot = WaterSpot.objects.create(
            type="beach",
            name="경포해수욕장",
            lat=37.8055,
            lng=128.9070,
            region="강원",
            address="강원특별자치도 강릉시",
        )

    def test_dry_run_with_no_inputs_is_unknown_and_does_not_write(self) -> None:
        stdout = StringIO()
        call_command(
            "evaluate_water_conditions",
            "--dry-run",
            "--spot",
            str(self.spot.pk),
            "--activity",
            "swim",
            "--at",
            "2026-08-16T14:00:00+09:00",
            stdout=stdout,
        )

        self.assertIn("unknown=1", stdout.getvalue())
        self.assertEqual(ObservationSnapshot.objects.count(), 0)
        self.assertEqual(ConditionScore.objects.count(), 0)

    def test_persisted_empty_evidence_remains_unknown(self) -> None:
        call_command(
            "evaluate_water_conditions",
            "--spot",
            str(self.spot.pk),
            "--activity",
            "swim",
            "--at",
            "2026-08-16T14:00:00+09:00",
        )

        score = ConditionScore.objects.get()
        self.assertEqual(score.safety_status, "unknown")
        self.assertIsNone(score.score)
        self.assertEqual(score.snapshot.state, "missing")

    def test_naive_evaluation_time_is_rejected(self) -> None:
        with self.assertRaisesMessage(CommandError, "--at must include a timezone offset"):
            call_command(
                "evaluate_water_conditions",
                "--at",
                "2026-08-16T14:00:00",
            )

    def test_explicit_unsupported_activity_is_skipped_for_spot_type(self) -> None:
        self.spot.type = "hotspring"
        self.spot.save(update_fields=("type",))
        stdout = StringIO()

        call_command(
            "evaluate_water_conditions",
            "--spot",
            str(self.spot.pk),
            "--activity",
            "swim",
            "--at",
            "2026-08-16T14:00:00+09:00",
            stdout=stdout,
        )

        self.assertIn("evaluations=0", stdout.getvalue())
        self.assertEqual(ObservationSnapshot.objects.count(), 0)
        self.assertEqual(ConditionScore.objects.count(), 0)

    def test_family_profile_is_not_persisted_for_non_swim_activity(self) -> None:
        stdout = StringIO()

        call_command(
            "evaluate_water_conditions",
            "--spot",
            str(self.spot.pk),
            "--activity",
            "surf",
            "--profile",
            "family",
            "--at",
            "2026-08-16T14:00:00+09:00",
            stdout=stdout,
        )

        self.assertIn("evaluations=0", stdout.getvalue())
        self.assertEqual(ConditionScore.objects.count(), 0)
