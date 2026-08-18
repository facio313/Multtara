from __future__ import annotations

from datetime import datetime, timedelta
from io import StringIO
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase

from apps.conditions.models import (
    HydraulicCalibration,
    ObservationMetric,
    ObservationMetricLineage,
    ObservationSnapshot,
)
from apps.spots.models import WaterSpot
from services.ingestion.derived import (
    DERIVATION_VERSION,
    derive_facility_fit_observation,
    derive_flow_suitability_observation,
    derive_hci_beach_observations,
    derive_suitability_metrics_for_spot,
    dew_point_from_relative_humidity,
    flow_suitability_score,
    kma_sky_cloud_cover_upper_pct,
    parse_kma_pcp_interval,
)
from services.ingestion.fusion import (
    DERIVED_PROVIDER,
    FUSION_PROVIDER,
    evaluate_fused_spot,
    fuse_spot_observations,
)
from services.water_index import (
    Activity,
    Metric,
    MetricMode,
    MetricState,
    ObservationSet,
    OnsenSessionEvidence,
    OnsenSessionPreferences,
    SafetyStatus,
    apply_onsen_session_overlay,
    build_onsen_session_overlay,
)


KST = ZoneInfo("Asia/Seoul")
AT = datetime(2026, 8, 18, 14, tzinfo=KST)
PUBLIC_URL = "https://www.weather.go.kr/w/weather/forecast/short-term.do"
OPERATOR_URL = "https://www.gn.go.kr/public/facility-status"
CALIBRATION_URL = "https://www.me.go.kr/public/river-calibration"


def add_metric(
    snapshot: ObservationSnapshot,
    *,
    name: str,
    value,
    unit: str,
    source: str,
    station_id: str,
    spatial_scope: str | None = None,
    observed_at: datetime | None = None,
    fetched_at: datetime | None = None,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
    mode: str = "observed",
    confidence: float = 1.0,
    source_url: str = PUBLIC_URL,
) -> ObservationMetric:
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
        value_fields["numeric_value"] = float(value)
    else:
        value_type = "text"
        value_fields["text_value"] = str(value)
    return ObservationMetric.objects.create(
        snapshot=snapshot,
        name=name,
        value_type=value_type,
        **value_fields,
        unit=unit,
        mode=mode,
        state="valid",
        confidence=confidence,
        source=source,
        source_url=source_url,
        station_id=station_id,
        spatial_scope=spatial_scope or snapshot.spatial_scope,
        observed_at=observed_at or snapshot.observed_at,
        fetched_at=fetched_at or snapshot.fetched_at,
        valid_from=valid_from if valid_from is not None else snapshot.valid_from,
        valid_until=(
            valid_until if valid_until is not None else snapshot.valid_until
        ),
    )


