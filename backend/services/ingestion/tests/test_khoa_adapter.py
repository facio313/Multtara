from __future__ import annotations

import unittest
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from services.ingestion.khoa_adapter import (
    KhoaAdapterError,
    adapt_beach_forecast,
    adapt_mudflat_forecast,
    adapt_rip_current_forecast,
    adapt_surf_forecast,
)
from services.ingestion.marine import MarineIngestionService, match_observation_to_spot
from services.providers.base import ProviderResult
from services.providers.khoa import (
    BeachForecast,
    KhoaClient,
    MudflatForecast,
    RipCurrentForecast,
    SurfForecast,
)
from services.water_index import Activity, EvaluationContext, SafetyStatus, evaluate_water_index


KST = ZoneInfo("Asia/Seoul")
UTC = ZoneInfo("UTC")


def beach_record(**overrides: object) -> BeachForecast:
    values: dict[str, object] = {
        "place_name": "경포해수욕장",
        "latitude": Decimal("37.8055"),
        "longitude": Decimal("128.9070"),
        "forecast_date": date(2026, 8, 16),
        "forecast_time_code": "오후",
        "score": None,
        "official_grade": "매우좋음",
        "maximum_wave_height": Decimal("0.8"),
        "average_water_temperature": Decimal("24.2"),
        "average_air_temperature": Decimal("28.1"),
        "maximum_wind_speed": Decimal("4.4"),
    }
    values.update(overrides)
    return BeachForecast(**values)  # type: ignore[arg-type]


