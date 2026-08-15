from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("conditions", "0002_water_index_constraints"),
    ]

    operations = [
        migrations.AddField(
            model_name="watercondition",
            name="marine_indices",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
