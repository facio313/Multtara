"""Synchronize KMA grid weather into auditable condition snapshots."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db.models import QuerySet
from django.utils import timezone

from apps.spots.models import WaterSpot
from services.ingestion.kma_adapter import KmaAdapterError
from services.ingestion.weather import (
    KmaMode,
    WeatherIngestionService,
    latest_available_issue,
)
from services.provider_config import ProviderConfig
from services.providers.base import ProviderError
from services.providers.kma import KmaClient


class Command(BaseCommand):
    help = (
        "Fetch KMA village weather and persist typed observations without "
        "inferring activity safety clearance."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Fetch and normalize without writing database rows.",
        )
        parser.add_argument(
            "--mode",
            choices=[mode.value for mode in KmaMode],
            default=KmaMode.NOWCAST.value,
            help="KMA product to collect (default: nowcast).",
        )
        parser.add_argument(
            "--spot",
            action="append",
            dest="spot_selectors",
            metavar="ID_OR_EXACT_NAME",
            help="Limit collection to a WaterSpot id or exact name; repeatable.",
        )
        parser.add_argument(
            "--issued-at",
            type=_parse_issued_at,
            metavar="ISO-8601",
            help="Explicit timezone-aware provider base time.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        provider_config = ProviderConfig.from_environment()
        if not provider_config.kma:
            raise CommandError("KMA provider credential is not configured")

        mode = KmaMode(options["mode"])
        spots = tuple(_resolve_spots(options.get("spot_selectors")))
        if not spots:
            raise CommandError("No WaterSpot rows are available for weather collection")
        issued_at = options.get("issued_at") or latest_available_issue(
            mode, timezone.now()
        )

        client = KmaClient(provider_config.kma)
        try:
            report = WeatherIngestionService(client).sync(
                mode=mode,
                issued_at=issued_at,
                spots=spots,
                dry_run=bool(options.get("dry_run")),
            )
        except ProviderError as exc:
            raise CommandError(str(exc)) from None
        except (KmaAdapterError, ValueError):
            raise CommandError("KMA data could not be normalized safely") from None
        except Exception:
            # Never echo arbitrary exception text: prepared URLs may contain a key.
            raise CommandError("Weather synchronization failed internally") from None
        finally:
            client.close()

        state = "dry-run" if report.dry_run else "persisted"
        self.stdout.write(
            self.style.SUCCESS(
                " ".join(
                    (
                        f"KMA weather sync complete ({state})",
                        f"mode={report.mode.value}",
                        f"grids={report.requested_grids}",
                        f"values={report.fetched_values}",
                        f"normalized={report.normalized_snapshots}",
                        f"persisted={report.persisted_snapshots}",
                    )
                )
            )
        )


def _parse_issued_at(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        raise CommandError("--issued-at must be a valid ISO-8601 datetime") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CommandError("--issued-at must include a timezone offset")
    return parsed


def _resolve_spots(selectors: list[str] | None) -> QuerySet[WaterSpot]:
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
