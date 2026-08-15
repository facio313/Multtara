import json

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def encode_text_as_json(apps, schema_editor):
    SafetyCard = apps.get_model("trips", "SafetyCard")
    for card in SafetyCard.objects.all():
        changed = False
        risks = card.risk_factors
        if isinstance(risks, str):
            text = risks.strip()
            if not text:
                payload = []
            elif text.startswith("["):
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    payload = [text]
            else:
                payload = [text]
            card.risk_factors = json.dumps(payload, ensure_ascii=False)
            changed = True
        shared = card.shared_with
        if isinstance(shared, str):
            text = shared.strip()
            if not text:
                payload = []
            elif text.startswith("["):
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    payload = [part.strip() for part in text.split(",") if part.strip()]
            else:
                payload = [part.strip() for part in text.split(",") if part.strip()]
            card.shared_with = json.dumps(payload, ensure_ascii=False)
            changed = True
        if changed:
            card.save(update_fields=["risk_factors", "shared_with"])


class Migration(migrations.Migration):

    dependencies = [
        ("trips", "0002_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(encode_text_as_json, migrations.RunPython.noop),
        migrations.AddField(
            model_name="safetycard",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AlterModelOptions(
            name="safetycard",
            options={"ordering": ["-created_at"]},
        ),
        migrations.AlterField(
            model_name="safetycard",
            name="risk_factors",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AlterField(
            model_name="safetycard",
            name="shared_with",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AlterField(
            model_name="safetycard",
            name="spot",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="safety_cards",
                to="spots.waterspot",
            ),
        ),
        migrations.AlterField(
            model_name="safetycard",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="safety_cards",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
