"""T31: areas outside the city centre, so a far place makes its own open plan.

T280: the rows are written with the San Francisco names (the demo world since T192). A live
database applied this migration long ago, so the new text changes nothing there. On an empty
database seed() later writes the full rows, including the addresses and the parking lines."""
from django.db import migrations

AREAS = [
    ("Sausalito", "Sausalito", 37.8591, -122.4853, "sausalito,marin"),
    ("Oakland - Downtown", "Oakland", 37.8044, -122.2712, "oakland,downtown oakland,jack london"),
    ("Berkeley - Downtown", "Berkeley", 37.8716, -122.2727, "berkeley,downtown berkeley,shattuck"),
    ("North Beach", "San Francisco", 37.8000, -122.4100, "north beach,little italy,columbus,telegraph hill"),
    ("Daly City", "Daly City", 37.6879, -122.4702, "daly city,serramonte"),
]

ACTIVITIES = [
    ("Sausalito waterfront restaurants", "lunch", "Sausalito", 2, ["seafood", "sea", "outdoor"], "Lunch by the water"),
    ("Marin Headlands", "weekend", "Sausalito", 1, ["park", "sea", "walk"], "Cliff walk with a view of the bridge"),
    ("Swan's Market", "lunch", "Oakland - Downtown", 1, ["food hall", "cafe", "sandwich"], "Food hall lunch, quick"),
    ("Shattuck Avenue cafes", "lunch", "Berkeley - Downtown", 2, ["cafe", "coffee", "quiet"], "Quiet main-street cafes"),
    ("North Beach trattorias", "lunch", "North Beach", 1, ["italian", "pizza", "cheap"], "Small Italian places on Columbus Ave"),
    ("Vesuvio Cafe", "evening", "North Beach", 2, ["bar", "historic", "outdoor"], "Old bar next to City Lights"),
    ("Serramonte Center food court", "lunch", "Daly City", 1, ["food court", "indoor", "sandwich"], "Simple mall lunch"),
]


def add(apps, schema_editor):
    Area = apps.get_model("planner", "Area")
    Activity = apps.get_model("planner", "Activity")
    areas = {}
    for name, city, lat, lon, aliases in AREAS:
        areas[name], _ = Area.objects.update_or_create(
            name=name, defaults={"city": city, "lat": lat, "lon": lon, "aliases": aliases})
    for name, kind, area, price, tags, note in ACTIVITIES:
        Activity.objects.update_or_create(
            name=name, defaults={"kind": kind, "area": areas[area], "price": price, "tags": tags, "note": note})


def remove(apps, schema_editor):
    Activity = apps.get_model("planner", "Activity")
    Activity.objects.filter(name__in=[a[0] for a in ACTIVITIES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("planner", "0006_two_step_approval"),
    ]

    operations = [
        migrations.RunPython(add, remove),
    ]
