from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient

from apps.conditions.models import ConditionScore, ObservationMetric, ObservationSnapshot
from apps.forecasts.models import DailyForecast
from apps.forecasts.serializers import daily_forecast_payload
from apps.spots.models import WaterSpot
from services.daily_forecasts import (
    ACTIVITY_NOT_SUPPORTED_FOR_SPOT,
    DAILY_FORECAST_METHODOLOGY_VERSION,
    FORECAST_EVIDENCE_UNRESOLVED,
    KhoaForecastEvidenceIngestionService,
    PROVIDER_HORIZON_UNAVAILABLE,
    REQUIRED_SAFETY_EVIDENCE_MISSING,
    evaluate_daily_forecasts,
)
from services.ingestion.fusion import fuse_spot_observations
from services.providers.base import ProviderResult, ProviderTransportError
from services.providers.khoa import BeachForecast, KhoaClient
from services.water_index import (
    Activity,
    SURF_GRADE_DETAIL_UNSUPPORTED,
    SURF_GRADE_SKILL_MISMATCH,
    SURF_SKILL_LEVEL_REQUIRED,
)


KST = ZoneInfo("Asia/Seoul")
NOW = datetime(2026, 8, 18, 9, 0, tzinfo=KST)
TARGET_DATE = date(2026, 8, 19)
TARGET = datetime(2026, 8, 19, 12, 0, tzinfo=KST)


