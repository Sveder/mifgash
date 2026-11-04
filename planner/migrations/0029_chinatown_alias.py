"""M13b (T184): 'near Chinatown' points to North Beach, the next area (about 700 m)."""
from django.db import migrations


def forward(apps, schema_editor):
    Area = apps.get_model("planner", "Area")
    for a in Area.objects.filter(name="North Beach"):
        words = [w for w in a.aliases.split(",") if w]
        if "chinatown" not in words:
            a.aliases = ",".join(words + ["chinatown"])
            a.save(update_fields=["aliases"])


def back(apps, schema_editor):
    Area = apps.get_model("planner", "Area")
    for a in Area.objects.filter(name="North Beach"):
        a.aliases = ",".join(w for w in a.aliases.split(",") if w and w != "chinatown")
        a.save(update_fields=["aliases"])


class Migration(migrations.Migration):
    dependencies = [("planner", "0028_group_places")]
    operations = [migrations.RunPython(forward, back)]
