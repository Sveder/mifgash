"""F8a (T260) step 2 of 3: one random uuid per existing row."""
import uuid

from django.db import migrations


def fill(apps, schema_editor):
    for name in ("Plan", "Offer"):
        model = apps.get_model("planner", name)
        for row in model.objects.filter(uid__isnull=True).only("pk"):
            row.uid = uuid.uuid4()
            row.save(update_fields=["uid"])


class Migration(migrations.Migration):
    dependencies = [("planner", "0033_uid_add")]
    operations = [migrations.RunPython(fill, migrations.RunPython.noop)]
