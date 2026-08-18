"""Create a small, deterministic and unmistakably DEMO-only catalog.

This command is intentionally non-destructive by default. It never fabricates
live condition scores or forecasts, and it never deletes operator/production
rows. The optional reset is scoped to rows created by this command.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.spots.models import WaterSpot


DEMO_CATALOG_SOURCE = "PONGDANG_DEMO"

DEMO_SPOTS: tuple[dict[str, object], ...] = (
    {
        "name": "[DEMO] 해변 체험 장소",
        "type": WaterSpot.SpotType.BEACH,
        "lat": 37.79,
        "lng": 128.91,
        "region": "DEMO · 강원",
    },
    {
        "name": "[DEMO] 계곡 체험 장소",
        "type": WaterSpot.SpotType.VALLEY,
        "lat": 37.72,
        "lng": 128.64,
        "region": "DEMO · 강원",
    },
    {
        "name": "[DEMO] 온천 체험 장소",
        "type": WaterSpot.SpotType.HOTSPRING,
        "lat": 36.95,
        "lng": 127.01,
        "region": "DEMO · 충청",
    },
    {
        "name": "[DEMO] 갯벌 체험 장소",
        "type": WaterSpot.SpotType.MUDFLAT,
        "lat": 37.22,
        "lng": 126.57,
        "region": "DEMO · 경기",
    },
    {
        "name": "[DEMO] 워터파크 체험 장소",
        "type": WaterSpot.SpotType.WATERPARK,
        "lat": 37.64,
        "lng": 127.68,
        "region": "DEMO · 강원",
    },
    {
        "name": "[DEMO] 호수 체험 장소",
        "type": WaterSpot.SpotType.LAKE,
        "lat": 37.01,
        "lng": 127.93,
        "region": "DEMO · 충청",
    },
)


class Command(BaseCommand):
    help = (
        "Create deterministic DEMO-only WaterSpot rows without scores, "
        "forecasts, observations, or deletion of real catalog data."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--reset-demo",
            action="store_true",
            help="Delete only PONGDANG_DEMO rows before recreating them.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report the bounded operation without changing the database.",
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        existing = WaterSpot.objects.filter(catalog_source=DEMO_CATALOG_SOURCE)
        reset_count = existing.count() if options["reset_demo"] else 0
        if options["dry_run"]:
            self.stdout.write(
                self.style.SUCCESS(
                    "DEMO catalog validated (dry-run): "
                    f"rows={len(DEMO_SPOTS)} reset_rows={reset_count}"
                )
            )
            return

        if options["reset_demo"]:
            existing.delete()

        created = 0
        updated = 0
        for item in DEMO_SPOTS:
            name = str(item["name"])
            defaults = {
                **item,
                "address": "DEMO 주소 — 실제 방문 정보가 아닙니다.",
                "tags": ["DEMO_ONLY"],
                "description": (
                    "UI 개발용 DEMO 장소입니다. 실제 운영·안전·예보 근거가 "
                    "없으며 방문 판단에 사용할 수 없습니다."
                ),
                "preference_features": {},
                "opening_windows": [],
                "catalog_confidence": 0.0,
                "catalog_verification": WaterSpot.VerificationState.UNKNOWN,
                "catalog_source": DEMO_CATALOG_SOURCE,
                "catalog_source_url": "",
                "accessibility_state": WaterSpot.AccessibilityState.UNKNOWN,
                "pet_policy": WaterSpot.PolicyState.UNKNOWN,
            }
            defaults.pop("name")
            _, was_created = WaterSpot.objects.update_or_create(
                name=name,
                catalog_source=DEMO_CATALOG_SOURCE,
                defaults=defaults,
            )
            created += int(was_created)
            updated += int(not was_created)

        self.stdout.write(
            self.style.SUCCESS(
                "DEMO catalog ready: "
                f"created={created} updated={updated} reset_rows={reset_count}. "
                "No condition scores or forecasts were fabricated."
            )
        )
