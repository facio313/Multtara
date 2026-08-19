"""Trip memory capture and past-vs-now replay without vision AI (C4)."""

from __future__ import annotations

import uuid
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.utils import timezone

from apps.content.models import TripMemory
from apps.spots.models import WaterSpot
from services.asmr_score import asmr_payload
from services.companion import companion_payload
from services.safety_radar import assess_safety
from services.spot_analytics import analytics_payload

MAX_PHOTO_BYTES = 2 * 1024 * 1024
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def _latest_condition(spot: WaterSpot):
    return spot.conditions.order_by("-fetched_at").first()


def snapshot_for(spot: WaterSpot) -> dict:
    condition = _latest_condition(spot)
    safety = assess_safety(spot.type, condition, spot.crowd_levels.order_by("-updated_at").first())
    scores = {}
    for row in spot.scores.all():
        scores.setdefault(row.activity, round(row.score))
    payload = {
        "image_url": spot.image_url,
        "water_temp": getattr(condition, "water_temp", None),
        "wave_height": getattr(condition, "wave_height", None),
        "water_quality_grade": getattr(condition, "water_quality_grade", None),
        "water_index": scores.get("swim") or scores.get("relax"),
        "safety": safety,
        "asmr": asmr_payload(spot, condition),
    }
    return payload


def save_photo(upload: UploadedFile, user_id: int) -> str:
    content_type = (upload.content_type or "").lower()
    if content_type not in ALLOWED_TYPES:
        raise ValueError("jpeg, png, webp 이미지만 올릴 수 있습니다.")
    if upload.size and upload.size > MAX_PHOTO_BYTES:
        raise ValueError("사진은 2MB 이하만 올릴 수 있습니다.")
    suffix = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }[content_type]
    folder = Path(settings.MEDIA_ROOT) / "memories"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{user_id}_{uuid.uuid4().hex}{suffix}"
    path = folder / name
    with path.open("wb") as handle:
        for chunk in upload.chunks():
            handle.write(chunk)
    return f"{settings.MEDIA_URL}memories/{name}"


def record_memory(
    user,
    spot: WaterSpot,
    *,
    photo_url: str = "",
    estimated_location: str = "",
    taken_at=None,
) -> TripMemory:
    return TripMemory.objects.create(
        user=user,
        spot=spot,
        photo_url=photo_url or spot.image_url or "",
        taken_at=taken_at or timezone.now(),
        estimated_location=estimated_location or f"{spot.region} {spot.name}".strip(),
        condition_snapshot=snapshot_for(spot),
    )


def memory_payload(row: TripMemory) -> dict:
    return {
        "id": row.id,
        "spot_id": row.spot_id,
        "name": row.spot.name,
        "region": row.spot.region,
        "type": row.spot.type,
        "photo_url": row.photo_url,
        "taken_at": row.taken_at,
        "estimated_location": row.estimated_location,
        "condition_snapshot": row.condition_snapshot or {},
    }


def replay_payload(row: TripMemory) -> dict:
    spot = row.spot
    then = row.condition_snapshot or {}
    now = snapshot_for(spot)
    then_photo = row.photo_url or then.get("image_url") or ""
    now_photo = spot.image_url or now.get("image_url") or ""
    delta = timezone.now() - row.taken_at
    if delta.days >= 365:
        ago = f"{delta.days // 365}년 전"
    elif delta.days >= 1:
        ago = f"{delta.days}일 전"
    else:
        ago = "오늘"
    analytics = analytics_payload(spot)
    caption = f"{ago} 당신이 방문한 {spot.name} vs 현재 모습"
    return {
        "memory": memory_payload(row),
        "caption": caption,
        "ago": ago,
        "then": {
            "photo_url": then_photo,
            "taken_at": row.taken_at,
            "location": row.estimated_location,
            "water_temp": then.get("water_temp"),
            "wave_height": then.get("wave_height"),
            "water_quality_grade": then.get("water_quality_grade"),
            "water_index": then.get("water_index"),
            "asmr_score": (then.get("asmr") or {}).get("asmr_score"),
        },
        "now": {
            "photo_url": now_photo,
            "water_temp": now.get("water_temp"),
            "wave_height": now.get("wave_height"),
            "water_quality_grade": now.get("water_quality_grade"),
            "water_index": now.get("water_index"),
            "asmr_score": (now.get("asmr") or {}).get("asmr_score"),
            "headline": analytics.get("headline"),
        },
        "companion": companion_payload(spot),
    }
