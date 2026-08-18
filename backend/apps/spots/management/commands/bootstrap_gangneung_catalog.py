"""Create the reviewed Gangneung MVP catalog without overwriting operator data."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.spots.bootstrap_catalog import CATALOG_VERIFIED_AT, GANGNEUNG_CORE_SPOTS
from apps.spots.models import WaterSpot


class Command(BaseCommand):
    help = (
        "Create the reviewed Gangneung MVP catalog. Existing same-name "
        "Gangneung rows are preserved and provider identifiers are never guessed."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and report actions without writing rows.",
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        dry_run = bool(options.get("dry_run"))
        created = 0
        preserved = 0

        for record in GANGNEUNG_CORE_SPOTS:
            existing = (
                WaterSpot.objects.filter(
                    name=record["name"],
                    region__icontains="강릉",
                )
                .order_by("pk")
                .first()
            )
            if existing is not None:
                preserved += 1
                self.stdout.write(
                    f"preserved spot_id={existing.pk} name={existing.name}"
                )
                continue

            spot = WaterSpot(
                **record,
                catalog_verified_at=CATALOG_VERIFIED_AT,
            )
            spot.full_clean()
            if dry_run:
                self.stdout.write(f"would-create name={spot.name}")
            else:
                spot.save()
                self.stdout.write(f"created spot_id={spot.pk} name={spot.name}")
            created += 1

        if dry_run:
            transaction.set_rollback(True)
        mode = "dry-run" if dry_run else "persisted"
        self.stdout.write(
            self.style.SUCCESS(
                f"Gangneung catalog bootstrap complete ({mode}): "
                f"created={created}, preserved={preserved}"
            )
        )
