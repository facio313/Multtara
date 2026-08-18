"""Bound historical condition storage while preserving latest and safety audit rows."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F, OuterRef, Q, Subquery
from django.utils import timezone

from apps.conditions.models import (
    ConditionScore,
    CrowdLevel,
    IngestionRun,
    ObservationSnapshot,
    WaterCondition,
)
from apps.forecasts.models import DailyForecast, WaterForecast
from apps.trips.models import Itinerary, RouteMatrixSnapshot
from services.ingestion.fusion import DERIVED_PROVIDER, FUSION_PROVIDER


class Command(BaseCommand):
    help = (
        "Prune bounded historical condition rows while retaining every latest "
        "group and a longer STOP/CAUTION audit window."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--score-days", type=_days, default=30)
        parser.add_argument("--safety-days", type=_days, default=365)
        parser.add_argument("--fusion-days", type=_days, default=30)
        parser.add_argument("--derived-days", type=_days, default=90)
        parser.add_argument("--source-days", type=_days, default=90)
        parser.add_argument("--legacy-days", type=_days, default=30)
        parser.add_argument("--forecast-days", type=_days, default=90)
        parser.add_argument("--route-days", type=_days, default=30)
        parser.add_argument("--run-days", type=_days, default=30)
        parser.add_argument("--failed-run-days", type=_days, default=90)
        parser.add_argument(
            "--batch-size",
            type=_batch_size,
            default=1_000,
        )
        parser.add_argument("--dry-run", action="store_true")

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        now = timezone.now()
        score_cutoff = now - timedelta(days=options["score_days"])
        safety_cutoff = now - timedelta(days=options["safety_days"])
        fusion_cutoff = now - timedelta(days=options["fusion_days"])
        derived_cutoff = now - timedelta(days=options["derived_days"])
        source_cutoff = now - timedelta(days=options["source_days"])
        legacy_cutoff = now - timedelta(days=options["legacy_days"])
        forecast_cutoff = now - timedelta(days=options["forecast_days"])
        route_cutoff = now - timedelta(days=options["route_days"])
        run_cutoff = now - timedelta(days=options["run_days"])
        failed_run_cutoff = now - timedelta(days=options["failed_run_days"])
        batch_size = options["batch_size"]
        protected_score_ids, protected_water_snapshot_ids = (
            _protected_itinerary_water_evidence_ids()
        )

        latest_score = (
            ConditionScore.objects.filter(
                spot_id=OuterRef("spot_id"),
                activity=OuterRef("activity"),
                participant_profile=OuterRef("participant_profile"),
                participant_skill_level=OuterRef("participant_skill_level"),
                methodology_version=OuterRef("methodology_version"),
            )
            .order_by("-evaluated_at", "-id")
            .values("id")[:1]
        )
        score_candidates = (
            ConditionScore.objects.annotate(latest_group_id=Subquery(latest_score))
            .exclude(pk=F("latest_group_id"))
            .exclude(pk__in=protected_score_ids)
            .filter(
                Q(
                    safety_status__in=("stop", "caution"),
                    computed_at__lt=safety_cutoff,
                )
                | (
                    ~Q(safety_status__in=("stop", "caution"))
                    & Q(computed_at__lt=score_cutoff)
                )
            )
            .order_by("pk")
        )

        latest_snapshot = (
            ObservationSnapshot.objects.filter(
                spot_id=OuterRef("spot_id"),
                provider=OuterRef("provider"),
                ingestion_version=OuterRef("ingestion_version"),
            )
            .order_by("-fetched_at", "-id")
            .values("id")[:1]
        )

        counts = {
            "scores": _delete_or_count(
                score_candidates,
                dry_run=options["dry_run"],
                batch_size=batch_size,
            )
        }

        daily_forecast_candidates = DailyForecast.objects.filter(
            Q(
                safety_status__in=("stop", "caution"),
                computed_at__lt=safety_cutoff,
            )
            | (
                ~Q(safety_status__in=("stop", "caution"))
                & Q(computed_at__lt=forecast_cutoff)
            )
        ).order_by("pk")
        counts["daily_forecasts"] = _delete_or_count(
            daily_forecast_candidates,
            dry_run=options["dry_run"],
            batch_size=batch_size,
        )

        # Scores and derived lineage are removed before source snapshots so
        # RESTRICT lineage edges continue protecting every retained derivation.
        fusion_candidates = (
            ObservationSnapshot.objects.filter(
                provider=FUSION_PROVIDER,
                created_at__lt=fusion_cutoff,
            )
            .annotate(latest_group_id=Subquery(latest_snapshot))
            .exclude(pk=F("latest_group_id"))
            .exclude(pk__in=protected_water_snapshot_ids)
            .filter(condition_scores__isnull=True)
            .distinct()
            .order_by("pk")
        )
        counts["fusion_snapshots"] = _delete_or_count(
            fusion_candidates,
            dry_run=options["dry_run"],
            batch_size=batch_size,
        )

        # A fused lineage RESTRICT edge protects every derived input still
        # needed for an audit. Once an unreferenced old derivation is removed,
        # its own lineage edges cascade and ordinary source retention can
        # consider the original evidence below.
        derived_candidates = (
            ObservationSnapshot.objects.filter(
                provider=DERIVED_PROVIDER,
                created_at__lt=derived_cutoff,
            )
            .annotate(latest_group_id=Subquery(latest_snapshot))
            .exclude(pk=F("latest_group_id"))
            .filter(condition_scores__isnull=True)
            .exclude(metrics__lineage_derivations__isnull=False)
            .distinct()
            .order_by("pk")
        )
        counts["derived_snapshots"] = _delete_or_count(
            derived_candidates,
            dry_run=options["dry_run"],
            batch_size=batch_size,
        )

        source_candidates = (
            ObservationSnapshot.objects.exclude(
                provider__in=(FUSION_PROVIDER, DERIVED_PROVIDER)
            )
            .filter(created_at__lt=source_cutoff)
            .annotate(latest_group_id=Subquery(latest_snapshot))
            .exclude(pk=F("latest_group_id"))
            .filter(condition_scores__isnull=True)
            .exclude(metrics__lineage_derivations__isnull=False)
            .distinct()
            .order_by("pk")
        )
        counts["source_snapshots"] = _delete_or_count(
            source_candidates,
            dry_run=options["dry_run"],
            batch_size=batch_size,
        )

        latest_legacy = (
            WaterCondition.objects.filter(spot_id=OuterRef("spot_id"))
            .order_by("-fetched_at", "-id")
            .values("id")[:1]
        )
        legacy_candidates = (
            WaterCondition.objects.filter(fetched_at__lt=legacy_cutoff)
            .annotate(latest_group_id=Subquery(latest_legacy))
            .exclude(pk=F("latest_group_id"))
            .order_by("pk")
        )
        counts["legacy_conditions"] = _delete_or_count(
            legacy_candidates,
            dry_run=options["dry_run"],
            batch_size=batch_size,
        )

        # CrowdLevel is mutable/latest-state data. Remove all but the newest
        # old row per spot if historical duplicates exist.
        latest_crowd = (
            CrowdLevel.objects.filter(spot_id=OuterRef("spot_id"))
            .order_by("-updated_at", "-id")
            .values("id")[:1]
        )
        crowd_candidates = (
            CrowdLevel.objects.filter(updated_at__lt=legacy_cutoff)
            .annotate(latest_group_id=Subquery(latest_crowd))
            .exclude(pk=F("latest_group_id"))
            .order_by("pk")
        )
        counts["crowd_levels"] = _delete_or_count(
            crowd_candidates,
            dry_run=options["dry_run"],
            batch_size=batch_size,
        )

        legacy_forecasts = WaterForecast.objects.filter(
            computed_at__lt=legacy_cutoff
        ).order_by("pk")
        counts["legacy_forecasts"] = _delete_or_count(
            legacy_forecasts,
            dry_run=options["dry_run"],
            batch_size=batch_size,
        )

        protected_route_ids = _protected_route_snapshot_ids()
        latest_route = (
            RouteMatrixSnapshot.objects.filter(
                provider=OuterRef("provider"),
                transport=OuterRef("transport"),
            )
            .order_by("-observed_at", "-id")
            .values("id")[:1]
        )
        route_candidates = (
            RouteMatrixSnapshot.objects.filter(valid_until__lt=route_cutoff)
            .annotate(latest_group_id=Subquery(latest_route))
            .exclude(pk=F("latest_group_id"))
            .exclude(pk__in=protected_route_ids)
            .order_by("pk")
        )
        counts["route_snapshots"] = _delete_or_count(
            route_candidates,
            dry_run=options["dry_run"],
            batch_size=batch_size,
        )

        latest_run = (
            IngestionRun.objects.filter(task_name=OuterRef("task_name"))
            .order_by("-started_at", "-id")
            .values("id")[:1]
        )
        run_candidates = (
            IngestionRun.objects.exclude(status=IngestionRun.Status.RUNNING)
            .annotate(latest_group_id=Subquery(latest_run))
            .exclude(pk=F("latest_group_id"))
            .filter(
                Q(
                    status=IngestionRun.Status.FAILED,
                    finished_at__lt=failed_run_cutoff,
                )
                | (
                    ~Q(status=IngestionRun.Status.FAILED)
                    & Q(finished_at__lt=run_cutoff)
                )
            )
            .order_by("pk")
        )
        counts["ingestion_runs"] = _delete_or_count(
            run_candidates,
            dry_run=options["dry_run"],
            batch_size=batch_size,
        )

        if options["dry_run"]:
            transaction.set_rollback(True)
        mode = "dry-run" if options["dry_run"] else "deleted"
        summary = " ".join(f"{name}={count}" for name, count in counts.items())
        self.stdout.write(
            self.style.SUCCESS(f"Condition retention complete ({mode}): {summary}")
        )


def _delete_or_count(queryset, *, dry_run: bool, batch_size: int) -> int:
    if dry_run:
        return queryset.count()
    model = queryset.model
    total = 0
    while True:
        ids = list(queryset.values_list("pk", flat=True)[:batch_size])
        if not ids:
            return total
        model.objects.filter(pk__in=ids).delete()
        total += len(ids)


def _protected_route_snapshot_ids() -> tuple[int, ...]:
    protected: set[int] = set()
    rows = Itinerary.objects.exclude(route_snapshot_ids=[]).values_list(
        "route_snapshot_ids", flat=True
    )
    for value in rows.iterator(chunk_size=500):
        if not isinstance(value, list):
            continue
        protected.update(
            item
            for item in value
            if isinstance(item, int) and not isinstance(item, bool) and item > 0
        )
    return tuple(sorted(protected))


def _protected_itinerary_water_evidence_ids() -> tuple[tuple[int, ...], tuple[int, ...]]:
    score_ids: set[int] = set()
    snapshot_ids: set[int] = set()
    rows = Itinerary.objects.exclude(water_evidence=[]).values_list(
        "water_evidence", flat=True
    )
    for value in rows.iterator(chunk_size=500):
        if not isinstance(value, list):
            continue
        for item in value:
            if not isinstance(item, dict):
                continue
            score_id = item.get("condition_score_id")
            snapshot_id = item.get("snapshot_id")
            if (
                isinstance(score_id, int)
                and not isinstance(score_id, bool)
                and score_id > 0
            ):
                score_ids.add(score_id)
            if (
                isinstance(snapshot_id, int)
                and not isinstance(snapshot_id, bool)
                and snapshot_id > 0
            ):
                snapshot_ids.add(snapshot_id)
    return tuple(sorted(score_ids)), tuple(sorted(snapshot_ids))


def _days(value: str) -> int:
    try:
        days = int(value)
    except (TypeError, ValueError):
        raise CommandError("retention days must be integers") from None
    if not 1 <= days <= 3_650:
        raise CommandError("retention days must be between 1 and 3650")
    return days


def _batch_size(value: str) -> int:
    try:
        size = int(value)
    except (TypeError, ValueError):
        raise CommandError("batch size must be an integer") from None
    if not 100 <= size <= 10_000:
        raise CommandError("batch size must be between 100 and 10000")
    return size
