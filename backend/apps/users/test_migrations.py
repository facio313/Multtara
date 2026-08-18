from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class LegacyUserActivityMigrationTests(TransactionTestCase):
    migrate_from = ("users", "0001_initial")
    migrate_to = ("users", "0002_user_profile_and_verified_activity")
    spots_state = ("spots", "0003_unique_curated_provider_identifiers")

    def test_out_of_range_rating_is_preserved_as_note_before_constraint(self) -> None:
        executor = MigrationExecutor(connection)
        # users.0001 predates the current WaterSpot columns, while users.0002
        # deliberately depends on spots.0003. Keep the spot schema at that
        # dependency state so the historical ORM matches the physical table.
        source_state = [self.migrate_from, self.spots_state]
        executor.migrate(source_state)
        old_apps = executor.loader.project_state(source_state).apps
        HistoricalUser = old_apps.get_model("users", "User")
        HistoricalWaterSpot = old_apps.get_model("spots", "WaterSpot")
        HistoricalActivity = old_apps.get_model("users", "UserActivity")
        user = HistoricalUser.objects.create(
            username="legacy-rating-user",
            password="unusable",
        )
        spot = HistoricalWaterSpot.objects.create(
            type="beach",
            name="Legacy rating beach",
            lat=37.8,
            lng=128.9,
            region="Gangwon",
            address="Gangneung",
        )
        original_text = "원래 사용자가 남긴 문장과 공백  "
        invalid = HistoricalActivity.objects.create(
            user=user,
            spot=spot,
            action="click",
            rating=9,
            review_text=original_text,
        )
        valid = HistoricalActivity.objects.create(
            user=user,
            spot=spot,
            action="visited",
            rating=5,
            review_text="",
        )

        try:
            executor = MigrationExecutor(connection)
            executor.migrate([self.migrate_to])
            new_apps = executor.loader.project_state([self.migrate_to]).apps
            MigratedActivity = new_apps.get_model("users", "UserActivity")
            migrated_invalid = MigratedActivity.objects.get(pk=invalid.pk)
            migrated_valid = MigratedActivity.objects.get(pk=valid.pk)

            self.assertEqual(migrated_invalid.action, "review")
            self.assertIsNone(migrated_invalid.rating)
            self.assertEqual(
                migrated_invalid.review_text,
                original_text
                + "\n\n[PONGDANG_LEGACY_RATING_OUT_OF_RANGE=9]",
            )
            self.assertEqual(migrated_invalid.user_id, user.pk)
            self.assertEqual(migrated_invalid.spot_id, spot.pk)

            self.assertEqual(migrated_valid.action, "review")
            self.assertEqual(migrated_valid.rating, 5)
            self.assertEqual(migrated_valid.review_text, "")
            self.assertEqual(
                MigratedActivity.objects.filter(pk__in=(invalid.pk, valid.pk)).count(),
                2,
            )
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
