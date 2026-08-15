"""
KHOA (국립해양조사원) wrappers: tide, water temperature, beach/surf/mudflat
index, rip current, and observed waves via data.go.kr.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from services.public_data import PublicDataError, get_json, is_skippable_error, iter_records, require_service_key
from services.stations import CACHE_TTL, match_score, rip_beach_code, row_place_name, wave_obs_code

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


BEACH_URL = "https://apis.data.go.kr/1192136/fcstBeachv2/GetFcstBeachApiServicev2"
SURF_URL = "https://apis.data.go.kr/1192136/fcstSurfingv2/GetFcstSurfingApiServicev2"
MUDFLAT_URL = "https://apis.data.go.kr/1192136/fcstMudflatv2/GetFcstMudflatApiServicev2"
RIP_URL = "https://apis.data.go.kr/1192136/ripCurrent/GetRipCurrentApiService"
WAVE_URL = "https://apis.data.go.kr/1192136/noonWave/GetNoonWaveApiService"

RIP_TO_LEVEL = {
    "관심": "low",
    "attention": "low",
    "interest": "low",
    "1": "low",
    "주의": "medium",
    "caution": "medium",
    "2": "medium",
    "경계": "high",
    "warning": "high",
    "3": "high",
    "위험": "high",
    "danger": "high",
    "4": "high",
    "low": "low",
    "medium": "medium",
    "high": "high",
}


def _soft_json(url: str, params: dict, cache_key: str, ttl: int) -> list[dict]:
    try:
        payload = get_json(
            url,
            params,
            service_key=_service_key(),
            cache_key=cache_key,
            ttl=ttl,
        )
    except PublicDataError as exc:
        if is_skippable_error(exc):
            return []
        raise
    return iter_records(payload)


def _text(row: dict, *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    lowered = {str(k).lower(): v for k, v in row.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _forecast_rows(kind: str, url: str) -> list[dict]:
    day = _today()
    rows: list[dict] = []
    for page in range(1, 9):
        chunk = _soft_json(
            url,
            {"type": "json", "numOfRows": 300, "pageNo": page, "reqDate": day},
            cache_key=f"khoa:{kind}:list:{day}:p{page}",
            ttl=CACHE_TTL["marine_index"],
        )
        rows.extend(chunk)
        if len(chunk) < 300:
            break
    return rows


def _pick_period(rows: list[dict]) -> dict:
    now = datetime.now(KST)
    today = now.strftime("%Y-%m-%d")
    noon = "오전" if now.hour < 12 else "오후"

    def stamp(row: dict) -> str:
        return str(row.get("predcYmd") or row.get("obsrvnDt") or "")

    dated = [row for row in rows if today in stamp(row)] or rows
    period = [row for row in dated if str(row.get("predcNoonSeCd") or "") == noon]
    return (period or dated)[-1]


def _match_row(spot_name: str, rows: list[dict]) -> dict | None:
    scored: list[tuple[int, dict]] = []
    for row in rows:
        score = match_score(spot_name, row_place_name(row))
        if score >= 90:
            scored.append((score, row))
    if not scored:
        return None
    best = max(item[0] for item in scored)
    return _pick_period([row for score, row in scored if score == best])


def _index_payload(row: dict, kind: str) -> dict:
    grade = _text(
        row,
        "totalIndex",
        "lastScrCn",
        "grdCn",
        "beachGrd",
        "idxCn",
        "opnStat",
    )
    score = _first_number(row, "lastScr", "score", "beachScr", "idx", "totalIndex")
    wave = _first_number(row, "maxWvhgt", "avgWvhgt", "wvhgt", "maxWh", "wh", "wavHgt")
    water_temp = _first_number(row, "avgWtem", "wtem", "waterTemp", "tw", "wt")
    payload = {
        "kind": kind,
        "grade": grade,
        "place": row_place_name(row),
        "period": _text(row, "predcNoonSeCd"),
    }
    if score is not None:
        payload["score"] = score
    if wave is not None:
        payload["wave_height"] = wave
    if water_temp is not None:
        payload["water_temp"] = water_temp
    return {key: value for key, value in payload.items() if value not in (None, "")}


def normalize_rip_level(value: Any) -> str:
    token = str(value or "").strip().lower()
    if not token:
        return ""
    return RIP_TO_LEVEL.get(token, RIP_TO_LEVEL.get(str(value).strip(), ""))


def fetch_forecast_index(spot_name: str, kind: str) -> dict | None:
    url = {"beach": BEACH_URL, "surf": SURF_URL, "mudflat": MUDFLAT_URL}[kind]
    row = _match_row(spot_name, _forecast_rows(kind, url))
    if row is None:
        return None
    return _index_payload(row, kind)


def fetch_rip_current(beach_code: str, req_date: str | None = None) -> dict | None:
    if not beach_code:
        return None
    day = req_date or _today()
    rows = _soft_json(
        RIP_URL,
        {"type": "json", "beachCode": beach_code, "reqDate": day, "numOfRows": 20, "pageNo": 1},
        cache_key=f"khoa:rip:{beach_code}:{day}",
        ttl=CACHE_TTL["marine_rip"],
    )
    if not rows:
        return None
    row = rows[-1]
    grade = _text(row, "lastScrCn", "idxCn", "grdCn", "ripIdx", "grade")
    level = normalize_rip_level(grade) or normalize_rip_level(_text(row, "lastScr", "idx", "index"))
    wave = _first_number(row, "wvhgt", "maxWvhgt", "wh", "maxWh", "wavHgt")
    payload = {
        "kind": "rip",
        "grade": grade or level,
        "level": level,
        "score": _first_number(row, "lastScr"),
        "message": _text(row, "wrnMsg", "warnMsg", "message", "rmk"),
        "place": _text(row, "obsvtrNm", "beachNm", "plcNm", "placeNm"),
    }
    if wave is not None:
        payload["wave_height"] = wave
    water_temp = _first_number(row, "wtem", "waterTemp", "tw")
    if water_temp is not None:
        payload["water_temp"] = water_temp
    return {key: value for key, value in payload.items() if value not in (None, "")}


def fetch_wave_height(obs_code: str, req_date: str | None = None) -> float | None:
    if not obs_code:
        return None
    day = req_date or _today()
    rows = _soft_json(
        WAVE_URL,
        {"type": "json", "obsCode": obs_code, "reqDate": day, "numOfRows": 50, "pageNo": 1, "min": 60},
        cache_key=f"khoa:wave:{obs_code}:{day}",
        ttl=CACHE_TTL["marine_wave"],
    )
    if not rows:
        return None
    return _first_number(rows[-1], "wvhgt", "maxWvhgt", "wh", "sigWh", "maxWh", "wavHgt", "waveHeight", "swh", "avgWh")


def fetch_marine_extras(spot) -> dict:
    """Beach/surf/mudflat index, rip current, and wave. Missing APIs are skipped."""
    extras: dict[str, Any] = {}
    indices: dict[str, dict] = {}
    spot_type = getattr(spot, "type", "")
    name = getattr(spot, "name", "")

    if spot_type == "sea":
        beach = fetch_forecast_index(name, "beach")
        if beach:
            indices["beach"] = beach
        surf = fetch_forecast_index(name, "surf")
        if surf:
            indices["surf"] = surf
        rip = fetch_rip_current(rip_beach_code(spot))
        if rip:
            indices["rip"] = rip
            if rip.get("level"):
                extras["rip_current_risk"] = rip["level"]
    elif spot_type == "tidal_flat":
        mud = fetch_forecast_index(name, "mudflat")
        if mud:
            indices["mudflat"] = mud
        beach = fetch_forecast_index(name, "beach")
        if beach:
            indices.setdefault("beach", beach)

    wave = None
    for payload in indices.values():
        if wave is None and payload.get("wave_height") is not None:
            wave = payload["wave_height"]
    if wave is None:
        wave = fetch_wave_height(wave_obs_code(spot))
    if wave is not None:
        extras["wave_height"] = wave

    water_temp = None
    for payload in indices.values():
        if payload.get("water_temp") is not None:
            water_temp = payload["water_temp"]
            break
    if water_temp is not None:
        extras["water_temp"] = water_temp

    if indices:
        extras["marine_indices"] = indices
    return extras
