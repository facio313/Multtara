"""Build one to seven exact-date Water Index forecast projections."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db.models import QuerySet
from django.utils import timezone

from apps.spots.models import WaterSpot
from services.daily_forecasts import MAX_DAILY_FORECAST_DAYS, evaluate_daily_forecasts
from services.water_index import Activity, SURF_PARTICIPANT_SKILL_LEVELS


class Command(BaseCommand):
    help = (
        "Fuse exact provider validity windows at 12:00 Asia/Seoul and persist "
        "fail-closed daily forecast projections."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--days",
            type=_parse_days,
            default=MAX_DAILY_FORECAST_DAYS,
            metavar="1..7",
        )
        parser.add_argument(
            "--start-date",
            type=_parse_date,
            metavar="YYYY-MM-DD",
            help="First forecast date (default: current Asia/Seoul date).",
        )
        parser.add_argument(
            "--spot",
            action="append",
            dest="spot_selectors",
            metavar="ID_OR_EXACT_NAME",
        )
        parser.add_argument(
            "--activity",
            action="append",
            choices=[item.value for item in Activity],
        )
        parser.add_argument(
            "--profile",
            action="append",
            choices=("general", "family"),
        )
        parser.add_argument(
            "--participant-skill-level",
            action="append",
            choices=sorted(SURF_PARTICIPANT_SKILL_LEVELS),
            help=(
                "Surf identity to evaluate (repeatable). The default persists "
                "unspecified, beginner, intermediate, and advanced."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        spots = tuple(_resolve_spots(options.get("spot_selectors")))
        if not spots:
            raise CommandError("No WaterSpot rows are available for forecast evaluation")
        activities = tuple(
            Activity(value)
            for value in (
                options.get("activity") or [item.value for item in Activity]
            )
        )
        profiles = tuple(options.get("profile") or ("general", "family"))
        skill_levels = tuple(
            options.get("participant_skill_level")
            or ("unspecified", "beginner", "intermediate", "advanced")
        )
        start_date = options.get("start_date") or timezone.localdate()
        try:
            report = evaluate_daily_forecasts(
                spots=spots,
                activities=activities,
                start_date=start_date,
                days=options["days"],
                profiles=profiles,
                skill_levels=skill_levels,
                dry_run=bool(options.get("dry_run")),
            )
        except (TypeError, ValueError):
            raise CommandError("Daily forecast evaluation input is invalid") from None
        mode = "dry-run" if report.dry_run else "persisted"
        self.stdout.write(
            self.style.SUCCESS(
                f"Daily forecast evaluation complete ({mode}): "
                f"dates={report.requested_dates}, "
                f"evaluated={report.evaluated_projections}, "
                f"created={report.created_projections}, "
                f"updated={report.updated_projections}, "
                f"unavailable={report.unavailable_projections}"
            )
        )


def _parse_days(value: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise CommandError("--days must be an integer between 1 and 7") from None
    if not 1 <= parsed <= MAX_DAILY_FORECAST_DAYS:
        raise CommandError("--days must be between 1 and 7")
    return parsed


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError:
        raise CommandError("--start-date must use YYYY-MM-DD") from None


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
