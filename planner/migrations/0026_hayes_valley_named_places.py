"""T219: the Hayes Valley lunch options are named places with a street number.

'Hayes Valley cafes' (a street corner) becomes Arlequin Cafe, 384 Hayes St. The row keeps its id,
so a plan that holds it keeps its link. Blue Bottle Coffee Hayes Valley is new. The three lunch
places get a parking line for the calendar invite.
"""
from django.db import migrations

PARKING = "Street parking, or the paid Performing Arts Garage at 360 Grove St"
RENAMES = {"Hayes Valley cafes": "Arlequin Cafe"}
# name: (kind, price, tags, note, address)
PLACES = {
    "Arlequin Cafe": ("lunch", 1, ["cafe", "coffee", "outdoor", "sandwich", "quiet"],
                      "Cafe with a quiet back garden", "384 Hayes St, San Francisco"),
    "Blue Bottle Coffee Hayes Valley": ("lunch", 1, ["coffee", "outdoor", "quick"],
                                        "Coffee and a pastry, sit in Patricia's Green", "315 Linden St, San Francisco"),
}
PARKED = ["Souvla", "Arlequin Cafe", "Blue Bottle Coffee Hayes Valley"]


def forward(apps, schema_editor):
    Activity = apps.get_model("planner", "Activity")
    Area = apps.get_model("planner", "Area")
    for old, new in RENAMES.items():
        if not Activity.objects.filter(name=new).exists():
            Activity.objects.filter(name=old).update(name=new)
    area = Area.objects.filter(name="Hayes Valley").first()
    if area is None:
        return  # an empty database: seed() builds the world
    for name, (kind, price, tags, note, address) in PLACES.items():
        Activity.objects.update_or_create(name=name, defaults={
            "kind": kind, "area": area, "price": price, "tags": tags, "note": note, "address": address,
            "parking": PARKING})
    Activity.objects.filter(name__in=PARKED).update(parking=PARKING)


class Migration(migrations.Migration):
    dependencies = [("planner", "0025_sandbox_person")]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