class KhoaAdapterTests(unittest.TestCase):
    def test_beach_preserves_grade_provenance_and_does_not_fabricate_safety(self) -> None:
        fetched_at = datetime(2026, 8, 16, 10, 30, tzinfo=KST)
        observation = adapt_beach_forecast(beach_record(), fetched_at=fetched_at)

        self.assertEqual(observation.provider, "KHOA")
        self.assertEqual(
            observation.source_url,
            "https://apis.data.go.kr/1192136/fcstBeachv2/GetFcstBeachApiServicev2",
        )
        self.assertNotIn("?", observation.source_url)
        self.assertEqual(
            observation.observations.get("official_activity_grade").value,
            "매우좋음",
        )
        self.assertEqual(observation.valid_from, datetime(2026, 8, 16, 12, tzinfo=KST))
        self.assertEqual(
            observation.valid_until,
            datetime(2026, 8, 16, 23, 59, 59, 999999, tzinfo=KST),
        )
        self.assertEqual(observation.evaluation_at, observation.valid_from)
        self.assertIn("place:경포해수욕장", observation.spatial_scope)
        self.assertIn("point:37.8055,128.9070", observation.spatial_scope)

        emitted = set(observation.observations.metrics)
        forbidden_clear_signals = {
            "official_entry_status",
            "weather_alert_level",
            "lightning_clearance_minutes",
            "water_quality_status",
            "marine_hazard_status",
            "patrol_status",
            "designated_swim_zone_status",
            "adult_supervision_status",
            "rip_current_risk",
        }
        self.assertTrue(emitted.isdisjoint(forbidden_clear_signals))
        self.assertIn("maximum_wave_height_m", emitted)
        self.assertNotIn("wave_height_m", emitted)

    def test_family_swim_from_beach_forecast_alone_is_unknown(self) -> None:
        observation = adapt_beach_forecast(
            beach_record(),
            fetched_at=datetime(2026, 8, 16, 13, tzinfo=KST),
        )
        result = evaluate_water_index(
            observation.observations,
            EvaluationContext(
                activity=Activity.SWIM,
                at=observation.evaluation_at,
                participant_profile="family",
            ),
        )

        self.assertEqual(result.safety_status, SafetyStatus.UNKNOWN)
        self.assertIsNone(result.score)
        self.assertIn("adult_supervision_status", result.missing_metrics)
        self.assertIn("designated_swim_zone_status", result.missing_metrics)
        self.assertIn("water_quality_status", result.missing_metrics)

    def test_mudflat_uses_only_explicit_official_window_as_tide_signal(self) -> None:
        record = MudflatForecast(
            place_name="장화리 갯벌",
            latitude=Decimal("37.6"),
            longitude=Decimal("126.4"),
            forecast_date=date(2026, 8, 17),
            experience_start_time="23:30",
            experience_end_time="01:10",
            weather="맑음",
            score=None,
            official_grade="좋음",
            maximum_air_temperature=Decimal("27"),
            minimum_air_temperature=Decimal("21"),
            maximum_wind_speed=Decimal("5"),
            minimum_wind_speed=Decimal("2"),
        )
        observation = adapt_mudflat_forecast(
            record,
            fetched_at=datetime(2026, 8, 17, 14, 45, tzinfo=UTC),
        )

        self.assertEqual(observation.valid_from, datetime(2026, 8, 17, 23, 30, tzinfo=KST))
        self.assertEqual(observation.valid_until, datetime(2026, 8, 18, 1, 10, tzinfo=KST))
        self.assertIs(observation.observations.get("tide_window_open").value, True)
        self.assertEqual(
            observation.observations.get("official_tide_window_start").value,
            "2026-08-17T23:30:00+09:00",
        )
        self.assertEqual(
            observation.observations.get("official_tide_window_end").value,
            "2026-08-18T01:10:00+09:00",
        )
        self.assertEqual(observation.observations.get("weather_description").value, "맑음")
        self.assertIsNone(observation.observations.get("fog_status"))
        self.assertIsNone(observation.observations.get("marine_hazard_status"))
        self.assertIsNone(observation.observations.get("designated_route_status"))

    def test_mudflat_before_and_after_official_window_are_explicit_stop(self) -> None:
        record = MudflatForecast(
            place_name="장화리 갯벌",
            latitude=Decimal("37.6"),
            longitude=Decimal("126.4"),
            forecast_date=date(2026, 8, 17),
            experience_start_time="09:00",
            experience_end_time="11:00",
            weather="맑음",
            score=None,
            official_grade="좋음",
            maximum_air_temperature=Decimal("27"),
            minimum_air_temperature=Decimal("21"),
            maximum_wind_speed=Decimal("5"),
            minimum_wind_speed=Decimal("2"),
        )

        for evaluated_at in (
            datetime(2026, 8, 17, 8, 59, tzinfo=KST),
            datetime(2026, 8, 17, 11, 1, tzinfo=KST),
        ):
            with self.subTest(evaluated_at=evaluated_at):
                observation = adapt_mudflat_forecast(
                    record,
                    fetched_at=evaluated_at,
                )
                tide = observation.observations.get("tide_window_open")
                self.assertIs(tide.value, False)
                self.assertEqual(tide.valid_from, evaluated_at)
                self.assertEqual(tide.valid_until, evaluated_at)
                result = evaluate_water_index(
                    observation.observations,
                    EvaluationContext(Activity.MUDFLAT, observation.evaluation_at),
                )
                self.assertEqual(result.safety_status, SafetyStatus.STOP)
                self.assertIn(
                    "OUTSIDE_OFFICIAL_TIDE_WINDOW",
                    {gate.reason_code for gate in result.gates},
                )

    def test_mudflat_window_boundaries_are_inclusive(self) -> None:
        record = MudflatForecast(
            place_name="장화리 갯벌",
            latitude=Decimal("37.6"),
            longitude=Decimal("126.4"),
            forecast_date=date(2026, 8, 17),
            experience_start_time="09:00",
            experience_end_time="11:00",
            weather=None,
            score=None,
            official_grade=None,
            maximum_air_temperature=None,
            minimum_air_temperature=None,
            maximum_wind_speed=None,
            minimum_wind_speed=None,
        )

        for evaluated_at in (
            datetime(2026, 8, 17, 9, tzinfo=KST),
            datetime(2026, 8, 17, 11, tzinfo=KST),
        ):
            with self.subTest(evaluated_at=evaluated_at):
                observation = adapt_mudflat_forecast(
                    record,
                    fetched_at=evaluated_at,
                )
                self.assertIs(
                    observation.observations.get("tide_window_open").value,
                    True,
                )

    def test_mudflat_window_is_not_extended_to_an_unrelated_date(self) -> None:
        record = MudflatForecast(
            place_name="장화리 갯벌",
            latitude=Decimal("37.6"),
            longitude=Decimal("126.4"),
            forecast_date=date(2026, 8, 17),
            experience_start_time="09:00",
            experience_end_time="11:00",
            weather=None,
            score=None,
            official_grade=None,
            maximum_air_temperature=None,
            minimum_air_temperature=None,
            maximum_wind_speed=None,
            minimum_wind_speed=None,
        )
        observation = adapt_mudflat_forecast(
            record,
            fetched_at=datetime(2026, 8, 16, 10, tzinfo=KST),
        )

        self.assertIsNone(observation.observations.get("tide_window_open"))
        self.assertIsNotNone(
            observation.observations.get("official_tide_window_start")
        )
        result = evaluate_water_index(
            observation.observations,
            EvaluationContext(Activity.MUDFLAT, observation.evaluation_at),
        )
        self.assertEqual(result.safety_status, SafetyStatus.UNKNOWN)

    def test_equal_mudflat_start_and_end_is_invalid_not_twenty_four_hours(self) -> None:
        record = MudflatForecast(
            place_name="장화리 갯벌",
            latitude=Decimal("37.6"),
            longitude=Decimal("126.4"),
            forecast_date=date(2026, 8, 17),
            experience_start_time="09:00",
            experience_end_time="09:00",
            weather="맑음",
            score=None,
            official_grade="좋음",
            maximum_air_temperature=Decimal("27"),
            minimum_air_temperature=Decimal("21"),
            maximum_wind_speed=Decimal("5"),
            minimum_wind_speed=Decimal("2"),
        )

        observation = adapt_mudflat_forecast(
            record,
            fetched_at=datetime(2026, 8, 16, 9, tzinfo=KST),
        )

        self.assertIsNone(observation.valid_from)
        self.assertIsNone(observation.valid_until)
        self.assertEqual(observation.state, "error")
        self.assertEqual(dict(observation.observations.metrics), {})

    def test_provider_record_id_is_idempotent_and_revision_sensitive(self) -> None:
        fetched_at = datetime(2026, 8, 16, 13, tzinfo=KST)
        first = adapt_beach_forecast(beach_record(), fetched_at=fetched_at)
        repeated = adapt_beach_forecast(beach_record(), fetched_at=fetched_at)
        revised = adapt_beach_forecast(
            beach_record(official_grade="보통"), fetched_at=fetched_at
        )

        self.assertEqual(first.provider_record_id, repeated.provider_record_id)
        self.assertNotEqual(first.provider_record_id, revised.provider_record_id)
        self.assertNotIn("매우좋음", first.provider_record_id)

    def test_invalid_forecast_period_emits_no_metrics_and_fails_closed(self) -> None:
        fetched_at = datetime(2026, 8, 16, 13, tzinfo=KST)
        invalid_code = adapt_beach_forecast(
            beach_record(forecast_time_code="알수없음"), fetched_at=fetched_at
        )
        missing_date = adapt_beach_forecast(
            beach_record(forecast_date=None), fetched_at=fetched_at
        )

        for observation in (invalid_code, missing_date):
            with self.subTest(provider_record_id=observation.provider_record_id):
                self.assertEqual(observation.state, "error")
                self.assertEqual(dict(observation.observations.metrics), {})
                self.assertIsNone(observation.valid_from)
                self.assertIsNone(observation.valid_until)
                result = evaluate_water_index(
                    observation.observations,
                    EvaluationContext(
                        activity=Activity.SWIM,
                        at=observation.evaluation_at,
                        participant_profile="family",
                    ),
                )
                self.assertEqual(result.safety_status, SafetyStatus.UNKNOWN)
                self.assertIsNone(result.score)

    def test_expired_forecast_is_preserved_as_stale_not_live(self) -> None:
        observation = adapt_beach_forecast(
            beach_record(
                forecast_date=date(2026, 8, 15),
                forecast_time_code="오전",
            ),
            fetched_at=datetime(2026, 8, 16, 13, tzinfo=KST),
        )

        self.assertEqual(observation.state, "stale")
        self.assertEqual(
            observation.evaluation_at,
            datetime(2026, 8, 16, 13, tzinfo=KST),
        )
        result = evaluate_water_index(
            observation.observations,
            EvaluationContext(
                activity=Activity.SWIM,
                at=observation.evaluation_at,
                participant_profile="family",
            ),
        )
        self.assertEqual(result.safety_status, SafetyStatus.UNKNOWN)
        self.assertIn("official_activity_grade", result.stale_or_conflicting_metrics)

    def test_surf_grade_is_exact_but_does_not_clear_safety_gates(self) -> None:
        record = SurfForecast(
            place_name="죽도",
            latitude=Decimal("38.0"),
            longitude=Decimal("128.7"),
            forecast_date=date(2026, 8, 16),
            forecast_time_code="오전",
            score=None,
            official_grade="좋음",
            grade_detail="초중급자에게 적합",
            average_wave_height=Decimal("1.2"),
            average_wave_period=Decimal("8"),
            average_wind_speed=Decimal("3.5"),
            average_water_temperature=Decimal("23"),
        )
        observation = adapt_surf_forecast(
            record,
            fetched_at=datetime(2026, 8, 16, 8, tzinfo=KST),
        )
        result = evaluate_water_index(
            observation.observations,
            EvaluationContext(
                activity=Activity.SURF,
                at=observation.evaluation_at,
            ),
        )

        self.assertEqual(
            observation.observations.get("official_activity_grade").value,
            "좋음",
        )
        self.assertEqual(
            observation.observations.get("official_grade_detail").value,
            "초중급자에게 적합",
        )
        self.assertEqual(result.safety_status, SafetyStatus.UNKNOWN)
        self.assertIsNone(result.score)

    def test_rip_current_localizes_source_time_and_rejects_future_observation(self) -> None:
        record = RipCurrentForecast(
            beach_code="GYEONGPO",
            beach_name="경포해수욕장",
            observed_at=datetime(2026, 8, 16, 14, 30),
            latitude=Decimal("37.8055"),
            longitude=Decimal("128.9070"),
            official_index="62.5",
            index_value=Decimal("62.5"),
            risk_message="주의",
            wave_height_m=Decimal("0.7"),
            wave_period_seconds=Decimal("7.1"),
            water_temperature_celsius=Decimal("24.3"),
            air_temperature_celsius=Decimal("29.0"),
            wind_direction="NE",
            wind_speed_mps=Decimal("3.2"),
        )
        observation = adapt_rip_current_forecast(
            record,
            fetched_at=datetime(2026, 8, 16, 14, 35, tzinfo=KST),
        )
        risk = observation.observations.get("rip_current_risk")

        self.assertEqual(observation.source_observed_at, datetime(2026, 8, 16, 14, 30, tzinfo=KST))
        self.assertEqual(risk.observed_at, observation.source_observed_at)
        self.assertEqual(
            observation.valid_until,
            datetime(2026, 8, 16, 14, 50, tzinfo=KST),
        )
        self.assertEqual(risk.valid_until, observation.valid_until)
        self.assertEqual(risk.station_id, "GYEONGPO")
        self.assertEqual(risk.value, 62.5)

        with self.assertRaises(KhoaAdapterError):
            adapt_rip_current_forecast(
                record,
                fetched_at=datetime(2026, 8, 16, 14, 20, tzinfo=KST),
            )

    def test_requires_timezone_aware_fetch_timestamp(self) -> None:
        with self.assertRaises(KhoaAdapterError):
            adapt_beach_forecast(
                beach_record(), fetched_at=datetime(2026, 8, 16, 10)
            )


