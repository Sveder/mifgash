"""T162 (M2): the seeded demo people get US/international first names.

Renames only a row whose name AND handle are the old seed values, so a real person who signed up
with one of these names keeps it. avi_demo and dana_demo (the Instinct run) are not seed rows and stay.
"""
from django.db import migrations

RENAME = {"Tamar": "Emma", "Dana": "Alex", "Yaron": "Lucas", "Noa": "Priya", "Amir": "Mateo",
          "Shira": "Sofia", "Eitan": "Ethan", "Lior": "Jordan", "Maya": "Maria"}


def forward(apps, schema_editor):
    Person = apps.get_model("planner", "Person")
    for old, new in RENAME.items():
        if Person.objects.filter(handle=new.lower()).exists():
            continue
        Person.objects.filter(name=old, handle=old.lower()).update(name=new, handle=new.lower())


def backward(apps, schema_editor):
    Person = apps.get_model("planner", "Person")
    for old, new in RENAME.items():
        if Person.objects.filter(handle=old.lower()).exists():
            continue
        Person.objects.filter(name=new, handle=new.lower()).update(name=old, handle=old.lower())


class Migration(migrations.Migration):
    dependencies = [("planner", "0020_offer_reason")]
    operations = [migrations.RunPython(forward, backward)]
