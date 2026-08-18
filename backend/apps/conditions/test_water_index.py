"""Invariant and boundary tests for the research-backed Water Index v1."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from unittest import TestCase

from services.water_index import (
    Activity,
    Decision,
    Environment,
    EvaluationContext,
    Metric,
    MetricMode,
    MetricState,
    ObservationSet,
    SafetyStatus,
    calculate_hci_beach,
    evaluate_water_index,
)


NOW = datetime(2026, 8, 15, 12, tzinfo=UTC)


def metric(
    name: str,
    value: float | int | str | bool,
    *,
    valid_for: timedelta | None = timedelta(hours=1),
    observed_ago: timedelta = timedelta(minutes=5),
    state: MetricState = MetricState.VALID,
    confidence: float = 1.0,
) -> Metric:
    return Metric(
        name=name,
        value=value,
        unit="canonical",
        source="test-authority",
        spatial_scope="spot:test-beach",
        observed_at=NOW - observed_ago,
        fetched_at=NOW - timedelta(minutes=1),
        valid_until=NOW + valid_for if valid_for is not None else None,
        source_url="https://example.test/source",
        confidence=confidence,
        state=state,
    )


def family_swim_metrics(*extra: Metric) -> ObservationSet:
    base = {
        item.name: item
        for item in (
            metric("official_entry_status", "open"),
            metric("weather_alert_level", "none"),
            metric("lightning_clearance_minutes", 30),
            metric("rip_current_risk", "attention"),
            metric("water_quality_status", "pass", valid_for=timedelta(days=1)),
            metric("marine_hazard_status", "clear"),
            metric("patrol_status", "active"),
            metric("designated_swim_zone_status", "open"),
            metric("adult_supervision_status", "confirmed"),
            metric("official_activity_grade", "very_good", valid_for=timedelta(hours=8)),
            metric("water_temperature_c", 24),
            metric("air_temperature_c", 26),
            metric("wave_height_m", 0.3),
            metric("wind_speed_ms", 3),
            metric("precipitation_1h_mm", 0),
            metric("uv_index", 3),
            metric("crowd_level", "low"),
        )
    }
    base.update({item.name: item for item in extra})
    return ObservationSet(base)


def family_context() -> EvaluationContext:
    return EvaluationContext(
        activity=Activity.SWIM,
        environment=Environment.MARINE_BEACH,
        participant_profile="family",
        at=NOW,
    )


class DomainContractTests(TestCase):
    def test_metric_requires_timezone_aware_timestamps(self):
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            Metric(
                name="air_temperature_c",
                value=20,
                unit="celsius",
                source="test",
                spatial_scope="spot:1",
                observed_at=datetime(2026, 8, 15, 12),
                fetched_at=NOW,
                valid_until=NOW + timedelta(hours=1),
            )

    def test_metric_requires_spatial_scope(self):
        with self.assertRaisesRegex(ValueError, "spatial_scope"):
            Metric(
                name="air_temperature_c",
                value=20,
                unit="celsius",
                source="test",
                spatial_scope="",
                observed_at=NOW,
                fetched_at=NOW,
                valid_until=NOW + timedelta(hours=1),
            )

    def test_numeric_metric_value_must_be_finite(self):
        for invalid in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(
                ValueError, "finite"
            ):
                metric("lightning_clearance_minutes", invalid)

    def test_observed_metric_cannot_come_from_the_future(self):
        with self.assertRaisesRegex(ValueError, "observed_at cannot be later"):
            Metric(
                name="air_temperature_c",
                value=20,
                unit="celsius",
                source="test",
                spatial_scope="spot:1",
                observed_at=NOW,
                fetched_at=NOW - timedelta(seconds=1),
                valid_until=NOW + timedelta(hours=1),
            )

    def test_forecast_requires_an_explicit_validity_window(self):
        with self.assertRaisesRegex(ValueError, "forecast metrics require"):
            Metric(
                name="air_temperature_c",
                value=20,
                unit="celsius",
                source="test",
                spatial_scope="spot:1",
                observed_at=NOW - timedelta(minutes=10),
                fetched_at=NOW - timedelta(minutes=9),
                valid_until=NOW + timedelta(hours=1),
                mode=MetricMode.FORECAST,
            )

    def test_observed_value_is_not_current_before_its_observation_time(self):
        future_observation = Metric(
            name="air_temperature_c",
            value=20,
            unit="celsius",
            source="test",
            spatial_scope="spot:1",
            observed_at=NOW + timedelta(minutes=1),
            fetched_at=NOW + timedelta(minutes=2),
            valid_until=NOW + timedelta(hours=1),
        )
        self.assertFalse(future_observation.is_current(NOW, max_age_seconds=3600))

    def test_explicit_validity_cannot_extend_a_shorter_policy_max_age(self):
        lightning = metric(
            "lightning_clearance_minutes",
            30,
            valid_for=timedelta(hours=1),
            observed_ago=timedelta(minutes=5),
        )

        self.assertTrue(lightning.is_current(NOW, max_age_seconds=300))
        self.assertFalse(
            lightning.is_current(
                NOW + timedelta(microseconds=1),
                max_age_seconds=300,
            )
        )

    def test_forecast_uses_its_provider_window_not_observation_max_age(self):
        target = NOW + timedelta(days=1)
        closure = Metric(
            name="official_stop_signal",
            value=True,
            unit="boolean",
            source="official",
            spatial_scope="spot:1",
            observed_at=NOW - timedelta(hours=1),
            fetched_at=NOW,
            valid_from=target,
            valid_until=target + timedelta(hours=1),
            mode=MetricMode.FORECAST,
        )

        self.assertTrue(closure.is_current(target, max_age_seconds=900))
        self.assertTrue(
            closure.is_current(
                target + timedelta(hours=1),
                max_age_seconds=900,
            )
        )
        self.assertFalse(
            closure.is_current(
                target + timedelta(hours=1, microseconds=1),
                max_age_seconds=900,
            )
        )

    def test_observation_set_is_immutable_and_rejects_duplicates(self):
        item = metric("air_temperature_c", 20)
        snapshot = ObservationSet.from_metrics(item)
        with self.assertRaises(TypeError):
            snapshot.metrics["air_temperature_c"] = item
        with self.assertRaisesRegex(ValueError, "duplicate"):
            ObservationSet.from_metrics(item, item)
        with self.assertRaises(FrozenInstanceError):
            item.value = 21

    def test_unsupported_activity_environment_combination_is_rejected(self):
        with self.assertRaisesRegex(
            ValueError,
            "unsupported activity/environment combination",
        ):
            EvaluationContext(
                activity=Activity.SWIM,
                environment=Environment.LICENSED_FACILITY,
                at=NOW,
            )


class HCIBeachTests(TestCase):
    def test_published_component_vectors(self):
        best = calculate_hci_beach(
            humidex=29,
            cloud_cover_pct=20,
            daily_precipitation_mm=0,
            average_wind_kmh=5,
        )
        moderate = calculate_hci_beach(
            humidex=24,
            cloud_cover_pct=70,
            daily_precipitation_mm=4,
            average_wind_kmh=25,
        )
        adverse = calculate_hci_beach(
            humidex=29,
            cloud_cover_pct=100,
            daily_precipitation_mm=30,
            average_wind_kmh=75,
        )
        self.assertEqual(best.score, 100)
        self.assertEqual(moderate.score, 66)
        self.assertEqual(adverse.score, 15)


class FamilySwimGateTests(TestCase):
    def test_complete_clear_snapshot_is_recommendable(self):
        result = evaluate_water_index(family_swim_metrics(), family_context())
        self.assertEqual(result.safety_status, SafetyStatus.CLEAR)
        self.assertEqual(result.decision, Decision.RECOMMENDED)
        self.assertGreaterEqual(result.score, 80)
        self.assertTrue(result.eligible_for_recommendation)
        self.assertEqual(result.methodology_version, "water-index-v1.0.0")

    def test_missing_critical_water_quality_abstains(self):
        values = family_swim_metrics().metrics
        snapshot = ObservationSet({key: value for key, value in values.items() if key != "water_quality_status"})
        result = evaluate_water_index(snapshot, family_context())
        self.assertEqual(result.safety_status, SafetyStatus.UNKNOWN)
        self.assertEqual(result.decision, Decision.UNKNOWN)
        self.assertIsNone(result.score)
        self.assertIn("water_quality_status", result.missing_metrics)

    def test_low_confidence_critical_input_is_unusable(self):
        result = evaluate_water_index(
            family_swim_metrics(
                metric(
                    "water_quality_status",
                    "pass",
                    valid_for=timedelta(days=1),
                    confidence=0.79,
                )
            ),
            family_context(),
        )
        self.assertEqual(result.safety_status, SafetyStatus.UNKNOWN)
        self.assertEqual(result.decision, Decision.UNKNOWN)
        self.assertIsNone(result.score)
        self.assertIn("water_quality_status", result.stale_or_conflicting_metrics)

    def test_stale_or_conflicting_safety_data_is_not_treated_as_clear(self):
        stale = metric(
            "water_quality_status",
            "pass",
            valid_for=timedelta(minutes=-1),
        )
        stale_result = evaluate_water_index(family_swim_metrics(stale), family_context())
        self.assertEqual(stale_result.safety_status, SafetyStatus.UNKNOWN)
        self.assertIn("water_quality_status", stale_result.stale_or_conflicting_metrics)

        conflict = metric(
            "water_quality_status",
            "pass",
            valid_for=timedelta(days=1),
            state=MetricState.CONFLICT,
        )
        conflict_result = evaluate_water_index(family_swim_metrics(conflict), family_context())
        self.assertEqual(conflict_result.safety_status, SafetyStatus.UNKNOWN)
        self.assertIsNone(conflict_result.score)

    def test_official_stop_overrides_high_suitability(self):
        result = evaluate_water_index(
            family_swim_metrics(metric("official_stop_signal", True)),
            family_context(),
        )
        self.assertEqual(result.safety_status, SafetyStatus.STOP)
        self.assertEqual(result.decision, Decision.BLOCKED)
        self.assertIsNone(result.score)
        self.assertFalse(result.eligible_for_recommendation)
        self.assertIn("OFFICIAL_STOP_ACTIVE", {gate.reason_code for gate in result.gates})

    def test_rip_current_numeric_boundaries(self):
        clear = evaluate_water_index(
            family_swim_metrics(metric("rip_current_risk", 29.99)),
            family_context(),
        )
        caution = evaluate_water_index(
            family_swim_metrics(metric("rip_current_risk", 30)),
            family_context(),
        )
        stop = evaluate_water_index(
            family_swim_metrics(metric("rip_current_risk", 55)),
            family_context(),
        )
        self.assertEqual(clear.safety_status, SafetyStatus.CLEAR)
        self.assertEqual(caution.safety_status, SafetyStatus.CAUTION)
        self.assertLessEqual(caution.score, 39)
        self.assertFalse(caution.eligible_for_recommendation)
        self.assertEqual(stop.safety_status, SafetyStatus.STOP)
        self.assertIsNone(stop.score)

        for malformed in (-0.01, 120.01):
            with self.subTest(malformed=malformed):
                result = evaluate_water_index(
                    family_swim_metrics(metric("rip_current_risk", malformed)),
                    family_context(),
                )
                self.assertEqual(result.safety_status, SafetyStatus.UNKNOWN)
                self.assertIn(
                    "SAFETY_VALUE_UNRECOGNIZED",
                    {gate.reason_code for gate in result.gates},
                )

    def test_lightning_requires_full_thirty_minute_clearance(self):
        blocked = evaluate_water_index(
            family_swim_metrics(metric("lightning_clearance_minutes", 29.99)),
            family_context(),
        )
        clear = evaluate_water_index(
            family_swim_metrics(metric("lightning_clearance_minutes", 30)),
            family_context(),
        )
        self.assertEqual(blocked.safety_status, SafetyStatus.STOP)
        self.assertEqual(clear.safety_status, SafetyStatus.CLEAR)

    def test_non_finite_lightning_text_abstains_instead_of_clearing(self):
        result = evaluate_water_index(
            family_swim_metrics(metric("lightning_clearance_minutes", "nan")),
            family_context(),
        )

        self.assertEqual(result.safety_status, SafetyStatus.UNKNOWN)
        self.assertIn(
            "SAFETY_VALUE_UNRECOGNIZED",
            {gate.reason_code for gate in result.gates},
        )

    def test_family_temperature_policy_boundaries(self):
        cold = evaluate_water_index(
            family_swim_metrics(metric("water_temperature_c", 14.99)),
            family_context(),
        )
        lower_edge = evaluate_water_index(
            family_swim_metrics(metric("water_temperature_c", 15)),
            family_context(),
        )
        clear_edge = evaluate_water_index(
            family_swim_metrics(metric("water_temperature_c", 18)),
            family_context(),
        )
        hot = evaluate_water_index(
            family_swim_metrics(metric("water_temperature_c", 31.01)),
            family_context(),
        )
        self.assertEqual(cold.safety_status, SafetyStatus.STOP)
        self.assertEqual(lower_edge.safety_status, SafetyStatus.CAUTION)
        self.assertEqual(clear_edge.safety_status, SafetyStatus.CLEAR)
        self.assertEqual(hot.safety_status, SafetyStatus.STOP)

    def test_active_patrol_is_required_for_family_profile(self):
        result = evaluate_water_index(
            family_swim_metrics(metric("patrol_status", "unknown")),
            family_context(),
        )
        self.assertEqual(result.safety_status, SafetyStatus.UNKNOWN)
        self.assertIn("SAFETY_VALUE_UNRECOGNIZED", {gate.reason_code for gate in result.gates})

        unavailable = evaluate_water_index(
            family_swim_metrics(metric("patrol_status", "off_duty")),
            family_context(),
        )
        self.assertEqual(unavailable.safety_status, SafetyStatus.CAUTION)
        self.assertLessEqual(unavailable.score, 39)
        self.assertIn("ACTIVE_PATROL_UNAVAILABLE", {gate.reason_code for gate in unavailable.gates})

    def test_adult_arm_reach_supervision_is_a_hard_gate(self):
        result = evaluate_water_index(
            family_swim_metrics(metric("adult_supervision_status", "unavailable")),
            family_context(),
        )
        self.assertEqual(result.safety_status, SafetyStatus.STOP)
        self.assertIsNone(result.score)
        self.assertIn(
            "ADULT_ARM_REACH_SUPERVISION_UNAVAILABLE",
            {gate.reason_code for gate in result.gates},
        )

    def test_designated_zone_is_required_and_a_closed_zone_blocks(self):
        values = family_swim_metrics().metrics
        missing = ObservationSet(
            {key: value for key, value in values.items() if key != "designated_swim_zone_status"}
        )
        missing_result = evaluate_water_index(missing, family_context())
        self.assertEqual(missing_result.safety_status, SafetyStatus.UNKNOWN)
        self.assertIn("designated_swim_zone_status", missing_result.missing_metrics)

        closed_result = evaluate_water_index(
            family_swim_metrics(metric("designated_swim_zone_status", "closed")),
            family_context(),
        )
        self.assertEqual(closed_result.safety_status, SafetyStatus.STOP)
        self.assertIn(
            "DESIGNATED_SWIM_ZONE_UNAVAILABLE",
            {gate.reason_code for gate in closed_result.gates},
        )

    def test_water_quality_advisory_blocks_water_contact(self):
        result = evaluate_water_index(
            family_swim_metrics(
                metric("water_quality_status", "advisory", valid_for=timedelta(days=1))
            ),
            family_context(),
        )
        self.assertEqual(result.safety_status, SafetyStatus.STOP)
        self.assertIn("WATER_QUALITY_ADVISORY", {gate.reason_code for gate in result.gates})

    def test_known_stop_takes_precedence_over_other_unknown_inputs(self):
        values = family_swim_metrics(metric("official_stop_signal", True)).metrics
        snapshot = ObservationSet(
            {key: value for key, value in values.items() if key != "water_quality_status"}
        )
        result = evaluate_water_index(snapshot, family_context())
        self.assertEqual(result.safety_status, SafetyStatus.STOP)
        self.assertEqual(result.decision, Decision.BLOCKED)
        self.assertIn("water_quality_status", result.missing_metrics)

    def test_low_score_confidence_abstains_without_inventing_a_hazard(self):
        low_confidence_names = {
            "official_activity_grade",
            "air_temperature_c",
            "wave_height_m",
            "wind_speed_ms",
            "precipitation_1h_mm",
            "uv_index",
            "crowd_level",
        }
        values = family_swim_metrics().metrics
        snapshot = ObservationSet(
            {
                key: (
                    metric(
                        key,
                        value.value,
                        valid_for=(value.valid_until - NOW) if value.valid_until else None,
                        confidence=0.5,
                    )
                    if key in low_confidence_names
                    else value
                )
                for key, value in values.items()
            }
        )
        result = evaluate_water_index(snapshot, family_context())
        self.assertEqual(result.safety_status, SafetyStatus.CLEAR)
        self.assertEqual(result.decision, Decision.UNKNOWN)
        self.assertIsNone(result.score)
        self.assertLess(result.confidence, 0.8)

    def test_optional_missing_weight_is_not_redistributed(self):
        values = family_swim_metrics().metrics
        snapshot = ObservationSet({key: value for key, value in values.items() if key != "crowd_level"})
        result = evaluate_water_index(snapshot, family_context())
        self.assertEqual(result.safety_status, SafetyStatus.CLEAR)
        self.assertIsNotNone(result.score)
        self.assertIsNotNone(result.score_range)
        self.assertLess(result.score_range[0], result.score_range[1])
        self.assertAlmostEqual(result.score_range[1] - result.score_range[0], 4.0)
        self.assertAlmostEqual(
            sum(contribution.configured_weight for contribution in result.contributions),
            0.96,
        )
        self.assertAlmostEqual(
            sum(contribution.effective_weight for contribution in result.contributions),
            0.96,
        )


class OtherActivityContractTests(TestCase):
    def test_relax_requires_current_official_coastal_access(self):
        common = (
            metric("weather_alert_level", "none"),
            metric("lightning_clearance_minutes", 45),
            metric("marine_hazard_status", "clear"),
            metric("hci_beach_score", 100),
            metric("crowd_level", "low"),
        )
        context = EvaluationContext(Activity.RELAX, NOW)

        missing = evaluate_water_index(
            ObservationSet.from_metrics(*common),
            context,
        )
        self.assertEqual(missing.safety_status, SafetyStatus.UNKNOWN)
        self.assertEqual(missing.decision, Decision.UNKNOWN)
        self.assertIsNone(missing.score)
        self.assertIn(
            "official_entry_status|access_status",
            missing.missing_metrics,
        )
        self.assertIn(
            "ACCESS_STATUS_MISSING",
            {gate.reason_code for gate in missing.gates},
        )

        for access_name in ("official_entry_status", "access_status"):
            with self.subTest(access_name=access_name):
                clear = evaluate_water_index(
                    ObservationSet.from_metrics(
                        *common,
                        metric(access_name, "open"),
                    ),
                    context,
                )
                self.assertEqual(clear.safety_status, SafetyStatus.CLEAR)
                self.assertEqual(clear.decision, Decision.RECOMMENDED)
                self.assertEqual(clear.score, 100)

    def test_relax_stale_or_closed_access_never_exposes_a_score(self):
        common = (
            metric("weather_alert_level", "none"),
            metric("lightning_clearance_minutes", 45),
            metric("marine_hazard_status", "clear"),
            metric("hci_beach_score", 100),
            metric("crowd_level", "low"),
        )
        context = EvaluationContext(Activity.RELAX, NOW)

        stale = evaluate_water_index(
            ObservationSet.from_metrics(
                *common,
                metric(
                    "official_entry_status",
                    "open",
                    valid_for=timedelta(minutes=-1),
                ),
            ),
            context,
        )
        self.assertEqual(stale.safety_status, SafetyStatus.UNKNOWN)
        self.assertEqual(stale.decision, Decision.UNKNOWN)
        self.assertIsNone(stale.score)
        self.assertIn(
            "official_entry_status|access_status",
            stale.stale_or_conflicting_metrics,
        )

        closed = evaluate_water_index(
            ObservationSet.from_metrics(
                *common,
                metric("access_status", "closed"),
            ),
            context,
        )
        self.assertEqual(closed.safety_status, SafetyStatus.STOP)
        self.assertEqual(closed.decision, Decision.BLOCKED)
        self.assertIsNone(closed.score)
        self.assertIn(
            "OFFICIAL_ACCESS_CLOSED",
            {gate.reason_code for gate in closed.gates},
        )

    def test_mudflat_official_window_is_a_gate(self):
        common = (
            metric("official_entry_status", "open"),
            metric("weather_alert_level", "none"),
            metric("lightning_clearance_minutes", 45),
            metric("marine_hazard_status", "clear"),
            metric("fog_status", "clear"),
            metric("designated_route_status", "verified", valid_for=timedelta(hours=8)),
            metric("official_activity_grade", "very_good", valid_for=timedelta(hours=8)),
            metric("crowd_level", "low"),
            metric("uv_index", 2),
        )
        context = EvaluationContext(Activity.MUDFLAT, NOW)
        allowed = evaluate_water_index(
            ObservationSet.from_metrics(*common, metric("tide_window_open", True, valid_for=timedelta(hours=2))),
            context,
        )
        stopped = evaluate_water_index(
            ObservationSet.from_metrics(*common, metric("tide_window_open", False, valid_for=timedelta(hours=2))),
            context,
        )
        self.assertEqual(allowed.safety_status, SafetyStatus.CLEAR)
        self.assertEqual(allowed.decision, Decision.RECOMMENDED)
        self.assertEqual(stopped.safety_status, SafetyStatus.STOP)
        self.assertIsNone(stopped.score)

    def test_onsen_above_40c_is_stopped(self):
        base = (
            metric("facility_status", "open"),
            metric("facility_hygiene_status", "pass", valid_for=timedelta(days=7)),
            metric("facility_operation_confidence", 1),
            metric("crowd_fit", 0.8),
            metric("amenity_fit", 1, valid_for=timedelta(days=1)),
            metric("indoor_weather_shelter", 1, valid_for=timedelta(days=1)),
            metric("preferred_temperature_fit", 1),
        )
        context = EvaluationContext(Activity.ONSEN, NOW)
        allowed = evaluate_water_index(
            ObservationSet.from_metrics(*base, metric("hot_tub_temperature_c", 40)),
            context,
        )
        stopped = evaluate_water_index(
            ObservationSet.from_metrics(*base, metric("hot_tub_temperature_c", 40.01)),
            context,
        )
        self.assertEqual(allowed.safety_status, SafetyStatus.CLEAR)
        self.assertGreaterEqual(allowed.score, 90)
        self.assertEqual(stopped.safety_status, SafetyStatus.STOP)
        self.assertIsNone(stopped.score)

    def test_rafting_without_site_specific_model_abstains(self):
        snapshot = ObservationSet.from_metrics(
            metric("operator_status", "open"),
            metric("weather_alert_level", "none"),
            metric("lightning_clearance_minutes", 40),
            metric("river_risk_level", "normal"),
            metric("safety_equipment_status", "verified"),
            metric("upstream_rain_risk", "none"),
            metric("operator_readiness", 1),
            metric("flow_trend_stability", 1),
            metric("thermal_gear_readiness", 1),
        )
        result = evaluate_water_index(snapshot, EvaluationContext(Activity.RAFTING, NOW))
        self.assertEqual(result.safety_status, SafetyStatus.CLEAR)
        self.assertEqual(result.decision, Decision.UNKNOWN)
        self.assertIsNone(result.score)
        self.assertIn("flow_suitability_score", result.missing_metrics)

    def test_hci_score_does_not_override_coastal_hazard(self):
        snapshot = ObservationSet.from_metrics(
            metric("official_entry_status", "open"),
            metric("weather_alert_level", "none"),
            metric("lightning_clearance_minutes", 45),
            metric("marine_hazard_status", "warning"),
            metric("hci_beach_score", 100),
            metric("crowd_level", "low"),
        )
        result = evaluate_water_index(snapshot, EvaluationContext(Activity.RELAX, NOW))
        self.assertEqual(result.safety_status, SafetyStatus.STOP)
        self.assertIsNone(result.score)
