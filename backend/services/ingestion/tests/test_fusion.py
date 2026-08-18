from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db.models.deletion import RestrictedError
from django.test import TestCase

from apps.conditions.models import (
    ObservationMetric,
    ObservationMetricLineage,
    ObservationSnapshot,
)
from apps.spots.models import WaterSpot
from services.ingestion.fusion import (
    FUSION_PROVIDER,
    environment_for_spot,
    evaluate_fused_spot,
    fuse_spot_observations,
)
from services.ingestion.khoa_adapter import adapt_mudflat_forecast
from services.ingestion.persistence import persist_observation
from services.providers.khoa import MudflatForecast
from services.water_index import (
    Activity,
    Decision,
    Environment,
    SafetyStatus,
    SURF_GRADE_SKILL_MISMATCH,
    SURF_SKILL_LEVEL_REQUIRED,
)


KST = ZoneInfo("Asia/Seoul")
AT = datetime(2026, 8, 16, 14, tzinfo=KST)


class ObservationFusionTests(TestCase):
    def setUp(self) -> None:
        self.spot = WaterSpot.objects.create(
            type="beach",
            name="경포해수욕장",
            lat=37.8055,
            lng=128.9070,
            region="강원",
            address="강원특별자치도 강릉시",
        )

    def add_metric(
        self,
        *,
        provider: str,
        source: str,
        name: str,
        value,
        state: str = "live",
        observed_at: datetime = AT - timedelta(minutes=5),
        fetched_at: datetime = AT - timedelta(minutes=2),
        confidence: float = 1.0,
        valid_from: datetime = AT - timedelta(minutes=10),
        valid_until: datetime = AT + timedelta(minutes=10),
    ) -> ObservationMetric:
        snapshot = ObservationSnapshot.objects.create(
            spot=self.spot,
            provider=provider,
            provider_record_id=f"{provider}-{name}-{ObservationSnapshot.objects.count()}",
            state=state,
            observed_at=observed_at,
            fetched_at=fetched_at,
            valid_from=valid_from,
            valid_until=valid_until,
            spatial_scope="test:point",
            source_url="https://example.go.kr/public",
            ingestion_version="test-v1",
        )
        value_fields = {
            "numeric_value": None,
            "text_value": None,
            "boolean_value": None,
        }
        if isinstance(value, bool):
            value_type = "boolean"
            value_fields["boolean_value"] = value
        elif isinstance(value, (int, float)):
            value_type = "number"
            value_fields["numeric_value"] = value
        else:
            value_type = "text"
            value_fields["text_value"] = str(value)
        return ObservationMetric.objects.create(
            snapshot=snapshot,
            name=name,
            value_type=value_type,
            **value_fields,
            unit="test",
            mode="observed",
            state="valid",
            confidence=confidence,
            source=source,
            source_url="https://example.go.kr/public",
            spatial_scope="test:point",
            observed_at=observed_at,
            fetched_at=fetched_at,
            valid_from=valid_from,
            valid_until=valid_until,
        )

    def test_fuses_domain_specific_sources_and_excludes_demo(self) -> None:
        grade = self.add_metric(
            provider="KHOA",
            source="KHOA",
            name="official_activity_grade",
            value="좋음",
        )
        temperature = self.add_metric(
            provider="KMA",
            source="KMA",
            name="air_temperature_c",
            value=27.0,
        )
        self.add_metric(
            provider="DEMO",
            source="LOCAL_AUTHORITY",
            name="official_entry_status",
            value="open",
            state="demo",
        )

        fused = fuse_spot_observations(spot=self.spot, at=AT, fetched_at=AT)

        self.assertEqual(
            set(fused.observations.metrics),
            {"official_activity_grade", "air_temperature_c"},
        )
        self.assertEqual(
            fused.source_metric_ids, tuple(sorted((grade.pk, temperature.pk)))
        )
        self.assertEqual(fused.provider, FUSION_PROVIDER)

    def test_rip_current_product_applies_to_surf_but_unrelated_beach_product_does_not(self) -> None:
        rip_current = self.add_metric(
            provider="KHOA",
            source="KHOA",
            name="rip_current_risk",
            value="attention",
        )
        rip_current.snapshot.provider_record_id = "rip-current:경포:202608181400"
        rip_current.snapshot.save(update_fields=("provider_record_id",))
        beach_grade = self.add_metric(
            provider="KHOA",
            source="KHOA",
            name="official_activity_grade",
            value="좋음",
        )
        beach_grade.snapshot.provider_record_id = "beach:경포:20260818:오후"
        beach_grade.snapshot.save(update_fields=("provider_record_id",))

        surf = fuse_spot_observations(
            spot=self.spot,
            activity=Activity.SURF,
            at=AT,
            fetched_at=AT,
        )

        self.assertIsNotNone(surf.observations.get("rip_current_risk"))
        self.assertIsNone(surf.observations.get("official_activity_grade"))

    def test_surf_scores_are_persisted_only_for_exact_authoritative_skill_scope(
        self,
    ) -> None:
        for provider, source, name, value in (
            (
                "LOCAL_AUTHORITY",
                "LOCAL_AUTHORITY",
                "official_entry_status",
                "open",
            ),
            ("KMA_WARNING", "KMA_WARNING", "weather_alert_level", "none"),
            (
                "KMA_LIGHTNING",
                "KMA_LIGHTNING",
                "lightning_clearance_minutes",
                30,
            ),
            ("KHOA", "KHOA", "rip_current_risk", "attention"),
            ("KMA_WARNING", "KMA_WARNING", "marine_hazard_status", "clear"),
            ("KHOA", "KHOA", "official_activity_grade", "매우좋음"),
            (
                "KHOA",
                "KHOA",
                "official_grade_detail",
                "초중급자에게 적합",
            ),
        ):
            metric = self.add_metric(
                provider=provider,
                source=source,
                name=name,
                value=value,
            )
            if name in {
                "rip_current_risk",
                "official_activity_grade",
                "official_grade_detail",
            }:
                prefix = "rip-current" if name == "rip_current_risk" else "surf"
                metric.snapshot.provider_record_id = f"{prefix}:scope:{name}"
                metric.snapshot.save(update_fields=("provider_record_id",))

        outcomes = {
            skill: evaluate_fused_spot(
                spot=self.spot,
                activity=Activity.SURF,
                at=AT,
                fetched_at=AT,
                participant_skill_level=skill,
                dry_run=False,
            )
            for skill in ("unspecified", "beginner", "intermediate", "advanced")
        }

        unscoped = outcomes["unspecified"].result
        self.assertEqual(unscoped.safety_status, SafetyStatus.CLEAR)
        self.assertEqual(unscoped.decision, Decision.UNKNOWN)
        self.assertIsNone(unscoped.score)
        self.assertIsNone(unscoped.score_range)
        self.assertTrue(
            any(
                gate.reason_code == SURF_SKILL_LEVEL_REQUIRED
                for gate in unscoped.gates
            )
        )
        for skill in ("beginner", "intermediate"):
            self.assertEqual(outcomes[skill].result.safety_status, SafetyStatus.CLEAR)
            self.assertIsNotNone(outcomes[skill].result.score)
            self.assertNotEqual(outcomes[skill].result.decision, Decision.UNKNOWN)
        advanced = outcomes["advanced"].result
        self.assertEqual(advanced.safety_status, SafetyStatus.CLEAR)
        self.assertEqual(advanced.decision, Decision.UNKNOWN)
        self.assertIsNone(advanced.score)
        self.assertIsNone(advanced.score_range)
        self.assertTrue(
            any(
                gate.reason_code == SURF_GRADE_SKILL_MISMATCH
                for gate in advanced.gates
            )
        )
        self.assertEqual(
            set(
                self.spot.conditionscore_set.values_list(
                    "participant_skill_level",
                    flat=True,
                )
            ),
            {"unspecified", "beginner", "intermediate", "advanced"},
        )

    def test_unapproved_source_cannot_clear_a_safety_gate(self) -> None:
        self.add_metric(
            provider="KMA",
            source="KMA",
            name="official_entry_status",
            value="open",
        )

        outcome = evaluate_fused_spot(
            spot=self.spot,
            activity=Activity.SWIM,
            at=AT,
            fetched_at=AT,
            participant_profile="general",
            dry_run=True,
        )

        self.assertIsNone(
            outcome.observation.observations.get("official_entry_status")
        )
        self.assertEqual(outcome.result.safety_status, SafetyStatus.UNKNOWN)
        self.assertIn("official_entry_status|access_status", outcome.result.missing_metrics)

    def test_stale_snapshot_cannot_be_revived_by_a_future_metric_expiry(self) -> None:
        self.add_metric(
            provider="LOCAL_AUTHORITY",
            source="LOCAL_AUTHORITY",
            name="official_entry_status",
            value="open",
            state="stale",
            valid_until=AT + timedelta(hours=6),
        )

        outcome = evaluate_fused_spot(
            spot=self.spot,
            activity=Activity.RELAX,
            at=AT,
            fetched_at=AT,
            dry_run=True,
        )

        self.assertIsNone(
            outcome.observation.observations.get("official_entry_status")
        )
        self.assertEqual(outcome.result.safety_status, SafetyStatus.UNKNOWN)
        self.assertIn(
            "official_entry_status|access_status",
            outcome.result.missing_metrics,
        )

    def test_official_stop_dominates_other_missing_inputs_and_persists(self) -> None:
        self.add_metric(
            provider="LOCAL_AUTHORITY",
            source="LOCAL_AUTHORITY",
            name="official_stop_signal",
            value=True,
        )

        outcome = evaluate_fused_spot(
            spot=self.spot,
            activity=Activity.SWIM,
            at=AT,
            fetched_at=AT,
            participant_profile="general",
            dry_run=False,
        )

        self.assertEqual(outcome.result.safety_status, SafetyStatus.STOP)
        self.assertIsNone(outcome.result.score)
        self.assertIsNotNone(outcome.persistence)
        score = self.spot.conditionscore_set.get()
        self.assertEqual(score.safety_status, "stop")
        self.assertIsNone(score.score)
        self.assertEqual(score.snapshot.provider, FUSION_PROVIDER)
        self.assertEqual(score.participant_profile, "general")

    def test_equal_authority_conflict_remains_unknown_not_clear(self) -> None:
        passed = self.add_metric(
            provider="MOE",
            source="MOE",
            name="water_quality_status",
            value="pass",
        )
        failed = self.add_metric(
            provider="LOCAL_AUTHORITY",
            source="LOCAL_AUTHORITY",
            name="water_quality_status",
            value="fail",
        )

        fused = fuse_spot_observations(spot=self.spot, at=AT, fetched_at=AT)
        metric = fused.observations.get("water_quality_status")

        self.assertEqual(metric.state.value, "conflict")
        outcome = evaluate_fused_spot(
            spot=self.spot,
            activity=Activity.SWIM,
            at=AT,
            fetched_at=AT,
            dry_run=False,
        )
        self.assertEqual(outcome.result.safety_status, SafetyStatus.UNKNOWN)
        self.assertIn("water_quality_status", outcome.result.stale_or_conflicting_metrics)
        derived = ObservationMetric.objects.get(
            snapshot__provider=FUSION_PROVIDER,
            name="water_quality_status",
        )
        lineage = {
            edge.source_metric_id: (edge.relation, edge.priority)
            for edge in derived.lineage_sources.all()
        }
        self.assertEqual(
            lineage,
            {
                failed.pk: (ObservationMetricLineage.Relation.SELECTED, 110),
                passed.pk: (ObservationMetricLineage.Relation.CONFLICT, 110),
            },
        )
        with self.assertRaises(RestrictedError):
            passed.delete()
        self.assertTrue(ObservationMetric.objects.filter(pk=passed.pk).exists())

        original_lineage_ids = tuple(
            derived.lineage_sources.order_by("pk").values_list("pk", flat=True)
        )
        evaluate_fused_spot(
            spot=self.spot,
            activity=Activity.SWIM,
            at=AT,
            fetched_at=AT,
            dry_run=False,
        )
        self.assertEqual(
            tuple(
                derived.lineage_sources.order_by("pk").values_list("pk", flat=True)
            ),
            original_lineage_ids,
        )
        self.spot.delete()
        self.assertEqual(ObservationMetricLineage.objects.count(), 0)

    def test_safety_conflict_ignores_source_priority_and_fails_closed(self) -> None:
        self.add_metric(
            provider="LOCAL_AUTHORITY",
            source="LOCAL_AUTHORITY",
            name="official_entry_status",
            value="open",
        )
        self.add_metric(
            provider="KHOA",
            source="KHOA",
            name="official_entry_status",
            value="closed",
        )

        fused = fuse_spot_observations(spot=self.spot, at=AT, fetched_at=AT)
        self.assertEqual(
            fused.observations.get("official_entry_status").state.value,
            "conflict",
        )
        outcome = evaluate_fused_spot(
            spot=self.spot,
            activity=Activity.SWIM,
            at=AT,
            fetched_at=AT,
            dry_run=True,
        )
        self.assertEqual(outcome.result.safety_status, SafetyStatus.UNKNOWN)
        self.assertIn(
            "official_entry_status|access_status",
            outcome.result.stale_or_conflicting_metrics,
        )

    def test_forged_provider_source_binding_and_unapproved_temperature_are_rejected(self) -> None:
        self.add_metric(
            provider="KMA",
            source="LOCAL_AUTHORITY",
            name="official_entry_status",
            value="open",
        )
        self.add_metric(
            provider="USER_REPORTED",
            source="USER_REPORTED",
            name="water_temperature_c",
            value=24,
        )
        self.add_metric(
            provider="USER_REPORTED",
            source="USER_REPORTED",
            name="official_activity_grade",
            value="very_good",
        )

        fused = fuse_spot_observations(spot=self.spot, at=AT, fetched_at=AT)

        self.assertIsNone(fused.observations.get("official_entry_status"))
        self.assertIsNone(fused.observations.get("water_temperature_c"))
        self.assertIsNone(fused.observations.get("official_activity_grade"))

    def test_fused_snapshot_uses_earliest_metric_specific_safety_expiry(self) -> None:
        self.add_metric(
            provider="LOCAL_AUTHORITY",
            source="LOCAL_AUTHORITY",
            name="official_entry_status",
            value="open",
            observed_at=AT - timedelta(minutes=1),
            fetched_at=AT,
        )
        self.add_metric(
            provider="KMA_WARNING",
            source="KMA_WARNING",
            name="weather_alert_level",
            value="none",
            observed_at=AT - timedelta(minutes=1),
            fetched_at=AT,
        )
        self.add_metric(
            provider="KMA_LIGHTNING",
            source="KMA_LIGHTNING",
            name="lightning_clearance_minutes",
            value=30,
            observed_at=AT - timedelta(minutes=1),
            fetched_at=AT,
        )
        self.add_metric(
            provider="KMA_WARNING",
            source="KMA_WARNING",
            name="marine_hazard_status",
            value="clear",
            observed_at=AT - timedelta(minutes=1),
            fetched_at=AT,
        )

        outcome = evaluate_fused_spot(
            spot=self.spot,
            activity=Activity.RELAX,
            at=AT,
            fetched_at=AT,
            dry_run=False,
        )

        expected_expiry = AT + timedelta(minutes=4)
        self.assertEqual(outcome.observation.valid_until, expected_expiry)
        self.assertEqual(
            ObservationSnapshot.objects.get(provider=FUSION_PROVIDER).valid_until,
            expected_expiry,
        )

    def test_relax_fusion_without_official_access_expires_immediately(self) -> None:
        self.add_metric(
            provider="KMA_WARNING",
            source="KMA_WARNING",
            name="weather_alert_level",
            value="none",
            observed_at=AT - timedelta(minutes=1),
            fetched_at=AT,
        )
        self.add_metric(
            provider="KMA_LIGHTNING",
            source="KMA_LIGHTNING",
            name="lightning_clearance_minutes",
            value=30,
            observed_at=AT - timedelta(minutes=1),
            fetched_at=AT,
        )
        self.add_metric(
            provider="KMA_WARNING",
            source="KMA_WARNING",
            name="marine_hazard_status",
            value="clear",
            observed_at=AT - timedelta(minutes=1),
            fetched_at=AT,
        )

        outcome = evaluate_fused_spot(
            spot=self.spot,
            activity=Activity.RELAX,
            at=AT,
            fetched_at=AT,
            dry_run=False,
        )

        self.assertEqual(outcome.result.safety_status, SafetyStatus.UNKNOWN)
        self.assertIsNone(outcome.result.score)
        self.assertIn(
            "official_entry_status|access_status",
            outcome.result.missing_metrics,
        )
        self.assertEqual(outcome.observation.valid_until, AT)
        self.assertEqual(
            ObservationSnapshot.objects.get(provider=FUSION_PROVIDER).valid_until,
            AT,
        )

    def test_fusion_derives_mudflat_gate_from_official_boundaries_at_requested_time(
        self,
    ) -> None:
        self.spot.type = "mudflat"
        self.spot.save(update_fields=("type",))
        record = MudflatForecast(
            place_name="경포해수욕장",
            latitude=Decimal("37.8055"),
            longitude=Decimal("128.9070"),
            forecast_date=date(2026, 8, 16),
            experience_start_time="15:00",
            experience_end_time="16:00",
            weather=None,
            score=None,
            official_grade=None,
            maximum_air_temperature=None,
            minimum_air_temperature=None,
            maximum_wind_speed=None,
            minimum_wind_speed=None,
        )
        source_observation = adapt_mudflat_forecast(
            record,
            fetched_at=datetime(2026, 8, 16, 13, tzinfo=KST),
        )
        persisted = persist_observation(
            spot=self.spot,
            observation=source_observation,
        )
        source_snapshot = ObservationSnapshot.objects.get(pk=persisted.snapshot_id)
        boundary_ids = set(
            source_snapshot.metrics.filter(
                name__in=(
                    "official_tide_window_start",
                    "official_tide_window_end",
                )
            ).values_list("pk", flat=True)
        )

        before = fuse_spot_observations(
            spot=self.spot,
            at=datetime(2026, 8, 16, 14, 59, tzinfo=KST),
            fetched_at=datetime(2026, 8, 16, 14, 59, tzinfo=KST),
        )
        inside = fuse_spot_observations(
            spot=self.spot,
            at=datetime(2026, 8, 16, 15, 30, tzinfo=KST),
            fetched_at=datetime(2026, 8, 16, 15, 30, tzinfo=KST),
        )
        after_at = datetime(2026, 8, 16, 16, 1, tzinfo=KST)
        after = fuse_spot_observations(
            spot=self.spot,
            at=after_at,
            fetched_at=after_at,
        )
        unrelated_at = datetime(2026, 8, 17, 10, tzinfo=KST)
        unrelated = fuse_spot_observations(
            spot=self.spot,
            at=unrelated_at,
            fetched_at=unrelated_at,
        )

        self.assertIs(before.observations.get("tide_window_open").value, False)
        self.assertIs(inside.observations.get("tide_window_open").value, True)
        self.assertIs(after.observations.get("tide_window_open").value, False)
        self.assertIsNone(unrelated.observations.get("tide_window_open"))
        self.assertEqual(set(after.source_metric_ids), boundary_ids)

        outcome = evaluate_fused_spot(
            spot=self.spot,
            activity=Activity.MUDFLAT,
            at=after_at,
            fetched_at=after_at,
            dry_run=False,
        )
        self.assertEqual(outcome.result.safety_status, SafetyStatus.STOP)
        derived = ObservationMetric.objects.get(
            snapshot__provider=FUSION_PROVIDER,
            name="tide_window_open",
        )
        self.assertIs(derived.value, False)
        self.assertEqual(
            set(
                derived.lineage_sources.values_list("source_metric_id", flat=True)
            ),
            boundary_ids,
        )
        self.assertEqual(
            set(derived.lineage_sources.values_list("relation", flat=True)),
            {ObservationMetricLineage.Relation.SELECTED},
        )

    def test_environment_is_derived_without_promoting_unknown_types(self) -> None:
        self.assertEqual(environment_for_spot(self.spot), Environment.MARINE_BEACH)
        self.spot.type = "river"
        self.assertEqual(environment_for_spot(self.spot), Environment.INLAND_WATER)
        self.spot.type = "unmapped"
        self.assertEqual(environment_for_spot(self.spot), Environment.WATERSIDE)

    def test_general_and_family_evaluations_persist_without_overwriting(self) -> None:
        evaluate_fused_spot(
            spot=self.spot,
            activity=Activity.SWIM,
            at=AT,
            fetched_at=AT,
            participant_profile="general",
            dry_run=False,
        )
        evaluate_fused_spot(
            spot=self.spot,
            activity=Activity.SWIM,
            at=AT,
            fetched_at=AT,
            participant_profile="beginner",
            dry_run=False,
        )

        scores = self.spot.conditionscore_set.order_by("participant_profile")
        self.assertEqual(scores.count(), 2)
        self.assertEqual(
            set(scores.values_list("participant_profile", flat=True)),
            {"general", "family"},
        )
        self.assertEqual(
            ObservationSnapshot.objects.filter(provider=FUSION_PROVIDER).count(),
            2,
        )

    def test_scheduler_retries_reuse_stable_outcome_and_record_one_expiry_transition(
        self,
    ) -> None:
        for provider, source, name, value in (
            (
                "LOCAL_AUTHORITY",
                "LOCAL_AUTHORITY",
                "official_entry_status",
                "open",
            ),
            ("KMA_WARNING", "KMA_WARNING", "weather_alert_level", "none"),
            (
                "KMA_LIGHTNING",
                "KMA_LIGHTNING",
                "lightning_clearance_minutes",
                30,
            ),
            ("KMA_WARNING", "KMA_WARNING", "marine_hazard_status", "clear"),
        ):
            self.add_metric(
                provider=provider,
                source=source,
                name=name,
                value=value,
                observed_at=AT - timedelta(minutes=1),
                fetched_at=AT,
                valid_until=AT + timedelta(minutes=30),
            )

        first = evaluate_fused_spot(
            spot=self.spot,
            activity=Activity.RELAX,
            at=AT,
            fetched_at=AT,
            dry_run=False,
        )
        repeated = evaluate_fused_spot(
            spot=self.spot,
            activity=Activity.RELAX,
            at=AT + timedelta(minutes=1),
            fetched_at=AT + timedelta(minutes=1),
            dry_run=False,
        )
        expired = evaluate_fused_spot(
            spot=self.spot,
            activity=Activity.RELAX,
            at=AT + timedelta(minutes=6),
            fetched_at=AT + timedelta(minutes=6),
            dry_run=False,
        )
        expired_retry = evaluate_fused_spot(
            spot=self.spot,
            activity=Activity.RELAX,
            at=AT + timedelta(minutes=7),
            fetched_at=AT + timedelta(minutes=7),
            dry_run=False,
        )

        self.assertEqual(first.persistence.snapshot_id, repeated.persistence.snapshot_id)
        self.assertFalse(repeated.persistence.snapshot_created)
        self.assertFalse(repeated.persistence.score_created)
        self.assertNotEqual(first.persistence.snapshot_id, expired.persistence.snapshot_id)
        self.assertEqual(
            expired.persistence.snapshot_id,
            expired_retry.persistence.snapshot_id,
        )
        self.assertEqual(
            ObservationSnapshot.objects.filter(provider=FUSION_PROVIDER).count(),
            2,
        )
        self.assertEqual(self.spot.conditionscore_set.count(), 2)
        first_score = self.spot.conditionscore_set.get(pk=first.persistence.score_id)
        self.assertEqual(first_score.evaluated_at, AT)
        self.assertEqual(expired.result.safety_status, SafetyStatus.UNKNOWN)
