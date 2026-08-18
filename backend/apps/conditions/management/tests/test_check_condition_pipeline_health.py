from __future__ import annotations

from datetime import timedelta
from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone

from apps.conditions.models import PipelineHeartbeat


class CheckConditionPipelineHealthCommandTests(TestCase):
    def test_current_running_heartbeat_passes(self):
        PipelineHeartbeat.objects.create(
            state=PipelineHeartbeat.State.RUNNING,
            current_tasks=["water-index-general"],
            last_seen_at=timezone.now(),
        )
        output = StringIO()

        call_command("check_condition_pipeline_health", stdout=output)

        self.assertIn("current", output.getvalue())
        self.assertNotIn("water-index-general", output.getvalue())

    def test_missing_stale_future_and_stopped_heartbeat_fail_closed(self):
        with self.assertRaisesRegex(CommandError, "missing"):
            call_command("check_condition_pipeline_health")

        heartbeat = PipelineHeartbeat.objects.create(
            state=PipelineHeartbeat.State.RUNNING,
            last_seen_at=timezone.now() - timedelta(hours=1),
        )
        with self.assertRaisesRegex(CommandError, "stale"):
            call_command("check_condition_pipeline_health")

        heartbeat.last_seen_at = timezone.now() + timedelta(minutes=1)
        heartbeat.save(update_fields=("last_seen_at",))
        with self.assertRaisesRegex(CommandError, "future"):
            call_command("check_condition_pipeline_health")

        heartbeat.last_seen_at = timezone.now()
        heartbeat.state = PipelineHeartbeat.State.STOPPED
        heartbeat.save(update_fields=("last_seen_at", "state"))
        with self.assertRaisesRegex(CommandError, "stopped"):
            call_command("check_condition_pipeline_health")

    def test_max_age_is_bounded(self):
        with self.assertRaisesRegex(CommandError, "between 60 and 3600"):
            call_command("check_condition_pipeline_health", "--max-age", "59")
