"""F8a (T260) step 3 of 3: uid is unique and not null; new rows get uuid4."""
import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("planner", "0034_uid_fill")]
    operations = [
        migrations.AlterField("plan", "uid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
        migrations.AlterField("offer", "uid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
    ]
