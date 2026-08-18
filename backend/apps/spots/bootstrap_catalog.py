"""Small, reviewed production bootstrap catalog for the Gangneung MVP.

The catalog deliberately contains only identities and public visitor facts that
were checked against Gangneung City sources. Provider identifiers are left
blank unless independently verified; missing activity/safety evidence remains
UNKNOWN in the condition pipeline.
"""

from __future__ import annotations

from datetime import UTC, datetime


CATALOG_VERIFIED_AT = datetime(2026, 8, 18, tzinfo=UTC)

GANGNEUNG_CORE_SPOTS: tuple[dict[str, object], ...] = (
    {
        "type": "beach",
        "name": "경포해변",
        "lat": 37.803,
        "lng": 128.91,
        "khoa_beach_code": "GYEONGPO",
        "region": "강릉 · 강원",
        "address": "강원특별자치도 강릉시 창해로 473 (강문동)",
        "tags": ["강릉MVP", "해변", "가족여행", "경포권"],
        "description": (
            "강릉시가 공개한 대표 해변 관광지입니다. 물 활동 가능 여부는 "
            "계절별 개장·입수 통제와 현재 안전 근거를 별도로 확인합니다."
        ),
        "preference_features": {"activity_level": 0.7, "quiet": 0.35},
        "opening_windows": [{"start_minute": 0, "end_minute": 1440}],
        "typical_duration_minutes": 120,
        "cost_krw": 0,
        "age_policy_known": True,
        "minimum_age": 0,
        "accessibility": (
            "공식 무장애 관광정보에서 접근로와 편의시설을 확인할 수 있습니다."
        ),
        "accessibility_state": "verified",
        "catalog_confidence": 0.9,
        "catalog_verification": "verified",
        "catalog_source": "Gangneung City tourism / KHOA ripCurrent",
        "catalog_source_url": (
            "https://bf.gn.go.kr/home/kor/M118973891/tourist/place/"
            "edit.do?act=detail&idx=3434"
        ),
    },
    {
        "type": "beach",
        "name": "안목해변",
        "lat": 37.7719,
        "lng": 128.9487,
        "region": "강릉 · 강원",
        "address": "강원특별자치도 강릉시 창해로14번길 20-1 (견소동)",
        "tags": ["강릉MVP", "해변", "커피거리", "산책"],
        "description": (
            "강릉시의 안목해변 커피거리 관광정보를 바탕으로 한 해안 산책 "
            "거점입니다. 공식 활동지수나 안전 상태는 인근 장소에서 복사하지 않습니다."
        ),
        "preference_features": {"activity_level": 0.35, "quiet": 0.45},
        "opening_windows": [{"start_minute": 0, "end_minute": 1440}],
        "typical_duration_minutes": 90,
        "cost_krw": 0,
        "age_policy_known": True,
        "minimum_age": 0,
        "accessibility": (
            "공식 무장애 관광정보에 주차장·접근로·화장실 정보가 있습니다."
        ),
        "accessibility_state": "partial",
        "catalog_confidence": 0.8,
        "catalog_verification": "partial",
        "catalog_source": "Gangneung City accessible tourism",
        "catalog_source_url": (
            "https://bf.gn.go.kr/home/kor/M118973891/tourist/place/"
            "edit.do?act=detail&idx=cb00d1a0008a85e71a41b8741facbffe"
            "2204a656dd05ba5b8d3522292b251bda"
        ),
    },
    {
        "type": "beach",
        "name": "사천진해변",
        "lat": 37.836,
        "lng": 128.878,
        "region": "강릉 · 강원",
        "address": "강원특별자치도 강릉시 사천면 진리해변길 131 (사천진리)",
        "tags": ["강릉MVP", "해변", "사천진", "산책"],
        "description": (
            "강릉시 관광정보로 확인한 사천진항 북쪽 해변입니다. KHOA 공식 지점 "
            "식별자가 없는 활동은 적합도와 안전 상태를 UNKNOWN으로 유지합니다."
        ),
        "preference_features": {"activity_level": 0.55, "quiet": 0.75},
        "opening_windows": [{"start_minute": 0, "end_minute": 1440}],
        "typical_duration_minutes": 90,
        "cost_krw": 0,
        "age_policy_known": True,
        "minimum_age": 0,
        "accessibility": (
            "공식 관광정보에서 주차장은 확인되나 연속 접근 동선은 미확인입니다."
        ),
        "accessibility_state": "partial",
        "catalog_confidence": 0.8,
        "catalog_verification": "partial",
        "catalog_source": "Gangneung City accessible tourism",
        "catalog_source_url": (
            "https://bf.gn.go.kr/home/kor/M118973891/tourist/place/"
            "edit.do?act=detail&idx=cb00d1a0008a85e71a41b8741facbffe"
            "e77fc6bd9e4df33e43a740570a03b5fb"
        ),
    },
)
