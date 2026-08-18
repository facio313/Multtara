"""Persist evidence-bound suitability derivations before index evaluation."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from django.core.management.base import BaseCommand, CommandError
from django.db.models import QuerySet
from django.utils import timezone

from apps.spots.models import WaterSpot
from services.ingestion.derived import derive_suitability_metrics_for_spot


class Command(BaseCommand):
    help = (
        "Derive HCI:Beach, verified facility-fit, and calibrated rafting-flow "
        "metrics without interpreting any result as safety clearance."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--spot",
            action="append",
            dest="spot_selectors",
            metavar="ID_OR_EXACT_NAME",
            help="Limit derivation to a WaterSpot id or exact name; repeatable.",
        )
        parser.add_argument(
            "--at",
            type=_parse_at,
            metavar="ISO-8601",
            help="Timezone-aware derivation time (default: now).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        spots = tuple(_resolve_spots(options.get("spot_selectors")))
        if not spots:
            raise CommandError("No WaterSpot rows are available for derivation")
        at = options.get("at") or timezone.now()
        dry_run = bool(options.get("dry_run"))
        derived = 0
        persisted = 0
        try:
            for spot in spots:
                report = derive_suitability_metrics_for_spot(
                    spot=spot,
                    at=at,
                    dry_run=dry_run,
                )
                derived += report.derived_snapshots
                persisted += report.persisted_snapshots
        except (TypeError, ValueError):
            raise CommandError("Suitability evidence could not be derived safely") from None
        except Exception:
            # Provider/source URLs may contain sensitive query material in bad
            # legacy rows. Keep command output bounded and credential-free.
            raise CommandError("Suitability derivation failed internally") from None
        mode = "dry-run" if dry_run else "persisted"
        self.stdout.write(
            self.style.SUCCESS(
                f"Suitability derivation complete ({mode}): "
                f"spots={len(spots)} derived={derived} persisted={persisted}"
            )
        )


def _parse_at(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        raise CommandError("--at must be a valid ISO-8601 datetime") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CommandError("--at must include a timezone offset")
    return parsed


def _resolve_spots(selectors: Iterable[str] | None) -> QuerySet[WaterSpot]:
    if not selectors:
        return WaterSpot.objects.all().order_by("pk")
    selected_ids: list[int] = []
    for selector in selectors:
        text = selector.strip()
        if not text:
            raise CommandError("--spot cannot be blank")
        matches = (
            WaterSpot.objects.filter(pk=int(text))
            if text.isdecimal()
            else WaterSpot.objects.filter(name__iexact=text)
        )
        ids = list(matches.values_list("pk", flat=True))
        if not ids:
            raise CommandError(f"WaterSpot not found for --spot selector: {text}")
        selected_ids.extend(ids)
    return WaterSpot.objects.filter(pk__in=selected_ids).order_by("pk")
