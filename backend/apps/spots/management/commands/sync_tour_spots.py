"""Enrich explicitly curated WaterSpot rows from TourAPI detailCommon2."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, QuerySet

from apps.spots.models import WaterSpot
from services.catalog import CatalogEnrichmentError, TourSpotEnrichmentService
from services.provider_config import ProviderConfig
from services.providers.base import ProviderError
from services.providers.tour_api import TourApiClient


class Command(BaseCommand):
    help = (
        "Enrich existing WaterSpot rows that have a curated TourAPI content id; "
        "never discovers or creates arbitrary tourism POIs."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--spot",
            action="append",
            dest="spot_selectors",
            metavar="ID_OR_EXACT_NAME",
            help="Limit to a WaterSpot primary key or exact name; repeatable.",
        )
        parser.add_argument(
            "--language",
            choices=("ko", "en", "ja", "zh-hans", "zh-hant"),
            default="ko",
            help="TourAPI Service2 language gateway (default: ko).",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Explicitly allow replacement of existing non-empty fields.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Fetch and validate details but do not update WaterSpot rows.",
        )
        parser.add_argument(
            "--audit-identifiers",
            action="store_true",
            help=(
                "Audit duplicate nonblank TourAPI/KHOA identifiers without "
                "reading credentials, calling providers, or changing rows."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        client: TourApiClient | None = None
        try:
            if options.get("audit_identifiers"):
                duplicate_counts = _duplicate_identifier_group_counts()
                if any(duplicate_counts.values()):
                    summary = ", ".join(
                        f"{field_name} groups={count}"
                        for field_name, count in duplicate_counts.items()
                        if count
                    )
                    raise CommandError(
                        "Duplicate nonblank WaterSpot curated identifiers were "
                        f"found ({summary}). Resolve them manually before applying "
                        "spots.0003; no rows were changed."
                    )
                self.stdout.write(
                    self.style.SUCCESS(
                        "WaterSpot curated identifier audit passed: no duplicate "
                        "nonblank tourapi_id or khoa_beach_code values"
                    )
                )
                return

            provider_config = ProviderConfig.from_environment()
            if not provider_config.tour_api:
                raise CommandError("TourAPI provider credential is not configured")

            spots = tuple(_resolve_spots(options.get("spot_selectors")))
            if not spots:
                raise CommandError(
                    "No curated WaterSpot rows are available for TourAPI sync"
                )

            client = TourApiClient(
                provider_config.tour_api,
                language=options["language"],
            )
            report = TourSpotEnrichmentService(client).sync(
                spots,
                overwrite=bool(options.get("overwrite")),
                dry_run=bool(options.get("dry_run")),
            )
        except ProviderError as exc:
            # Provider exceptions are sanitized at the shared HTTP boundary.
            raise CommandError(str(exc)) from None
        except CatalogEnrichmentError as exc:
            raise CommandError(str(exc)) from None
        except CommandError:
            raise
        except Exception:
            # Never echo arbitrary exception text: it may retain a prepared URL.
            raise CommandError(
                "TourAPI WaterSpot synchronization failed internally"
            ) from None
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    # Closing must not replace a sanitized primary result/error.
                    pass

        for result in report.results:
            changed = ",".join(result.changed_fields) if result.changed_fields else "none"
            self.stdout.write(
                f"spot_id={result.spot_id} status={result.status} "
                f"changed={changed} source=TourAPI"
            )
        mode = "dry-run" if report.dry_run else "persisted"
        self.stdout.write(
            self.style.SUCCESS(
                f"TourAPI WaterSpot sync complete ({mode}): "
                f"selected={len(report.results)}, "
                f"fetched={report.fetched_details}, "
                f"changed={report.changed_spots}, "
                f"skipped={report.skipped_spots}"
            )
        )


def _resolve_spots(selectors: list[str] | None) -> QuerySet[WaterSpot]:
    if not selectors:
        return WaterSpot.objects.exclude(tourapi_id="").order_by("pk")

    selected_ids: set[int] = set()
    for selector in selectors:
        text = selector.strip()
        if not text:
            raise CommandError("--spot cannot be blank")
        if text.isdecimal():
            matches = WaterSpot.objects.filter(pk=int(text))
        else:
            matches = WaterSpot.objects.filter(name__iexact=text)
        ids = tuple(matches.values_list("pk", flat=True))
        if not ids:
            raise CommandError("WaterSpot not found for one --spot selector")
        selected_ids.update(ids)
    return WaterSpot.objects.filter(pk__in=selected_ids).order_by("pk")


def _duplicate_identifier_group_counts() -> dict[str, int]:
    """Count duplicate groups without exposing curated provider identifiers."""

    counts: dict[str, int] = {}
    for field_name in ("tourapi_id", "khoa_beach_code"):
        counts[field_name] = (
            WaterSpot.objects.exclude(**{field_name: ""})
            .values(field_name)
            .annotate(row_count=Count("pk"))
            .filter(row_count__gt=1)
            .count()
        )
    return counts
