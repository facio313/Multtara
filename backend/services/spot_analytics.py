"""Long-term water-life analytics from stored condition history (C5)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from django.db.models.functions import ExtractWeekDay
from django.utils import timezone

from apps.conditions.models import WaterCondition
from apps.content.models import SpotAnalytics
from apps.forecasts.models import WaterForecast
from apps.spots.models import WaterSpot
from apps.users.models import UserActivity

GRADE_RANK = {"1": 1, "좋음": 1, "2": 2, "보통": 2, "3": 3, "나쁨": 3, "4": 4}


def _latest_condition(spot: WaterSpot) -> WaterCondition | None:
    cache = getattr(spot, "_prefetched_objects_cache", None)
    if cache is not None and "conditions" in cache:
        return next(iter(spot.conditions.all()), None)
    return spot.conditions.order_by("-fetched_at").first()


def _grade_rank(value: Any) -> int | None:
    token = str(value or "").strip()
    if not token:
        return None
    if token in GRADE_RANK:
        return GRADE_RANK[token]
    if token[0] in GRADE_RANK:
        return GRADE_RANK[token[0]]
    return None


def analytics_payload(spot: WaterSpot) -> dict:
    history = list(
        WaterCondition.objects.filter(spot=spot).order_by("fetched_at")
    )
    temps = [row.water_temp for row in history if row.water_temp is not None]
    grades = [row.water_quality_grade for row in history if row.water_quality_grade]
    current = _latest_condition(spot)
    current_temp = getattr(current, "water_temp", None)
    avg = round(sum(temps) / len(temps), 1) if temps else None

    percentile = None
    headline = "기록이 아직 짧습니다."
    if current_temp is not None and len(temps) >= 3:
        warmer_or_equal = sum(1 for value in temps if value <= current_temp)
        percentile = round(100 * warmer_or_equal / len(temps))
        from_top = max(1, min(99, 100 - percentile))
        if percentile <= 20:
            headline = f"현재 수온은 기록 중 하위 {percentile}% 수준입니다."
        else:
            headline = f"현재 수온은 기록 중 상위 {from_top}% 수준입니다."

    trend = ""
    ranked = [_grade_rank(value) for value in grades]
    ranked = [value for value in ranked if value is not None]
    if len(ranked) >= 2:
        if ranked[-1] < ranked[0]:
            trend = "개선"
        elif ranked[-1] > ranked[0]:
            trend = "악화"
        else:
            trend = "유지"
    elif ranked:
        trend = "유지"

    forecasts = list(
        WaterForecast.objects.filter(spot=spot).order_by("forecast_date").values_list(
            "forecast_date", "predicted_index"
        )
    )
    best_season = "여름" if spot.type in {"sea", "waterpark", "pool"} else "가을"
    if forecasts:
        best = max(forecasts, key=lambda item: item[1] or 0)
        month = best[0].month
        best_season = {
            12: "겨울",
            1: "겨울",
            2: "겨울",
            3: "봄",
            4: "봄",
            5: "봄",
            6: "여름",
            7: "여름",
            8: "여름",
        }.get(month, "가을")

    visits = UserActivity.objects.filter(spot=spot, action="visited")
    weekend = visits.annotate(wd=ExtractWeekDay("created_at")).filter(wd__in=(1, 7)).count()
    weekday = visits.count() - weekend
    if visits.count() >= 3 and weekend > weekday:
        crowd_trend = "주말 혼잡"
    elif visits.count() >= 3:
        crowd_trend = "평일 분산"
    elif spot.type in {"sea", "waterpark"}:
        crowd_trend = "주말 혼잡 예상"
    else:
        crowd_trend = "보통"

    monthly: dict[str, list[float]] = defaultdict(list)
    for row in history:
        if row.water_temp is None:
            continue
        stamp = timezone.localtime(row.fetched_at).strftime("%Y-%m")
        monthly[stamp].append(row.water_temp)
    series = [
        {"month": key, "avg_water_temp": round(sum(values) / len(values), 1)}
        for key, values in sorted(monthly.items())
    ]

    sample_days = len({timezone.localtime(row.fetched_at).date() for row in history})
    return {
        "avg_water_temp": avg,
        "avg_water_temp_5y": avg,
        "quality_trend": trend,
        "crowd_trend": crowd_trend,
        "best_season": best_season,
        "sample_days": sample_days,
        "percentile": percentile,
        "headline": headline,
        "current_water_temp": current_temp,
        "series": series,
    }


def persist_analytics(spot: WaterSpot) -> SpotAnalytics:
    payload = analytics_payload(spot)
    row, _created = SpotAnalytics.objects.update_or_create(
        spot=spot,
        defaults={
            "avg_water_temp_5y": payload["avg_water_temp"],
            "quality_trend": payload["quality_trend"],
            "crowd_trend": payload["crowd_trend"],
            "best_season": payload["best_season"],
        },
    )
    return row
