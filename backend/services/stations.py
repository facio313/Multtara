"""
Station and mid-forecast region codes for the 26 seed spots.

KHOA codes are nearest tide stations, not per-beach sensors.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.spots.models import WaterSpot

# getMidLandFcst regId
REGION_MID_LAND = {
    "서울": "11B00000",
    "인천": "11B00000",
    "경기": "11B00000",
    "강원": "11D20000",
    "충북": "11C10000",
    "충남": "11C20000",
    "대전": "11C20000",
    "전북": "11F10000",
    "전남": "11F20000",
    "광주": "11F20000",
    "대구": "11H10000",
    "경북": "11H10000",
    "부산": "11H20000",
    "울산": "11H20000",
    "경남": "11H20000",
    "제주": "11G00000",
}

# getMidTa city codes
REGION_MID_TA = {
    "서울": "11B10101",
    "인천": "11B20201",
    "경기": "11B20601",
    "강원": "11D20501",
    "충북": "11C10301",
    "충남": "11C20101",
    "전북": "11F10201",
    "경북": "11H10201",
    "부산": "11H20201",
    "제주": "11G00201",
}

SPOT_MID_LAND = {
    "동강 래프팅": "11D10000",
    "설악산 천불동계곡": "11D20000",
}

SPOT_MID_TA = {
    "동강 래프팅": "11D10401",
    "설악산 천불동계곡": "11D20401",
    "속초 해수욕장": "11D20401",
    "양양 설악비치": "11D20401",
    "덕구 온천": "11H10101",
}

# Nearest KHOA tide station for coastal / mudflat spots.
SPOT_KHOA_OBS = {
    "해운대 해수욕장": "DT_0005",
    "광안리 해수욕장": "DT_0005",
    "송정 해수욕장": "DT_0005",
    "경포 해수욕장": "DT_0026",
    "속초 해수욕장": "DT_0012",
    "양양 설악비치": "DT_0012",
    "을왕리 해수욕장": "DT_0001",
    "대천 해수욕장": "DT_0004",
    "협재 해수욕장": "DT_0023",
    "중문 색달 해변": "DT_0023",
    "동막 해수욕장 갯벌": "DT_0001",
    "선재도 갯벌": "DT_0001",
    "무창포 갯벌": "DT_0004",
}

# Rip-current beaches published by KHOA (sample code DAECHON).
SPOT_RIP_BEACH = {
    "해운대 해수욕장": "HAEUNDAE",
    "송정 해수욕장": "SONGJEONG",
    "중문 색달 해변": "JUNGMUN",
    "대천 해수욕장": "DAECHON",
    "경포 해수욕장": "GYEONGPO",
    "속초 해수욕장": "SOKCHO",
    "양양 설악비치": "NAKSAN",
}

# Optional noonWave buoy codes. Beach/surf index wave height is preferred.
SPOT_WAVE_OBS = {}

PLACE_ALIASES = {
    "양양 설악비치": ("낙산", "설악"),
    "중문 색달 해변": ("중문", "색달"),
    "동막 해수욕장 갯벌": ("동막",),
    "선재도 갯벌": ("선재",),
    "무창포 갯벌": ("무창포",),
    "광안리 해수욕장": ("광안",),
}

CACHE_TTL = {
    "weather_current": 60 * 30,
    "weather_forecast": 60 * 180,
    "marine_temp": 60 * 60,
    "marine_tide": 60 * 60 * 6,
    "marine_index": 60 * 60 * 3,
    "marine_rip": 60 * 30,
    "marine_wave": 60 * 60,
    "tour_spot_detail": 60 * 60 * 24,
    "water_quality": 60 * 60 * 24,
    "uv_index": 60 * 60 * 6,
}

# KMA living-weather UV areaNo (10-digit administrative codes).
REGION_UV_AREA = {
    "서울": "1100000000",
    "부산": "2600000000",
    "대구": "2700000000",
    "인천": "2800000000",
    "광주": "2900000000",
    "대전": "3000000000",
    "울산": "3100000000",
    "세종": "3611000000",
    "경기": "4100000000",
    "강원": "4200000000",
    "충북": "4300000000",
    "충남": "4400000000",
    "전북": "4500000000",
    "전남": "4600000000",
    "경북": "4700000000",
    "경남": "4800000000",
    "제주": "5000000000",
}

# Nearest NIER 물환경 수질측정망 station (ptNo), verified via getWaterMeasuringList.
SPOT_MOE_PT = {
    "동강 래프팅": "1001A75",  # 동강2
    "가평 용추계곡": "1015A20",  # 조종천1
    "명지계곡": "1013A70",  # 가평천1
    "청평호": "1015B30",  # 청평댐1
    "충주호": "1003B40",  # 충주댐1
    "지리산 뱀사골": "2018A20",  # 람천1
    "설악산 천불동계곡": "1011A10",  # 북천
}


def mid_land_id(spot: WaterSpot) -> str:
    if getattr(spot, "kma_mid_reg_id", ""):
        return spot.kma_mid_reg_id
    if spot.name in SPOT_MID_LAND:
        return SPOT_MID_LAND[spot.name]
    return REGION_MID_LAND.get(spot.region, "")


def mid_ta_id(spot: WaterSpot) -> str:
    if spot.name in SPOT_MID_TA:
        return SPOT_MID_TA[spot.name]
    return REGION_MID_TA.get(spot.region, "")


def khoa_obs_code(spot: WaterSpot) -> str:
    if getattr(spot, "khoa_obs_code", ""):
        return spot.khoa_obs_code
    return SPOT_KHOA_OBS.get(spot.name, "")


def uv_area_no(spot: WaterSpot) -> str:
    return REGION_UV_AREA.get(spot.region, "")


def moe_pt_no(spot: WaterSpot) -> str:
    return SPOT_MOE_PT.get(spot.name, "")


def rip_beach_code(spot: WaterSpot) -> str:
    return SPOT_RIP_BEACH.get(spot.name, "")


def wave_obs_code(spot: WaterSpot) -> str:
    return SPOT_WAVE_OBS.get(spot.name, "")


def place_tokens(spot_name: str) -> list[str]:
    tokens = [spot_name.replace(" ", "")]
    for extra in PLACE_ALIASES.get(spot_name, ()):
        tokens.append(extra)
    for suffix in ("해수욕장", "해변", "갯벌", "비치"):
        if spot_name.endswith(suffix):
            tokens.append(spot_name[: -len(suffix)].strip())
    return [token for token in tokens if token]


def row_matches_spot(spot_name: str, row: dict) -> bool:
    haystack = " ".join(
        str(row.get(key) or "")
        for key in (
            "plcNm",
            "placeNm",
            "placeName",
            "beachNm",
            "obsName",
            "staNm",
            "name",
            "title",
        )
    )
    compact = haystack.replace(" ", "")
    if not compact:
        return False
    return any(token.replace(" ", "") in compact for token in place_tokens(spot_name))