class DerivedMathAndSessionOverlayTests(SimpleTestCase):
    def test_kma_sky_and_pcp_categories_preserve_conservative_bounds(self) -> None:
        self.assertEqual(kma_sky_cloud_cover_upper_pct("1"), 50.0)
        self.assertEqual(kma_sky_cloud_cover_upper_pct(3), 80.0)
        self.assertEqual(kma_sky_cloud_cover_upper_pct(4.0), 100.0)
        self.assertIsNone(kma_sky_cloud_cover_upper_pct(2))

        no_rain = parse_kma_pcp_interval("강수없음")
        below_one = parse_kma_pcp_interval("1mm 미만")
        band = parse_kma_pcp_interval("30.0~50.0mm")
        above = parse_kma_pcp_interval("50.0mm 이상")
        self.assertEqual((no_rain.lower_mm, no_rain.upper_mm), (0.0, 0.0))
        self.assertEqual(
            (below_one.lower_mm, below_one.upper_mm, below_one.upper_inclusive),
            (0.0, 1.0, False),
        )
        self.assertEqual((band.lower_mm, band.upper_mm), (30.0, 50.0))
        self.assertEqual((above.lower_mm, above.upper_mm), (50.0, None))
        self.assertIsNone(parse_kma_pcp_interval("about a little"))

    def test_dew_point_and_site_specific_flow_curve_are_bounded(self) -> None:
        dew_point = dew_point_from_relative_humidity(
            air_temperature_c=28,
            relative_humidity_pct=70,
        )
        self.assertLess(dew_point, 28)
        self.assertAlmostEqual(
            dew_point_from_relative_humidity(
                air_temperature_c=28,
                relative_humidity_pct=100,
            ),
            28,
        )
        self.assertEqual(
            flow_suitability_score(
                flow_cms=10,
                q_min=10,
                q_opt_low=20,
                q_opt_high=30,
                q_max=40,
            ),
            0,
        )
        self.assertEqual(
            flow_suitability_score(
                flow_cms=15,
                q_min=10,
                q_opt_low=20,
                q_opt_high=30,
                q_max=40,
            ),
            50,
        )
        self.assertEqual(
            flow_suitability_score(
                flow_cms=25,
                q_min=10,
                q_opt_low=20,
                q_opt_high=30,
                q_max=40,
            ),
            100,
        )
        with self.assertRaises(ValueError):
            flow_suitability_score(
                flow_cms=25,
                q_min=10,
                q_opt_low=10,
                q_opt_high=30,
                q_max=40,
            )

    def test_onsen_overlay_emits_only_explicit_request_factors(self) -> None:
        evidence = OnsenSessionEvidence(
            amenities=frozenset({"sauna"}),
            crowd_level=0.3,
            water_temperature_c=37,
        )
        omitted = build_onsen_session_overlay(
            preferences=OnsenSessionPreferences(),
            evidence=evidence,
        )
        self.assertEqual(dict(omitted.metrics), {})
        self.assertFalse(omitted.persistable)
        self.assertEqual(omitted.source, "SESSION_CONTEXT")

        explicit = build_onsen_session_overlay(
            preferences=OnsenSessionPreferences(
                required_amenities=("sauna", "family-room"),
                crowd_target=0.2,
                preferred_temperature_c=39,
                temperature_tolerance_c=4,
            ),
            evidence=evidence,
        )
        self.assertEqual(explicit.metrics["amenity_fit"], 0.5)
        self.assertAlmostEqual(explicit.metrics["crowd_fit"], 0.9)
        self.assertEqual(explicit.metrics["preferred_temperature_fit"], 0.5)
        with self.assertRaises(TypeError):
            explicit.metrics["amenity_fit"] = 1.0  # type: ignore[index]

        forged_global = Metric(
            name="amenity_fit",
            value=1.0,
            unit="proportion",
            source=DERIVED_PROVIDER,
            spatial_scope="spot:1",
            observed_at=AT,
            fetched_at=AT,
            valid_from=AT,
            valid_until=AT + timedelta(hours=1),
            mode=MetricMode.OBSERVED,
            state=MetricState.VALID,
        )
        without_request = apply_onsen_session_overlay(
            observations=ObservationSet.from_metrics(forged_global),
            overlay=omitted,
            at=AT,
        )
        self.assertIsNone(without_request.get("amenity_fit"))
        with_request = apply_onsen_session_overlay(
            observations=ObservationSet.from_metrics(forged_global),
            overlay=explicit,
            at=AT,
        )
        self.assertEqual(with_request.get("amenity_fit").source, "SESSION_CONTEXT")
        self.assertEqual(with_request.get("amenity_fit").valid_until, AT)


