from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.test import TestCase

from apps.conditions.models import ConditionScore, ObservationMetric, ObservationSnapshot
from apps.spots.models import WaterSpot
from services.ingestion.khoa_adapter import adapt_beach_forecast
from services.ingestion.kma_adapter import adapt_weather_values
from services.ingestion.persistence import persist_evaluation, persist_observation
from services.providers.khoa import BeachForecast
from services.providers.kma import KmaClient, WeatherValue
from services.water_index import Activity, EvaluationContext, SafetyStatus, evaluate_water_index


KST = ZoneInfo("Asia/Seoul")


class IngestionPersistenceTests(TestCase):
    def setUp(self) -> None:
        self.spot = WaterSpot.objects.create(
            type="beach",
            name="경포해수욕장",
            lat=37.8055,
            lng=128.9070,
            region="강원",
            address="강원특별자치도 강릉시",
        )

    def _observation_and_result(self):
        record = BeachForecast(
            place_name="경포해수욕장",
            latitude=Decimal("37.8055"),
            longitude=Decimal("128.9070"),
            forecast_date=date(2026, 8, 16),
            forecast_time_code="오후",
            score=None,
            official_grade="매우좋음",
            maximum_wave_height=Decimal("0.8"),
            average_water_temperature=Decimal("24.2"),
            average_air_temperature=Decimal("28.1"),
            maximum_wind_speed=Decimal("4.4"),
        )
        observation = adapt_beach_forecast(
            record,
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
        return observation, result

    def test_repeated_persistence_is_idempotent_and_auditable(self) -> None:
        observation, result = self._observation_and_result()

        first = persist_evaluation(
            spot=self.spot,
            observation=observation,
            result=result,
            participant_profile="family",
        )
        second = persist_evaluation(
            spot=self.spot,
            observation=observation,
            result=result,
            participant_profile="beginner",
        )

        self.assertTrue(first.snapshot_created)
        self.assertTrue(first.score_created)
        self.assertFalse(second.snapshot_created)
        self.assertFalse(second.score_created)
        self.assertEqual(first.snapshot_id, second.snapshot_id)
        self.assertEqual(first.score_id, second.score_id)
        self.assertEqual(ObservationSnapshot.objects.count(), 1)
        self.assertEqual(ConditionScore.objects.count(), 1)
        self.assertEqual(
            ObservationMetric.objects.count(), len(observation.observations.metrics)
        )

        snapshot = ObservationSnapshot.objects.get()
        self.assertEqual(snapshot.provider, "KHOA")
        self.assertEqual(snapshot.provider_record_id, observation.provider_record_id)
        self.assertEqual(snapshot.source_url, observation.source_url)
        self.assertEqual(snapshot.spatial_scope, observation.spatial_scope)
        self.assertIsNone(snapshot.observed_at)
        self.assertEqual(snapshot.fetched_at, observation.fetched_at)
        self.assertEqual(snapshot.valid_from, observation.valid_from)
        self.assertEqual(snapshot.valid_until, observation.valid_until)

        grade = snapshot.metrics.get(name="official_activity_grade")
        self.assertEqual(grade.value_type, "text")
        self.assertEqual(grade.text_value, "매우좋음")
        self.assertIsNone(grade.numeric_value)
        self.assertIsNone(grade.boolean_value)
        self.assertEqual(grade.source_url, observation.source_url)
        self.assertEqual(grade.spatial_scope, observation.spatial_scope)

        score = ConditionScore.objects.get()
        self.assertEqual(score.safety_status, SafetyStatus.UNKNOWN.value)
        self.assertIsNone(score.score)
        self.assertIn("water_quality_status", score.missing_metrics)
        self.assertEqual(score.methodology_version, result.methodology_version)
        self.assertEqual(score.participant_profile, "family")
        self.assertEqual(score.snapshot_id, snapshot.pk)
        snapshot.full_clean()
        grade.full_clean()
        score.full_clean()

    def test_same_snapshot_keeps_general_and_family_evaluations_separate(self) -> None:
        observation, result = self._observation_and_result()

        general = persist_evaluation(
            spot=self.spot,
            observation=observation,
            result=result,
            participant_profile="general",
        )
        family = persist_evaluation(
            spot=self.spot,
            observation=observation,
            result=result,
            participant_profile="family",
        )

        self.assertNotEqual(general.score_id, family.score_id)
        self.assertEqual(
            set(ConditionScore.objects.values_list("participant_profile", flat=True)),
            {"general", "family"},
        )

    def test_weather_snapshot_is_idempotent_without_fabricating_a_score(self) -> None:
        weather = WeatherValue(
            category="T1H",
            value=Decimal("26.5"),
            unit="celsius",
            issued_at=datetime(2026, 8, 16, 13, tzinfo=KST),
            valid_at=datetime(2026, 8, 16, 13, tzinfo=KST),
            grid_x=92,
            grid_y=132,
        )
        observation = adapt_weather_values(
            (weather,),
            fetched_at=datetime(2026, 8, 16, 13, 45, tzinfo=KST),
            endpoint=KmaClient.NOWCAST_ENDPOINT,
            forecast=False,
        )[0]

        first = persist_observation(spot=self.spot, observation=observation)
        repeated = persist_observation(spot=self.spot, observation=observation)

        self.assertTrue(first.snapshot_created)
        self.assertFalse(repeated.snapshot_created)
        self.assertEqual(first.snapshot_id, repeated.snapshot_id)
        self.assertEqual(ObservationSnapshot.objects.count(), 1)
        self.assertEqual(ConditionScore.objects.count(), 0)
        snapshot = ObservationSnapshot.objects.get()
        self.assertEqual(snapshot.provider, "KMA")
        self.assertEqual(snapshot.metrics.get().name, "air_temperature_c")
