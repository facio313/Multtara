from django.db import migrations, models
from django.db.models import Count, Q


def assert_no_duplicate_curated_identifiers(apps, schema_editor):
    """Fail clearly without mutating legacy identifiers before uniqueness."""

    WaterSpot = apps.get_model("spots", "WaterSpot")
    database = schema_editor.connection.alias
    duplicate_fields = []
    for field_name in ("tourapi_id", "khoa_beach_code"):
        duplicate_exists = (
            WaterSpot.objects.using(database)
            .exclude(**{field_name: ""})
            .values(field_name)
            .annotate(row_count=Count("pk"))
            .filter(row_count__gt=1)
            .exists()
        )
        if duplicate_exists:
            duplicate_fields.append(field_name)

    if duplicate_fields:
        fields = ", ".join(duplicate_fields)
        raise RuntimeError(
            "Duplicate nonblank WaterSpot curated identifiers were found in "
            f"{fields}. Audit and resolve them manually before applying "
            "spots.0003; this migration does not modify existing identifiers."
        )


class Migration(migrations.Migration):

    dependencies = [
        ("spots", "0002_alter_waterspot_options_and_more"),
    ]

    operations = [
        migrations.RunPython(
            assert_no_duplicate_curated_identifiers,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="waterspot",
            constraint=models.UniqueConstraint(
                condition=~Q(tourapi_id=""),
                fields=("tourapi_id",),
                name="spot_tourapi_nonblank_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="waterspot",
            constraint=models.UniqueConstraint(
                condition=~Q(khoa_beach_code=""),
                fields=("khoa_beach_code",),
                name="spot_khoa_code_nonblank_uniq",
            ),
        ),
    ]