class HciBeachDerivationTests(TestCase):
    def setUp(self) -> None:
        self.spot = WaterSpot.objects.create(
            type="beach",
            name="HCI 근거 해변",
            lat=37.8,
            lng=128.9,
            region="강릉",
            address="강릉시",
        )

    def make_hci_source(
        self,
        *,
        include_daily: bool = True,
        forecast: bool = False,
        sky=1,
        pcp="강수없음",
        daily_rain: float = 0,
    ) -> dict[str, ObservationMetric]:
        if forecast:
            valid_from = AT + timedelta(days=1)
            valid_until = valid_from + timedelta(hours=1)
            observed_at = AT - timedelta(minutes=15)
            fetched_at = AT - timedelta(minutes=5)
            mode = "forecast"
        else:
            valid_from = AT - timedelta(minutes=10)
            valid_until = AT + timedelta(minutes=50)
            observed_at = AT - timedelta(minutes=10)
            fetched_at = AT - timedelta(minutes=5)
            mode = "observed"
        snapshot = ObservationSnapshot.objects.create(
            spot=self.spot,
            provider="KMA",
            provider_record_id=f"hci-source-{ObservationSnapshot.objects.count()}",
            state="live",
            observed_at=observed_at,
            fetched_at=fetched_at,
            valid_from=valid_from,
            valid_until=valid_until,
            spatial_scope="kma-grid:92,132",
            source_url=PUBLIC_URL,
            ingestion_version="kma-test-v1",
        )
        values = {
            "air_temperature_c": (28.0, "degC"),
            "relative_humidity_pct": (70.0, "percent"),
            "sky_condition_code": (sky, "provider_code"),
            "precipitation_amount_text": (pcp, "provider_text"),
            "wind_speed_ms": (2.0, "m/s"),
        }
        if include_daily:
            values["daily_precipitation_mm"] = (daily_rain, "mm")
        return {
            name: add_metric(
                snapshot,
                name=name,
                value=value,
                unit=unit,
                source="KMA",
                station_id="92,132",
                mode=mode,
            )
            for name, (value, unit) in values.items()
        }

    def test_complete_evidence_persists_components_lineage_and_never_clears_safety(self) -> None:
        inputs = self.make_hci_source()

        report = derive_suitability_metrics_for_spot(spot=self.spot, at=AT)

        self.assertEqual(report.derived_snapshots, 1)
        self.assertEqual(report.persisted_snapshots, 1)
        derived = ObservationSnapshot.objects.get(provider=DERIVED_PROVIDER)
        self.assertEqual(derived.ingestion_version, DERIVATION_VERSION)
        self.assertEqual(
            set(derived.metrics.values_list("name", flat=True)),
            {
                "hci_beach_score",
                "hci_beach_thermal_component",
                "hci_beach_aesthetic_component",
                "hci_beach_precipitation_component",
                "hci_beach_wind_component",
                "hci_beach_dew_point_c",
                "hci_beach_humidex",
                "hci_beach_cloud_cover_upper_pct",
            },
        )
        score = derived.metrics.get(name="hci_beach_score")
        self.assertEqual(
            set(score.lineage_sources.values_list("source_metric_id", flat=True)),
            {row.pk for row in inputs.values()},
        )
        for edge in score.lineage_sources.select_related("source_metric__snapshot"):
            self.assertEqual(edge.source_metric.snapshot.provider, "KMA")
        chained = ObservationMetricLineage(
            derived_metric=derived.metrics.get(name="hci_beach_humidex"),
            source_metric=score,
            relation="selected",
            priority=110,
        )
        with self.assertRaises(ValidationError):
            chained.full_clean()

        outcome = evaluate_fused_spot(
            spot=self.spot,
            activity=Activity.RELAX,
            at=AT,
            fetched_at=AT,
            dry_run=False,
        )
        self.assertIsNotNone(outcome.observation.observations.get("hci_beach_score"))
        self.assertEqual(outcome.result.safety_status, SafetyStatus.UNKNOWN)
        self.assertIsNone(outcome.result.score)
        fused_score = ObservationMetric.objects.get(
            snapshot__provider=FUSION_PROVIDER,
            name="hci_beach_score",
        )
        self.assertEqual(
            fused_score.lineage_sources.get().source_metric_id,
            score.pk,
        )

        repeated = derive_suitability_metrics_for_spot(
            spot=self.spot,
            at=AT + timedelta(minutes=1),
        )
        self.assertFalse(repeated.persistence[0].snapshot_created)
        self.assertEqual(
            ObservationSnapshot.objects.filter(provider=DERIVED_PROVIDER).count(),
            1,
        )
        derived.refresh_from_db()
        self.assertEqual(derived.fetched_at, AT)

    def test_pcp_is_not_promoted_to_a_daily_total(self) -> None:
        self.make_hci_source(include_daily=False, pcp="강수없음")

        self.assertEqual(derive_hci_beach_observations(spot=self.spot, at=AT), ())
        self.assertFalse(
            ObservationSnapshot.objects.filter(provider=DERIVED_PROVIDER).exists()
        )

    def test_spatial_or_validity_mismatch_abstains(self) -> None:
        inputs = self.make_hci_source()
        wind = inputs["wind_speed_ms"]
        wind.spatial_scope = "kma-grid:91,131"
        wind.save(update_fields=("spatial_scope",))
        self.assertEqual(derive_hci_beach_observations(spot=self.spot, at=AT), ())

        wind.spatial_scope = "kma-grid:92,132"
        wind.valid_until = AT + timedelta(minutes=40)
        wind.save(update_fields=("spatial_scope", "valid_until"))
        self.assertEqual(derive_hci_beach_observations(spot=self.spot, at=AT), ())

    def test_unknown_sky_pcp_and_inconsistent_daily_rain_abstain(self) -> None:
        self.make_hci_source(sky=2)
        self.assertEqual(derive_hci_beach_observations(spot=self.spot, at=AT), ())
        ObservationSnapshot.objects.all().delete()

        self.make_hci_source(pcp="provider prose changed")
        self.assertEqual(derive_hci_beach_observations(spot=self.spot, at=AT), ())
        ObservationSnapshot.objects.all().delete()

        self.make_hci_source(pcp="30~50mm", daily_rain=20)
        self.assertEqual(derive_hci_beach_observations(spot=self.spot, at=AT), ())

    def test_complete_future_forecast_window_is_derived_without_interpolation(self) -> None:
        self.make_hci_source(forecast=True)

        observations = derive_hci_beach_observations(spot=self.spot, at=AT)

        self.assertEqual(len(observations), 1)
        output = observations[0]
        self.assertEqual(output.valid_from, AT + timedelta(days=1))
        self.assertEqual(
            output.observations.get("hci_beach_score").mode.value,
            "forecast",
        )


