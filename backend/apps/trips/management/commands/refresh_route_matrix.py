"""Refresh a bounded, expiring route matrix from an operator-configured Valhalla."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from decouple import config
from django.core.management.base import BaseCommand, CommandError
from django.db.models import QuerySet
from django.utils import timezone

from apps.spots.models import WaterSpot
from apps.trips.models import TransportMode
from services.providers.base import ProviderError
from services.providers.valhalla import (
    MAX_MATRIX_LOCATIONS,
    RouteLocation,
    ValhallaMatrixClient,
)
from services.routing import persist_route_matrix


class Command(BaseCommand):
    help = (
        "Fetch and persist an expiring Valhalla all-to-all matrix for an "
        "explicitly curated spot set. No straight-line travel estimate is stored."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--spot",
            action="append",
            dest="spot_selectors",
            metavar="ID_OR_EXACT_NAME",
            help="Limit to a spot primary key or exact name; repeatable.",
        )
        parser.add_argument(
            "--region",
            help="Limit curated places by case-insensitive region containment.",
        )
        parser.add_argument(
            "--transport",
            choices=TransportMode.values,
            default=TransportMode.DRIVE,
        )
        parser.add_argument(
            "--valid-hours",
            type=int,
            choices=range(1, 169),
            default=24,
            help="Evidence validity in hours (1-168; default 24).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Call and validate the provider but do not persist a snapshot.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        base_url = config("ROUTING_MATRIX_URL", default="").strip()
        if not base_url:
            raise CommandError("ROUTING_MATRIX_URL is not configured")
        spots = tuple(
            _resolve_spots(
                options.get("spot_selectors"),
                region=options.get("region"),
            )
        )
        if len(spots) < 2:
            raise CommandError("At least two curated spots are required")
        if len(spots) > MAX_MATRIX_LOCATIONS:
            raise CommandError(
                f"Route matrix is bounded to {MAX_MATRIX_LOCATIONS} spots; "
                "provide --region or repeated --spot selectors"
            )

        locations = tuple(
            RouteLocation(
                spot_id=spot.pk,
                latitude=spot.lat,
                longitude=spot.lng,
            )
            for spot in spots
        )
        fetched_at = timezone.now()
        try:
            with ValhallaMatrixClient(base_url) as client:
                result = client.fetch_matrix(
                    locations,
                    transport=options["transport"],
                )
        except (ProviderError, ValueError) as exc:
            raise CommandError(str(exc)) from None
        except Exception:
            raise CommandError("Valhalla matrix refresh failed internally") from None

        if options.get("dry_run"):
            self.stdout.write(
                self.style.SUCCESS(
                    "Valhalla matrix validated (dry-run): "
                    f"spots={len(spots)}, reachable_pairs={len(result.values)}"
                )
            )
            return

        snapshot, created = persist_route_matrix(
            result,
            observed_at=fetched_at,
            fetched_at=fetched_at,
            valid_for=timedelta(hours=options["valid_hours"]),
            spot_ids=(spot.pk for spot in spots),
        )
        state = "created" if created else "deduplicated"
        self.stdout.write(
            self.style.SUCCESS(
                f"Valhalla route matrix {state}: snapshot_id={snapshot.pk}, "
                f"spots={len(spots)}, reachable_pairs={len(result.values)}, "
                f"transport={result.transport}"
            )
        )


def _resolve_spots(
    selectors: list[str] | None,
    *,
    region: str | None,
) -> QuerySet[WaterSpot]:
    queryset = WaterSpot.objects.exclude(catalog_verification="unknown")
    if region:
        queryset = queryset.filter(region__icontains=region.strip())
    if not selectors:
        return queryset.order_by("pk")

    selected_ids: set[int] = set()
    for selector in selectors:
        text = selector.strip()
        if not text:
            raise CommandError("--spot cannot be blank")
        matches = (
            queryset.filter(pk=int(text))
            if text.isdecimal()
            else queryset.filter(name__iexact=text)
        )
        ids = tuple(matches.values_list("pk", flat=True))
        if not ids:
            raise CommandError("No curated spot matched one --spot selector")
        selected_ids.update(ids)
    return queryset.filter(pk__in=selected_ids).order_by("pk")
