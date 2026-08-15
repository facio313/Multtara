from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.conditions.models import (
    ConditionScore,
    CrowdLevel,
    ObservationMetric,
    ObservationMetricLineage,
    ObservationSnapshot,
    WaterCondition,
)
from apps.conditions.serializers import ConditionScoreSerializer, ObservationSnapshotSerializer
from apps.conditions.views import ConditionScoreViewSet
from apps.spots.models import WaterSpot


def create_spot(name="Test Beach", spot_type="beach"):
    return WaterSpot.objects.create(
        type=spot_type,
        name=name,
        lat=37.123,
        lng=126.123,
        region="Gangwon",
        address="123 Test St",
    )


def create_snapshot(spot, *, record_id="beach-1", fetched_at=None, provider="KHOA"):
    fetched_at = fetched_at or timezone.now()
    return ObservationSnapshot.objects.create(
        spot=spot,
        provider=provider,
        provider_record_id=record_id,
        state=ObservationSnapshot.SourceState.LIVE,
        observed_at=fetched_at - timedelta(minutes=5),
        fetched_at=fetched_at,
        valid_from=fetched_at,
        valid_until=fetched_at + timedelta(hours=6),
        spatial_scope="Gyeongpo Beach point forecast",
        source_url="https://apis.data.go.kr/khoa/beach?serviceKey=SERVER_SECRET",
        ingestion_version="khoa-v1",
    )


def create_metric(snapshot, *, name="water_temperature_c", value=22.5):
    return ObservationMetric.objects.create(
        snapshot=snapshot,
        name=name,
        value_type=ObservationMetric.ValueType.NUMBER,
        numeric_value=value,
        unit="degC",
        mode=ObservationMetric.Mode.FORECAST,
        state=ObservationMetric.State.VALID,
        confidence=0.95,
        source="KHOA Beach Index",
        source_url=(
            "https://api-user:api-password@apis.data.go.kr/khoa/beach"
            "?serviceKey=SERVER_SECRET#response"
        ),
        station_id="GYEONGPO",
        spatial_scope=snapshot.spatial_scope,
        observed_at=snapshot.observed_at,
        fetched_at=snapshot.fetched_at,
        valid_from=snapshot.valid_from,
        valid_until=snapshot.valid_until,
    )