class FacilityFitDerivationTests(TestCase):
    def make_spot(self, **overrides) -> WaterSpot:
        values = {
            "type": "hotspring",
            "name": "검증 온천",
            "lat": 37.7,
            "lng": 128.8,
            "region": "강원",
            "address": "강원도",
            "indoor": True,
            "bad_weather_suitable": True,
            "catalog_confidence": 0.95,
            "catalog_verification": "verified",
            "catalog_source": "TOUR_API",
            "catalog_source_url": "https://korean.visitkorea.or.kr/facility/1",
            "catalog_verified_at": AT - timedelta(days=1),
        }
        values.update(overrides)
        return WaterSpot.objects.create(**values)

    def add_status(
        self,
        spot: WaterSpot,
        *,
        provider: str = "FACILITY_OPERATOR",
        source: str = "FACILITY_OPERATOR",
        value: str = "open",
        observed_at: datetime = AT - timedelta(minutes=5),
        scope: str | None = None,
        confidence: float = 0.9,
        source_url: str = OPERATOR_URL,
    ) -> ObservationMetric:
        actual_scope = scope or f"spot:{spot.pk}"
        snapshot = ObservationSnapshot.objects.create(
            spot=spot,
            provider=provider,
            provider_record_id=f"facility-{provider}-{ObservationSnapshot.objects.count()}",
            state="live",
            observed_at=observed_at,
            fetched_at=observed_at + timedelta(minutes=1),
            valid_from=observed_at,
            valid_until=AT + timedelta(hours=1),
            spatial_scope=actual_scope,
            source_url=source_url,
            ingestion_version="operator-test-v1",
        )
        return add_metric(
            snapshot,
            name="facility_status",
            value=value,
            unit="canonical",
            source=source,
            source_url=source_url,
            station_id=f"facility:{spot.pk}",
            observed_at=observed_at,
            fetched_at=observed_at + timedelta(minutes=1),
            confidence=confidence,
        )

    def test_verified_catalog_and_current_operator_create_only_global_factors(self) -> None:
        spot = self.make_spot()
        source = self.add_status(spot)

        report = derive_suitability_metrics_for_spot(spot=spot, at=AT)

        self.assertEqual(report.derived_snapshots, 1)
        derived = ObservationSnapshot.objects.get(provider=DERIVED_PROVIDER)
        values = {
            row.name: row.value
            for row in derived.metrics.all()
        }
        self.assertEqual(
            values,
            {
                "facility_operation_confidence": 0.9,
                "indoor_weather_shelter": 1.0,
            },
        )
        self.assertTrue(
            set(values).isdisjoint(
                {"amenity_fit", "crowd_fit", "preferred_temperature_fit"}
            )
        )
        self.assertEqual(
            set(
                ObservationMetricLineage.objects.filter(
                    derived_metric__snapshot=derived
                ).values_list("source_metric_id", flat=True)
            ),
            {source.pk},
        )
        fused = fuse_spot_observations(spot=spot, at=AT, fetched_at=AT)
        self.assertIsNotNone(
            fused.observations.get("facility_operation_confidence")
        )
        self.assertIsNotNone(fused.observations.get("indoor_weather_shelter"))

    def test_unverified_closed_conflicting_or_expired_evidence_abstains(self) -> None:
        unverified = self.make_spot(
            name="미검증",
            catalog_verification="partial",
        )
        self.add_status(unverified)
        self.assertIsNone(derive_facility_fit_observation(spot=unverified, at=AT))

        closed = self.make_spot(name="폐쇄")
        self.add_status(closed, value="closed")
        self.assertIsNone(derive_facility_fit_observation(spot=closed, at=AT))

        conflict = self.make_spot(name="충돌")
        self.add_status(conflict, provider="FACILITY_OPERATOR", source="FACILITY_OPERATOR")
        self.add_status(
            conflict,
            provider="LOCAL_AUTHORITY",
            source="LOCAL_AUTHORITY",
            value="closed",
        )
        self.assertIsNone(derive_facility_fit_observation(spot=conflict, at=AT))

        expired = self.make_spot(name="만료")
        self.add_status(expired, observed_at=AT - timedelta(minutes=31))
        self.assertIsNone(derive_facility_fit_observation(spot=expired, at=AT))

    def test_default_false_catalog_flags_do_not_claim_a_negative_shelter_score(self) -> None:
        spot = self.make_spot(
            name="실내 근거 없음",
            indoor=False,
            bad_weather_suitable=False,
        )
        self.add_status(spot)

        observation = derive_facility_fit_observation(spot=spot, at=AT)

        self.assertIsNotNone(observation)
        self.assertIsNotNone(
            observation.observations.get("facility_operation_confidence")
        )
        self.assertIsNone(
            observation.observations.get("indoor_weather_shelter")
        )

    def test_provider_binding_scope_and_public_url_are_required(self) -> None:
        forged = self.make_spot(name="위조")
        self.add_status(
            forged,
            provider="LOCAL_AUTHORITY",
            source="FACILITY_OPERATOR",
        )
        self.assertIsNone(derive_facility_fit_observation(spot=forged, at=AT))

        wrong_scope = self.make_spot(name="범위")
        self.add_status(wrong_scope, scope="region:gangwon")
        self.assertIsNone(derive_facility_fit_observation(spot=wrong_scope, at=AT))

        query_url = self.make_spot(
            name="URL",
            catalog_source_url="https://example.go.kr/facility?key=secret",
        )
        self.add_status(query_url)
        self.assertIsNone(derive_facility_fit_observation(spot=query_url, at=AT))

    def test_persisted_session_or_safety_claims_from_derived_provider_are_ignored(self) -> None:
        spot = self.make_spot()
        snapshot = ObservationSnapshot.objects.create(
            spot=spot,
            provider=DERIVED_PROVIDER,
            provider_record_id="forged-derived-context",
            state="live",
            observed_at=AT - timedelta(minutes=1),
            fetched_at=AT,
            valid_from=AT - timedelta(minutes=1),
            valid_until=AT + timedelta(minutes=10),
            spatial_scope=f"spot:{spot.pk}",
            ingestion_version="forged-v1",
        )
        add_metric(
            snapshot,
            name="amenity_fit",
            value=1.0,
            unit="proportion",
            source=DERIVED_PROVIDER,
            station_id="forged",
        )
        add_metric(
            snapshot,
            name="facility_status",
            value="open",
            unit="canonical",
            source=DERIVED_PROVIDER,
            station_id="forged",
        )

        fused = fuse_spot_observations(spot=spot, at=AT, fetched_at=AT)

        self.assertIsNone(fused.observations.get("amenity_fit"))
        self.assertIsNone(fused.observations.get("facility_status"))


