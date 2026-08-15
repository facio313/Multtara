"""
TourAPI 4.0 (KorService2) keyword search used to enrich existing seed spots.
"""

from __future__ import annotations

from typing import Any

from services.public_data import PublicDataError, get_json, iter_records, require_service_key
from services.stations import CACHE_TTL

BASE_URL = "https://apis.data.go.kr/B551011/KorService2"
COMMON_PARAMS = {
    "MobileOS": "ETC",
    "MobileApp": "PongDang",
    "_type": "json",
    "numOfRows": 20,
    "pageNo": 1,
}
PREFERRED_TYPES = {"12", "28", "15", "25"}


def _service_key() -> str:
    return require_service_key("TOUR_API_KEY")


def _norm(value: str) -> str:
    return "".join(str(value).split()).lower()


def _pick_item(rows: list[dict], keyword: str) -> dict:
    target = _norm(keyword)
    ranked: list[tuple[int, dict]] = []
    for item in rows:
        title = _norm(str(item.get("title") or ""))
        content_type = str(item.get("contenttypeid") or "")
        score = 0
        if title == target:
            score += 100
        elif target in title or title in target:
            score += 60
        if content_type in PREFERRED_TYPES:
            score += 25
        if item.get("firstimage") or item.get("firstimage2"):
            score += 5
        ranked.append((score, item))
    ranked.sort(key=lambda row: row[0], reverse=True)
    if ranked and ranked[0][0] >= 60:
        return ranked[0][1]
    return {}


def search_spot(keyword: str) -> dict[str, str]:
    if not keyword:
        raise PublicDataError("TourAPI keyword is empty.")
    compact = _norm(keyword) or keyword
    payload = get_json(
        f"{BASE_URL}/searchKeyword2",
        {**COMMON_PARAMS, "keyword": compact},
        service_key=_service_key(),
        cache_key=f"tour:search:{compact}",
        ttl=CACHE_TTL["tour_spot_detail"],
    )
    item = _pick_item(iter_records(payload), keyword)
    content_id = str(item.get("contentid") or item.get("contentId") or "")
    image = str(item.get("firstimage") or item.get("firstimage2") or "")
    overview = ""
    if content_id:
        detail = get_json(
            f"{BASE_URL}/detailCommon2",
            {**COMMON_PARAMS, "numOfRows": 1, "contentId": content_id},
            service_key=_service_key(),
            cache_key=f"tour:detail:{content_id}",
            ttl=CACHE_TTL["tour_spot_detail"],
        )
        detail_item = iter_records(detail)[0] if iter_records(detail) else {}
        overview = str(detail_item.get("overview") or "")
        image = str(detail_item.get("firstimage") or detail_item.get("firstimage2") or image)
        if not image:
            photos = get_json(
                f"{BASE_URL}/detailImage2",
                {**COMMON_PARAMS, "contentId": content_id},
                service_key=_service_key(),
                cache_key=f"tour:image:{content_id}",
                ttl=CACHE_TTL["tour_spot_detail"],
            )
            photo = iter_records(photos)[0] if iter_records(photos) else {}
            image = str(photo.get("originimgurl") or photo.get("smallimageurl") or "")
    return {
        "tourapi_id": content_id,
        "image_url": image,
        "description": overview,
    }
