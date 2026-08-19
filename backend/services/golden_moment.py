"""High-tide × sunset golden calendar from stored tides and solar geometry (C3)."""

from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from django.utils import timezone

from apps.forecasts.models import GoldenMoment
from apps.spots.models import WaterSpot
from services.tide_timer import parse_clock

KST = ZoneInfo("Asia/Seoul")
LUNAR_SHIFT_MIN = 50
OVERLAP_MINUTES = 30
HORIZON_DAYS = 30
SEA_TYPES = {"sea", "tidal_flat", "lake"}


def approximate_sunset(lat: float, lng: float, day: date) -> time:
    n = day.timetuple().tm_yday
    decl = math.radians(23.44 * math.sin(math.radians((360 / 365) * (n - 81))))
    lat_r = math.radians(lat)
    cos_ha = -math.tan(lat_r) * math.tan(decl)
    cos_ha = max(-1.0, min(1.0, cos_ha))
    ha = math.degrees(math.acos(cos_ha))
    solar = 12 + ha / 15 - (lng / 15)
    kst = (solar + 9) % 24
    hour = int(kst)
    minute = int((kst - hour) * 60)
    return time(hour, max(0, min(59, minute)))


def _minutes(clock: time) -> int:
    return clock.hour * 60 + clock.minute


def _shift_clock(clock: time, delta_min: int) -> time:
    total = (_minutes(clock) + delta_min) % (24 * 60)
    return time(total // 60, total % 60)


def _high_tides(condition: Any) -> list[time]:
    schedule = getattr(condition, "tide_schedule", None) or {}
    clocks = []
    for raw in schedule.get("high_tide") or []:
        clock = parse_clock(raw)
        if clock is not None:
            clocks.append(clock)
    return clocks


def find_golden_moments(
    spot: WaterSpot,
    *,
    condition: Any = None,
    start: date | None = None,
    days: int = HORIZON_DAYS,
) -> list[dict]:
    if condition is None:
        condition = spot.conditions.order_by("-fetched_at").first()
    today = start or timezone.localdate()
    highs = _high_tides(condition)
    rows: list[dict] = []
    for offset in range(days):
        day = today + timedelta(days=offset)
        sunset = approximate_sunset(spot.lat, spot.lng, day)
        sunset_min = _minutes(sunset)
        matched = False
        for base in highs:
            clock = _shift_clock(base, LUNAR_SHIFT_MIN * offset)
            if abs(_minutes(clock) - sunset_min) <= OVERLAP_MINUTES:
                rows.append(
                    {
                        "date": day.isoformat(),
                        "time": clock.strftime("%H:%M"),
                        "sunset": sunset.strftime("%H:%M"),
                        "type": "high_tide_sunset",
                        "label": "만조×일몰",
                    }
                )
                matched = True
                break
        if not matched and offset == 0 and spot.type in SEA_TYPES:
            rows.append(
                {
                    "date": day.isoformat(),
                    "time": sunset.strftime("%H:%M"),
                    "sunset": sunset.strftime("%H:%M"),
                    "type": "sunset",
                    "label": "일몰",
                }
            )
    return rows


def golden_moments(spot: WaterSpot, condition: Any = None) -> list[dict]:
    stored = list(
        GoldenMoment.objects.filter(spot=spot, date__gte=timezone.localdate()).order_by("date", "time")[:12]
    )
    if stored:
        return [moment_payload(row, spot) for row in stored]
    return find_golden_moments(spot, condition=condition)


def moment_payload(row: GoldenMoment, spot: WaterSpot | None = None) -> dict:
    spot = spot or row.spot
    sunset = approximate_sunset(spot.lat, spot.lng, row.date)
    kind = row.type or "sunset"
    return {
        "date": row.date.isoformat(),
        "time": row.time.strftime("%H:%M"),
        "sunset": sunset.strftime("%H:%M"),
        "type": kind,
        "label": "만조×일몰" if kind == "high_tide_sunset" else "일몰",
    }


def persist_golden_moments(spot: WaterSpot, condition: Any = None) -> list[GoldenMoment]:
    today = timezone.localdate()
    computed = find_golden_moments(spot, condition=condition, start=today, days=HORIZON_DAYS)
    keep: list[tuple[date, str]] = []
    saved: list[GoldenMoment] = []
    for item in computed:
        day = date.fromisoformat(item["date"])
        clock = datetime.strptime(item["time"], "%H:%M").time()
        row, _created = GoldenMoment.objects.update_or_create(
            spot=spot,
            date=day,
            type=item["type"],
            defaults={"time": clock},
        )
        keep.append((day, item["type"]))
        saved.append(row)
    extra = GoldenMoment.objects.filter(spot=spot, date__gte=today)
    for row in extra:
        if (row.date, row.type) not in keep:
            row.delete()
    return saved


def calendar_for_month(year: int, month: int) -> list[dict]:
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    rows = (
        GoldenMoment.objects.filter(date__gte=start, date__lt=end, type="high_tide_sunset")
        .select_related("spot")
        .order_by("date", "time", "spot__name")
    )
    payload = []
    for row in rows:
        item = moment_payload(row)
        item.update(
            {
                "spot_id": row.spot_id,
                "name": row.spot.name,
                "region": row.spot.region,
            }
        )
        payload.append(item)
    if payload:
        return payload
    for spot in WaterSpot.objects.filter(type__in=SEA_TYPES).order_by("id")[:40]:
        persist_golden_moments(spot)
    rows = (
        GoldenMoment.objects.filter(date__gte=start, date__lt=end, type="high_tide_sunset")
        .select_related("spot")
        .order_by("date", "time", "spot__name")
    )
    out = []
    for row in rows:
        item = moment_payload(row)
        item.update(
            {
                "spot_id": row.spot_id,
                "name": row.spot.name,
                "region": row.spot.region,
            }
        )
        out.append(item)
    return out