class FakeKhoaClient:
    def __init__(self, result: ProviderResult[BeachForecast]) -> None:
        self.result = result
        self.request_dates: list[date] = []

    def fetch_beach_forecasts(self, *, request_date: date) -> ProviderResult[BeachForecast]:
        self.request_dates.append(request_date)
        return self.result


class MarineIngestionServiceTests(unittest.TestCase):
    def test_dry_run_matches_suffix_variants_and_never_calls_persister(self) -> None:
        result = ProviderResult(
            provider="KHOA",
            endpoint="/1192136/fcstBeachv2/GetFcstBeachApiServicev2",
            records=(beach_record(),),
            reported_total_count=1,
        )
        client = FakeKhoaClient(result)
        persisted: list[object] = []
        service = MarineIngestionService(
            client,  # type: ignore[arg-type]
            persister=lambda **kwargs: persisted.append(kwargs),  # type: ignore[arg-type]
            clock=lambda: datetime(2026, 8, 16, 13, tzinfo=KST),
        )
        spot = SimpleNamespace(
            pk=7,
            name="경포 해변",
            type="beach",
            lat=37.8056,
            lng=128.9071,
        )

        report = service.sync(
            activities=(Activity.SWIM,),
            request_date=date(2026, 8, 16),
            spots=(spot,),
            dry_run=True,
        )

        self.assertEqual(client.request_dates, [date(2026, 8, 16)])
        self.assertEqual(report.fetched_records, 1)
        self.assertEqual(report.matched_records, 1)
        self.assertEqual(report.persisted_records, 0)
        self.assertEqual(report.activities[0].unknown_results, 1)
        self.assertEqual(persisted, [])

    def test_coordinates_cannot_replace_a_curated_provider_identity(self) -> None:
        observation = adapt_beach_forecast(
            beach_record(place_name="이름이 다른 곳"),
            fetched_at=datetime(2026, 8, 16, 13, tzinfo=KST),
        )
        close_beach = SimpleNamespace(
            pk=1, name="근처", type="beach", lat=37.8057, lng=128.9072
        )
        close_river = SimpleNamespace(
            pk=2, name="더 가까운 강", type="river", lat=37.8055, lng=128.9070
        )
        far_beach = SimpleNamespace(
            pk=3, name="먼 해변", type="beach", lat=36.0, lng=127.0
        )

        self.assertIsNone(
            match_observation_to_spot(
                observation, (close_river, far_beach, close_beach)
            )
        )

        conflicting_exact_name = SimpleNamespace(
            pk=4,
            name="경포해수욕장",
            type="beach",
            lat=35.0,
            lng=126.0,
        )
        named_observation = adapt_beach_forecast(
            beach_record(),
            fetched_at=datetime(2026, 8, 16, 13, tzinfo=KST),
        )
        self.assertIsNone(
            match_observation_to_spot(named_observation, (conflicting_exact_name,))
        )

    def test_curated_beach_code_collects_rip_current_without_guessing(self) -> None:
        class Client:
            def fetch_beach_forecasts(self, *, request_date):
                return ProviderResult(
                    provider="KHOA",
                    endpoint=KhoaClient.BEACH_ENDPOINT,
                    records=(),
                    reported_total_count=0,
                )

            def fetch_rip_current_forecasts(self, *, beach_code, request_date):
                self.requested_code = beach_code
                return ProviderResult(
                    provider="KHOA",
                    endpoint=KhoaClient.RIP_CURRENT_ENDPOINT,
                    records=(
                        RipCurrentForecast(
                            beach_code=beach_code,
                            beach_name="경포해수욕장",
                            observed_at=datetime(2026, 8, 16, 13, 30),
                            latitude=Decimal("37.8055"),
                            longitude=Decimal("128.9070"),
                            official_index="62.5",
                            index_value=Decimal("62.5"),
                            risk_message="경계",
                            wave_height_m=Decimal("0.7"),
                            wave_period_seconds=Decimal("7"),
                            water_temperature_celsius=Decimal("24"),
                            air_temperature_celsius=Decimal("28"),
                            wind_direction="NE",
                            wind_speed_mps=Decimal("3"),
                        ),
                    ),
                    reported_total_count=1,
                )

        client = Client()
        service = MarineIngestionService(
            client,  # type: ignore[arg-type]
            clock=lambda: datetime(2026, 8, 16, 13, 35, tzinfo=KST),
        )
        spot = SimpleNamespace(
            pk=9,
            name="경포해수욕장",
            type="beach",
            lat=37.8055,
            lng=128.9070,
            khoa_beach_code="GYEONGPO",
        )

        report = service.sync(
            activities=(Activity.SWIM,),
            request_date=date(2026, 8, 16),
            spots=(spot,),
            dry_run=True,
        )

        self.assertEqual(client.requested_code, "GYEONGPO")
        self.assertEqual(report.fetched_records, 1)
        self.assertEqual(report.matched_records, 1)
        self.assertEqual(report.activities[0].unknown_results, 0)

    def test_rip_response_code_or_coordinate_conflict_is_rejected(self) -> None:
        class Client:
            def fetch_beach_forecasts(self, *, request_date):
                return ProviderResult(
                    provider="KHOA",
                    endpoint=KhoaClient.BEACH_ENDPOINT,
                    records=(),
                    reported_total_count=0,
                )

            def fetch_rip_current_forecasts(self, *, beach_code, request_date):
                return ProviderResult(
                    provider="KHOA",
                    endpoint=KhoaClient.RIP_CURRENT_ENDPOINT,
                    records=(
                        RipCurrentForecast(
                            beach_code="DIFFERENT",
                            beach_name="다른 해변",
                            observed_at=datetime(2026, 8, 16, 13, 30),
                            latitude=Decimal("35.0"),
                            longitude=Decimal("126.0"),
                            official_index="10",
                            index_value=Decimal("10"),
                            risk_message="관심",
                            wave_height_m=None,
                            wave_period_seconds=None,
                            water_temperature_celsius=None,
                            air_temperature_celsius=None,
                            wind_direction=None,
                            wind_speed_mps=None,
                        ),
                    ),
                    reported_total_count=1,
                )

        report = MarineIngestionService(
            Client(),  # type: ignore[arg-type]
            clock=lambda: datetime(2026, 8, 16, 13, 35, tzinfo=KST),
        ).sync(
            activities=(Activity.SWIM,),
            request_date=date(2026, 8, 16),
            spots=(
                SimpleNamespace(
                    pk=9,
                    name="경포해수욕장",
                    type="beach",
                    lat=37.8055,
                    lng=128.9070,
                    khoa_beach_code="GYEONGPO",
                ),
            ),
            dry_run=True,
        )

        self.assertEqual(report.fetched_records, 1)
        self.assertEqual(report.matched_records, 0)
        self.assertEqual(report.activities[0].skipped_records, 1)


if __name__ == "__main__":
    unittest.main()
