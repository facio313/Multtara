"""
환경부/국립환경과학원 수질측정망 (A1, A8).

The plan names B090026/WaterqualityService/getInfo, which is EIA 수질 개요
(mgtNo 사업코드) and is not usable for spot BOD/pH/DO. River and lake grades
come from NIER WaterQualityService (1480523).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from services.public_data import PublicDataError, get_json, iter_records, require_service_key
from services.stations import CACHE_TTL

KST = ZoneInfo("Asia/Seoul")
QUALITY_URL = "https://apis.data.go.kr/1480523/WaterQualityService/getWaterMeasuringList"

BOD_KEYS = ("ITEM_BOD", "itemBod", "bod", "BOD", "wrtBod", "iemdBod", "itemBOD")
GRADE_KEYS = ("ITEM_LVL", "lv", "grade", "wqi", "itemLv", "wqGrd", "lirv", "wqiGrade", "itemWqi")


def _service_key() -> str:
    return require_service_key("MOE_API_KEY")


def _to_float(value: Any) -> float | None:
    if value is None or value == "" or value == "-":
        return None
    text = str(value).strip()
    try:
        return float(text)
    except ValueError:
        return None


def _first_number(row: dict, *keys: str) -> float | None:
    for key in keys:
        parsed = _to_float(row.get(key))
        if parsed is not None:
            return parsed
    lowered = {str(name).lower(): value for name, value in row.items()}
    for key in keys:
        parsed = _to_float(lowered.get(key.lower()))
        if parsed is not None:
            return parsed
    return None


def grade_from_bod(bod: float) -> str:
    if bod <= 2:
        return "1"
    if bod <= 5:
        return "2"
    if bod <= 8:
        return "3"
    return "4"


def normalize_grade(raw: Any) -> str | None:
    if raw is None or raw == "":
        return None
    token = str(raw).strip()
    mapping = {
        "1": "1",
        "ia": "1",
        "ib": "1",
        "i": "1",
        "매우좋음": "1",
        "좋음": "1",
        "2": "2",
        "ii": "2",
        "약간좋음": "2",
        "보통": "2",
        "3": "3",
        "iii": "3",
        "약간나쁨": "3",
        "4": "4",
        "iv": "4",
        "v": "4",
        "vi": "4",
        "나쁨": "4",
        "매우나쁨": "4",
    }
    key = token.lower().replace("등급", "")
    if key in mapping:
        return mapping[key]
    try:
        number = int(float(token))
    except (TypeError, ValueError):
        return None
    if number <= 1:
        return "1"
    if number == 2:
        return "2"
    if number == 3:
        return "3"
    return "4"


def grade_from_row(row: dict[str, Any]) -> str | None:
    for key in GRADE_KEYS:
        if key in row:
            parsed = normalize_grade(row.get(key))
            if parsed:
                return parsed
    bod = _first_number(row, *BOD_KEYS)
    if bod is not None:
        return grade_from_bod(bod)
    return None


def _latest_row(rows: list[dict]) -> dict | None:
    if not rows:
        return None

    def sort_key(row: dict) -> tuple:
        return (
            str(row.get("WMCYMD") or row.get("wmcymd") or row.get("ymd") or row.get("itemWmcymd") or ""),
            str(row.get("WMYR") or row.get("wmyr") or row.get("itemWmyr") or ""),
            str(row.get("WMOD") or row.get("wmod") or row.get("itemWmod") or ""),
            str(row.get("WMWK") or row.get("wmwk") or row.get("itemWmwk") or ""),
        )

    return sorted(rows, key=sort_key)[-1]


def fetch_water_quality(pt_no: str) -> dict[str, Any]:
    if not pt_no:
        raise PublicDataError("MOE station code is missing.")
    year = datetime.now(KST).year
    rows: list[dict] = []
    for query_year in (year, year - 1, year - 2):
        payload = get_json(
            QUALITY_URL,
            {
                "pageNo": 1,
                "numOfRows": 200,
                "resultType": "JSON",
                "ptNoList": pt_no,
                "wmyrList": str(query_year),
            },
            service_key=_service_key(),
            cache_key=f"moe:wq:{pt_no}:{query_year}",
            ttl=CACHE_TTL["water_quality"],
        )
        rows.extend(iter_records(payload))
    usable = [row for row in rows if grade_from_row(row)]
    row = _latest_row(usable)
    if row is None:
        raise PublicDataError(f"No water-quality rows for station {pt_no}.")
    grade = grade_from_row(row)
    if not grade:
        raise PublicDataError(f"Water-quality grade missing for station {pt_no}.")
    return {
        "water_quality_grade": grade,
        "bod": _first_number(row, *BOD_KEYS),
        "pt_no": pt_no,
    }
