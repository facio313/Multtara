from __future__ import annotations

from datetime import timedelta

from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.conditions.models import ConditionScore, ObservationMetric, ObservationSnapshot
from apps.spots.models import WaterSpot
from apps.trips.models import Itinerary, RouteMatrixSnapshot
from apps.users.models import User
from services.ingestion.fusion import FUSION_PROVIDER, FUSION_VERSION
from services.providers.valhalla import RouteMatrixResult, RouteMatrixValue
from services.routing import persist_route_matrix
from apps.trips.views import MAX_CANDIDATE_POOL


@override_settings(PONGDANG_SSO_ENABLED=False)
class RecommendationApiTests(TestCase):
    """Exercise public planning plus the local-branch saved-owner flow."""

    def setUp(self) -> None:
        cache.clear()
        self.client = APIClient()
        self.now = timezone.now()

    def spot(
        self,
        name: str,
        *,
        confidence: float = 1.0,
        **overrides,
    ) -> WaterSpot:
        values = {
            "type": "beach",
            "name": name,
            "lat": 37.8055,
            "lng": 128.9070,
            "region": "강원",
            "address": "강원특별자치도 강릉시",
            "preference_features": {"quiet": 0.9, "activity_level": 0.2},
            "opening_windows": [{"start_minute": 0, "end_minute": 1440}],
            "cost_krw": 0,
            "age_policy_known": True,
            "minimum_age": 0,
            "catalog_confidence": confidence,
            "catalog_verification": "verified",
            "tags": ["coast", "calm"],
        }
        values.update(overrides)
        return WaterSpot.objects.create(**values)

    def condition(
        self,
        spot: WaterSpot,
        *,
        activity: str = "swim",
        safety: str = "clear",
        decision: str = "recommended",
        score: float | None = 90.0,
        evaluated_at=None,
        participant_profile: str = "general",
        participant_skill_level: str = "unspecified",
        include_family_gates: bool = False,
        missing_metrics: tuple[str, ...] = (),
        lightning_age_minutes: int = 2,
        official_grade_detail: str | None = None,
        methodology_version: str = "water-index-v1.0.0",
    ) -> ConditionScore:
        evaluated_at = evaluated_at or self.now
        snapshot = ObservationSnapshot.objects.create(
            spot=spot,
            provider=FUSION_PROVIDER,
            provider_record_id=(
                f"fusion-{spot.pk}-{activity}-{evaluated_at.isoformat()}"
            ),
            state="live",
            fetched_at=evaluated_at,
            valid_from=evaluated_at - timedelta(minutes=10),
            valid_until=evaluated_at + timedelta(minutes=10),
            spatial_scope=f"spot:{spot.pk}",
            ingestion_version=FUSION_VERSION,
        )
        metrics = [
            ("official_entry_status", "open", "LOCAL_AUTHORITY", 2, 10),
            ("weather_alert_level", "none", "KMA_WARNING", 2, 10),
            (
                "lightning_clearance_minutes",
                30,
                "KMA_LIGHTNING",
                lightning_age_minutes,
                10,
            ),
            ("rip_current_risk", "attention", "KHOA", 2, 10),
            ("water_quality_status", "pass", "MOE", 2, 1_440),
            ("marine_hazard_status", "clear", "KMA_WARNING", 2, 10),
            ("official_activity_grade", "very_good", "KHOA", 2, 480),
            ("water_temperature_c", 24, "KHOA", 2, 60),
            ("air_temperature_c", 26, "KMA", 2, 60),
            ("wave_height_m", 0.3, "KHOA", 2, 60),
            ("wind_speed_ms", 3, "KMA", 2, 60),
            ("precipitation_1h_mm", 0, "KMA", 2, 60),
            ("uv_index", 3, "KMA", 2, 60),
            ("crowd_level", "low", "LOCAL_AUTHORITY", 2, 60),
        ]
        if include_family_gates:
            metrics.extend(
                (
                    ("patrol_status", "active", "LOCAL_AUTHORITY", 2, 10),
                    (
                        "designated_swim_zone_status",
                        "open",
                        "LOCAL_AUTHORITY",
                        2,
                        10,
                    ),
                )
            )
        if official_grade_detail is not None:
            metrics.append(
                (
                    "official_grade_detail",
                    official_grade_detail,
                    "KHOA",
                    2,
                    480,
                )
            )
        for name, value, source, observed_age, valid_minutes in metrics:
            if name in missing_metrics:
                continue
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
                value_fields["text_value"] = value
            ObservationMetric.objects.create(
                snapshot=snapshot,
                name=name,
                value_type=value_type,
                **value_fields,
                unit="canonical",
                mode="observed",
                state="valid",
                confidence=1.0,
                source=source,
                source_url="https://example.go.kr/status",
                spatial_scope=f"spot:{spot.pk}",
                observed_at=evaluated_at - timedelta(minutes=observed_age),
                fetched_at=evaluated_at,
                valid_from=evaluated_at - timedelta(minutes=10),
                valid_until=evaluated_at + timedelta(minutes=valid_minutes),
            )
        persisted_score = score
        persisted_decision = decision
        if activity == "surf" and participant_skill_level == "unspecified":
            # The unscoped row retains its full source snapshot for
            # request-time, skill-matched evaluation but cannot publish a
            # participant suitability result by itself.
            persisted_score = None
            if safety in {"clear", "unknown"}:
                persisted_decision = "unknown"
        return ConditionScore.objects.create(
            spot=spot,
            snapshot=snapshot,
            activity=activity,
            participant_profile=participant_profile,
            participant_skill_level=participant_skill_level,
            score=persisted_score,
            safety_status=safety,
            decision=persisted_decision,
            confidence=1.0,
            coverage=1.0,
            methodology_version=methodology_version,
            evaluated_at=evaluated_at,
        )

    def payload(self, **overrides):
        data = {
            "activity": "swim",
            "preferences": [
                {"feature": "quiet", "target": 1.0, "weight": 0.7},
                {
                    "feature": "activity_level",
                    "target": 0.0,
                    "weight": 0.3,
                },
            ],
            "party": {
                "ages": [30],
                "requires_accessibility": False,
                "bringing_pet": False,
            },
            "persona_label": "wellness",
            "limit": 6,
        }
        data.update(overrides)
        return data

    def test_only_current_clear_operating_candidate_is_recommended(self) -> None:
        eligible = self.spot("검증된 해변")
        self.condition(eligible)
        self.spot("자료 없는 해변")
        stopped = self.spot("통제된 해변")
        self.condition(stopped, safety="stop", decision="blocked", score=None)

        response = self.client.post(
            "/api/v1/trips/recommendations/",
            self.payload(),
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["persona_label"], "wellness")
        self.assertEqual(len(body["recommendations"]), 1)
        recommendation = body["recommendations"][0]
        self.assertEqual(recommendation["spot"]["id"], eligible.pk)
        self.assertEqual(
            recommendation["water_index"]["safety_status"], "clear"
        )
        self.assertEqual(
            recommendation["water_index"]["sources"],
            [
                "KHOA",
                "KMA",
                "KMA_LIGHTNING",
                "KMA_WARNING",
                "LOCAL_AUTHORITY",
                "MOE",
            ],
        )
        self.assertGreater(body["excluded_summary"]["SAFETY_BLOCKED"], 0)
        self.assertGreater(body["excluded_summary"]["SAFETY_UNKNOWN"], 0)
        refs = recommendation["water_index"]["source_refs"]
        self.assertTrue(refs)
        self.assertTrue(all(ref["source_url"] == "https://example.go.kr/status" for ref in refs))
        self.assertNotIn("serviceKey", str(recommendation))
        self.assertIsNotNone(recommendation["water_index"]["valid_until"])
        self.assertEqual(
            recommendation["explanation"]["policy_version"],
            "recommendation-v1",
        )

    def test_demo_and_unverified_catalog_rows_are_not_recommended(self) -> None:
        eligible = self.spot("검증된 해변")
        demo = self.spot(
            "데모 해변",
            catalog_source="PONGDANG_DEMO",
            catalog_verification="verified",
        )
        unverified = self.spot(
            "미검증 해변",
            catalog_verification="unknown",
        )
        self.condition(eligible)
        self.condition(demo)
        self.condition(unverified)

        response = self.client.post(
            "/api/v1/trips/recommendations/",
            self.payload(),
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["spot"]["id"] for item in response.json()["recommendations"]],
            [eligible.pk],
        )

    def test_recommendation_image_url_is_public_and_credential_free(self) -> None:
        spot = self.spot(
            "공개 이미지",
            image_url=(
                "https://cdn.example.com/travel/photo.jpg"
                "?serviceKey=server-secret#private"
            ),
        )
        self.condition(spot)

        response = self.client.post(
            "/api/v1/trips/recommendations/",
            self.payload(),
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["recommendations"][0]["spot"]["image_url"],
            "https://cdn.example.com/travel/photo.jpg",
        )

    def test_future_or_old_condition_is_not_used_as_current_safety(self) -> None:
        future = self.spot("미래 평가")
        self.condition(future, evaluated_at=self.now + timedelta(hours=1))
        old = self.spot("오래된 평가")
        self.condition(old, evaluated_at=self.now - timedelta(minutes=16))

        response = self.client.post(
            "/api/v1/trips/recommendations/",
            self.payload(),
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["recommendations"], [])
        self.assertEqual(response.json()["excluded_summary"]["SAFETY_UNKNOWN"], 2)

    def test_metric_specific_lightning_expiry_invalidates_recent_clear_score(self) -> None:
        stale = self.spot("낙뢰 근거 만료")
        self.condition(stale, lightning_age_minutes=6)

        response = self.client.post(
            "/api/v1/trips/recommendations/",
            self.payload(),
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["recommendations"], [])
        self.assertEqual(response.json()["excluded_summary"]["SAFETY_UNKNOWN"], 1)

    def test_recorded_stop_remains_blocked_after_the_reuse_window(self) -> None:
        stopped = self.spot("명시적 통제 유지")
        self.condition(
            stopped,
            safety="stop",
            decision="blocked",
            score=None,
            evaluated_at=self.now - timedelta(hours=2),
        )

        response = self.client.post(
            "/api/v1/trips/recommendations/",
            self.payload(),
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["recommendations"], [])
        self.assertEqual(response.json()["excluded_summary"]["SAFETY_BLOCKED"], 1)

    def test_minor_party_requires_family_score_and_explicit_session_supervision(self) -> None:
        general_only = self.spot("일반 평가만 있음")
        self.condition(general_only, participant_profile="general")
        family_missing_patrol = self.spot("순찰 근거 없음")
        self.condition(
            family_missing_patrol,
            participant_profile="family",
            safety="unknown",
            decision="unknown",
            score=None,
            include_family_gates=True,
            missing_metrics=("patrol_status",),
        )
        family_ready = self.spot("가족 근거 완비")
        self.condition(
            family_ready,
            participant_profile="family",
            safety="unknown",
            decision="unknown",
            score=None,
            include_family_gates=True,
        )
        payload = self.payload()
        payload["party"] = {
            "ages": [10, 35],
            "requires_accessibility": False,
            "bringing_pet": False,
            "adult_supervision_confirmed": True,
        }

        response = self.client.post(
            "/api/v1/trips/recommendations/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["participant_profile"], "family")
        self.assertEqual(
            [item["spot"]["id"] for item in body["recommendations"]],
            [family_ready.pk],
        )
        self.assertEqual(
            body["recommendations"][0]["water_index"]["participant_profile"],
            "family",
        )
        self.assertEqual(
            body["recommendations"][0]["water_index"]["safety_status"],
            "clear",
        )
        self.assertIn(
            "SESSION_CONTEXT",
            body["recommendations"][0]["water_index"]["sources"],
        )

    def test_minor_party_without_confirmed_supervision_fails_closed(self) -> None:
        family = self.spot("감독 확인 필요")
        self.condition(
            family,
            participant_profile="family",
            safety="unknown",
            decision="unknown",
            score=None,
            include_family_gates=True,
        )
        payload = self.payload()
        payload["party"]["ages"] = [8, 38]

        response = self.client.post(
            "/api/v1/trips/recommendations/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["recommendations"], [])
        self.assertEqual(response.json()["excluded_summary"]["SAFETY_UNKNOWN"], 1)

    def test_adult_beginner_swimmer_uses_conservative_family_profile(self) -> None:
        family_ready = self.spot("성인 초급 수영")
        self.condition(
            family_ready,
            participant_profile="family",
            safety="unknown",
            decision="unknown",
            score=None,
            include_family_gates=True,
        )
        payload = self.payload()
        payload["party"].update(
            {
                "ages": [30],
                "adult_supervision_confirmed": True,
                "participant_skill_level": "beginner",
            }
        )

        response = self.client.post(
            "/api/v1/trips/recommendations/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["participant_profile"], "family")
        self.assertEqual(body["participant_skill_level"], "beginner")
        self.assertEqual(
            [item["spot"]["id"] for item in body["recommendations"]],
            [family_ready.pk],
        )

    def test_surf_official_grade_requires_explicit_matching_skill(self) -> None:
        scenarios = (
            ("beginner", "초중급자에게 적합", True),
            ("intermediate", "초중급자에게 적합", True),
            ("advanced", "초중급자에게 적합", False),
            ("unspecified", "초중급자에게 적합", False),
            ("intermediate", "모든 서퍼에게 적합", False),
        )
        for index, (skill_level, grade_detail, expected) in enumerate(scenarios):
            with self.subTest(
                skill_level=skill_level,
                grade_detail=grade_detail,
            ):
                region = f"서핑-{index}"
                spot = self.spot(f"서핑 포인트 {index}", region=region)
                self.condition(
                    spot,
                    activity="surf",
                    official_grade_detail=grade_detail,
                    participant_skill_level=skill_level,
                )
                payload = self.payload(activity="surf", region=region)
                payload["party"]["participant_skill_level"] = skill_level

                response = self.client.post(
                    "/api/v1/trips/recommendations/",
                    payload,
                    format="json",
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    bool(response.json()["recommendations"]),
                    expected,
                )

    def test_invalid_participant_skill_level_is_rejected(self) -> None:
        payload = self.payload()
        payload["party"]["participant_skill_level"] = "expert"

        response = self.client.post(
            "/api/v1/trips/recommendations/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("participant_skill_level", response.json()["party"])

    def test_not_recommended_water_index_is_not_eligible(self) -> None:
        unsuitable = self.spot("안전하지만 부적합")
        self.condition(
            unsuitable,
            safety="clear",
            decision="not_recommended",
            score=35,
        )

        response = self.client.post(
            "/api/v1/trips/recommendations/",
            self.payload(),
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["recommendations"], [])
        self.assertEqual(response.json()["excluded_summary"]["SAFETY_BLOCKED"], 1)

    def test_missing_windows_or_cost_are_not_inferred_as_open_or_free(self) -> None:
        no_window = self.spot("시간 미확인", opening_windows=[])
        self.condition(no_window)
        no_cost = self.spot("요금 미확인", cost_krw=None)
        self.condition(no_cost)

        response = self.client.post(
            "/api/v1/trips/recommendations/",
            self.payload(),
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["recommendations"], [])
        self.assertEqual(response.json()["excluded_summary"]["OPERATION_UNKNOWN"], 2)

    def test_unsupported_activity_spot_type_pair_is_rejected_or_excluded(self) -> None:
        invalid_request = self.payload(spot_type="waterpark")
        response = self.client.post(
            "/api/v1/trips/recommendations/",
            invalid_request,
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("spot_type", response.json())

        mixed_catalog = self.spot("수영으로 잘못 분류된 시설", type="waterpark")
        self.condition(mixed_catalog)
        response = self.client.post(
            "/api/v1/trips/recommendations/",
            self.payload(),
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["recommendations"], [])
        self.assertEqual(response.json()["excluded_summary"]["SAFETY_UNKNOWN"], 1)

    def test_response_serializes_the_request_time_evaluation_used_for_ranking(self) -> None:
        spot = self.spot("재평가 응답 일치")
        stored = self.condition(
            spot,
            safety="clear",
            decision="consider",
            score=60,
        )

        response = self.client.post(
            "/api/v1/trips/recommendations/",
            self.payload(),
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        water_index = response.json()["recommendations"][0]["water_index"]
        self.assertEqual(water_index["decision"], "recommended")
        self.assertGreaterEqual(water_index["suitability_score"], 80)
        self.assertNotEqual(water_index["suitability_score"], stored.score)
        self.assertNotEqual(
            water_index["evaluated_at"],
            stored.evaluated_at.isoformat().replace("+00:00", "Z"),
        )

    def test_historical_scores_are_reduced_to_latest_rows_in_the_database(self) -> None:
        spot = self.spot("이력 다수 해변")
        for minutes_ago in range(8, -1, -1):
            self.condition(
                spot,
                evaluated_at=self.now - timedelta(minutes=minutes_ago),
            )

        with CaptureQueriesContext(connection) as queries:
            response = self.client.post(
                "/api/v1/trips/recommendations/",
                self.payload(),
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["recommendations"]), 1)
        self.assertLessEqual(len(queries), 5)

    def test_cross_spot_snapshot_cannot_supply_another_spots_safety(self) -> None:
        source_spot = self.spot("근거 원본", region="강원")
        source_score = self.condition(source_spot)
        snapshot = source_score.snapshot
        source_score.delete()
        target = self.spot("근거 도용 대상", region="서울")
        ConditionScore.objects.create(
            spot=target,
            snapshot=snapshot,
            activity="swim",
            participant_profile="general",
            score=95,
            safety_status="clear",
            decision="recommended",
            confidence=1.0,
            coverage=1.0,
            methodology_version="water-index-v1.0.0",
            evaluated_at=self.now,
        )

        response = self.client.post(
            "/api/v1/trips/recommendations/",
            self.payload(region="서울"),
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["candidate_count"], 1)
        self.assertEqual(response.json()["recommendations"], [])
        self.assertEqual(response.json()["excluded_summary"]["SAFETY_UNKNOWN"], 1)

    def test_party_constraints_fail_closed(self) -> None:
        spot = self.spot("접근성 미확인")
        self.condition(spot)
        payload = self.payload()
        payload["party"]["requires_accessibility"] = True

        response = self.client.post(
            "/api/v1/trips/recommendations/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["recommendations"], [])
        self.assertEqual(
            response.json()["excluded_summary"]["ACCESSIBILITY_UNKNOWN"], 1
        )

    def test_invalid_or_duplicate_preferences_are_rejected(self) -> None:
        invalid = self.payload(
            preferences=[
                {"feature": "quiet", "target": 0.5},
                {"feature": "QUIET", "target": 0.7},
            ]
        )
        response = self.client.post(
            "/api/v1/trips/recommendations/",
            invalid,
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_preference_count_has_an_inclusive_twenty_item_limit(self) -> None:
        preferences = [
            {"feature": f"feature_{index}", "target": 0.5, "weight": 1.0}
            for index in range(20)
        ]

        accepted = self.client.post(
            "/api/v1/trips/recommendations/",
            self.payload(preferences=preferences),
            format="json",
        )
        rejected = self.client.post(
            "/api/v1/trips/recommendations/",
            self.payload(
                preferences=[
                    *preferences,
                    {"feature": "feature_20", "target": 0.5, "weight": 1.0},
                ]
            ),
            format="json",
        )

        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(rejected.status_code, 400)
        self.assertIn("preferences", rejected.json())

    def test_unfiltered_candidate_scope_must_fit_the_bounded_pool(self) -> None:
        WaterSpot.objects.bulk_create(
            [
                WaterSpot(
                    type="beach",
                    name=f"후보 {index}",
                    lat=37.8,
                    lng=128.9,
                    region="강원",
                    address="강원특별자치도 강릉시",
                    catalog_verification="verified",
                )
                for index in range(MAX_CANDIDATE_POOL)
            ]
        )

        boundary = self.client.post(
            "/api/v1/trips/recommendations/",
            self.payload(),
            format="json",
        )
        self.spot("후보 상한 초과")
        too_broad = self.client.post(
            "/api/v1/trips/recommendations/",
            self.payload(),
            format="json",
        )

        self.assertEqual(boundary.status_code, 200)
        self.assertEqual(boundary.json()["candidate_pool_evaluated"], 100)
        self.assertEqual(too_broad.status_code, 400)
        self.assertIn("region", too_broad.json())

    def test_recommendation_throttle_ignores_spoofed_forwarding_headers(self) -> None:
        responses = [
            self.client.post(
                "/api/v1/trips/recommendations/",
                self.payload(),
                format="json",
                HTTP_X_FORWARDED_FOR=f"198.51.100.{index}",
            )
            for index in range(1, 12)
        ]

        self.assertTrue(all(response.status_code == 200 for response in responses[:10]))
        self.assertEqual(responses[10].status_code, 429)

    def test_dynamic_water_suitability_overrides_legacy_catalog_feature(self) -> None:
        spot = self.spot(
            "동적 수질 적합도",
            preference_features={"water_suitability": 0.0},
        )
        self.condition(spot)
        payload = self.payload(
            preferences=[
                {"feature": "water_suitability", "target": 1.0, "weight": 1.0}
            ]
        )

        response = self.client.post(
            "/api/v1/trips/recommendations/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        recommendation = response.json()["recommendations"][0]
        contribution = recommendation["contributions"][0]
        self.assertEqual(contribution["feature"], "water_suitability")
        self.assertGreater(contribution["candidate_value"], 0.8)

    def test_non_current_methodology_version_is_not_reused(self) -> None:
        spot = self.spot("호환되지 않는 방법론")
        self.condition(
            spot,
            methodology_version="water-index-v999-experimental",
        )

        response = self.client.post(
            "/api/v1/trips/recommendations/",
            self.payload(),
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["recommendations"], [])
        self.assertEqual(response.json()["excluded_summary"]["SAFETY_UNKNOWN"], 1)

    def itinerary_payload(self, *, start, end, candidate, save=False):
        return {
            "recommendation": self.payload(region="강원", limit=3),
            "candidate_ids": [candidate.pk],
            "start_spot": start.pk,
            "end_spot": end.pk,
            "transport": "drive",
            "plan_date": timezone.localdate().isoformat(),
            "start_minute": 480,
            "end_minute": 720,
            "budget_krw": 20_000,
            "bad_weather": False,
            "save": save,
            "title": "검증된 강릉 하루",
        }

    def route_matrix(self, *, start, end, candidate, observed_at=None, hours=24):
        observed_at = observed_at or timezone.now()
        result = RouteMatrixResult(
            provider="valhalla",
            source_url="https://routing.example.com/valhalla?internal=removed",
            transport="drive",
            values=(
                RouteMatrixValue(start.pk, candidate.pk, 300, 2_000),
                RouteMatrixValue(candidate.pk, end.pk, 360, 2_500),
                RouteMatrixValue(start.pk, end.pk, 900, 8_000),
            ),
        )
        return persist_route_matrix(
            result,
            observed_at=observed_at,
            fetched_at=observed_at,
            valid_for=timedelta(hours=hours),
            spot_ids=(start.pk, end.pk, candidate.pk),
        )[0]

    def test_itinerary_plan_uses_only_persisted_current_route_evidence(self):
        start = self.spot("출발 거점")
        end = self.spot("종료 거점")
        candidate = self.spot("일정 후보")
        self.condition(candidate)
        route_snapshot = self.route_matrix(
            start=start,
            end=end,
            candidate=candidate,
        )

        response = self.client.post(
            "/api/v1/trips/itineraries/plan/",
            self.itinerary_payload(start=start, end=end, candidate=candidate),
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "draft")
        self.assertEqual(
            [item["candidate_id"] for item in body["plan"]["visits"]],
            [str(candidate.pk)],
        )
        self.assertEqual(
            body["route_evidence"]["snapshot_ids"],
            [route_snapshot.pk],
        )
        self.assertEqual(body["route_evidence"]["data_state"], "live")
        self.assertEqual(
            body["route_evidence"]["source_urls"],
            ["https://routing.example.com/valhalla"],
        )
        self.assertIsNotNone(body["safety_revalidation_required_at"])
        self.assertEqual(len(body["water_evidence"]), 1)
        self.assertEqual(body["water_evidence"][0]["spot_id"], candidate.pk)
        self.assertEqual(body["water_evidence"][0]["safety_status"], "clear")
        self.assertTrue(body["water_evidence"][0]["source_refs"])
        self.assertIn("revalidated", body["execution_notice"])
        self.assertIsNone(body["saved_itinerary_id"])

    def test_unvisited_expired_candidate_does_not_expire_visited_water_evidence(self):
        start = self.spot("방문 근거 출발")
        end = self.spot("방문 근거 종료")
        visited = self.spot("실제 방문 후보")
        unvisited = self.spot("만료되어 탈락한 후보")
        self.condition(visited)
        expired = self.condition(unvisited)
        expired_at = self.now - timedelta(minutes=1)
        ObservationSnapshot.objects.filter(pk=expired.snapshot_id).update(
            valid_until=expired_at,
        )
        ObservationMetric.objects.filter(snapshot_id=expired.snapshot_id).update(
            valid_until=expired_at,
        )
        self.route_matrix(start=start, end=end, candidate=visited)
        payload = self.itinerary_payload(
            start=start,
            end=end,
            candidate=visited,
        )
        payload["candidate_ids"] = [visited.pk, unvisited.pk]

        response = self.client.post(
            "/api/v1/trips/itineraries/plan/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(
            [item["candidate_id"] for item in body["plan"]["visits"]],
            [str(visited.pk)],
        )
        self.assertEqual(
            [item["spot_id"] for item in body["water_evidence"]],
            [visited.pk],
        )
        self.assertEqual(
            body["safety_revalidation_required_at"],
            body["water_evidence"][0]["valid_until"],
        )

    def test_missing_or_expired_route_matrix_fails_closed(self):
        start = self.spot("경로 없는 출발")
        end = self.spot("경로 없는 종료")
        candidate = self.spot("경로 없는 후보")
        self.condition(candidate)
        self.route_matrix(
            start=start,
            end=end,
            candidate=candidate,
            observed_at=timezone.now() - timedelta(days=2),
            hours=1,
        )

        response = self.client.post(
            "/api/v1/trips/itineraries/plan/",
            self.itinerary_payload(start=start, end=end, candidate=candidate),
            format="json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["reason_code"], "NO_CURRENT_ROUTE_TO_END")
        self.assertEqual(response.json()["route_evidence"]["data_state"], "missing")

    def test_unsafe_candidate_is_skipped_even_when_its_route_exists(self):
        start = self.spot("안전 게이트 출발")
        end = self.spot("안전 게이트 종료")
        candidate = self.spot("통제 후보")
        self.condition(candidate, safety="stop", decision="blocked", score=None)
        self.route_matrix(start=start, end=end, candidate=candidate)

        response = self.client.post(
            "/api/v1/trips/itineraries/plan/",
            self.itinerary_payload(start=start, end=end, candidate=candidate),
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["plan"]["visits"], [])
        self.assertEqual(
            response.json()["plan"]["skipped"][0]["reason_code"],
            "HARD_GATE_FAILED",
        )

    def test_saved_itinerary_is_private_immutable_and_omits_party_details(self):
        start = self.spot("저장 출발")
        end = self.spot("저장 종료")
        candidate = self.spot("저장 후보")
        self.condition(candidate)
        self.route_matrix(start=start, end=end, candidate=candidate)
        owner = User.objects.create_user(
            username="itinerary-owner",
            password="Very-Long!Itinerary-Passphrase-2026",
        )

        anonymous = self.client.post(
            "/api/v1/trips/itineraries/plan/",
            self.itinerary_payload(
                start=start,
                end=end,
                candidate=candidate,
                save=True,
            ),
            format="json",
        )
        self.assertEqual(anonymous.status_code, 401)

        self.client.force_authenticate(owner)
        saved_response = self.client.post(
            "/api/v1/trips/itineraries/plan/",
            self.itinerary_payload(
                start=start,
                end=end,
                candidate=candidate,
                save=True,
            ),
            format="json",
        )
        self.assertEqual(saved_response.status_code, 200)
        saved = Itinerary.objects.get(pk=saved_response.json()["saved_itinerary_id"])
        self.assertEqual(saved.party_size, 1)
        self.assertEqual(saved.participant_profile, "general")
        self.assertEqual(saved.participant_skill_level, "unspecified")
        self.assertNotIn("party", saved.request_snapshot)
        self.assertNotIn("ages", str(saved.request_snapshot))
        self.assertEqual(
            saved.request_snapshot["participant_profile"],
            "general",
        )
        self.assertEqual(
            saved.request_snapshot["participant_skill_level"],
            "unspecified",
        )
        self.assertEqual(saved.route_evidence["data_state"], "live")
        self.assertEqual(saved.water_evidence[0]["spot_id"], candidate.pk)
        self.assertEqual(
            saved.water_evidence[0]["participant_skill_level"],
            "unspecified",
        )
        self.assertIsNotNone(saved.route_revalidation_required_at)
        self.assertIsNotNone(saved.safety_revalidation_required_at)
        original_schedule = saved.schedule

        detail = self.client.get(f"/api/v1/trips/itineraries/{saved.pk}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["evidence_status"]["state"], "current")
        self.assertEqual(detail.json()["participant_profile"], "general")
        self.assertEqual(detail.json()["participant_skill_level"], "unspecified")
        self.assertEqual(detail.json()["route_evidence"]["data_state"], "live")
        self.assertEqual(detail.json()["water_evidence"][0]["spot_id"], candidate.pk)

        patched = self.client.patch(
            f"/api/v1/trips/itineraries/{saved.pk}/",
            {
                "title": "수정한 제목",
                "status": "accepted",
                "schedule": {"visits": ["tampered"]},
            },
            format="json",
        )
        self.assertEqual(patched.status_code, 200)
        saved.refresh_from_db()
        self.assertEqual(saved.title, "수정한 제목")
        self.assertEqual(saved.schedule, original_schedule)

        invalid_transition = self.client.patch(
            f"/api/v1/trips/itineraries/{saved.pk}/",
            {"status": "completed"},
            format="json",
        )
        self.assertEqual(invalid_transition.status_code, 400)

        other = User.objects.create_user(
            username="itinerary-other",
            password="Very-Long!Itinerary-Passphrase-2026",
        )
        self.client.force_authenticate(other)
        self.assertEqual(
            self.client.get(f"/api/v1/trips/itineraries/{saved.pk}/").status_code,
            404,
        )
        self.assertEqual(
            self.client.get("/api/v1/trips/itineraries/").json()["results"],
            [],
        )
        self.assertEqual(RouteMatrixSnapshot.objects.count(), 1)

    def test_saved_surf_itinerary_preserves_skill_evaluation_identity(self):
        start = self.spot("서핑 일정 출발")
        end = self.spot("서핑 일정 종료")
        candidate = self.spot("서핑 일정 후보")
        condition = self.condition(
            candidate,
            activity="surf",
            official_grade_detail="초중급자에게 적합",
            participant_skill_level="beginner",
        )
        self.route_matrix(start=start, end=end, candidate=candidate)
        owner = User.objects.create_user(
            username="surf-itinerary-owner",
            password="Very-Long!Surf-Itinerary-Passphrase-2026",
        )
        self.client.force_authenticate(owner)
        payload = self.itinerary_payload(
            start=start,
            end=end,
            candidate=candidate,
            save=True,
        )
        payload["recommendation"]["activity"] = "surf"
        payload["recommendation"]["party"].update(
            {
                "ages": [12, 38],
                "participant_skill_level": "beginner",
            }
        )

        response = self.client.post(
            "/api/v1/trips/itineraries/plan/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["participant_skill_level"], "beginner")
        saved = Itinerary.objects.get(pk=response.json()["saved_itinerary_id"])
        self.assertEqual(saved.participant_profile, "general")
        self.assertEqual(saved.participant_skill_level, "beginner")
        self.assertEqual(
            saved.request_snapshot["participant_skill_level"],
            "beginner",
        )
        self.assertEqual(len(saved.water_evidence), 1)
        row = saved.water_evidence[0]
        self.assertEqual(row["participant_skill_level"], "beginner")
        self.assertEqual(
            row["condition_score_participant_skill_level"],
            "beginner",
        )
        self.assertEqual(row["condition_score_id"], condition.pk)
        self.assertEqual(
            saved.evidence_revalidation_reasons(at=timezone.now()),
            (),
        )

    def test_saved_itinerary_rejects_deleted_or_mismatched_evidence_references(self):
        start = self.spot("근거 무결성 출발")
        end = self.spot("근거 무결성 종료")
        candidate = self.spot("근거 무결성 후보")
        self.condition(candidate)
        self.route_matrix(start=start, end=end, candidate=candidate)
        owner = User.objects.create_user(
            username="evidence-integrity-owner",
            password="Very-Long!Evidence-Integrity-Passphrase-2026",
        )
        self.client.force_authenticate(owner)
        created = self.client.post(
            "/api/v1/trips/itineraries/plan/",
            self.itinerary_payload(
                start=start,
                end=end,
                candidate=candidate,
                save=True,
            ),
            format="json",
        )
        self.assertEqual(created.status_code, 200)
        saved = Itinerary.objects.get(pk=created.json()["saved_itinerary_id"])
        score_id = saved.water_evidence[0]["condition_score_id"]
        ConditionScore.objects.filter(pk=score_id).delete()

        detail = self.client.get(f"/api/v1/trips/itineraries/{saved.pk}/")
        transition = self.client.patch(
            f"/api/v1/trips/itineraries/{saved.pk}/",
            {"status": "accepted"},
            format="json",
        )

        self.assertEqual(detail.status_code, 200)
        self.assertIn(
            "WATER_EVIDENCE_REFERENCE_INVALID",
            detail.json()["evidence_status"]["reason_codes"],
        )
        self.assertEqual(transition.status_code, 400)

        # A syntactically valid but missing route ID is equally non-executable.
        saved.water_evidence = []
        saved.schedule = {"visits": []}
        saved.route_evidence["snapshot_ids"] = [999_999]
        saved.route_snapshot_ids = [999_999]
        saved.save(
            update_fields=(
                "water_evidence",
                "schedule",
                "route_evidence",
                "route_snapshot_ids",
            )
        )
        reasons = saved.evidence_revalidation_reasons(at=timezone.now())
        self.assertIn("ROUTE_EVIDENCE_REFERENCE_INVALID", reasons)

    def test_family_swim_transition_uses_non_persisted_supervision_reconfirmation(self):
        start = self.spot("가족 수영 출발")
        end = self.spot("가족 수영 종료")
        candidate = self.spot("가족 수영 후보")
        self.condition(
            candidate,
            participant_profile="family",
            safety="unknown",
            decision="unknown",
            score=None,
            include_family_gates=True,
        )
        self.route_matrix(start=start, end=end, candidate=candidate)
        owner = User.objects.create_user(
            username="family-itinerary-owner",
            password="Very-Long!Family-Itinerary-Passphrase-2026",
        )
        self.client.force_authenticate(owner)
        payload = self.itinerary_payload(
            start=start,
            end=end,
            candidate=candidate,
            save=True,
        )
        payload["recommendation"]["party"].update(
            {
                "ages": [8, 38],
                "adult_supervision_confirmed": True,
            }
        )
        created = self.client.post(
            "/api/v1/trips/itineraries/plan/",
            payload,
            format="json",
        )

        self.assertEqual(created.status_code, 200)
        saved = Itinerary.objects.get(pk=created.json()["saved_itinerary_id"])
        self.assertEqual(saved.participant_profile, "family")
        self.assertNotIn("adult_supervision_confirmed", saved.request_snapshot)
        self.assertTrue(
            saved.water_evidence[0][
                "session_context_reconfirmation_required"
            ]
        )

        detail = self.client.get(f"/api/v1/trips/itineraries/{saved.pk}/")
        self.assertIn(
            "ADULT_SUPERVISION_RECONFIRMATION_REQUIRED",
            detail.json()["evidence_status"]["reason_codes"],
        )
        without_confirmation = self.client.patch(
            f"/api/v1/trips/itineraries/{saved.pk}/",
            {"status": "accepted"},
            format="json",
        )
        self.assertEqual(without_confirmation.status_code, 400)

        accepted = self.client.patch(
            f"/api/v1/trips/itineraries/{saved.pk}/",
            {
                "status": "accepted",
                "adult_supervision_confirmed": True,
            },
            format="json",
        )
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()["status"], "accepted")
        self.assertNotIn("adult_supervision_confirmed", accepted.json())
        self.assertIn(
            "ADULT_SUPERVISION_RECONFIRMATION_REQUIRED",
            accepted.json()["evidence_status"]["reason_codes"],
        )

        started = self.client.patch(
            f"/api/v1/trips/itineraries/{saved.pk}/",
            {
                "status": "started",
                "adult_supervision_confirmed": True,
            },
            format="json",
        )
        self.assertEqual(started.status_code, 200)
        self.assertEqual(started.json()["status"], "started")

    def test_saved_itinerary_cannot_advance_after_evidence_expiry(self):
        start = self.spot("만료 출발")
        end = self.spot("만료 종료")
        candidate = self.spot("만료 후보")
        self.condition(candidate)
        self.route_matrix(start=start, end=end, candidate=candidate)
        owner = User.objects.create_user(
            username="expired-itinerary-owner",
            password="Very-Long!Itinerary-Passphrase-2026",
        )
        self.client.force_authenticate(owner)
        created = self.client.post(
            "/api/v1/trips/itineraries/plan/",
            self.itinerary_payload(
                start=start,
                end=end,
                candidate=candidate,
                save=True,
            ),
            format="json",
        )
        self.assertEqual(created.status_code, 200)
        saved = Itinerary.objects.get(pk=created.json()["saved_itinerary_id"])
        Itinerary.objects.filter(pk=saved.pk).update(
            safety_revalidation_required_at=timezone.now() - timedelta(seconds=1),
            route_revalidation_required_at=timezone.now() - timedelta(seconds=1),
        )

        detail = self.client.get(f"/api/v1/trips/itineraries/{saved.pk}/")
        transition = self.client.patch(
            f"/api/v1/trips/itineraries/{saved.pk}/",
            {"status": "accepted"},
            format="json",
        )

        self.assertEqual(detail.status_code, 200)
        self.assertEqual(
            detail.json()["evidence_status"]["state"],
            "revalidation_required",
        )
        self.assertIn(
            "SAFETY_EVIDENCE_REVALIDATION_REQUIRED",
            detail.json()["evidence_status"]["reason_codes"],
        )
        self.assertEqual(transition.status_code, 400)
        self.assertIn("ITINERARY_REVALIDATION_REQUIRED", str(transition.json()))
