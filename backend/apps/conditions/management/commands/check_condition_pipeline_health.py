from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.conditions.models import PipelineHeartbeat


class Command(BaseCommand):
    help = "Fail unless the long-running condition collector heartbeat is current."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--max-age", type=_max_age, default=900, metavar="SECONDS")

    def handle(self, *args: Any, **options: Any) -> None:
        at = timezone.now()
        heartbeat = PipelineHeartbeat.objects.filter(key="condition-pipeline").first()
        if heartbeat is None:
            raise CommandError("Condition pipeline heartbeat is missing")
        if heartbeat.last_seen_at > at:
            raise CommandError("Condition pipeline heartbeat is in the future")
        if heartbeat.last_seen_at < at - timedelta(seconds=options["max_age"]):
            raise CommandError("Condition pipeline heartbeat is stale")
        if heartbeat.state == PipelineHeartbeat.State.STOPPED:
            raise CommandError("Condition pipeline is stopped")
        self.stdout.write(
            self.style.SUCCESS(
                f"Condition pipeline heartbeat is current: state={heartbeat.state}"
            )
        )


def _max_age(value: str) -> int:
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        raise CommandError("heartbeat max age must be integer seconds") from None
    if not 60 <= seconds <= 3_600:
        raise CommandError("heartbeat max age must be between 60 and 3600 seconds")
    return seconds