class FlowSuitabilityDerivationTests(TestCase):
    def setUp(self) -> None:
        self.spot = WaterSpot.objects.create(
            type="river",
            name="교정 래프팅 지점",
            lat=37.2,
            lng=128.2,
            region="강원",
            address="강원도",
        )

    def calibration(self, **overrides) -> HydraulicCalibration:
        values = {
            "spot": self.spot,
            "version": "site-calibration-v1",
            "station_id": "MOE-STATION-1",
            "spatial_scope": f"spot:{self.spot.pk}",
            "authority": "MOE",
            "q_min": 10.0,
            "q_opt_low": 20.0,
            "q_opt_high": 30.0,
            "q_max": 40.0,
            "evidence_url": CALIBRATION_URL,
            "verified": True,
            "verified_at": AT - timedelta(days=1),
            "active": True,
        }
        values.update(overrides)
        return HydraulicCalibration.objects.create(**values)

    def add_flow(
        self,
        *,
        value: float = 15,
        provider: str = "MOE",
        source: str = "MOE",
        station_id: str = "MOE-STATION-1",
        scope: str | None = None,
        observed_at: datetime = AT - timedelta(minutes=5),
        unit: str = "m3/s",
    ) -> ObservationMetric:
        actual_scope = scope or f"spot:{self.spot.pk}"
        snapshot = ObservationSnapshot.objects.create(
            spot=self.spot,
            provider=provider,
            provider_record_id=f"flow-{ObservationSnapshot.objects.count()}",
            state="live",
            observed_at=observed_at,
            fetched_at=observed_at + timedelta(minutes=1),
            valid_from=observed_at,
            valid_until=AT + timedelta(hours=1),
            spatial_scope=actual_scope,
            source_url="https://www.me.go.kr/public/river-flow",
            ingestion_version="flow-test-v1",
        )
        return add_metric(
            snapshot,
            name="river_flow_cms",
            value=value,
            unit=unit,
            source=source,
            source_url="https://www.me.go.kr/public/river-flow",
            station_id=station_id,
            observed_at=observed_at,
            fetched_at=observed_at + timedelta(minutes=1),
        )

    def test_calibrated_official_flow_persists_lineage_but_not_safety_clearance(self) -> None:
        calibration = self.calibration()
        calibration.full_clean()
        source = self.add_flow(value=15)

        report = derive_suitability_metrics_for_spot(spot=self.spot, at=AT)

        self.assertEqual(report.derived_snapshots, 1)
        score = ObservationMetric.objects.get(
            snapshot__provider=DERIVED_PROVIDER,
            name="flow_suitability_score",
        )
        self.assertEqual(score.numeric_value, 50.0)
        self.assertEqual(score.station_id, calibration.station_id)
        self.assertEqual(score.source_url, CALIBRATION_URL)
        self.assertEqual(score.lineage_sources.get().source_metric_id, source.pk)

        outcome = evaluate_fused_spot(
            spot=self.spot,
            activity=Activity.RAFTING,
            at=AT,
            fetched_at=AT,
            dry_run=False,
        )
        self.assertIsNotNone(
            outcome.observation.observations.get("flow_suitability_score")
        )
        self.assertEqual(outcome.result.safety_status, SafetyStatus.UNKNOWN)
        self.assertIsNone(outcome.result.score)

    def test_missing_unverified_or_invalid_calibration_abstains(self) -> None:
        self.add_flow()
        self.assertIsNone(
            derive_flow_suitability_observation(spot=self.spot, at=AT)
        )

        unverified = self.calibration(verified=False, verified_at=None, active=False)
        self.assertIsNone(
            derive_flow_suitability_observation(spot=self.spot, at=AT)
        )
        unverified.delete()

        invalid = HydraulicCalibration(
            spot=self.spot,
            version="invalid-v1",
            station_id="MOE-STATION-1",
            spatial_scope=f"spot:{self.spot.pk}",
            authority="MOE",
            q_min=20,
            q_opt_low=10,
            q_opt_high=30,
            q_max=40,
            evidence_url=CALIBRATION_URL,
            verified=True,
            verified_at=AT,
            active=True,
        )
        with self.assertRaises(ValidationError):
            invalid.full_clean()

    def test_station_scope_authority_unit_and_expiry_must_match(self) -> None:
        self.calibration()
        wrong_station = self.add_flow(station_id="OTHER")
        self.assertIsNone(
            derive_flow_suitability_observation(spot=self.spot, at=AT)
        )
        wrong_station.snapshot.delete()

        wrong_scope = self.add_flow(scope="river-basin:nationwide")
        self.assertIsNone(
            derive_flow_suitability_observation(spot=self.spot, at=AT)
        )
        wrong_scope.snapshot.delete()

        forged = self.add_flow(provider="LOCAL_AUTHORITY", source="MOE")
        self.assertIsNone(
            derive_flow_suitability_observation(spot=self.spot, at=AT)
        )
        forged.snapshot.delete()

        wrong_unit = self.add_flow(unit="canonical")
        self.assertIsNone(
            derive_flow_suitability_observation(spot=self.spot, at=AT)
        )
        wrong_unit.snapshot.delete()

        self.add_flow(observed_at=AT - timedelta(minutes=16))
        self.assertIsNone(
            derive_flow_suitability_observation(spot=self.spot, at=AT)
        )

    def test_calibration_requires_public_evidence_and_ordered_thresholds(self) -> None:
        query_evidence = HydraulicCalibration(
            spot=self.spot,
            version="query-url-v1",
            station_id="MOE-STATION-1",
            spatial_scope=f"spot:{self.spot.pk}",
            authority="MOE",
            q_min=10,
            q_opt_low=20,
            q_opt_high=30,
            q_max=40,
            evidence_url="https://example.go.kr/calibration?key=secret",
            verified=True,
            verified_at=AT,
            active=True,
        )
        with self.assertRaises(ValidationError):
            query_evidence.full_clean()

        inactive_unverified = HydraulicCalibration(
            spot=self.spot,
            version="unverified-v1",
            station_id="MOE-STATION-1",
            spatial_scope=f"spot:{self.spot.pk}",
            authority="MOE",
            q_min=10,
            q_opt_low=20,
            q_opt_high=30,
            q_max=40,
            evidence_url=CALIBRATION_URL,
            verified=False,
            verified_at=None,
            active=True,
        )
        with self.assertRaises(ValidationError):
            inactive_unverified.full_clean()