class ConditionModelTests(TestCase):
    def setUp(self):
        self.spot = create_spot()

    def test_water_condition_creation(self):
        condition = WaterCondition.objects.create(
            spot=self.spot,
            water_temp=20.5,
            air_temp=25.0,
        )
        self.assertEqual(condition.water_temp, 20.5)

    def test_legacy_condition_score_creation_remains_compatible(self):
        score = ConditionScore.objects.create(
            spot=self.spot,
            activity="surfing",
            score=8.5,
        )
        self.assertEqual(score.activity, "surfing")
        self.assertEqual(score.score, 8.5)
        self.assertEqual(score.safety_status, ConditionScore.SafetyStatus.UNKNOWN)
        self.assertEqual(score.methodology_version, "legacy-unversioned")
        self.assertEqual(score.participant_profile, "general")

    def test_snapshot_score_uniqueness_is_participant_profile_aware(self):
        snapshot = create_snapshot(self.spot)
        general = ConditionScore.objects.create(
            spot=self.spot,
            snapshot=snapshot,
            activity="swim",
            participant_profile="general",
            methodology_version="water-index-v1.0.0",
        )
        family = ConditionScore.objects.create(
            spot=self.spot,
            snapshot=snapshot,
            activity="swim",
            participant_profile="family",
            methodology_version="water-index-v1.0.0",
        )
        self.assertNotEqual(general.pk, family.pk)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ConditionScore.objects.create(
                spot=self.spot,
                snapshot=snapshot,
                activity="swim",
                participant_profile="family",
                methodology_version="water-index-v1.0.0",
            )

    def test_nullable_score_keeps_safety_and_decision_separate(self):
        score = ConditionScore.objects.create(
            spot=self.spot,
            activity="swim",
            score=None,
            safety_status=ConditionScore.SafetyStatus.STOP,
            decision=ConditionScore.Decision.BLOCKED,
            confidence=0.98,
            coverage=1.0,
            gates=[{"reason_code": "OFFICIAL_ACCESS_CLOSED"}],
            methodology_version="water-index-v1.0.0",
        )
        self.assertIsNone(score.score)
        self.assertEqual(score.safety_status, "stop")
        self.assertEqual(score.decision, "blocked")

    def test_score_validates_snapshot_spot_and_score_range(self):
        other_spot = create_spot("Other Beach")
        snapshot = create_snapshot(other_spot)
        score = ConditionScore(
            spot=self.spot,
            snapshot=snapshot,
            activity="swim",
            score=70,
            score_range=[75, 90],
        )
        with self.assertRaises(ValidationError) as raised:
            score.full_clean()
        self.assertIn("snapshot", raised.exception.message_dict)
        self.assertIn("score_range", raised.exception.message_dict)

    def test_score_database_constraints_reject_out_of_range_values(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ConditionScore.objects.create(
                spot=self.spot,
                activity="surf",
                score=101,
                confidence=1.0,
                coverage=1.0,
            )

    def test_current_methodology_enforces_fail_closed_score_policy(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ConditionScore.objects.create(
                spot=self.spot,
                activity="swim",
                score=90,
                safety_status=ConditionScore.SafetyStatus.UNKNOWN,
                decision=ConditionScore.Decision.UNKNOWN,
                methodology_version="water-index-v1.0.0",
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            ConditionScore.objects.create(
                spot=self.spot,
                activity="swim",
                score=40,
                safety_status=ConditionScore.SafetyStatus.CAUTION,
                decision=ConditionScore.Decision.CAUTION,
                methodology_version="water-index-v1.0.0",
            )

    def test_null_public_score_can_preserve_an_uncertainty_range(self):
        score = ConditionScore(
            spot=self.spot,
            activity="swim",
            score=None,
            safety_status=ConditionScore.SafetyStatus.CLEAR,
            decision=ConditionScore.Decision.UNKNOWN,
            score_range=[20, 80],
            methodology_version="water-index-v1.0.0",
        )
        score.full_clean()

    def test_serializer_never_exposes_legacy_score_as_safe_when_status_unknown(self):
        score = ConditionScore.objects.create(
            spot=self.spot,
            activity="swim",
            score=8.5,
        )
        data = ConditionScoreSerializer(score).data
        self.assertIsNone(data["score"])
        self.assertIsNone(data["suitability_score"])
        with self.assertRaises(IntegrityError), transaction.atomic():
            ConditionScore.objects.create(
                spot=self.spot,
                activity="surf",
                score=80,
                confidence=-0.01,
                coverage=1.0,
            )

    def test_crowd_level_creation(self):
        crowd = CrowdLevel.objects.create(
            spot=self.spot,
            predicted_level="high",
        )
        self.assertEqual(crowd.predicted_level, "high")


class ObservationPersistenceTests(TestCase):
    def setUp(self):
        self.spot = create_spot()
        self.now = timezone.now()
        self.snapshot = create_snapshot(self.spot, fetched_at=self.now)

    def test_scalar_metric_round_trip_preserves_type_and_provenance(self):
        metric = create_metric(self.snapshot)
        loaded = ObservationMetric.objects.select_related("snapshot").get(pk=metric.pk)
        self.assertEqual(loaded.value, 22.5)
        self.assertEqual(loaded.value_type, ObservationMetric.ValueType.NUMBER)
        self.assertEqual(loaded.station_id, "GYEONGPO")
        self.assertEqual(loaded.snapshot.provider_record_id, "beach-1")

    def test_missing_metric_has_typed_null_value(self):
        metric = ObservationMetric.objects.create(
            snapshot=self.snapshot,
            name="water_quality_status",
            value_type=ObservationMetric.ValueType.TEXT,
            state=ObservationMetric.State.MISSING,
            confidence=0.0,
            source="MOE",
            spatial_scope="Gyeongpo Beach",
            observed_at=self.now - timedelta(minutes=5),
            fetched_at=self.now,
        )
        self.assertIsNone(metric.value)

    def test_snapshot_metric_name_is_unique(self):
        create_metric(self.snapshot)
        with self.assertRaises(IntegrityError), transaction.atomic():
            create_metric(self.snapshot, value=23.0)

    def test_provider_record_is_idempotent_per_ingestion_version(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            create_snapshot(self.spot, record_id="beach-1", fetched_at=self.now)

        new_version = ObservationSnapshot.objects.create(
            spot=self.spot,
            provider="KHOA",
            provider_record_id="beach-1",
            state=ObservationSnapshot.SourceState.LIVE,
            observed_at=self.now - timedelta(minutes=5),
            fetched_at=self.now,
            spatial_scope="Gyeongpo Beach point forecast",
            ingestion_version="khoa-v2",
        )
        self.assertNotEqual(new_version.pk, self.snapshot.pk)

    def test_blank_provider_record_ids_can_record_repeated_errors(self):
        for _ in range(2):
            ObservationSnapshot.objects.create(
                spot=self.spot,
                provider="KHOA",
                state=ObservationSnapshot.SourceState.ERROR,
                fetched_at=self.now,
                spatial_scope="Gyeongpo Beach",
                ingestion_version="khoa-v1",
            )
        self.assertEqual(
            ObservationSnapshot.objects.filter(provider_record_id="").count(),
            2,
        )

    def test_typed_value_constraint_rejects_mismatched_columns(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ObservationMetric.objects.create(
                snapshot=self.snapshot,
                name="bad_metric",
                value_type=ObservationMetric.ValueType.TEXT,
                numeric_value=12.0,
                state=ObservationMetric.State.VALID,
                source="test",
                spatial_scope="test point",
                observed_at=self.now - timedelta(minutes=1),
                fetched_at=self.now,
            )

    def test_metric_constraints_reject_future_observation_and_bad_confidence(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ObservationMetric.objects.create(
                snapshot=self.snapshot,
                name="future_metric",
                value_type=ObservationMetric.ValueType.NUMBER,
                numeric_value=12,
                confidence=0.5,
                source="test",
                spatial_scope="test point",
                observed_at=self.now + timedelta(minutes=1),
                fetched_at=self.now,
            )

    def test_forecast_metric_requires_both_validity_bounds(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ObservationMetric.objects.create(
                snapshot=self.snapshot,
                name="windowless_forecast",
                value_type=ObservationMetric.ValueType.NUMBER,
                numeric_value=12,
                mode=ObservationMetric.Mode.FORECAST,
                source="test",
                spatial_scope="test point",
                observed_at=self.now - timedelta(minutes=1),
                fetched_at=self.now,
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            ObservationMetric.objects.create(
                snapshot=self.snapshot,
                name="bad_confidence",
                value_type=ObservationMetric.ValueType.NUMBER,
                numeric_value=12,
                confidence=1.01,
                source="test",
                spatial_scope="test point",
                observed_at=self.now - timedelta(minutes=1),
                fetched_at=self.now,
            )

    def test_serializer_exposes_public_provenance_without_secret_query(self):
        create_metric(self.snapshot)
        snapshot = ObservationSnapshot.objects.prefetch_related("metrics").get(
            pk=self.snapshot.pk
        )
        data = ObservationSnapshotSerializer(snapshot).data
        self.assertEqual(
            data["provenance"]["source_url"],
            "https://apis.data.go.kr/khoa/beach",
        )
        metric = data["metrics"][0]
        self.assertEqual(metric["provenance"]["source_url"], "")
        serialized = str(data)
        self.assertNotIn("SERVER_SECRET", serialized)
        self.assertNotIn("api-password", serialized)
        self.assertNotIn("numeric_value", metric)
        self.assertNotIn("text_value", metric)
        self.assertNotIn("raw_payload", serialized)

    def test_serializer_exposes_minimal_credential_free_metric_lineage(self):
        source = create_metric(self.snapshot)
        fused_snapshot = create_snapshot(
            self.spot,
            record_id="fused-lineage",
            fetched_at=self.now,
            provider="PONGDANG_FUSION",
        )
        derived = create_metric(
            fused_snapshot,
            name="water_temperature_c",
            value=22.5,
        )
        ObservationMetricLineage.objects.create(
            derived_metric=derived,
            source_metric=source,
            relation=ObservationMetricLineage.Relation.SELECTED,
            priority=110,
        )

        data = ObservationSnapshotSerializer(fused_snapshot).data

        lineage = data["metrics"][0]["lineage"]
        self.assertEqual(len(lineage), 1)
        self.assertEqual(lineage[0]["source_metric_id"], source.pk)
        self.assertEqual(lineage[0]["relation"], "selected")
        self.assertEqual(lineage[0]["priority"], 110)
        self.assertEqual(lineage[0]["provider"], "KHOA")
        self.assertEqual(lineage[0]["source_url"], "")
        self.assertNotIn("provider_record_id", lineage[0])
        serialized = str(data)
        self.assertNotIn("SERVER_SECRET", serialized)
        self.assertNotIn("api-password", serialized)


class ConditionViewSetTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.spot = create_spot("Test River API", "river")
        self.now = timezone.now()
        self.snapshot = create_snapshot(self.spot, fetched_at=self.now)
        create_metric(self.snapshot)
        self.old_score = ConditionScore.objects.create(
            spot=self.spot,
            activity="swim",
            score=70,
            safety_status=ConditionScore.SafetyStatus.CLEAR,
            decision=ConditionScore.Decision.CONSIDER,
            confidence=0.8,
            coverage=0.8,
            score_range=[70, 90],
            methodology_version="water-index-v1.0.0",
            evaluated_at=self.now - timedelta(hours=1),
        )
        self.score = ConditionScore.objects.create(
            spot=self.spot,
            snapshot=self.snapshot,
            activity="swim",
            score=85,
            safety_status=ConditionScore.SafetyStatus.CLEAR,
            decision=ConditionScore.Decision.RECOMMENDED,
            confidence=0.95,
            coverage=1.0,
            score_range=[85, 85],
            gates=[
                {
                    "reason_code": "ACCESS_OPEN",
                    "source_url": "https://api.example/gate?api_key=DO_NOT_EXPOSE",
                    "raw_payload": {"internal": True},
                }
            ],
            contributions=[
                {
                    "metric_name": "water_temperature_c",
                    "source_url": "https://api.example/metric?serviceKey=DO_NOT_EXPOSE",
                    "headers": {"Authorization": "Bearer DO_NOT_EXPOSE"},
                }
            ],
            methodology_version="water-index-v1.0.0",
            evaluated_at=self.now,
        )

    def test_queryset_selects_spot_and_prefetches_snapshot_metrics(self):
        viewset = ConditionScoreViewSet()
        queryset = viewset.get_queryset()
        with self.assertNumQueries(3):
            scores = list(queryset)
            self.assertEqual(scores[0].spot.name, "Test River API")
            self.assertEqual(scores[0].snapshot.metrics.all()[0].value, 22.5)

    def test_observation_api_is_read_only_filterable_and_query_bounded(self):
        other_spot = create_spot("Other")
        create_snapshot(other_spot, record_id="other")
        url = f"/api/v1/conditions/observations/?spot={self.spot.pk}&provider=KHOA"
        with CaptureQueriesContext(connection=transaction.get_connection()) as queries:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(queries), 4)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["metrics"][0]["value"], 22.5)
        self.assertEqual(
            self.client.post("/api/v1/conditions/observations/", {}).status_code,
            405,
        )

    def test_latest_api_returns_latest_filtered_spot_activity_only(self):
        other_spot = create_spot("Surf Beach")
        ConditionScore.objects.create(
            spot=other_spot,
            activity="surf",
            score=92,
            safety_status=ConditionScore.SafetyStatus.CLEAR,
            decision=ConditionScore.Decision.RECOMMENDED,
            confidence=1.0,
            coverage=1.0,
            score_range=[92, 92],
            methodology_version="water-index-v1.0.0",
            evaluated_at=self.now,
        )
        response = self.client.get(
            f"/api/v1/conditions/scores/latest/?spot={self.spot.pk}&activity=swim"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        result = response.data["results"][0]
        self.assertEqual(result["id"], self.score.pk)
        self.assertEqual(result["score"], 85.0)
        self.assertEqual(result["suitability_score"], 85.0)
        self.assertEqual(result["safety_status"], "clear")
        self.assertEqual(result["decision"], "recommended")
        self.assertEqual(result["participant_profile"], "general")
        self.assertEqual(
            result["gates"][0]["source_url"],
            "https://api.example/gate",
        )
        self.assertNotIn("raw_payload", result["gates"][0])
        self.assertEqual(
            result["contributions"][0]["source_url"],
            "https://api.example/metric",
        )
        self.assertNotIn("headers", result["contributions"][0])
        self.assertNotIn("DO_NOT_EXPOSE", str(result))

    def test_latest_api_groups_profiles_and_ignores_future_evaluations(self):
        family = ConditionScore.objects.create(
            spot=self.spot,
            snapshot=self.snapshot,
            activity="swim",
            participant_profile="family",
            score=None,
            safety_status=ConditionScore.SafetyStatus.UNKNOWN,
            decision=ConditionScore.Decision.UNKNOWN,
            confidence=0.8,
            coverage=0.8,
            methodology_version="water-index-v1.0.0",
            evaluated_at=self.now,
        )
        future_snapshot = create_snapshot(
            self.spot,
            record_id="future-profile",
            fetched_at=self.now + timedelta(hours=1),
        )
        future = ConditionScore.objects.create(
            spot=self.spot,
            snapshot=future_snapshot,
            activity="swim",
            participant_profile="general",
            score=99,
            safety_status=ConditionScore.SafetyStatus.CLEAR,
            decision=ConditionScore.Decision.RECOMMENDED,
            confidence=1.0,
            coverage=1.0,
            methodology_version="water-index-v1.0.0",
            evaluated_at=self.now + timedelta(hours=1),
        )

        response = self.client.get(
            f"/api/v1/conditions/scores/latest/?spot={self.spot.pk}&activity=swim"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], self.score.pk)
        self.assertNotEqual(response.data["results"][0]["id"], future.pk)

        family_only = self.client.get(
            f"/api/v1/conditions/scores/latest/?spot={self.spot.pk}"
            "&activity=swim&participant_profile=family"
        )
        self.assertEqual(family_only.data["count"], 1)
        self.assertEqual(family_only.data["results"][0]["id"], family.pk)

    def test_score_list_serialization_has_no_n_plus_one_queries(self):
        for index in range(3):
            snapshot = create_snapshot(
                self.spot,
                record_id=f"beach-extra-{index}",
                fetched_at=self.now + timedelta(minutes=index + 1),
            )
            create_metric(snapshot)
            ConditionScore.objects.create(
                spot=self.spot,
                snapshot=snapshot,
                activity=f"activity-{index}",
                score=80,
                safety_status=ConditionScore.SafetyStatus.CLEAR,
                decision=ConditionScore.Decision.RECOMMENDED,
                confidence=1.0,
                coverage=1.0,
                score_range=[80, 80],
                evaluated_at=self.now + timedelta(minutes=index + 1),
            )
        with CaptureQueriesContext(connection=transaction.get_connection()) as queries:
            response = self.client.get("/api/v1/conditions/scores/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 5)
        self.assertLessEqual(len(queries), 4)

    def test_score_api_is_read_only(self):
        response = self.client.post(
            "/api/v1/conditions/scores/",
            {"spot": self.spot.pk, "activity": "swim", "score": 99},
            format="json",
        )
        self.assertEqual(response.status_code, 405)
