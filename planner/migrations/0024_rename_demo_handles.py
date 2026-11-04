"""T194 (M2 check): the two demo people from the first agent run get international handles.

0022 kept the handles avi_demo and dana_demo and changed only the display names (Adam Demo,
Diana Demo). The handles still show in friend search and API answers, so they change too:
avi_demo -> adam_demo, dana_demo -> diana_demo. The agent keys belong to the person row, so the
keys keep working. A new handle that is already taken leaves the row as it is.
"""
from django.db import migrations

RENAME = {"avi_demo": "adam_demo", "dana_demo": "diana_demo"}


def forward(apps, schema_editor):
    Person = apps.get_model("planner", "Person")
    for old, new in RENAME.items():
        if not Person.objects.filter(handle=new).exists():
            Person.objects.filter(handle=old).update(handle=new)


def backward(apps, schema_editor):
    Person = apps.get_model("planner", "Person")
    for old, new in RENAME.items():
        if not Person.objects.filter(handle=old).exists():
            Person.objects.filter(handle=new).update(handle=old)


class Migration(migrations.Migration):
    dependencies = [("planner", "0023_rebuild_calendar_links")]
    operations = [migrations.RunPython(forward, backward)]
