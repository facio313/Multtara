from __future__ import annotations

from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import TestCase

from apps.conditions.models import IngestionRun
from apps.conditions.management.commands.run_condition_pipeline import _pipeline_tasks


class ConditionPipelineCommandTests(TestCase):
    def test_evaluators_depend_on_due_provider_collection(self):
        tasks = _pipeline_tasks(
            config=SimpleNamespace(
                kma="configured",
                khoa="configured",
                routing_matrix="https://routing.example.test",
            ),
            options={
                "weather_interval": 1_800,
                "marine_interval": 3_600,
                "forecast_weather_interval": 10_800,
                "forecast_marine_interval": 21_600,
                "evaluate_interval": 300,
                "forecast_evaluate_interval": 3_600,
                "derive_interval": 300,
                "retention_interval": 86_400,
                "route_matrix_interval": 86_400,
            },
        )
        by_name = {task.name: task for task in tasks}

        self.assertEqual(
            by_name["water-index-general"].depends_on,
            ("weather-nowcast", "marine", "derive-suitability"),
        )
        self.assertEqual(
            by_name["daily-forecast"].depends_on,
            (
                "weather-short-forecast",
                "marine-activity-forecast",
                "derive-suitability",
            ),
        )
        self.assertEqual(
            by_name["derive-suitability"].depends_on,
            (
                "weather-nowcast",
                "marine",
                "weather-short-forecast",
                "marine-activity-forecast",
            ),
        )
        self.assertEqual(
            by_name["route-matrix-drive"].depends_on,
            (
                "water-index-general",
                "water-index-family",
                "daily-forecast",
                "condition-retention",
            ),
        )
        self.assertEqual(
            by_name["route-matrix-walk"].depends_on,
            ("route-matrix-drive",),
        )
        self.assertEqual(
            by_name["route-matrix-bicycle"].depends_on,
            ("route-matrix-walk",),
        )

    @patch(
        "apps.conditions.management.commands.run_condition_pipeline.ProviderConfig.from_environment"
    )
    @patch("apps.conditions.management.commands.run_condition_pipeline.call_command")
    def test_once_runs_configured_collectors_and_both_profiles(
        self, nested_call, provider_config
    ):
        provider_config.return_value = SimpleNamespace(
            kma="configured",
            khoa="configured",
            routing_matrix="",
        )
        output = StringIO()

        call_command("run_condition_pipeline", "--once", stdout=output)

        self.assertEqual(nested_call.call_count, 9)
        self.assertEqual(
            nested_call.call_args_list[0].args[:3],
            ("sync_weather_conditions", "--mode", "nowcast"),
        )
        self.assertEqual(nested_call.call_args_list[1].args[0], "sync_marine_conditions")
        self.assertEqual(
            nested_call.call_args_list[2].args[:3],
            ("sync_weather_conditions", "--mode", "short"),
        )
        self.assertEqual(
            nested_call.call_args_list[3].args[0],
            "sync_forecast_evidence",
        )
        self.assertEqual(
            nested_call.call_args_list[4].args[0],
            "derive_suitability_metrics",
        )
        self.assertEqual(
            nested_call.call_args_list[5].args[:3],
            ("evaluate_water_conditions", "--profile", "general"),
        )
        self.assertEqual(
            nested_call.call_args_list[6].args[:3],
            ("evaluate_water_conditions", "--profile", "family"),
        )
        self.assertEqual(nested_call.call_args_list[7].args[0], "evaluate_daily_forecasts")
        self.assertEqual(nested_call.call_args_list[8].args[0], "prune_condition_history")
        self.assertEqual(
            IngestionRun.objects.filter(status=IngestionRun.Status.SUCCEEDED).count(),
            9,
        )

    @patch(
        "apps.conditions.management.commands.run_condition_pipeline.ProviderConfig.from_environment"
    )
    @patch("apps.conditions.management.commands.run_condition_pipeline.call_command")
    def test_missing_provider_keys_skip_collectors_but_keep_fail_closed_evaluation(
        self, nested_call, provider_config
    ):
        provider_config.return_value = SimpleNamespace(
            kma="",
            khoa="",
            routing_matrix="",
        )
        output = StringIO()

        call_command("run_condition_pipeline", "--once", stdout=output)

        self.assertEqual(nested_call.call_count, 5)
        self.assertEqual(
            [item.args[0] for item in nested_call.call_args_list],
            [
                "derive_suitability_metrics",
                "evaluate_water_conditions",
                "evaluate_water_conditions",
                "evaluate_daily_forecasts",
                "prune_condition_history",
            ],
        )
        self.assertIn("safely skipped", output.getvalue())

    @patch(
        "apps.conditions.management.commands.run_condition_pipeline.ProviderConfig.from_environment"
    )
    @patch("apps.conditions.management.commands.run_condition_pipeline.call_command")
    def test_configured_route_matrix_runs_three_modes_in_sequence(
        self, nested_call, provider_config
    ):
        provider_config.return_value = SimpleNamespace(
            kma="",
            khoa="",
            routing_matrix="https://routing.example.test",
        )

        call_command(
            "run_condition_pipeline",
            "--once",
            "--route-matrix-interval",
            "86400",
            stdout=StringIO(),
        )

        self.assertEqual(nested_call.call_count, 8)
        route_calls = nested_call.call_args_list[-3:]
        self.assertEqual(
            [call.args for call in route_calls],
            [
                (
                    "refresh_route_matrix",
                    "--transport",
                    "drive",
                    "--valid-hours",
                    "48",
                ),
                (
                    "refresh_route_matrix",
                    "--transport",
                    "walk",
                    "--valid-hours",
                    "48",
                ),
                (
                    "refresh_route_matrix",
                    "--transport",
                    "bicycle",
                    "--valid-hours",
                    "48",
                ),
            ],
        )

    @patch(
        "apps.conditions.management.commands.run_condition_pipeline.ProviderConfig.from_environment"
    )
    @patch("apps.conditions.management.commands.run_condition_pipeline.call_command")
    def test_once_uses_bounded_error_without_exception_or_secret(
        self, nested_call, provider_config
    ):
        provider_config.return_value = SimpleNamespace(
            kma="configured",
            khoa="",
            routing_matrix="",
        )
        nested_call.side_effect = RuntimeError(
            "https://provider.invalid/?serviceKey=must-not-be-rendered"
        )
        stdout = StringIO()
        stderr = StringIO()

        with self.assertRaisesRegex(CommandError, "failed task"):
            call_command(
                "run_condition_pipeline",
                "--once",
                stdout=stdout,
                stderr=stderr,
            )

        combined = stdout.getvalue() + stderr.getvalue()
        self.assertNotIn("serviceKey", combined)
        self.assertNotIn("must-not-be-rendered", combined)
        self.assertIn("failed safely", combined)
        failed = IngestionRun.objects.filter(status=IngestionRun.Status.FAILED)
        self.assertEqual(failed.count(), 7)
        self.assertTrue(all(row.error_code == "COMMAND_FAILED" for row in failed))
        self.assertNotIn("serviceKey", str(list(failed.values("details"))))

    def test_interval_bounds_are_enforced(self):
        with self.assertRaises(CommandError):
            call_command("run_condition_pipeline", "--once", "--weather-interval", "59")
