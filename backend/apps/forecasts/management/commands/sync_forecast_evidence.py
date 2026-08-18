"""Synchronize provider-advertised KHOA activity forecast evidence."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db.models import QuerySet

from apps.spots.models import WaterSpot
from services.daily_forecasts import (
    KHOA_FORECAST_ACTIVITIES,
    KhoaForecastEvidenceIngestionService,
)
from services.provider_config import ProviderConfig
from services.providers.khoa import KhoaClient
from services.water_index import Activity


class Command(BaseCommand):
    help = (
        "Fetch the KHOA beach/surf/mudflat horizon once per product and persist "
        "typed forecast metrics without fabricating unavailable dates."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Fetch and normalize without writing database rows.",
        )
        parser.add_argument(
            "--spot",
            action="append",
            dest="spot_selectors",
            metavar="ID_OR_EXACT_NAME",
            help="Limit matching to a WaterSpot id or exact name; repeatable.",
        )
        parser.add_argument(
            "--activity",
            action="append",
            choices=[item.value for item in KHOA_FORECAST_ACTIVITIES],
            help="Limit collection to swim, surf, or mudflat; repeatable.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        config = ProviderConfig.from_environment()
        if not config.khoa:
            raise CommandError("KHOA provider credential is not configured")
        activities = tuple(
            Activity(value)
            for value in (
                options.get("activity")
                or [item.value for item in KHOA_FORECAST_ACTIVITIES]
            )
        )
        spots = tuple(_resolve_spots(options.get("spot_selectors")))
        if not spots:
            raise CommandError("No WaterSpot rows are available for forecast matching")

        client = KhoaClient(config.khoa)
        try:
            report = KhoaForecastEvidenceIngestionService(client).sync(
                activities=activities,
                spots=spots,
                dry_run=bool(options.get("dry_run")),
            )
        except (TypeError, ValueError):
            raise CommandError("KHOA forecast data could not be normalized safely") from None
        except Exception:
            # Arbitrary provider exceptions can retain credential-bearing URLs.
            raise CommandError("Forecast evidence synchronization failed internally") from None
        finally:
            client.close()

        mode = "dry-run" if report.dry_run else "persisted"
        for item in report.activities:
            state = "provider-failed" if item.provider_failed else "ok"
            self.stdout.write(
                " ".join(
                    (
                        f"activity={item.activity.value}",
                        f"state={state}",
                        f"fetched={item.fetched_records}",
                        f"matched={item.matched_records}",
                        f"persisted={item.persisted_records}",
                        f"skipped={item.skipped_records}",
                    )
                )
            )
        if report.failed_activities:
            raise CommandError(
                "KHOA forecast evidence sync completed with "
                f"{len(report.failed_activities)} failed product(s)"
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"KHOA forecast evidence sync complete ({mode}): "
                f"fetched={report.fetched_records}, "
                f"persisted={report.persisted_records}"
            )
        )


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
