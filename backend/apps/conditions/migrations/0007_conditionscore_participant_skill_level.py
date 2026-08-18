from django.db import migrations, models


SURF_SKILL_REASON = "SURF_SKILL_LEVEL_REQUIRED"


def normalize_unscoped_surf_scores(apps, schema_editor):
    """Preserve legacy rows/evidence while removing unscoped suitability."""

    ConditionScore = apps.get_model("conditions", "ConditionScore")
    database = schema_editor.connection.alias
    rows = (
        ConditionScore.objects.using(database)
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
        row.participant_skill_level = "unspecified"
        row.score = None
        row.score_range = []
        row.decision = decision
        row.gates = gates
        row.missing_metrics = missing
        row.save(
            update_fields=(
                "participant_skill_level",
                "score",
                "score_range",
                "decision",
                "gates",
                "missing_metrics",
            )
        )

    ConditionScore.objects.using(database).filter(score__isnull=True).update(
        score_range=[]
    )


class Migration(migrations.Migration):

    dependencies = [
        ("conditions", "0006_hydraulic_calibration"),
    ]

    operations = [
        migrations.AddField(
            model_name="conditionscore",
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
            normalize_unscoped_surf_scores,
            migrations.RunPython.noop,
        ),
        migrations.RemoveConstraint(
            model_name="conditionscore",
            name="cond_score_snap_act_prof_uniq",
        ),
        migrations.AddConstraint(
            model_name="conditionscore",
            constraint=models.UniqueConstraint(
                condition=models.Q(("snapshot__isnull", False)),
                fields=(
                    "snapshot",
                    "activity",
                    "participant_profile",
                    "participant_skill_level",
                    "methodology_version",
                ),
                name="cond_score_snap_act_prof_uniq",
            ),
        ),
        migrations.RemoveIndex(
            model_name="conditionscore",
            name="cond_score_spot_act_prof_idx",
        ),
        migrations.AddIndex(
            model_name="conditionscore",
            index=models.Index(
                fields=[
                    "spot",
                    "activity",
                    "participant_profile",
                    "participant_skill_level",
                    "-evaluated_at",
                ],
                name="cond_score_spot_act_prof_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="conditionscore",
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
                name="cond_score_skill_activity_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="conditionscore",
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
                name="cond_score_surf_unscoped_policy",
            ),
        ),
        migrations.AddConstraint(
            model_name="conditionscore",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("score__isnull", False),
                    ("score_range", []),
                    _connector="OR",
                ),
                name="cond_score_null_range_empty",
            ),
        ),
    ]
