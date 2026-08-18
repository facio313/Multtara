"""Fuse current observations and evaluate versioned Water Index results."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any, Iterable

from django.core.management.base import BaseCommand, CommandError
from django.db.models import QuerySet
from django.utils import timezone

from apps.spots.models import WaterSpot
from services.ingestion.fusion import activity_supported_for_spot, evaluate_fused_spot
from services.water_index import (
    Activity,
    CONCRETE_SURF_SKILL_LEVELS,
    SURF_SKILL_LEVEL_UNSPECIFIED,
)


class Command(BaseCommand):
    help = (
        "Fuse current non-demo provider observations and persist fail-closed "
        "Water Index evaluations."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Evaluate without writing fusion snapshots or scores.",
        )
        parser.add_argument(
            "--spot",
            action="append",
            dest="spot_selectors",
            metavar="ID_OR_EXACT_NAME",
            help="Limit evaluation to a WaterSpot id or exact name; repeatable.",
        )
        parser.add_argument(
            "--activity",
            action="append",
            choices=[activity.value for activity in Activity],
            help="Evaluate a specific activity; repeatable (default: type-based).",
        )
        parser.add_argument(
            "--profile",
            choices=("general", "family", "beginner"),
            default="general",
            help="Participant safety profile (default: general).",
        )
        parser.add_argument(
            "--participant-skill-level",
            action="append",
            choices=(
                SURF_SKILL_LEVEL_UNSPECIFIED,
                *CONCRETE_SURF_SKILL_LEVELS,
            ),
            help=(
                "Surf participant identity; repeatable. The default evaluates "
                "unspecified plus every supported explicit skill."
            ),
        )
        parser.add_argument(
            "--at",
            type=_parse_at,
            metavar="ISO-8601",
            help="Timezone-aware evaluation time (default: current minute).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        spots = tuple(_resolve_spots(options.get("spot_selectors")))
        if not spots:
            raise CommandError("No WaterSpot rows are available for evaluation")
        fetched_at = timezone.now()
        at = options.get("at") or fetched_at.replace(second=0, microsecond=0)
        explicit = tuple(Activity(value) for value in (options.get("activity") or ()))
        dry_run = bool(options.get("dry_run"))
        profile = options["profile"]
        surf_skill_levels = tuple(
            options.get("participant_skill_level")
            or (
                SURF_SKILL_LEVEL_UNSPECIFIED,
                *CONCRETE_SURF_SKILL_LEVELS,
            )
        )
        decisions: Counter[str] = Counter()
        persisted = 0

        try:
            for spot in spots:
                activities = explicit or activities_for_spot(spot)
                for activity in activities:
                    if not activity_supported_for_spot(spot, activity):
                        continue
                    # The family profile adds swimming-only safety gates.
                    # Persisting duplicate family identities for other
                    # activities makes request/profile provenance ambiguous.
                    if profile == "family" and activity is not Activity.SWIM:
                        continue
                    skill_levels = (
                        surf_skill_levels
                        if activity is Activity.SURF
                        else (SURF_SKILL_LEVEL_UNSPECIFIED,)
                    )
                    for skill_level in skill_levels:
                        outcome = evaluate_fused_spot(
                            spot=spot,
                            activity=activity,
                            at=at,
                            fetched_at=fetched_at,
                            participant_profile=profile,
                            participant_skill_level=skill_level,
                            dry_run=dry_run,
                        )
                        decisions[outcome.result.safety_status.value] += 1
                        persisted += int(outcome.persistence is not None)
        except (TypeError, ValueError):
            raise CommandError("Stored observations could not be fused safely") from None
        except Exception:
            raise CommandError("Water Index evaluation failed internally") from None

        mode = "dry-run" if dry_run else "persisted"
        summary = " ".join(
            f"{status}={decisions.get(status, 0)}"
            for status in ("clear", "caution", "stop", "unknown")
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Water Index evaluation complete ({mode}): "
                f"spots={len(spots)} evaluations={sum(decisions.values())} "
                f"persisted={persisted} {summary}"
            )
        )


def activities_for_spot(spot: Any) -> tuple[Activity, ...]:
    spot_type = str(getattr(spot, "type", "")).strip().lower()
    if spot_type in {"beach", "sea", "marine_beach"}:
        return (Activity.SWIM, Activity.SURF, Activity.RELAX)
    if spot_type in {"river"}:
        return (Activity.SWIM, Activity.RAFTING, Activity.RELAX)
    if spot_type in {"valley", "lake", "riverside", "reservoir"}:
        return (Activity.SWIM, Activity.RELAX)
    if spot_type in {"mudflat", "tidal_flat"}:
        return (Activity.MUDFLAT, Activity.RELAX)
    if spot_type in {"hotspring", "pool", "waterpark", "licensed_facility"}:
        return (Activity.ONSEN, Activity.RELAX)
    return (Activity.RELAX,)


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
