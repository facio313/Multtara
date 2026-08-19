"""Run bounded provider collection and Water Index evaluation on a schedule."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
import time
from typing import Any

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from django.utils import timezone

from apps.conditions.models import IngestionRun, PipelineHeartbeat
from services.provider_config import ProviderConfig


@dataclass(frozen=True, slots=True)
class PipelineTask:
    name: str
    interval_seconds: int
    command: str
    arguments: tuple[str, ...] = ()
    enabled: bool = True
    depends_on: tuple[str, ...] = ()


class Command(BaseCommand):
    help = (
        "Continuously collect configured official observations and reevaluate "
        "Water Index results without extending stale evidence."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--weather-interval",
            type=_positive_interval,
            default=1800,
            metavar="SECONDS",
        )
        parser.add_argument(
            "--marine-interval",
            type=_positive_interval,
            default=3600,
            metavar="SECONDS",
        )
        parser.add_argument(
            "--evaluate-interval",
            type=_positive_interval,
            default=300,
            metavar="SECONDS",
        )
        parser.add_argument(
            "--forecast-weather-interval",
            type=_positive_interval,
            default=10_800,
            metavar="SECONDS",
        )
        parser.add_argument(
            "--forecast-marine-interval",
            type=_positive_interval,
            default=21_600,
            metavar="SECONDS",
        )
        parser.add_argument(
            "--forecast-evaluate-interval",
            type=_positive_interval,
            default=3_600,
            metavar="SECONDS",
        )
        parser.add_argument(
            "--derive-interval",
            type=_positive_interval,
            default=300,
            metavar="SECONDS",
        )
        parser.add_argument(
            "--retention-interval",
            type=_positive_interval,
            default=86_400,
            metavar="SECONDS",
        )
        parser.add_argument(
            "--route-matrix-interval",
            type=_positive_interval,
            default=86_400,
            metavar="SECONDS",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="Run each enabled task once and exit non-zero on task failure.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Pass --dry-run to collection and evaluation commands.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        config = ProviderConfig.from_environment()
        tasks = _pipeline_tasks(config=config, options=options)
        enabled = tuple(task for task in tasks if task.enabled)
        skipped = tuple(task.name for task in tasks if not task.enabled)
        if skipped:
            self.stdout.write(
                "Pipeline providers not configured; safely skipped: "
                + ", ".join(skipped)
            )
        if not enabled:
            raise CommandError("No condition pipeline tasks are enabled")

        if options["once"]:
            failures = sum(
                not self._execute(task, dry_run=options["dry_run"])
                for task in enabled
            )
            if failures:
                raise CommandError(
                    f"Condition pipeline completed with {failures} failed task(s)"
                )
            return

        next_run = {task.name: 0.0 for task in enabled}
        running: dict[str, Future[bool]] = {}
        last_results = {task.name: True for task in enabled}
        executor = ThreadPoolExecutor(
            max_workers=min(4, len(enabled)),
            thread_name_prefix="condition-pipeline",
        )
        self._heartbeat(state=PipelineHeartbeat.State.STARTING, current_tasks=[])
        self.stdout.write(
            self.style.SUCCESS(
                "Condition pipeline started: " + ", ".join(task.name for task in enabled)
            )
        )
        try:
            while True:
                now = time.monotonic()
                for task in enabled:
                    future = running.get(task.name)
                    if future is None or not future.done():
                        continue
                    try:
                        last_results[task.name] = future.result()
                    except Exception:
                        # _execute already contains task failures, but keep the
                        # scheduler fail-closed if a worker itself terminates.
                        last_results[task.name] = False
                    del running[task.name]
                    next_run[task.name] = now + task.interval_seconds

                for task in enabled:
                    if task.name in running or now < next_run[task.name]:
                        continue
                    if any(
                        dependency in running
                        or now >= next_run[dependency]
                        for dependency in task.depends_on
                        if dependency in next_run
                    ):
                        continue
                    running[task.name] = executor.submit(
                        self._execute_in_worker,
                        task,
                        dry_run=options["dry_run"],
                    )

                state = (
                    PipelineHeartbeat.State.DEGRADED
                    if not all(last_results.values())
                    else PipelineHeartbeat.State.RUNNING
                )
                self._heartbeat(state=state, current_tasks=sorted(running))

                pending_times = [
                    next_run[task.name]
                    for task in enabled
                    if task.name not in running
                ]
                delay = (
                    max(0.25, min(pending_times) - time.monotonic())
                    if pending_times
                    else 5.0
                )
                time.sleep(min(delay, 5.0))
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Condition pipeline stopped"))
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
            self._heartbeat(state=PipelineHeartbeat.State.STOPPED, current_tasks=[])

    def _execute_in_worker(self, task: PipelineTask, *, dry_run: bool) -> bool:
        close_old_connections()
        try:
            return self._execute(task, dry_run=dry_run)
        finally:
            close_old_connections()

    def _execute(self, task: PipelineTask, *, dry_run: bool) -> bool:
        arguments = list(task.arguments)
        if dry_run:
            arguments.append("--dry-run")
        run = IngestionRun.objects.create(
            task_name=task.name,
            status=IngestionRun.Status.RUNNING,
            details={
                "command": task.command,
                "dry_run": dry_run,
            },
        )
        try:
            call_command(task.command, *arguments, stdout=self.stdout, stderr=self.stderr)
        except Exception:
            # Provider exceptions may retain prepared credential-bearing URLs.
            # Never echo the exception or its repr from the long-running loop.
            run.status = IngestionRun.Status.FAILED
            run.finished_at = timezone.now()
            run.error_code = "COMMAND_FAILED"
            run.save(update_fields=("status", "finished_at", "error_code"))
            self.stderr.write(self.style.ERROR(f"Pipeline task failed safely: {task.name}"))
            return False
        else:
            run.status = IngestionRun.Status.SUCCEEDED
            run.finished_at = timezone.now()
            run.error_code = ""
            run.save(update_fields=("status", "finished_at", "error_code"))
            return True

    @staticmethod
    def _heartbeat(*, state: str, current_tasks: list[str]) -> None:
        PipelineHeartbeat.objects.update_or_create(
            key="condition-pipeline",
            defaults={
                "state": state,
                "current_tasks": current_tasks,
                "last_seen_at": timezone.now(),
            },
        )


def _pipeline_tasks(*, config: ProviderConfig, options: dict[str, Any]) -> tuple[PipelineTask, ...]:
    current_dependencies = tuple(
        name
        for name, configured in (
            ("weather-nowcast", config.kma),
            ("marine", config.khoa),
        )
        if configured
    )
    forecast_dependencies = tuple(
        name
        for name, configured in (
            ("weather-short-forecast", config.kma),
            ("marine-activity-forecast", config.khoa),
        )
        if configured
    )
    derivation_dependencies = (*current_dependencies, *forecast_dependencies)
    route_enabled = bool(config.routing_matrix)
    return (
        PipelineTask(
            name="weather-nowcast",
            interval_seconds=options["weather_interval"],
            command="sync_weather_conditions",
            arguments=("--mode", "nowcast"),
            enabled=bool(config.kma),
        ),
        PipelineTask(
            name="marine",
            interval_seconds=options["marine_interval"],
            command="sync_marine_conditions",
            enabled=bool(config.khoa),
        ),
        PipelineTask(
            name="weather-short-forecast",
            interval_seconds=options["forecast_weather_interval"],
            command="sync_weather_conditions",
            arguments=("--mode", "short"),
            enabled=bool(config.kma),
        ),
        PipelineTask(
            name="marine-activity-forecast",
            interval_seconds=options["forecast_marine_interval"],
            command="sync_forecast_evidence",
            enabled=bool(config.khoa),
        ),
        PipelineTask(
            name="derive-suitability",
            interval_seconds=options["derive_interval"],
            command="derive_suitability_metrics",
            depends_on=derivation_dependencies,
        ),
        PipelineTask(
            name="water-index-general",
            interval_seconds=options["evaluate_interval"],
            command="evaluate_water_conditions",
            arguments=("--profile", "general"),
            depends_on=(*current_dependencies, "derive-suitability"),
        ),
        PipelineTask(
            name="water-index-family",
            interval_seconds=options["evaluate_interval"],
            command="evaluate_water_conditions",
            arguments=("--profile", "family"),
            depends_on=(*current_dependencies, "derive-suitability"),
        ),
        PipelineTask(
            name="daily-forecast",
            interval_seconds=options["forecast_evaluate_interval"],
            command="evaluate_daily_forecasts",
            depends_on=(*forecast_dependencies, "derive-suitability"),
        ),
        PipelineTask(
            name="condition-retention",
            interval_seconds=options["retention_interval"],
            command="prune_condition_history",
        ),
        PipelineTask(
            name="route-matrix-drive",
            interval_seconds=options["route_matrix_interval"],
            command="refresh_route_matrix",
            arguments=("--transport", "drive", "--valid-hours", "48"),
            enabled=route_enabled,
            depends_on=(
                "water-index-general",
                "water-index-family",
                "daily-forecast",
                "condition-retention",
            ),
        ),
        PipelineTask(
            name="route-matrix-walk",
            interval_seconds=options["route_matrix_interval"],
            command="refresh_route_matrix",
            arguments=("--transport", "walk", "--valid-hours", "48"),
            enabled=route_enabled,
            depends_on=("route-matrix-drive",),
        ),
        PipelineTask(
            name="route-matrix-bicycle",
            interval_seconds=options["route_matrix_interval"],
            command="refresh_route_matrix",
            arguments=("--transport", "bicycle", "--valid-hours", "48"),
            enabled=route_enabled,
            depends_on=("route-matrix-walk",),
        ),
    )


def _positive_interval(value: str) -> int:
    try:
        interval = int(value)
    except (TypeError, ValueError):
        raise CommandError("pipeline intervals must be integer seconds") from None
    if not 60 <= interval <= 86_400:
        raise CommandError("pipeline intervals must be between 60 and 86400 seconds")
    return interval
