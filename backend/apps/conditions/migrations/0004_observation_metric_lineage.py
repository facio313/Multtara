import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("conditions", "0003_condition_score_participant_profile"),
    ]

    operations = [
        migrations.CreateModel(
            name="ObservationMetricLineage",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "relation",
                    models.CharField(
                        choices=[
                            ("selected", "Selected input"),
                            ("conflict", "Conflicting input"),
                        ],
                        max_length=16,
                    ),
                ),
                ("priority", models.PositiveSmallIntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "derived_metric",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lineage_sources",
                        to="conditions.observationmetric",
                    ),
                ),
                (
                    "source_metric",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.RESTRICT,
                        related_name="lineage_derivations",
                        to="conditions.observationmetric",
                    ),
                ),
            ],
            options={
                "ordering": (
                    "derived_metric_id",
                    "-priority",
                    "source_metric_id",
                ),
                "indexes": [
                    models.Index(
                        fields=["derived_metric", "relation"],
                        name="cond_lineage_derived_rel_idx",
                    ),
                    models.Index(
                        fields=["source_metric"],
                        name="cond_lineage_source_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("derived_metric", "source_metric"),
                        name="cond_metric_lineage_edge_uniq",
                    ),
                    models.CheckConstraint(
                        check=models.Q(
                            ("derived_metric", models.F("source_metric")),
                            _negated=True,
                        ),
                        name="cond_metric_lineage_not_self",
                    ),
                    models.CheckConstraint(
                        check=models.Q(
                            ("relation__in", ("selected", "conflict"))
                        ),
                        name="cond_metric_lineage_relation_valid",
                    ),
                ],
            },
        ),
    ]
