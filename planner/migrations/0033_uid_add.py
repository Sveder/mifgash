"""F8a (T260) step 1 of 3: add Plan.uid and Offer.uid, nullable, no unique yet."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("planner", "0032_person_city")]
    operations = [
        migrations.AddField("plan", "uid", models.UUIDField(null=True, editable=False)),
        migrations.AddField("offer", "uid", models.UUIDField(null=True, editable=False)),
    ]
