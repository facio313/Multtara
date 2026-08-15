"""
KHOA (국립해양조사원) wrappers: observed water temperature and high/low tide.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from services.public_data import PublicDataError, get_json, iter_records, require_service_key
from services.stations import CACHE_TTL

KST = ZoneInfo("Asia/Seoul")
TEMP_URL = "https://apis.data.go.kr/1192136/surveyWaterTemp/GetSurveyWaterTempApiService"
TIDE_URL = "https://apis.data.go.kr/1192136/tideFcstHghLw/GetTideFcstHghLwApiService"

HIGH_LABELS = {"고조", "만조", "high", "h", "1", "3"}
LOW_LABELS = {"저조", "간조", "low", "l", "2", "4"}


def _service_key() -> str:
    return require_service_key("KHOA_API_KEY")


def _today(now: datetime | None = None) -> str:
    current = now or datetime.now(KST)
    return current.strftime("%Y%m%d")


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _first_number(row: dict, *keys: str) -> float | None:
    for key in keys:
        if key in row:
            parsed = _to_float(row.get(key))
            if parsed is not None:
                return parsed
    lowered = {str(k).lower(): v for k, v in row.items()}
    for key in keys:
        parsed = _to_float(lowered.get(key.lower()))
        if parsed is not None:
            return parsed
    return None


def _time_token(value: Any) -> str | None:
    if value is None or value == "":
        return None
    text = str(value).strip().replace("T", " ")
    if " " in text:
        text = text.split(" ")[-1]
    text = text.replace("시", ":").replace("분", "")
    if len(text) == 4 and text.isdigit():
        return f"{text[:2]}:{text[2:]}"
    if len(text) >= 5 and text[2] == ":":
        return text[:5]
    return text[:5] if text else None


def _hl_bucket(row: dict) -> str | None:
    for key in ("extrSe", "hlCode", "hl_code", "tideSe", "hlcode", "code", "tphCode"):
        raw = row.get(key)
        if raw is None:
            continue
        token = str(raw).strip().lower()
        if token in {label.lower() for label in HIGH_LABELS} or "고" in str(raw) or "만조" in str(raw):
            return "high_tide"
        if token in {label.lower() for label in LOW_LABELS} or "저" in str(raw) or "간조" in str(raw):
            return "low_tide"
    return None


def fetch_water_temperature(obs_code: str, req_date: str | None = None) -> float | None:
    if not obs_code:
        raise PublicDataError("KHOA obsCode is missing.")
    day = req_date or _today()
    payload = get_json(
        TEMP_URL,
        {
            "type": "json",
            "obsCode": obs_code,
            "reqDate": day,
            "numOfRows": 50,
            "pageNo": 1,
            "min": 60,
        },
        service_key=_service_key(),
        cache_key=f"khoa:temp:{obs_code}:{day}",
        ttl=CACHE_TTL["marine_temp"],
    )
    records = iter_records(payload)
    if not records:
        return None
    latest = records[-1]
    return _first_number(
        latest,
        "wtem",
        "waterTemp",
        "water_temp",
        "tw",
        "wt",
        "obsWaterTemp",
        "temp",
        "wtrTemp",
    )


def fetch_tide_schedule(obs_code: str, req_date: str | None = None) -> dict[str, list[str]]:
    if not obs_code:
        raise PublicDataError("KHOA obsCode is missing.")
    day = req_date or _today()
    payload = get_json(
        TIDE_URL,
        {
            "type": "json",
            "obsCode": obs_code,
            "reqDate": day,
            "numOfRows": 20,
            "pageNo": 1,
        },
        service_key=_service_key(),
        cache_key=f"khoa:tide:{obs_code}:{day}",
        ttl=CACHE_TTL["marine_tide"],
    )
    schedule = {"low_tide": [], "high_tide": []}
    for row in iter_records(payload):
        bucket = _hl_bucket(row)
        stamp = None
        for key in ("predcDt", "tphTime", "tph_time", "predTime", "tideTime", "time", "tph_dt"):
            stamp = _time_token(row.get(key))
            if stamp:
                break
        if not bucket or not stamp:
            continue
        if stamp not in schedule[bucket]:
            schedule[bucket].append(stamp)
    return schedule