class DeriveSuitabilityCommandTests(TestCase):
    make_hci_source = HciBeachDerivationTests.make_hci_source

    def setUp(self) -> None:
        self.spot = WaterSpot.objects.create(
            type="beach",
            name="명령 대상 해변",
            lat=37.8,
            lng=128.9,
            region="강릉",
            address="강릉시",
        )

    def test_spot_scoped_dry_run_then_persist(self) -> None:
        self.make_hci_source()
        output = StringIO()

        call_command(
            "derive_suitability_metrics",
            "--dry-run",
            "--spot",
            str(self.spot.pk),
            "--at",
            AT.isoformat(),
            stdout=output,
        )

        self.assertIn("dry-run", output.getvalue())
        self.assertIn("derived=1", output.getvalue())
        self.assertFalse(
            ObservationSnapshot.objects.filter(provider=DERIVED_PROVIDER).exists()
        )

        call_command(
            "derive_suitability_metrics",
            "--spot",
            self.spot.name,
            "--at",
            AT.isoformat(),
            stdout=StringIO(),
        )
        self.assertTrue(
            ObservationSnapshot.objects.filter(provider=DERIVED_PROVIDER).exists()
        )

    def test_unknown_spot_and_naive_time_are_rejected(self) -> None:
        with self.assertRaises(CommandError):
            call_command("derive_suitability_metrics", "--spot", "missing")
        with self.assertRaises(CommandError):
            call_command(
                "derive_suitability_metrics",
                "--spot",
                str(self.spot.pk),
                "--at",
                "2026-08-18T14:00:00",
            )
