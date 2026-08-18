from __future__ import annotations

from datetime import timedelta

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class DailyForecastSurfSkillMigrationTests(TransactionTestCase):
    migrate_from = ("forecasts", "0002_dailyforecast")
    migrate_to = ("forecasts", "0003_dailyforecast_participant_skill_level")

    def test_legacy_rows_become_explicit_fail_closed_identities(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps
        WaterSpot = old_apps.get_model("spots", "WaterSpot")
        DailyForecast = old_apps.get_model("forecasts", "DailyForecast")
        spot = WaterSpot.objects.create(
            type="beach",
            name="Legacy daily surf",
            lat=37.8,
            lng=128.9,
            region="Gangwon",
            address="Gangneung",
        )
        target = timezone.now() + timedelta(days=1)

        def create_row(**overrides):
            values = {
                "spot": spot,
                "forecast_date": target.date(),
                "activity": "relax",
                "participant_profile": "general",
                "target_at": target,
                "score": 90,
                "safety_status": "clear",
                "decision": "recommended",
                "confidence": 1.0,
                "coverage": 1.0,
                "score_range": [85, 95],
                "gates": [],
                "contributions": [{"metric_name": "legacy"}],
                "missing_metrics": [],
                "stale_or_conflicting_metrics": [],
                "limitations": [],
                "availability": "available",
                "unavailable_reason": "",
                "evidence": [{"provider": "KHOA"}],
                "evidence_fingerprint": "a" * 64,
                "valid_from": target - timedelta(hours=1),
                "valid_until": target + timedelta(hours=1),
                "methodology_version": "water-index-v1.0.0",
                "projection_methodology_version": "daily-forecast-v1.0.0",
                "evaluated_at": timezone.now(),
            }
            values.update(overrides)
            return DailyForecast.objects.create(**values)

        surf = create_row(
            activity="surf",
            evidence_fingerprint="b" * 64,
            gates=[{"reason_code": "LEGACY_SURF"}],
        )
        partial = create_row(
            availability="partial",
            unavailable_reason="LEGACY_PARTIAL",
            evidence_fingerprint="c" * 64,
        )
        stopped = create_row(
            score=None,
            safety_status="stop",
            decision="blocked",
            score_range=[80, 90],
            contributions=[],
            evidence_fingerprint="d" * 64,
        )

        try:
            executor = MigrationExecutor(connection)
            executor.migrate([self.migrate_to])
            new_apps = executor.loader.project_state([self.migrate_to]).apps
            MigratedForecast = new_apps.get_model("forecasts", "DailyForecast")
            migrated_surf = MigratedForecast.objects.get(pk=surf.pk)
            migrated_partial = MigratedForecast.objects.get(pk=partial.pk)
            migrated_stop = MigratedForecast.objects.get(pk=stopped.pk)

            self.assertEqual(migrated_surf.participant_skill_level, "unspecified")
            self.assertEqual(migrated_surf.availability, "partial")
            self.assertEqual(migrated_surf.safety_status, "unknown")
            self.assertEqual(migrated_surf.decision, "unknown")
            self.assertIsNone(migrated_surf.score)
            self.assertEqual(migrated_surf.score_range, [])
            self.assertEqual(migrated_surf.contributions, [])
            self.assertIn("LEGACY_SURF", str(migrated_surf.gates))
            self.assertIn("SURF_SKILL_LEVEL_REQUIRED", str(migrated_surf.gates))

            self.assertEqual(migrated_partial.safety_status, "unknown")
            self.assertEqual(migrated_partial.decision, "unknown")
            self.assertIsNone(migrated_partial.score)
            self.assertEqual(migrated_partial.score_range, [])
            self.assertEqual(migrated_partial.contributions, [])

            self.assertEqual(migrated_stop.availability, "available")
            self.assertEqual(migrated_stop.safety_status, "stop")
            self.assertEqual(migrated_stop.decision, "blocked")
            self.assertEqual(migrated_stop.score_range, [])
            self.assertEqual(MigratedForecast.objects.count(), 3)
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