class DailyForecastServiceTests(TestCase):
    def setUp(self) -> None:
        self.spot = WaterSpot.objects.create(
            type="beach",
            name="경포해수욕장",
            lat=37.8055,
            lng=128.9070,
            region="강원",
            address="강원특별자치도 강릉시",
        )

    def add_forecast_metric(
        self,
        *,
        provider: str,
        provider_record_id: str,
        source: str,
        name: str,
        value,
        valid_from: datetime = TARGET,
        valid_until: datetime = TARGET + timedelta(hours=1),
        observed_at: datetime = NOW - timedelta(hours=1),
        fetched_at: datetime = NOW,
    ) -> ObservationMetric:
        snapshot = ObservationSnapshot.objects.create(
            spot=self.spot,
            provider=provider,
            provider_record_id=provider_record_id,
            state="live",
            observed_at=observed_at,
            fetched_at=fetched_at,
            valid_from=valid_from,
            valid_until=valid_until,
            spatial_scope="test:forecast-point",
            source_url="https://example.go.kr/forecast",
            ingestion_version="test-forecast-v1",
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
            mode="forecast",
            state="valid",
            confidence=1.0,
            source=source,
            source_url="https://example.go.kr/forecast",
            spatial_scope="test:forecast-point",
            observed_at=observed_at,
            fetched_at=fetched_at,
            valid_from=valid_from,
            valid_until=valid_until,
        )

    def test_partial_weather_evidence_never_becomes_a_safe_score(self) -> None:
        metric = self.add_forecast_metric(
            provider="KMA",
            provider_record_id="kma-short-issue-1",
            source="KMA",
            name="air_temperature_c",
            value=27.0,
        )

        report = evaluate_daily_forecasts(
            spots=(self.spot,),
            activities=(Activity.RELAX,),
            start_date=TARGET_DATE,
            days=1,
            profiles=("general",),
            clock=lambda: NOW,
        )

        self.assertEqual(report.created_projections, 1)
        forecast = DailyForecast.objects.get()
        self.assertEqual(forecast.safety_status, "unknown")
        self.assertIsNone(forecast.score)
        self.assertEqual(forecast.availability, "partial")
        self.assertEqual(
            forecast.unavailable_reason,
            REQUIRED_SAFETY_EVIDENCE_MISSING,
        )
        self.assertEqual(forecast.evidence[0]["metric_id"], metric.pk)
        self.assertEqual(forecast.evidence[0]["mode"], "forecast")
        self.assertEqual(forecast.evidence[0]["provider"], "KMA")

    def test_available_safety_with_low_suitability_coverage_has_no_range(self) -> None:
        for provider, source, record_id, name, value in (
            (
                "LOCAL_AUTHORITY",
                "LOCAL_AUTHORITY",
                "access:open",
                "official_entry_status",
                "open",
            ),
            (
                "KMA_WARNING",
                "KMA_WARNING",
                "weather:none",
                "weather_alert_level",
                "none",
            ),
            (
                "KMA_LIGHTNING",
                "KMA_LIGHTNING",
                "lightning:clear",
                "lightning_clearance_minutes",
                30,
            ),
            (
                "KMA_WARNING",
                "KMA_WARNING",
                "marine:clear",
                "marine_hazard_status",
                "clear",
            ),
        ):
            self.add_forecast_metric(
                provider=provider,
                provider_record_id=record_id,
                source=source,
                name=name,
                value=value,
            )

        evaluate_daily_forecasts(
            spots=(self.spot,),
            activities=(Activity.RELAX,),
            start_date=TARGET_DATE,
            days=1,
            profiles=("general",),
            clock=lambda: NOW,
        )

        forecast = DailyForecast.objects.get()
        self.assertEqual(forecast.availability, "available")
        self.assertEqual(forecast.safety_status, "clear")
        self.assertEqual(forecast.decision, "unknown")
        self.assertIsNone(forecast.score)
        self.assertEqual(forecast.score_range, [])
        self.assertEqual(forecast.contributions, [])

    def test_khoa_activity_score_is_not_republished_as_a_pongdang_safe_score(
        self,
    ) -> None:
        self.add_forecast_metric(
            provider="KHOA",
            provider_record_id="beach:provider-score",
            source="KHOA",
            name="official_activity_score",
            value=99,
        )
        self.add_forecast_metric(
            provider="KHOA",
            provider_record_id="beach:provider-grade",
            source="KHOA",
            name="official_activity_grade",
            value="매우좋음",
        )

        evaluate_daily_forecasts(
            spots=(self.spot,),
            activities=(Activity.SWIM,),
            start_date=TARGET_DATE,
            days=1,
            clock=lambda: NOW,
        )

        forecast = DailyForecast.objects.get()
        self.assertEqual(forecast.safety_status, "unknown")
        self.assertIsNone(forecast.score)
        self.assertIn(
            "official_entry_status|access_status",
            forecast.missing_metrics,
        )

    def test_repeated_identical_evidence_updates_instead_of_duplicating(self) -> None:
        self.add_forecast_metric(
            provider="KMA",
            provider_record_id="kma-short-stable",
            source="KMA",
            name="air_temperature_c",
            value=26.0,
        )
        first = evaluate_daily_forecasts(
            spots=(self.spot,),
            activities=(Activity.RELAX,),
            start_date=TARGET_DATE,
            days=1,
            clock=lambda: NOW,
        )
        second_at = NOW + timedelta(minutes=5)
        second = evaluate_daily_forecasts(
            spots=(self.spot,),
            activities=(Activity.RELAX,),
            start_date=TARGET_DATE,
            days=1,
            clock=lambda: second_at,
        )

        self.assertEqual(first.created_projections, 1)
        self.assertEqual(second.created_projections, 0)
        self.assertEqual(second.updated_projections, 1)
        self.assertEqual(DailyForecast.objects.count(), 1)
        self.assertEqual(DailyForecast.objects.get().evaluated_at, second_at)

    def test_provider_horizon_is_not_interpolated_into_the_next_day(self) -> None:
        self.add_forecast_metric(
            provider="KMA",
            provider_record_id="kma-only-first-day",
            source="KMA",
            name="air_temperature_c",
            value=25.0,
        )

        evaluate_daily_forecasts(
            spots=(self.spot,),
            activities=(Activity.RELAX,),
            start_date=TARGET_DATE,
            days=2,
            clock=lambda: NOW,
        )

        first, second = DailyForecast.objects.order_by("forecast_date")
        self.assertEqual(first.availability, "partial")
        self.assertEqual(second.safety_status, "unknown")
        self.assertIsNone(second.score)
        self.assertEqual(second.availability, "unavailable")
        self.assertEqual(second.unavailable_reason, PROVIDER_HORIZON_UNAVAILABLE)
        self.assertEqual(second.evidence, [])

    def test_future_forecast_stop_dominates_missing_inputs_until_provider_expiry(self) -> None:
        self.add_forecast_metric(
            provider="KHOA",
            provider_record_id="official-future-stop",
            source="KHOA",
            name="official_stop_signal",
            value=True,
            valid_from=TARGET - timedelta(hours=1),
            valid_until=TARGET + timedelta(hours=1),
            # Much older than the observed-signal max age. A typed forecast is
            # governed by its explicit future validity window instead.
            observed_at=NOW - timedelta(hours=2),
        )

        evaluate_daily_forecasts(
            spots=(self.spot,),
            activities=(Activity.RELAX,),
            start_date=TARGET_DATE,
            days=1,
            clock=lambda: NOW,
        )

        forecast = DailyForecast.objects.get()
        self.assertEqual(forecast.safety_status, "stop")
        self.assertEqual(forecast.decision, "blocked")
        self.assertIsNone(forecast.score)
        self.assertEqual(forecast.availability, "available")

    def test_conflicting_forecast_evidence_remains_unknown(self) -> None:
        for index, (provider, value) in enumerate(
            (("LOCAL_AUTHORITY", "open"), ("OFFICIAL_LOCAL", "closed"))
        ):
            self.add_forecast_metric(
                provider=provider,
                provider_record_id=f"local-access-{index}",
                source=provider,
                name="official_entry_status",
                value=value,
            )
        self.add_forecast_metric(
            provider="KMA",
            provider_record_id="weather-context",
            source="KMA",
            name="air_temperature_c",
            value=24,
        )

        evaluate_daily_forecasts(
            spots=(self.spot,),
            activities=(Activity.RELAX,),
            start_date=TARGET_DATE,
            days=1,
            clock=lambda: NOW,
        )

        forecast = DailyForecast.objects.get()
        self.assertEqual(forecast.safety_status, "unknown")
        self.assertIsNone(forecast.score)
        self.assertEqual(forecast.availability, "partial")
        self.assertEqual(forecast.unavailable_reason, FORECAST_EVIDENCE_UNRESOLVED)
        self.assertIn(
            "official_entry_status|access_status",
            forecast.stale_or_conflicting_metrics,
        )

    def test_khoa_activity_products_do_not_cross_activity_boundaries(self) -> None:
        self.add_forecast_metric(
            provider="KHOA",
            provider_record_id="beach:one",
            source="KHOA",
            name="official_activity_grade",
            value="beach-grade",
        )
        self.add_forecast_metric(
            provider="KHOA",
            provider_record_id="surf:one",
            source="KHOA",
            name="official_activity_grade",
            value="surf-grade",
        )

        swim = fuse_spot_observations(
            spot=self.spot,
            at=TARGET,
            fetched_at=NOW,
            activity=Activity.SWIM,
        )
        surf = fuse_spot_observations(
            spot=self.spot,
            at=TARGET,
            fetched_at=NOW,
            activity=Activity.SURF,
        )

        self.assertEqual(
            swim.observations.get("official_activity_grade").value,
            "beach-grade",
        )
        self.assertEqual(
            surf.observations.get("official_activity_grade").value,
            "surf-grade",
        )

    def test_surf_daily_identity_requires_exact_authoritative_grade_detail(
        self,
    ) -> None:
        for provider, source, record_id, name, value in (
            (
                "LOCAL_AUTHORITY",
                "LOCAL_AUTHORITY",
                "access:open",
                "official_entry_status",
                "open",
            ),
            (
                "KMA_WARNING",
                "KMA_WARNING",
                "weather:none",
                "weather_alert_level",
                "none",
            ),
            (
                "KMA_LIGHTNING",
                "KMA_LIGHTNING",
                "lightning:clear",
                "lightning_clearance_minutes",
                30,
            ),
            (
                "KHOA",
                "KHOA",
                "rip-current:clear",
                "rip_current_risk",
                "attention",
            ),
            (
                "KMA_WARNING",
                "KMA_WARNING",
                "marine:clear",
                "marine_hazard_status",
                "clear",
            ),
            (
                "KHOA",
                "KHOA",
                "surf:grade",
                "official_activity_grade",
                "매우좋음",
            ),
            (
                "KHOA",
                "KHOA",
                "surf:detail",
                "official_grade_detail",
                "초중급자에게 적합",
            ),
        ):
            self.add_forecast_metric(
                provider=provider,
                provider_record_id=record_id,
                source=source,
                name=name,
                value=value,
            )

        report = evaluate_daily_forecasts(
            spots=(self.spot,),
            activities=(Activity.SURF,),
            start_date=TARGET_DATE,
            days=1,
            profiles=("general",),
            clock=lambda: NOW,
        )

        self.assertEqual(report.evaluated_projections, 4)
        rows = {
            row.participant_skill_level: row
            for row in DailyForecast.objects.all()
        }
        self.assertEqual(
            set(rows),
            {"unspecified", "beginner", "intermediate", "advanced"},
        )
        self.assertEqual(rows["unspecified"].safety_status, "unknown")
        self.assertEqual(rows["unspecified"].decision, "unknown")
        self.assertIsNone(rows["unspecified"].score)
        self.assertEqual(rows["unspecified"].score_range, [])
        self.assertEqual(
            rows["unspecified"].unavailable_reason,
            SURF_SKILL_LEVEL_REQUIRED,
        )
        for skill in ("beginner", "intermediate"):
            self.assertEqual(rows[skill].availability, "available")
            self.assertEqual(rows[skill].safety_status, "clear")
            self.assertIsNotNone(rows[skill].score)
        self.assertEqual(rows["advanced"].safety_status, "unknown")
        self.assertIsNone(rows["advanced"].score)
        self.assertEqual(rows["advanced"].score_range, [])
        self.assertEqual(
            rows["advanced"].unavailable_reason,
            SURF_GRADE_SKILL_MISMATCH,
        )

    def test_similar_but_unsupported_surf_grade_detail_stays_unknown(self) -> None:
        self.add_forecast_metric(
            provider="KHOA",
            provider_record_id="surf:grade",
            source="KHOA",
            name="official_activity_grade",
            value="매우좋음",
        )
        self.add_forecast_metric(
            provider="KHOA",
            provider_record_id="surf:detail",
            source="KHOA",
            name="official_grade_detail",
            value="초급~중급",
        )

        evaluate_daily_forecasts(
            spots=(self.spot,),
            activities=(Activity.SURF,),
            start_date=TARGET_DATE,
            days=1,
            profiles=("general",),
            skill_levels=("beginner",),
            clock=lambda: NOW,
        )

        row = DailyForecast.objects.get()
        self.assertEqual(row.safety_status, "unknown")
        self.assertIsNone(row.score)
        self.assertEqual(row.score_range, [])
        self.assertEqual(
            row.unavailable_reason,
            SURF_GRADE_DETAIL_UNSUPPORTED,
        )


