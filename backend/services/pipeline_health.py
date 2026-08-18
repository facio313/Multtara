"""Credential-free freshness report for the background condition pipeline."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from apps.conditions.models import IngestionRun, PipelineHeartbeat
from services.provider_config import ProviderConfig


TASK_MAX_AGES = {
    "weather-nowcast": timedelta(hours=2),
    "marine": timedelta(hours=3),
    "weather-short-forecast": timedelta(hours=6),
    "marine-activity-forecast": timedelta(hours=12),
    "derive-suitability": timedelta(minutes=20),
    "water-index-general": timedelta(minutes=20),
    "water-index-family": timedelta(minutes=20),
    "daily-forecast": timedelta(hours=3),
    "condition-retention": timedelta(days=2),
    "route-matrix-drive": timedelta(hours=36),
    "route-matrix-walk": timedelta(hours=36),
    "route-matrix-bicycle": timedelta(hours=36),
}


def pipeline_health_report(
    *,
    at: datetime,
    config: ProviderConfig,
    heartbeat_max_age: timedelta = timedelta(minutes=10),
) -> tuple[dict[str, Any], bool]:
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("pipeline health time must be timezone-aware")
    expected = {
        "water-index-general",
        "water-index-family",
        "derive-suitability",
        "daily-forecast",
        "condition-retention",
    }
    if config.kma:
        expected.update(("weather-nowcast", "weather-short-forecast"))
    if config.khoa:
        expected.update(("marine", "marine-activity-forecast"))
    if config.routing_matrix:
        expected.update(
            (
                "route-matrix-drive",
                "route-matrix-walk",
                "route-matrix-bicycle",
            )
        )

    heartbeat = PipelineHeartbeat.objects.filter(key="condition-pipeline").first()
    heartbeat_fresh = bool(
        heartbeat
        and heartbeat.last_seen_at <= at
        and heartbeat.last_seen_at >= at - heartbeat_max_age
        and heartbeat.state
        in {
            PipelineHeartbeat.State.STARTING,
            PipelineHeartbeat.State.RUNNING,
        }
    )
    heartbeat_state = (
        "missing"
        if heartbeat is None
        else "future"
        if heartbeat.last_seen_at > at
        else "stale"
        if heartbeat.last_seen_at < at - heartbeat_max_age
        else heartbeat.state
    )

    task_rows: dict[str, dict[str, Any]] = {}
    healthy = heartbeat_fresh
    for task_name in sorted(expected):
        latest = IngestionRun.objects.filter(task_name=task_name).order_by(
            "-started_at", "-id"
        ).first()
        latest_success = (
            IngestionRun.objects.filter(
                task_name=task_name,
                status=IngestionRun.Status.SUCCEEDED,
            )
            .order_by("-finished_at", "-id")
            .first()
        )
        max_age = TASK_MAX_AGES[task_name]
        current = bool(
            latest_success
            and latest_success.finished_at
            and latest_success.finished_at <= at
            and latest_success.finished_at >= at - max_age
        )
        state = "never_succeeded"
        if latest and latest.status == IngestionRun.Status.RUNNING:
            state = "running"
        elif latest and latest.status == IngestionRun.Status.FAILED:
            state = "failed"
        elif latest_success and latest_success.finished_at and latest_success.finished_at > at:
            state = "future"
        elif current:
            state = "current"
        elif latest_success:
            state = "stale"
        task_rows[task_name] = {
            "state": state,
            "last_started_at": latest.started_at if latest else None,
            "last_finished_at": latest.finished_at if latest else None,
            "last_success_at": (
                latest_success.finished_at if latest_success else None
            ),
            "max_age_seconds": int(max_age.total_seconds()),
            "last_error_code": (
                latest.error_code
                if latest and latest.status == IngestionRun.Status.FAILED
                else ""
            ),
        }
        if not current:
            healthy = False
        if state == "failed":
            healthy = False

    return (
        {
            "status": "ok" if healthy else "degraded",
            "heartbeat": {
                "state": heartbeat_state,
                "last_seen_at": heartbeat.last_seen_at if heartbeat else None,
                "current_tasks": heartbeat.current_tasks if heartbeat else [],
                "max_age_seconds": int(heartbeat_max_age.total_seconds()),
            },
            "tasks": task_rows,
            "manual_integrations": {
                "tour_api": "configured" if config.tour_api else "not_configured",
                "water_quality": "configured" if config.moe else "not_configured",
                "operational_access": "operator_workflow",
                "warnings_and_lightning": "operator_or_future_adapter",
                "routing_matrix": (
                    "scheduled" if config.routing_matrix else "not_configured"
                ),
            },
        },
        healthy,
    )
