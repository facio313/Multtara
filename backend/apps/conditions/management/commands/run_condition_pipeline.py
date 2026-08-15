"""Run bounded provider collection and Water Index evaluation on a schedule."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Callable

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from services.provider_config import ProviderConfig


@dataclass(frozen=True, slots=True)
class PipelineTask:
    name: str
    interval_seconds: int
    command: str
    arguments: tuple[str, ...] = ()
    enabled: bool = True


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
            failures = sum(not self._execute(task, dry_run=options["dry_run"]) for task in enabled)
            if failures:
                raise CommandError(
                    f"Condition pipeline completed with {failures} failed task(s)"
                )
            return

        next_run = {task.name: 0.0 for task in enabled}
        self.stdout.write(
            self.style.SUCCESS(
                "Condition pipeline started: " + ", ".join(task.name for task in enabled)
            )
        )
        try:
            while True:
                now = time.monotonic()
                for task in enabled:
                    if now < next_run[task.name]:
                        continue
                    self._execute(task, dry_run=options["dry_run"])
                    # Failure never preserves or extends old evidence. Schedule
                    # a bounded retry at the normal task cadence.
                    next_run[task.name] = time.monotonic() + task.interval_seconds
                delay = max(1.0, min(next_run.values()) - time.monotonic())
                time.sleep(min(delay, 60.0))
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Condition pipeline stopped"))

    def _execute(self, task: PipelineTask, *, dry_run: bool) -> bool:
        arguments = list(task.arguments)
        if dry_run:
            arguments.append("--dry-run")
        try:
            call_command(task.command, *arguments, stdout=self.stdout, stderr=self.stderr)
        except Exception:
            # Provider exceptions may retain prepared credential-bearing URLs.
            # Never echo the exception or its repr from the long-running loop.
            self.stderr.write(self.style.ERROR(f"Pipeline task failed safely: {task.name}"))
            return False
        return True


def _pipeline_tasks(*, config: ProviderConfig, options: dict[str, Any]) -> tuple[PipelineTask, ...]:
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
            name="water-index-general",
            interval_seconds=options["evaluate_interval"],
            command="evaluate_water_conditions",
            arguments=("--profile", "general"),
        ),
        PipelineTask(
            name="water-index-family",
            interval_seconds=options["evaluate_interval"],
            command="evaluate_water_conditions",
            arguments=("--profile", "family"),
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