class KhoaForecastEvidenceIngestionTests(TestCase):
    def setUp(self) -> None:
        self.spot = WaterSpot.objects.create(
            type="beach",
            name="경포해수욕장",
            lat=37.8055,
            lng=128.9070,
            region="강원",
            address="강원특별자치도 강릉시",
        )

    def test_partial_product_failure_preserves_successful_raw_evidence_only(self) -> None:
        beach = BeachForecast(
            place_name="경포해수욕장",
            latitude=Decimal("37.8055"),
            longitude=Decimal("128.9070"),
            forecast_date=TARGET_DATE,
            forecast_time_code="PM",
            score=Decimal("82"),
            official_grade="좋음",
            maximum_wave_height=Decimal("0.5"),
            average_water_temperature=Decimal("23"),
            average_air_temperature=Decimal("27"),
            maximum_wind_speed=Decimal("4"),
        )

        class PartialClient:
            def fetch_beach_forecasts(self):
                return ProviderResult(
                    provider="KHOA",
                    endpoint=KhoaClient.BEACH_ENDPOINT,
                    records=(beach,),
                    reported_total_count=1,
                )

            def fetch_surf_forecasts(self):
                raise ProviderTransportError("KHOA", status_code=503)

        report = KhoaForecastEvidenceIngestionService(
            PartialClient(),  # type: ignore[arg-type]
            clock=lambda: NOW,
        ).sync(
            activities=(Activity.SWIM, Activity.SURF),
            spots=(self.spot,),
        )

        self.assertEqual(report.failed_activities, (Activity.SURF,))
        self.assertEqual(report.persisted_records, 1)
        snapshot = ObservationSnapshot.objects.get()
        self.assertEqual(snapshot.provider, "KHOA")
        self.assertTrue(snapshot.provider_record_id.startswith("beach:"))
        self.assertIsNone(snapshot.observed_at)
        self.assertTrue(
            all(metric.mode == "forecast" for metric in snapshot.metrics.all())
        )
        self.assertEqual(ConditionScore.objects.count(), 0)


class DailyForecastApiTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.spot = WaterSpot.objects.create(
            type="beach",
            name="API 해변",
            lat=37.8,
            lng=128.9,
            region="강원",
            address="강릉시",
        )

    def surf_grade_evidence(self, detail: str = "초중급자에게 적합") -> list[dict]:
        common = {
            "unit": "text",
            "mode": "forecast",
            "state": "valid",
            "confidence": 1.0,
            "provider": "KHOA",
            "source": "KHOA",
            "ingestion_version": "khoa-surf-v1",
            "station_id": "surf-point-1",
            "spatial_scope": "khoa-surf:37.8,128.9",
            "source_url": "https://www.khoa.go.kr/surf",
            "issued_at": (NOW - timedelta(hours=1)).isoformat(),
            "observed_at": (NOW - timedelta(hours=1)).isoformat(),
            "fetched_at": NOW.isoformat(),
            "valid_from": TARGET.isoformat(),
            "valid_until": (TARGET + timedelta(hours=1)).isoformat(),
        }
        return [
            {
                **common,
                "metric_id": 20,
                "provider_record_id": "surf:grade",
                "name": "official_activity_grade",
                "value": "매우좋음",
            },
            {
                **common,
                "metric_id": 21,
                "provider_record_id": "surf:detail",
                "name": "official_grade_detail",
                "value": detail,
            },
        ]

    def create_projection(
        self,
        *,
        forecast_date: date = TARGET_DATE,
        activity: str = "relax",
        participant_profile: str = "general",
        participant_skill_level: str = "unspecified",
        fingerprint: str,
        evaluated_at: datetime,
        safety_status: str = "clear",
        decision: str = "recommended",
        score: float | None = 88,
        availability: str = "available",
        reason: str = "",
        valid_until: datetime = TARGET + timedelta(hours=1),
        evidence: list[dict] | None = None,
    ) -> DailyForecast:
        evidence = evidence or [
            {
                "metric_id": 10,
                "name": "air_temperature_c",
                "value": 27,
                "unit": "celsius",
                "mode": "forecast",
                "state": "valid",
                "confidence": 1.0,
                "provider": "KMA",
                "source": "KMA",
                "provider_record_id": "kma-grid-record",
                "ingestion_version": "kma-adapter-v1",
                "station_id": "",
                "spatial_scope": "kma-grid:92,132",
                "source_url": (
                    "https://apis.data.go.kr/weather?serviceKey=secret"
                ),
                "service_key": "must-not-leak",
                "issued_at": (NOW - timedelta(hours=1)).isoformat(),
                "observed_at": (NOW - timedelta(hours=1)).isoformat(),
                "fetched_at": NOW.isoformat(),
                "valid_from": TARGET.isoformat(),
                "valid_until": valid_until.isoformat(),
            }
        ]
        return DailyForecast.objects.create(
            spot=self.spot,
            forecast_date=forecast_date,
            activity=activity,
            participant_profile=participant_profile,
            participant_skill_level=participant_skill_level,
            target_at=datetime.combine(forecast_date, datetime.min.time(), tzinfo=KST)
            + timedelta(hours=12),
            score=score,
            safety_status=safety_status,
            decision=decision,
            confidence=0.9,
            coverage=0.8,
            score_range=[80, 92] if score is not None else [],
            gates=[],
            contributions=(
                [{"metric_name": "air_temperature_c"}]
                if availability == "available" and score is not None
                else []
            ),
            missing_metrics=[],
            stale_or_conflicting_metrics=[],
            limitations=[],
            availability=availability,
            unavailable_reason=reason,
            evidence=evidence,
            evidence_fingerprint=fingerprint.ljust(64, "0")[:64],
            evidence_issued_at=NOW - timedelta(hours=1),
            evidence_fetched_at=NOW,
            valid_from=TARGET,
            valid_until=valid_until,
            methodology_version="water-index-v1.0.0",
            projection_methodology_version=DAILY_FORECAST_METHODOLOGY_VERSION,
            evaluated_at=evaluated_at,
        )

    def get_daily(
        self,
        *,
        activity: str = "relax",
        participant_profile: str = "general",
        participant_skill_level: str = "unspecified",
        start_date=TARGET_DATE,
        days=1,
    ):
        return self.client.get(
            "/api/v1/forecasts/daily/",
            {
                "spot": self.spot.pk,
                "activity": activity,
                "participant_profile": participant_profile,
                "participant_skill_level": participant_skill_level,
                "start_date": start_date.isoformat(),
                "days": days,
            },
        )

    @patch("apps.forecasts.views.timezone.now", return_value=NOW)
    def test_missing_provider_days_return_exact_unknown_rows(self, _now) -> None:
        response = self.get_daily(days=7)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 7)
        self.assertEqual(body["reference_time"], "12:00:00")
        self.assertEqual(
            [item["forecast_date"] for item in body["results"]],
            [
                (TARGET_DATE + timedelta(days=offset)).isoformat()
                for offset in range(7)
            ],
        )
        for item in body["results"]:
            self.assertEqual(item["safety_status"], "unknown")
            self.assertIsNone(item["score"])
            self.assertIsNone(item["suitability_score"])
            self.assertEqual(item["unavailable_reason"], PROVIDER_HORIZON_UNAVAILABLE)

    @patch("apps.forecasts.views.timezone.now", return_value=NOW)
    def test_unscoped_surf_query_is_explicitly_unknown(self, _now) -> None:
        response = self.get_daily(activity="surf")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["participant_skill_level"], "unspecified")
        item = body["results"][0]
        self.assertEqual(item["participant_skill_level"], "unspecified")
        self.assertEqual(item["safety_status"], "unknown")
        self.assertEqual(item["decision"], "unknown")
        self.assertIsNone(item["score"])
        self.assertEqual(item["score_range"], [])
        self.assertEqual(item["unavailable_reason"], SURF_SKILL_LEVEL_REQUIRED)

    @patch("apps.forecasts.views.timezone.now", return_value=NOW)
    def test_surf_api_selects_exact_skill_and_revalidates_grade_scope(
        self,
        _now,
    ) -> None:
        evidence = self.surf_grade_evidence()
        self.create_projection(
            activity="surf",
            participant_skill_level="beginner",
            fingerprint="surf-beginner",
            evaluated_at=NOW,
            evidence=evidence,
        )
        # A direct writer can satisfy scalar DB checks while attaching a grade
        # that is not scoped to advanced participants. The API must still
        # revalidate the evidence and fail closed at read time.
        self.create_projection(
            activity="surf",
            participant_skill_level="advanced",
            fingerprint="surf-advanced",
            evaluated_at=NOW,
            evidence=evidence,
        )

        beginner = self.get_daily(
            activity="surf",
            participant_skill_level="beginner",
        ).json()["results"][0]
        advanced = self.get_daily(
            activity="surf",
            participant_skill_level="advanced",
        ).json()["results"][0]

        self.assertEqual(beginner["participant_skill_level"], "beginner")
        self.assertEqual(beginner["safety_status"], "clear")
        self.assertEqual(beginner["score"], 88.0)
        self.assertEqual(advanced["participant_skill_level"], "advanced")
        self.assertEqual(advanced["safety_status"], "unknown")
        self.assertEqual(advanced["decision"], "unknown")
        self.assertIsNone(advanced["score"])
        self.assertEqual(advanced["score_range"], [])
        self.assertEqual(
            advanced["unavailable_reason"],
            SURF_GRADE_SKILL_MISMATCH,
        )

    @patch("apps.forecasts.views.timezone.now", return_value=NOW)
    def test_valid_but_unsupported_activity_is_unknown_not_a_fabricated_score(
        self, _now
    ) -> None:
        response = self.get_daily(activity="onsen")

        self.assertEqual(response.status_code, 200)
        item = response.json()["results"][0]
        self.assertEqual(item["safety_status"], "unknown")
        self.assertIsNone(item["score"])
        self.assertEqual(item["unavailable_reason"], ACTIVITY_NOT_SUPPORTED_FOR_SPOT)

    @patch("apps.forecasts.views.timezone.now", return_value=NOW)
    def test_latest_evaluation_wins_without_falling_back_to_older_clear(self, _now) -> None:
        self.create_projection(
            fingerprint="old",
            evaluated_at=NOW - timedelta(minutes=10),
            score=91,
        )
        self.create_projection(
            fingerprint="new",
            evaluated_at=NOW - timedelta(minutes=5),
            safety_status="unknown",
            decision="unknown",
            score=None,
            availability="partial",
            reason=REQUIRED_SAFETY_EVIDENCE_MISSING,
        )

        item = self.get_daily().json()["results"][0]

        self.assertEqual(item["safety_status"], "unknown")
        self.assertIsNone(item["score"])
        self.assertEqual(item["unavailable_reason"], REQUIRED_SAFETY_EVIDENCE_MISSING)

    def test_expiry_boundary_is_inclusive_then_fails_closed(self) -> None:
        boundary = TARGET
        self.create_projection(
            fingerprint="boundary",
            evaluated_at=NOW,
            valid_until=boundary,
        )
        with patch("apps.forecasts.views.timezone.now", return_value=boundary):
            current = self.get_daily().json()["results"][0]
        with patch(
            "apps.forecasts.views.timezone.now",
            return_value=boundary + timedelta(microseconds=1),
        ):
            expired = self.get_daily().json()["results"][0]

        self.assertEqual(current["safety_status"], "clear")
        self.assertEqual(current["score"], 88.0)
        self.assertEqual(expired["safety_status"], "unknown")
        self.assertIsNone(expired["score"])
        self.assertEqual(expired["unavailable_reason"], "FORECAST_EVIDENCE_EXPIRED")
        self.assertEqual(expired["confidence"], 0.0)
        self.assertEqual(expired["contributions"], [])

    def test_expired_stop_is_no_longer_published_as_a_current_stop(self) -> None:
        self.create_projection(
            fingerprint="stop",
            evaluated_at=NOW,
            safety_status="stop",
            decision="blocked",
            score=None,
            valid_until=TARGET,
        )
        with patch(
            "apps.forecasts.views.timezone.now",
            return_value=TARGET + timedelta(seconds=1),
        ):
            item = self.get_daily().json()["results"][0]

        self.assertEqual(item["safety_status"], "unknown")
        self.assertEqual(item["decision"], "unknown")
        self.assertIsNone(item["score"])

    @patch("apps.forecasts.views.timezone.now", return_value=NOW)
    def test_provenance_preserves_times_and_strips_credentials(self, _now) -> None:
        self.create_projection(fingerprint="provenance", evaluated_at=NOW)

        item = self.get_daily().json()["results"][0]

        evidence = item["evidence"][0]
        self.assertEqual(evidence["provider"], "KMA")
        self.assertEqual(evidence["mode"], "forecast")
        self.assertEqual(evidence["spatial_scope"], "kma-grid:92,132")
        self.assertEqual(evidence["issued_at"], (NOW - timedelta(hours=1)).isoformat())
        self.assertEqual(evidence["fetched_at"], NOW.isoformat())
        self.assertEqual(evidence["valid_from"], TARGET.isoformat())
        self.assertEqual(evidence["source_url"], "https://apis.data.go.kr/weather")
        self.assertEqual(item["methodology_version"], "water-index-v1.0.0")
        self.assertEqual(
            item["projection_methodology_version"],
            DAILY_FORECAST_METHODOLOGY_VERSION,
        )
        self.assertNotIn("service_key", evidence)
        self.assertNotIn("secret", str(item))

    @patch("apps.forecasts.views.timezone.now", return_value=NOW)
    def test_query_contract_requires_bounded_days_and_required_dimensions(self, _now) -> None:
        for days in (0, 8):
            with self.subTest(days=days):
                response = self.get_daily(days=days)
                self.assertEqual(response.status_code, 400)
        missing = self.client.get("/api/v1/forecasts/daily/")
        self.assertEqual(missing.status_code, 400)
        past = self.get_daily(start_date=NOW.date() - timedelta(days=1))
        self.assertEqual(past.status_code, 400)
        non_surf_skill = self.get_daily(
            activity="relax",
            participant_skill_level="beginner",
        )
        self.assertEqual(non_surf_skill.status_code, 400)
        non_swim_family = self.get_daily(
            activity="surf",
            participant_profile="family",
        )
        self.assertEqual(non_swim_family.status_code, 400)
        swim_family = self.get_daily(
            activity="swim",
            participant_profile="family",
        )
        self.assertEqual(swim_family.status_code, 200)

    def test_database_rejects_public_values_for_non_available_forecast(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_projection(
                fingerprint="unsafe-partial",
                evaluated_at=NOW,
                availability="partial",
                reason=REQUIRED_SAFETY_EVIDENCE_MISSING,
                safety_status="clear",
                decision="recommended",
                score=88,
            )

    def test_serializer_fails_closed_for_malformed_non_available_instance(self) -> None:
        row = self.create_projection(
            fingerprint="malformed-read",
            evaluated_at=NOW,
        )
        row.availability = "partial"
        row.unavailable_reason = REQUIRED_SAFETY_EVIDENCE_MISSING

        payload = daily_forecast_payload(row, as_of=NOW)

        self.assertEqual(payload["safety_status"], "unknown")
        self.assertEqual(payload["decision"], "unknown")
        self.assertIsNone(payload["score"])
        self.assertEqual(payload["score_range"], [])
        self.assertEqual(payload["contributions"], [])

    def test_model_validates_score_range_and_unscoped_surf_policy(self) -> None:
        row = self.create_projection(
            fingerprint="range-shape",
            evaluated_at=NOW,
        )
        row.score_range = [90, 80]
        with self.assertRaises(ValidationError):
            row.full_clean()

        row.activity = "surf"
        row.participant_skill_level = "unspecified"
        row.score_range = [80, 92]
        with self.assertRaises(ValidationError):
            row.full_clean()

        stored_stop = self.create_projection(
            fingerprint="stop-range-leak",
            evaluated_at=NOW,
            safety_status="stop",
            decision="blocked",
            score=None,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            DailyForecast.objects.filter(pk=stored_stop.pk).update(
                score_range=[80, 90]
            )
