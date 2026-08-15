from django.db import migrations, models


def deduplicate_profile_scores(apps, schema_editor):
    """Keep the newest legacy row before enforcing profile-aware idempotency."""

    condition_score = apps.get_model("conditions", "ConditionScore")
    duplicate_groups = (
        condition_score.objects.filter(snapshot__isnull=False)
        .values(
            "snapshot_id",
            "activity",
            "participant_profile",
            "methodology_version",
        )
        .annotate(row_count=models.Count("id"))
        .filter(row_count__gt=1)
    )
    for group in duplicate_groups.iterator():
        filters = {
            "snapshot_id": group["snapshot_id"],
            "activity": group["activity"],
            "participant_profile": group["participant_profile"],
            "methodology_version": group["methodology_version"],
        }
        rows = condition_score.objects.filter(**filters)
        newest_id = (
            rows.order_by("-evaluated_at", "-id")
            .values_list("id", flat=True)
            .first()
        )
        rows.exclude(id=newest_id).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("conditions", "0002_auditable_observations"),
    ]

    operations = [
        migrations.AddField(
            model_name="conditionscore",
            name="participant_profile",
            field=models.CharField(
                choices=[
                    ("unknown", "Unknown legacy profile"),
                    ("general", "General"),
                    ("family", "Family"),
                ],
                default="unknown",
                max_length=16,
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="conditionscore",
            name="participant_profile",
            field=models.CharField(
                choices=[
                    ("unknown", "Unknown legacy profile"),
                    ("general", "General"),
                    ("family", "Family"),
                ],
                default="general",
                max_length=16,
            ),
        ),
        migrations.RunPython(
            deduplicate_profile_scores,
            migrations.RunPython.noop,
        ),
        migrations.RemoveIndex(
            model_name="conditionscore",
            name="cond_score_spot_act_eval_idx",
        ),
        migrations.AddIndex(
            model_name="conditionscore",
            index=models.Index(
                fields=[
                    "spot",
                    "activity",
                    "participant_profile",
                    "-evaluated_at",
                ],
                name="cond_score_spot_act_prof_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="conditionscore",
            constraint=models.UniqueConstraint(
                condition=models.Q(snapshot__isnull=False),
                fields=(
                    "snapshot",
                    "activity",
                    "participant_profile",
                    "methodology_version",
                ),
                name="cond_score_snap_act_prof_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="conditionscore",
            constraint=models.CheckConstraint(
                check=models.Q(
                    participant_profile__in=("unknown", "general", "family")
                ),
                name="cond_score_profile_valid",
            ),
        ),
    ]
