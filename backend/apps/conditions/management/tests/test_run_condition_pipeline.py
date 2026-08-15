from __future__ import annotations

from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase


class ConditionPipelineCommandTests(SimpleTestCase):
    @patch(
        "apps.conditions.management.commands.run_condition_pipeline.ProviderConfig.from_environment"
    )
    @patch("apps.conditions.management.commands.run_condition_pipeline.call_command")
    def test_once_runs_configured_collectors_and_both_profiles(
        self, nested_call, provider_config
    ):
        provider_config.return_value = SimpleNamespace(kma="configured", khoa="configured")
        output = StringIO()

        call_command("run_condition_pipeline", "--once", stdout=output)

        self.assertEqual(nested_call.call_count, 4)
        self.assertEqual(nested_call.call_args_list[0].args[:3], ("sync_weather_conditions", "--mode", "nowcast"))
        self.assertEqual(nested_call.call_args_list[1].args[0], "sync_marine_conditions")
        self.assertEqual(
            nested_call.call_args_list[2].args[:3],
            ("evaluate_water_conditions", "--profile", "general"),
        )
        self.assertEqual(
            nested_call.call_args_list[3].args[:3],
            ("evaluate_water_conditions", "--profile", "family"),
        )

    @patch(
        "apps.conditions.management.commands.run_condition_pipeline.ProviderConfig.from_environment"
    )
    @patch("apps.conditions.management.commands.run_condition_pipeline.call_command")
    def test_missing_provider_keys_skip_collectors_but_keep_fail_closed_evaluation(
        self, nested_call, provider_config
    ):
        provider_config.return_value = SimpleNamespace(kma="", khoa="")
        output = StringIO()

        call_command("run_condition_pipeline", "--once", stdout=output)

        self.assertEqual(nested_call.call_count, 2)
        self.assertTrue(
            all(item.args[0] == "evaluate_water_conditions" for item in nested_call.call_args_list)
        )
        self.assertIn("safely skipped", output.getvalue())

    @patch(
        "apps.conditions.management.commands.run_condition_pipeline.ProviderConfig.from_environment"
    )
    @patch("apps.conditions.management.commands.run_condition_pipeline.call_command")
    def test_once_uses_bounded_error_without_exception_or_secret(
        self, nested_call, provider_config
    ):
        provider_config.return_value = SimpleNamespace(kma="configured", khoa="")
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

    def test_interval_bounds_are_enforced(self):
        with self.assertRaises(CommandError):
            call_command("run_condition_pipeline", "--once", "--weather-interval", "59")
