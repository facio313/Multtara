"""
KMA (기상청) wrappers: ultra-short observation, short forecast, mid-term forecast.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from services.grid_converter import latlon_to_grid
from services.public_data import PublicDataError, get_json, iter_records, require_service_key
from services.stations import CACHE_TTL

KST = ZoneInfo("Asia/Seoul")
VILAGE_URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0"
MID_URL = "https://apis.data.go.kr/1360000/MidFcstInfoService"
VILAGE_BASE_HOURS = (2, 5, 8, 11, 14, 17, 20, 23)


def _now() -> datetime:
    return datetime.now(KST)


def _to_float(value: Any) -> float | None:
    if value is None or value == "" or value == "-":
        return None
    text = str(value).strip().replace("mm", "")
    if text in {"강수없음", "없음"}:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return None


def _service_key() -> str:
    return require_service_key("KMA_API_KEY")


def _ncst_base(now: datetime | None = None) -> tuple[str, str]:
    current = now or _now()
    moment = current.replace(minute=0, second=0, microsecond=0)
    if current.minute < 40:
        moment -= timedelta(hours=1)
    return moment.strftime("%Y%m%d"), moment.strftime("%H00")


def _vilage_base(now: datetime | None = None) -> tuple[str, str]:
    current = now or _now()
    available = current - timedelta(minutes=10)
    earlier = [hour for hour in VILAGE_BASE_HOURS if hour <= available.hour]
    if earlier:
        moment = available.replace(hour=earlier[-1], minute=0, second=0, microsecond=0)
    else:
        previous = available - timedelta(days=1)
        moment = previous.replace(hour=23, minute=0, second=0, microsecond=0)
    return moment.strftime("%Y%m%d"), moment.strftime("%H00")


def _mid_tm_fc(now: datetime | None = None) -> str:
    current = now or _now()
    today_06 = current.replace(hour=6, minute=0, second=0, microsecond=0)
    today_18 = current.replace(hour=18, minute=0, second=0, microsecond=0)
    if current >= today_18 + timedelta(minutes=10):
        return current.strftime("%Y%m%d") + "1800"
    if current >= today_06 + timedelta(minutes=10):
        return current.strftime("%Y%m%d") + "0600"
    yesterday = current - timedelta(days=1)
    return yesterday.strftime("%Y%m%d") + "1800"


def fetch_ultra_short_observation(lat: float, lng: float) -> dict[str, float | None]:
    nx, ny = latlon_to_grid(lat, lng)
    base_date, base_time = _ncst_base()
    payload = get_json(
        f"{VILAGE_URL}/getUltraSrtNcst",
        {
            "pageNo": 1,
            "numOfRows": 200,
            "dataType": "JSON",
            "base_date": base_date,
            "base_time": base_time,
            "nx": nx,
            "ny": ny,
        },
        service_key=_service_key(),
        cache_key=f"kma:ncst:{nx}:{ny}:{base_date}{base_time}",
        ttl=CACHE_TTL["weather_current"],
    )
    categories: dict[str, Any] = {}
    for row in iter_records(payload):
        category = row.get("category")
        if category:
            categories[str(category)] = row.get("obsrValue")
    return {
        "air_temp": _to_float(categories.get("T1H")),
        "wind_speed": _to_float(categories.get("WSD")),
        "rainfall_recent": _to_float(categories.get("RN1")),
        "nx": nx,
        "ny": ny,
    }


def _group_vilage(payload: Any) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in iter_records(payload):
        date = str(row.get("fcstDate") or "")
        time = str(row.get("fcstTime") or "")
        if not date:
            continue
        slot = grouped.setdefault(date, {})
        category = str(row.get("category") or "")
        if time == "1200" or category not in slot:
            slot[category] = row.get("fcstValue")
        if category in {"TMP", "WSD", "WAV", "POP", "PCP"} and time == "1500" and category not in slot:
            slot[category] = row.get("fcstValue")
    return grouped


def fetch_short_forecast(lat: float, lng: float) -> dict[str, dict[str, float | None]]:
    nx, ny = latlon_to_grid(lat, lng)
    base_date, base_time = _vilage_base()
    payload = get_json(
        f"{VILAGE_URL}/getVilageFcst",
        {
            "pageNo": 1,
            "numOfRows": 1000,
            "dataType": "JSON",
            "base_date": base_date,
            "base_time": base_time,
            "nx": nx,
            "ny": ny,
        },
        service_key=_service_key(),
        cache_key=f"kma:vilage:{nx}:{ny}:{base_date}{base_time}",
        ttl=CACHE_TTL["weather_forecast"],
    )
    days: dict[str, dict[str, float | None]] = {}
    for date, categories in _group_vilage(payload).items():
        rain = _to_float(categories.get("PCP"))
        pop = _to_float(categories.get("POP"))
        if rain is None and pop is not None:
            rain = pop * 0.3
        days[date] = {
            "air_temp": _to_float(categories.get("TMP")),
            "wind_speed": _to_float(categories.get("WSD")),
            "wave_height": _to_float(categories.get("WAV")),
            "rainfall_recent": rain,
        }
    return days


def _mid_row(payload: Any) -> dict[str, Any]:
    rows = iter_records(payload)
    return rows[0] if rows else {}


def fetch_mid_forecast(land_reg_id: str, ta_reg_id: str) -> dict[int, dict[str, float | None]]:
    if not land_reg_id or not ta_reg_id:
        raise PublicDataError("Mid-term region codes are missing.")
    tm_fc = _mid_tm_fc()
    key = _service_key()
    land = get_json(
        f"{MID_URL}/getMidLandFcst",
        {"pageNo": 1, "numOfRows": 10, "dataType": "JSON", "regId": land_reg_id, "tmFc": tm_fc},
        service_key=key,
        cache_key=f"kma:mid-land:{land_reg_id}:{tm_fc}",
        ttl=CACHE_TTL["weather_forecast"],
    )
    temp = get_json(
        f"{MID_URL}/getMidTa",
        {"pageNo": 1, "numOfRows": 10, "dataType": "JSON", "regId": ta_reg_id, "tmFc": tm_fc},
        service_key=key,
        cache_key=f"kma:mid-ta:{ta_reg_id}:{tm_fc}",
        ttl=CACHE_TTL["weather_forecast"],
    )
    land_row = _mid_row(land)
    temp_row = _mid_row(temp)
    days: dict[int, dict[str, float | None]] = {}
    for offset in range(3, 8):
        min_temp = _to_float(temp_row.get(f"taMin{offset}"))
        max_temp = _to_float(temp_row.get(f"taMax{offset}"))
        air = None
        if min_temp is not None and max_temp is not None:
            air = (min_temp + max_temp) / 2
        elif max_temp is not None:
            air = max_temp
        elif min_temp is not None:
            air = min_temp
        pop = _to_float(land_row.get(f"rnSt{offset}Am"))
        if pop is None:
            pop = _to_float(land_row.get(f"rnSt{offset}"))
        rain = None if pop is None else pop * 0.3
        days[offset] = {"air_temp": air, "rainfall_recent": rain, "wind_speed": None, "wave_height": None}
    return days


def seven_day_outlook(
    lat: float,
    lng: float,
    *,
    land_reg_id: str,
    ta_reg_id: str,
    today: datetime | None = None,
) -> list[dict]:
    """D+1..D+7 rows used by Water Forecast. Short forecast wins on overlap."""
    current = today or _now()
    today_date = current.date()
    short: dict[str, dict[str, float | None]] = {}
    try:
        short = fetch_short_forecast(lat, lng)
    except PublicDataError:
        short = {}
    mid: dict[int, dict[str, float | None]] = {}
    try:
        mid = fetch_mid_forecast(land_reg_id, ta_reg_id)
    except PublicDataError:
        mid = {}

    rows: list[dict] = []
    for offset in range(1, 8):
        target = today_date + timedelta(days=offset)
        key = target.strftime("%Y%m%d")
        values = dict(short.get(key) or {})
        if offset in mid:
            for field, value in mid[offset].items():
                if values.get(field) is None and value is not None:
                    values[field] = value
        rows.append(
            {
                "forecast_date": target,
                "air_temp": values.get("air_temp"),
                "wind_speed": values.get("wind_speed"),
                "wave_height": values.get("wave_height"),
                "rainfall_recent": values.get("rainfall_recent"),
                "source": "kma",
            }
        )
    return rows
