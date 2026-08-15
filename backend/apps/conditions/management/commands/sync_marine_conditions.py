"""Synchronize KHOA marine activity observations into condition snapshots."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db.models import QuerySet
from django.utils import timezone

from apps.spots.models import WaterSpot
from services.ingestion.khoa_adapter import KhoaAdapterError
from services.ingestion.marine import MarineIngestionService, SUPPORTED_ACTIVITIES
from services.provider_config import ProviderConfig
from services.providers.base import ProviderError
from services.providers.khoa import KhoaClient
from services.water_index import Activity


class Command(BaseCommand):
    help = (
        "Fetch KHOA beach/surf/mudflat activity data, evaluate it with the "
        "safety-first Water Index, and persist auditable snapshots."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Fetch, match, and evaluate without writing database rows.",
        )
        parser.add_argument(
            "--spot",
            action="append",
            dest="spot_selectors",
            metavar="ID_OR_EXACT_NAME",
            help="Limit matching to a WaterSpot primary key or exact name; repeatable.",
        )
        parser.add_argument(
            "--activity",
            action="append",
            choices=[activity.value for activity in SUPPORTED_ACTIVITIES],
            help="Limit collection to swim, surf, or mudflat; repeatable (default: all).",
        )
        parser.add_argument(
            "--date",
            type=_parse_request_date,
            dest="request_date",
            metavar="YYYY-MM-DD",
            help="Provider forecast date (default: local date in Asia/Seoul).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        provider_config = ProviderConfig.from_environment()
        if not provider_config.khoa:
            raise CommandError("KHOA provider credential is not configured")

        activities = tuple(
            Activity(value)
            for value in (
                options.get("activity")
                or [activity.value for activity in SUPPORTED_ACTIVITIES]
            )
        )
        request_date = options.get("request_date") or timezone.localdate()
        spots = tuple(_resolve_spots(options.get("spot_selectors")))
        if not spots:
            raise CommandError("No WaterSpot rows are available for marine matching")

        client = KhoaClient(provider_config.khoa)
        try:
            report = MarineIngestionService(client).sync(
                activities=activities,
                request_date=request_date,
                spots=spots,
                dry_run=bool(options.get("dry_run")),
            )
        except ProviderError as exc:
            # Provider errors are deliberately sanitized at the HTTP boundary.
            raise CommandError(str(exc)) from None
        except (KhoaAdapterError, ValueError):
            raise CommandError("KHOA data could not be normalized safely") from None
        except CommandError:
            raise
        except Exception:
            # Never echo arbitrary exception text: prepared URLs may contain a key.
            raise CommandError("Marine condition synchronization failed internally") from None
        finally:
            client.close()

        mode = "dry-run" if report.dry_run else "persisted"
        for item in report.activities:
            self.stdout.write(
                " ".join(
                    (
                        f"activity={item.activity.value}",
                        f"fetched={item.fetched_records}",
                        f"matched={item.matched_records}",
                        f"persisted={item.persisted_records}",
                        f"skipped={item.skipped_records}",
                        f"unknown={item.unknown_results}",
                    )
                )
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"KHOA marine sync complete ({mode}): "
                f"fetched={report.fetched_records}, "
                f"matched={report.matched_records}, "
                f"persisted={report.persisted_records}"
            )
        )


def _parse_request_date(value: str) -> date:
    text = value.strip()
    for format_string in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, format_string).date()
        except ValueError:
            continue
    raise CommandError("--date must use YYYY-MM-DD or YYYYMMDD")


def _resolve_spots(selectors: list[str] | None) -> QuerySet[WaterSpot]:
    if not selectors:
        return WaterSpot.objects.all().order_by("pk")

    selected_ids: list[int] = []
    for selector in selectors:
        text = selector.strip()
        if not text:
            raise CommandError("--spot cannot be blank")
        if text.isdecimal():
            matches = WaterSpot.objects.filter(pk=int(text))
        else:
            matches = WaterSpot.objects.filter(name__iexact=text)
        ids = list(matches.values_list("pk", flat=True))
        if not ids:
            raise CommandError(f"WaterSpot not found for --spot selector: {text}")
        selected_ids.extend(ids)
    return WaterSpot.objects.filter(pk__in=selected_ids).order_by("pk")
