from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.conditions.models import ConditionScore, ObservationSnapshot
from apps.forecasts.models import DailyForecast, WaterForecast
from apps.spots.management.commands.seed_dummy_data import (
    DEMO_CATALOG_SOURCE,
    DEMO_SPOTS,
)
from apps.spots.models import WaterSpot


class SeedDummyDataCommandTests(TestCase):
    def setUp(self):
        self.real_spot = WaterSpot.objects.create(
            name="운영자 검증 장소",
            type=WaterSpot.SpotType.BEACH,
            lat=37.8,
            lng=128.9,
            region="강원",
            address="검증 주소",
            catalog_source="LOCAL_OPERATOR",
        )

    def test_seed_is_idempotent_and_never_fabricates_condition_evidence(self):
        call_command("seed_dummy_data")
        call_command("seed_dummy_data")

        demo = WaterSpot.objects.filter(catalog_source=DEMO_CATALOG_SOURCE)
        self.assertEqual(demo.count(), len(DEMO_SPOTS))
        self.assertTrue(WaterSpot.objects.filter(pk=self.real_spot.pk).exists())
        self.assertTrue(all(row.type in WaterSpot.SpotType.values for row in demo))
        self.assertTrue(all(row.catalog_confidence == 0.0 for row in demo))
        self.assertEqual(ObservationSnapshot.objects.count(), 0)
        self.assertEqual(ConditionScore.objects.count(), 0)
        self.assertEqual(WaterForecast.objects.count(), 0)
        self.assertEqual(DailyForecast.objects.count(), 0)

    def test_reset_and_dry_run_are_scoped_to_demo_rows(self):
        call_command("seed_dummy_data")
        first_demo = WaterSpot.objects.filter(
            catalog_source=DEMO_CATALOG_SOURCE
        ).first()
        assert first_demo is not None
        first_id = first_demo.pk

        output = StringIO()
        call_command("seed_dummy_data", "--dry-run", "--reset-demo", stdout=output)
        self.assertTrue(WaterSpot.objects.filter(pk=first_id).exists())
        self.assertIn("dry-run", output.getvalue())

        call_command("seed_dummy_data", "--reset-demo")
        self.assertFalse(WaterSpot.objects.filter(pk=first_id).exists())
        self.assertTrue(WaterSpot.objects.filter(pk=self.real_spot.pk).exists())
