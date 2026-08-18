from __future__ import annotations

from datetime import timedelta

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class ConditionScoreSurfSkillMigrationTests(TransactionTestCase):
    migrate_from = ("conditions", "0006_hydraulic_calibration")
    migrate_to = ("conditions", "0007_conditionscore_participant_skill_level")

    def test_legacy_surf_and_null_ranges_are_normalized_without_losing_rows(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps
        WaterSpot = old_apps.get_model("spots", "WaterSpot")
        ConditionScore = old_apps.get_model("conditions", "ConditionScore")
        spot = WaterSpot.objects.create(
            type="beach",
            name="Legacy surf condition",
            lat=37.8,
            lng=128.9,
            region="Gangwon",
            address="Gangneung",
        )
        now = timezone.now()
        surf = ConditionScore.objects.create(
            spot=spot,
            activity="surf",
            participant_profile="general",
            score=88,
            safety_status="clear",
            decision="recommended",
            confidence=1.0,
            coverage=0.8,
            score_range=[80, 90],
            gates=[{"reason_code": "LEGACY_SURF"}],
            missing_metrics=[],
            methodology_version="water-index-v1.0.0",
            evaluated_at=now,
        )
        stopped = ConditionScore.objects.create(
            spot=spot,
            activity="swim",
            participant_profile="general",
            score=None,
            safety_status="stop",
            decision="blocked",
            score_range=[80, 90],
            methodology_version="water-index-v1.0.0",
            evaluated_at=now - timedelta(minutes=1),
        )

        try:
            executor = MigrationExecutor(connection)
            executor.migrate([self.migrate_to])
            new_apps = executor.loader.project_state([self.migrate_to]).apps
            MigratedScore = new_apps.get_model("conditions", "ConditionScore")
            migrated_surf = MigratedScore.objects.get(pk=surf.pk)
            migrated_stop = MigratedScore.objects.get(pk=stopped.pk)

            self.assertEqual(migrated_surf.participant_skill_level, "unspecified")
            self.assertEqual(migrated_surf.safety_status, "clear")
            self.assertEqual(migrated_surf.decision, "unknown")
            self.assertIsNone(migrated_surf.score)
            self.assertEqual(migrated_surf.score_range, [])
            self.assertIn("LEGACY_SURF", str(migrated_surf.gates))
            self.assertIn("SURF_SKILL_LEVEL_REQUIRED", str(migrated_surf.gates))
            self.assertIn(
                "participant_skill_level",
                migrated_surf.missing_metrics,
            )
            self.assertEqual(migrated_stop.score_range, [])
            self.assertEqual(MigratedScore.objects.count(), 2)
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
