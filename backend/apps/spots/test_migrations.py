from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class CuratedIdentifierMigrationTests(TransactionTestCase):
    migrate_from = ("spots", "0002_alter_waterspot_options_and_more")
    migrate_to = ("spots", "0003_unique_curated_provider_identifiers")

    def test_duplicate_identifiers_fail_without_modifying_legacy_rows(self) -> None:
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        historical_apps = executor.loader.project_state([self.migrate_from]).apps
        HistoricalWaterSpot = historical_apps.get_model("spots", "WaterSpot")
        common = {
            "type": "beach",
            "lat": 37.8,
            "lng": 128.9,
            "region": "강원",
            "address": "강원특별자치도 강릉시",
            "tourapi_id": "duplicate-tour-id",
            "khoa_beach_code": "duplicate-khoa-code",
        }
        first = HistoricalWaterSpot.objects.create(name="첫 장소", **common)
        second = HistoricalWaterSpot.objects.create(name="둘째 장소", **common)

        try:
            with self.assertRaisesRegex(
                RuntimeError,
                "tourapi_id, khoa_beach_code.*does not modify",
            ):
                MigrationExecutor(connection).migrate([self.migrate_to])

            rows = tuple(
                HistoricalWaterSpot.objects.filter(pk__in=(first.pk, second.pk))
                .order_by("pk")
                .values_list("tourapi_id", "khoa_beach_code")
            )
            self.assertEqual(
                rows,
                (
                    ("duplicate-tour-id", "duplicate-khoa-code"),
                    ("duplicate-tour-id", "duplicate-khoa-code"),
                ),
            )
        finally:
            # The production migration never chooses a winner. This cleanup is
            # limited to the disposable test database so the suite can restore
            # the latest schema even when the assertion above fails.
            HistoricalWaterSpot.objects.filter(pk=second.pk).delete()
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
