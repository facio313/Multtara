from django.db import migrations, models


SURF_SKILL_REASON = "SURF_SKILL_LEVEL_REQUIRED"


def normalize_unscoped_surf_forecasts(apps, schema_editor):
    """Retain old projections as auditable, explicitly unscoped UNKNOWN rows."""

    DailyForecast = apps.get_model("forecasts", "DailyForecast")
    database = schema_editor.connection.alias
    rows = (
        DailyForecast.objects.using(database)
        .filter(activity="surf")
        .iterator(chunk_size=500)
    )
    for row in rows:
        if row.safety_status == "stop":
            decision = "blocked"
        elif row.safety_status == "caution":
            decision = "caution"
        else:
            decision = "unknown"
        gates = list(row.gates) if isinstance(row.gates, list) else []
        if not any(
            isinstance(gate, dict)
            and gate.get("reason_code") == SURF_SKILL_REASON
            for gate in gates
        ):
            gates.append(
                {
                    "rule_id": "suitability.surf.skill_grade",
                    "severity": "unknown",
                    "metric_name": "participant_skill_level",
                    "reason_code": SURF_SKILL_REASON,
                }
            )
        missing = (
            list(row.missing_metrics)
            if isinstance(row.missing_metrics, list)
            else []
        )
        if "participant_skill_level" not in missing:
            missing.append("participant_skill_level")
        update_fields = [
            "participant_skill_level",
            "score",
            "score_range",
            "decision",
            "gates",
            "missing_metrics",
        ]
        row.participant_skill_level = "unspecified"
        row.score = None
        row.score_range = []
        row.decision = decision
        row.gates = gates
        row.missing_metrics = missing
        if row.safety_status not in {"stop", "caution"} and (
            row.availability == "available"
        ):
            row.availability = "partial"
            row.unavailable_reason = SURF_SKILL_REASON
            update_fields.extend(("availability", "unavailable_reason"))
        row.save(update_fields=update_fields)

    # Historical rows may have used ``partial`` as a disclosure label while
    # still carrying a clear/recommended score. Preserve the row and evidence,
    # but make every non-available public projection explicitly fail closed.
    non_available = (
        DailyForecast.objects.using(database)
        .exclude(availability="available")
        .iterator(chunk_size=500)
    )
    for row in non_available:
        row.safety_status = "unknown"
        row.decision = "unknown"
        row.score = None
        row.score_range = []
        row.contributions = []
        row.save(
            update_fields=(
                "safety_status",
                "decision",
                "score",
                "score_range",
                "contributions",
            )
        )

    # The engine now suppresses ranges whenever the point score is absent.
    # Normalize old rows before model validation starts enforcing that pair.
    DailyForecast.objects.using(database).filter(score__isnull=True).update(
        score_range=[]
    )


class Migration(migrations.Migration):

    dependencies = [
        ("forecasts", "0002_dailyforecast"),
    ]

    operations = [
        migrations.AddField(
            model_name="dailyforecast",
            name="participant_skill_level",
            field=models.CharField(
                choices=[
                    ("unspecified", "Unspecified"),
                    ("beginner", "Beginner"),
                    ("intermediate", "Intermediate"),
                    ("advanced", "Advanced"),
                ],
                default="unspecified",
                max_length=16,
            ),
        ),
        migrations.RunPython(
            normalize_unscoped_surf_forecasts,
            migrations.RunPython.noop,
        ),
        migrations.RemoveConstraint(
            model_name="dailyforecast",
            name="daily_fcst_evidence_uniq",
        ),
        migrations.AddConstraint(
            model_name="dailyforecast",
            constraint=models.UniqueConstraint(
                fields=(
                    "spot",
                    "forecast_date",
                    "activity",
                    "participant_profile",
                    "participant_skill_level",
                    "methodology_version",
                    "projection_methodology_version",
                    "evidence_fingerprint",
                ),
                name="daily_fcst_evidence_uniq",
            ),
        ),
        migrations.RemoveIndex(
            model_name="dailyforecast",
            name="daily_fcst_lookup_idx",
        ),
        migrations.AddIndex(
            model_name="dailyforecast",
            index=models.Index(
                fields=[
                    "spot",
                    "activity",
                    "participant_profile",
                    "participant_skill_level",
                    "forecast_date",
                    "-evaluated_at",
                ],
                name="daily_fcst_lookup_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="dailyforecast",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("activity", "surf"),
                        (
                            "participant_skill_level__in",
                            (
                                "unspecified",
                                "beginner",
                                "intermediate",
                                "advanced",
                            ),
                        ),
                    ),
                    models.Q(
                        models.Q(("activity", "surf"), _negated=True),
                        ("participant_skill_level", "unspecified"),
                    ),
                    _connector="OR",
                ),
                name="daily_fcst_skill_activity_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="dailyforecast",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("activity", "surf"),
                        ("participant_skill_level", "unspecified"),
                        _negated=True,
                    ),
                    models.Q(
                        ("score__isnull", True),
                        models.Q(
                            models.Q(
                                ("decision", "unknown"),
                                ("safety_status", "clear"),
                            ),
                            models.Q(
                                ("decision", "unknown"),
                                ("safety_status", "unknown"),
                            ),
                            models.Q(
                                ("decision", "caution"),
                                ("safety_status", "caution"),
                            ),
                            models.Q(
                                ("decision", "blocked"),
                                ("safety_status", "stop"),
                            ),
                            _connector="OR",
                        ),
                    ),
                    _connector="OR",
                ),
                name="daily_fcst_surf_unscoped_policy",
            ),
        ),
        migrations.AddConstraint(
            model_name="dailyforecast",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("availability", "available"),
                    models.Q(
                        ("availability__in", ("partial", "unavailable")),
                        ("contributions", []),
                        ("decision", "unknown"),
                        ("safety_status", "unknown"),
                        ("score__isnull", True),
                        ("score_range", []),
                    ),
                    _connector="OR",
                ),
                name="daily_fcst_availability_public",
            ),
        ),
        migrations.AddConstraint(
            model_name="dailyforecast",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("score__isnull", False),
                    ("score_range", []),
                    _connector="OR",
                ),
                name="daily_fcst_null_range_empty",
            ),
        ),
    ]
