from django.db import migrations


def rename_owner(apps, schema_editor):
    """The seeded demo owner was 'Michael' (@michael), the real user's name. Rename the row in place,
    so its slots, friend links and token stay. Skip when 'tamar' is taken."""
    Person = apps.get_model("planner", "Person")
    if Person.objects.filter(handle="tamar").exists():
        return
    Person.objects.filter(handle="michael", name="Michael", is_owner=True).update(name="Tamar", handle="tamar")


class Migration(migrations.Migration):

    dependencies = [
        ('planner', '0018_email_fallback'),
    ]

    operations = [
        migrations.RunPython(rename_owner, migrations.RunPython.noop),
    ]
