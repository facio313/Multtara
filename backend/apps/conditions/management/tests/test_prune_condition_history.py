from __future__ import annotations

from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.conditions.models import (
    ConditionScore,
    IngestionRun,
    ObservationMetric,
    ObservationMetricLineage,
    ObservationSnapshot,
)
from apps.forecasts.models import DailyForecast, WaterForecast
from apps.spots.models import WaterSpot
from apps.trips.models import Itinerary, RouteMatrixSnapshot
from services.ingestion.fusion import (
    DERIVED_PROVIDER,
    FUSION_PROVIDER,
    FUSION_VERSION,
)


class PruneConditionHistoryTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.spot = WaterSpot.objects.create(
            type="beach",
            name="보존 테스트",
            lat=37.8,
            lng=128.9,
            region="강릉",
            address="강릉시",
        )

    def snapshot(self, provider, record_id, *, age_days):
        row = ObservationSnapshot.objects.create(
            spot=self.spot,
            provider=provider,
            provider_record_id=record_id,
            state="live",
            fetched_at=self.now - timedelta(days=age_days),
            spatial_scope=f"spot:{self.spot.pk}",
            ingestion_version=(FUSION_VERSION if provider == FUSION_PROVIDER else "v1"),
        )
        ObservationSnapshot.objects.filter(pk=row.pk).update(
            created_at=self.now - timedelta(days=age_days)
        )
        row.refresh_from_db()
        return row

    def score(
        self,
        snapshot,
        *,
        age_days,
        safety="unknown",
        activity="swim",
        participant_skill_level="unspecified",
    ):
        decision = "blocked" if safety == "stop" else "unknown"
        row = ConditionScore.objects.create(
            spot=self.spot,
            snapshot=snapshot,
            activity=activity,
            participant_profile="general",
            participant_skill_level=participant_skill_level,
            score=None,
            safety_status=safety,
            decision=decision,
            confidence=0,
            coverage=0,
            methodology_version="test-methodology-v1",
            evaluated_at=self.now - timedelta(days=age_days),
        )
        ConditionScore.objects.filter(pk=row.pk).update(
            computed_at=self.now - timedelta(days=age_days)
        )
        row.refresh_from_db()
        return row

    def test_retention_preserves_latest_row_for_each_surf_skill_identity(self):
        rows = {}
        for skill, suffix in (("beginner", "b"), ("advanced", "a")):
            old_snapshot = self.snapshot(
                FUSION_PROVIDER,
                f"surf-{suffix}-old",
                age_days=60,
            )
            latest_snapshot = self.snapshot(
                FUSION_PROVIDER,
                f"surf-{suffix}-latest",
                age_days=50,
            )
            rows[(skill, "old")] = self.score(
                old_snapshot,
                age_days=60,
                activity="surf",
                participant_skill_level=skill,
            )
            rows[(skill, "latest")] = self.score(
                latest_snapshot,
                age_days=50,
                activity="surf",
                participant_skill_level=skill,
            )

        call_command(
            "prune_condition_history",
            "--score-days",
            "30",
            "--fusion-days",
            "30",
            stdout=StringIO(),
        )

        for skill in ("beginner", "advanced"):
            self.assertFalse(
                ConditionScore.objects.filter(
                    pk=rows[(skill, "old")].pk
                ).exists()
            )
            self.assertTrue(
                ConditionScore.objects.filter(
                    pk=rows[(skill, "latest")].pk
                ).exists()
            )

    def metric(self, snapshot, name, value, *, age_days):
        observed_at = self.now - timedelta(days=age_days)
        return ObservationMetric.objects.create(
            snapshot=snapshot,
            name=name,
            value_type="number",
            numeric_value=value,
            unit="test",
            mode="observed",
            state="valid",
            confidence=1,
            source=snapshot.provider,
            spatial_scope=snapshot.spatial_scope,
            observed_at=observed_at,
            fetched_at=observed_at,
            valid_from=observed_at,
            valid_until=self.now + timedelta(days=1),
        )

    def test_dry_run_then_prune_preserves_latest_and_longer_stop_audit(self):
        old_source = self.snapshot("KMA", "old", age_days=120)
        latest_source = self.snapshot("KMA", "latest", age_days=100)
        old_fusion = self.snapshot(FUSION_PROVIDER, "fusion-old", age_days=50)
        newer_fusion = self.snapshot(FUSION_PROVIDER, "fusion-latest", age_days=40)
        old_score = self.score(old_fusion, age_days=50)
        latest_score = self.score(newer_fusion, age_days=40)
        old_stop_snapshot = self.snapshot(
            FUSION_PROVIDER,
            "fusion-stop",
            age_days=100,
        )
        stop_score = self.score(old_stop_snapshot, age_days=100, safety="stop")

        output = StringIO()
        call_command(
            "prune_condition_history",
            "--dry-run",
            "--score-days",
            "30",
            "--fusion-days",
            "30",
            "--source-days",
            "90",
            stdout=output,
        )
        self.assertTrue(ConditionScore.objects.filter(pk=old_score.pk).exists())
        self.assertIn("dry-run", output.getvalue())

        call_command(
            "prune_condition_history",
            "--score-days",
            "30",
            "--safety-days",
            "365",
            "--fusion-days",
            "30",
            "--source-days",
            "90",
            stdout=StringIO(),
        )

        self.assertFalse(ConditionScore.objects.filter(pk=old_score.pk).exists())
        self.assertTrue(ConditionScore.objects.filter(pk=latest_score.pk).exists())
        self.assertTrue(ConditionScore.objects.filter(pk=stop_score.pk).exists())
        self.assertFalse(ObservationSnapshot.objects.filter(pk=old_source.pk).exists())
        self.assertTrue(ObservationSnapshot.objects.filter(pk=latest_source.pk).exists())
        self.assertFalse(ObservationSnapshot.objects.filter(pk=old_fusion.pk).exists())
        self.assertTrue(ObservationSnapshot.objects.filter(pk=newer_fusion.pk).exists())
        self.assertTrue(
            ObservationSnapshot.objects.filter(pk=old_stop_snapshot.pk).exists()
        )

    def test_lineage_protects_derived_and_original_evidence_until_consumer_is_removed(self):
        old_source = self.snapshot("KMA", "source-old", age_days=120)
        self.snapshot("KMA", "source-latest", age_days=100)
        source_metric = self.metric(
            old_source,
            "air_temperature_c",
            25,
            age_days=120,
        )
        old_derived = self.snapshot(
            DERIVED_PROVIDER,
            "derived-old",
            age_days=120,
        )
        self.snapshot(
            DERIVED_PROVIDER,
            "derived-latest",
            age_days=100,
        )
        derived_metric = self.metric(
            old_derived,
            "hci_beach_score",
            80,
            age_days=120,
        )
        ObservationMetricLineage.objects.create(
            derived_metric=derived_metric,
            source_metric=source_metric,
            relation="selected",
            priority=110,
        )
        fused = self.snapshot(FUSION_PROVIDER, "fused-consumer", age_days=40)
        fused_metric = self.metric(
            fused,
            "hci_beach_score",
            80,
            age_days=40,
        )
        ObservationMetricLineage.objects.create(
            derived_metric=fused_metric,
            source_metric=derived_metric,
            relation="selected",
            priority=110,
        )

        call_command(
            "prune_condition_history",
            "--fusion-days",
            "30",
            "--derived-days",
            "90",
            "--source-days",
            "90",
            stdout=StringIO(),
        )
        self.assertTrue(
            ObservationSnapshot.objects.filter(pk=old_derived.pk).exists()
        )
        self.assertTrue(
            ObservationSnapshot.objects.filter(pk=old_source.pk).exists()
        )

        fused.delete()
        call_command(
            "prune_condition_history",
            "--derived-days",
            "90",
            "--source-days",
            "90",
            stdout=StringIO(),
        )
        self.assertFalse(
            ObservationSnapshot.objects.filter(pk=old_derived.pk).exists()
        )
        self.assertFalse(
            ObservationSnapshot.objects.filter(pk=old_source.pk).exists()
        )

    def test_prunes_forecasts_routes_and_runs_without_breaking_audit_references(self):
        old_daily = self.daily_forecast("old-daily", age_days=120)
        retained_stop = self.daily_forecast(
            "retained-stop",
            age_days=120,
            safety="stop",
        )
        expired_stop = self.daily_forecast(
            "expired-stop",
            age_days=400,
            safety="stop",
        )
        old_legacy = WaterForecast.objects.create(
            spot=self.spot,
            forecast_date=timezone.localdate(),
            predicted_index=42,
        )
        WaterForecast.objects.filter(pk=old_legacy.pk).update(
            computed_at=self.now - timedelta(days=40)
        )
        recent_legacy = WaterForecast.objects.create(
            spot=self.spot,
            forecast_date=timezone.localdate() + timedelta(days=1),
            predicted_index=43,
        )

        unreferenced_route = self.route_snapshot("route-unreferenced", age_days=100)
        referenced_route = self.route_snapshot("route-referenced", age_days=90)
        latest_route = self.route_snapshot("route-latest", age_days=80)
        referenced_fusion = self.snapshot(
            FUSION_PROVIDER,
            "itinerary-water-score",
            age_days=60,
        )
        referenced_score = self.score(referenced_fusion, age_days=60)
        referenced_snapshot_only = self.snapshot(
            FUSION_PROVIDER,
            "itinerary-water-snapshot",
            age_days=55,
        )
        newest_fusion = self.snapshot(
            FUSION_PROVIDER,
            "itinerary-water-latest",
            age_days=40,
        )
        newest_score = self.score(newest_fusion, age_days=40)
        user = get_user_model().objects.create_user(
            username="retention-user",
            password="strong-test-password",
        )
        Itinerary.objects.create(
            user=user,
            start_point="강릉역",
            route_snapshot_ids=[referenced_route.pk],
            water_evidence=[
                {
                    "condition_score_id": referenced_score.pk,
                    "snapshot_id": referenced_fusion.pk,
                },
                {
                    "condition_score_id": None,
                    "snapshot_id": referenced_snapshot_only.pk,
                },
            ],
        )

        old_run = self.ingestion_run("weather", age_days=40)
        latest_run = self.ingestion_run("weather", age_days=35)
        old_failed_run = self.ingestion_run(
            "marine",
            age_days=100,
            status=IngestionRun.Status.FAILED,
        )
        latest_failed_run = self.ingestion_run(
            "marine",
            age_days=95,
            status=IngestionRun.Status.FAILED,
        )

        output = StringIO()
        call_command(
            "prune_condition_history",
            "--forecast-days",
            "90",
            "--safety-days",
            "365",
            "--legacy-days",
            "30",
            "--route-days",
            "30",
            "--run-days",
            "30",
            "--failed-run-days",
            "90",
            stdout=output,
        )

        self.assertFalse(DailyForecast.objects.filter(pk=old_daily.pk).exists())
        self.assertTrue(DailyForecast.objects.filter(pk=retained_stop.pk).exists())
        self.assertFalse(DailyForecast.objects.filter(pk=expired_stop.pk).exists())
        self.assertFalse(WaterForecast.objects.filter(pk=old_legacy.pk).exists())
        self.assertTrue(WaterForecast.objects.filter(pk=recent_legacy.pk).exists())
        self.assertFalse(
            RouteMatrixSnapshot.objects.filter(pk=unreferenced_route.pk).exists()
        )
        self.assertTrue(
            RouteMatrixSnapshot.objects.filter(pk=referenced_route.pk).exists()
        )
        self.assertTrue(RouteMatrixSnapshot.objects.filter(pk=latest_route.pk).exists())
        self.assertTrue(ConditionScore.objects.filter(pk=referenced_score.pk).exists())
        self.assertTrue(ConditionScore.objects.filter(pk=newest_score.pk).exists())
        self.assertTrue(
            ObservationSnapshot.objects.filter(pk=referenced_fusion.pk).exists()
        )
        self.assertTrue(
            ObservationSnapshot.objects.filter(pk=referenced_snapshot_only.pk).exists()
        )
        self.assertFalse(IngestionRun.objects.filter(pk=old_run.pk).exists())
        self.assertTrue(IngestionRun.objects.filter(pk=latest_run.pk).exists())
        self.assertFalse(IngestionRun.objects.filter(pk=old_failed_run.pk).exists())
        self.assertTrue(IngestionRun.objects.filter(pk=latest_failed_run.pk).exists())
        self.assertIn("route_snapshots=1", output.getvalue())

    def daily_forecast(self, fingerprint, *, age_days, safety="unknown"):
        target_at = self.now - timedelta(days=age_days)
        row = DailyForecast.objects.create(
            spot=self.spot,
            forecast_date=target_at.date(),
            activity="swim",
            participant_profile="general",
            target_at=target_at,
            score=None,
            safety_status=safety,
            decision="blocked" if safety == "stop" else "unknown",
            confidence=0,
            coverage=0,
            availability="available" if safety == "stop" else "unavailable",
            unavailable_reason="" if safety == "stop" else "test_retention",
            evidence_fingerprint=fingerprint,
            methodology_version="test-methodology-v1",
            projection_methodology_version="test-projection-v1",
            evaluated_at=target_at,
        )
        DailyForecast.objects.filter(pk=row.pk).update(computed_at=target_at)
        row.refresh_from_db()
        return row

    def route_snapshot(self, record_id, *, age_days):
        observed_at = self.now - timedelta(days=age_days)
        return RouteMatrixSnapshot.objects.create(
            provider="valhalla",
            transport="drive",
            provider_record_id=record_id,
            observed_at=observed_at,
            fetched_at=observed_at + timedelta(hours=1),
            valid_until=observed_at + timedelta(days=1),
            source_url="https://routing.example.test",
            spot_set_hash=record_id,
        )

    def ingestion_run(self, task_name, *, age_days, status="succeeded"):
        started_at = self.now - timedelta(days=age_days)
        return IngestionRun.objects.create(
            task_name=task_name,
            status=status,
            started_at=started_at,
            finished_at=started_at + timedelta(minutes=1),
            error_code="COMMAND_FAILED" if status == "failed" else "",
        )
