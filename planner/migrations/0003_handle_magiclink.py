import re

import django.db.models.deletion
from django.db import migrations, models


def fill_handles(apps, schema_editor):
    Person = apps.get_model("planner", "Person")
    seen = set()
    for p in Person.objects.order_by("pk"):
        base = re.sub(r"[^a-z0-9_]", "", p.name.lower())[:28] or "user"
        h, n = base, 1
        while h in seen:
            n += 1
            h = f"{base}{n}"
        seen.add(h)
        p.handle = h
        p.save(update_fields=["handle"])


class Migration(migrations.Migration):

    dependencies = [
        ("planner", "0002_contacts_encrypted_agent_keys"),
    ]

    operations = [
        migrations.AddField(
            model_name="person",
            name="handle",
            field=models.CharField(max_length=32, null=True),
        ),
        migrations.RunPython(fill_handles, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="person",
            name="handle",
            field=models.CharField(help_text="public user name for friend search: lower case, letters digits and underscore", max_length=32, unique=True),
        ),
        migrations.AlterField(
            model_name="person",
            name="home_area",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="planner.area"),
        ),
        migrations.CreateModel(
            name="MagicLink",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("person", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="magic_links", to="planner.person")),
            ],
        ),
    ]
