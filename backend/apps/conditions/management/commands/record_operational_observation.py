"""Record a time-bounded official safety observation for one curated spot."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.spots.models import WaterSpot
from services.ingestion.operational import (
    SOURCE_METRICS,
    build_operational_observation,
)
from services.ingestion.persistence import persist_observation


class Command(BaseCommand):
    help = (
        "Persist a trusted, expiring operational safety update with public "
        "provenance. This command never infers a missing clearance."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--spot", required=True, metavar="ID_OR_EXACT_NAME")
        parser.add_argument(
            "--source",
            required=True,
            choices=sorted(SOURCE_METRICS),
            help="Authority class permitted to assert the supplied metrics.",
        )
        parser.add_argument(
            "--record-id",
            required=True,
            help="Stable public identifier from the authority or operator record.",
        )
        parser.add_argument(
            "--source-url",
            required=True,
            help="Public HTTPS evidence URL without credentials or query data.",
        )
        parser.add_argument("--observed-at", required=True, type=_parse_datetime)
        parser.add_argument("--valid-until", required=True, type=_parse_datetime)
        parser.add_argument(
            "--metric",
            action="append",
            dest="metrics",
            required=True,
            metavar="NAME=VALUE",
            help="Repeat for every scalar official assertion.",
        )
        parser.add_argument("--confidence", type=float, default=1.0)
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and normalize without writing database rows.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        spot = _resolve_spot(options["spot"])
        fetched_at = timezone.now()
        try:
            observation = build_operational_observation(
                source=options["source"],
                provider_record_id=options["record_id"],
                source_url=options["source_url"],
                spatial_scope=f"spot:{spot.pk}",
                observed_at=options["observed_at"],
                fetched_at=fetched_at,
                valid_until=options["valid_until"],
                metric_assignments=options["metrics"],
                confidence=options["confidence"],
            )
        except (TypeError, ValueError) as exc:
            raise CommandError(str(exc)) from None

        if options["dry_run"]:
            self.stdout.write(
                self.style.SUCCESS(
                    "Operational observation validated (dry-run): "
                    f"spot={spot.pk} source={observation.provider} "
                    f"metrics={len(observation.observations.metrics)}"
                )
            )
            return

        result = persist_observation(spot=spot, observation=observation)
        self.stdout.write(
            self.style.SUCCESS(
                "Operational observation persisted: "
                f"spot={spot.pk} source={observation.provider} "
                f"metrics={len(observation.observations.metrics)} "
                f"snapshot={result.snapshot_id} created={result.snapshot_created}"
            )
        )


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        raise CommandError("timestamps must use ISO-8601") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CommandError("timestamps must include a timezone offset")
    return parsed


def _resolve_spot(selector: str) -> WaterSpot:
    text = selector.strip()
    if not text:
        raise CommandError("--spot cannot be blank")
    queryset = (
        WaterSpot.objects.filter(pk=int(text))
        if text.isdecimal()
        else WaterSpot.objects.filter(name__iexact=text)
    )
    matches = tuple(queryset[:2])
    if not matches:
        raise CommandError("WaterSpot was not found")
    if len(matches) > 1:
        raise CommandError("WaterSpot name is ambiguous; use its numeric id")
    return matches[0]
