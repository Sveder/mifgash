"""T192 (M2b): the demo world moves to San Francisco.

Renames the Area and Activity rows in place, so live plans, offers and people keep their links,
and writes the new city, point, aliases, address, parking, tags and note from planner/seed.py.
Then it replaces the old place names and the old first names inside stored text (agent messages,
agent events, chat turns, plan text, offer reasons), so an old outing reads the new place name.

T280: the live database applied this migration on 2/11. A fresh database never holds the old rows
(0007 writes the new names), so the old names are replaced by neutral keys ('Old area 01',
'Old place 01'); the rename code stays and the tests drive it with these keys.
The two Instinct demo people keep their handles (dana_demo, avi_demo); only the display name changes. One way: the backward step does nothing.
"""
import re

from django.db import migrations

AREAS = {
    "Old area 01": 'Noe Valley',
    "Old area 02": 'Financial District',
    "Old area 03": 'Golden Gate Park',
    "Old area 04": 'Castro',
    "Old area 05": 'SoMa',
    "Old area 06": 'Mission',
    "Old area 07": 'Marina',
    "Old area 08": 'Hayes Valley',
    "Old area 09": 'Richmond',
    "Old area 10": 'Sausalito',
    "Old area 11": 'Oakland - Downtown',
    "Old area 12": 'Berkeley - Downtown',
    "Old area 13": 'North Beach',
    "Old area 14": 'Daly City',
}

ACTIVITIES = {
    "Old place 01": 'Ferry Building Marketplace',
    "Old place 02": 'Souvla',
    "Old place 03": 'La Taqueria',
    "Old place 04": 'Embarcadero Center lunch spots',
    "Old place 05": '24th Street cafes',
    "Old place 06": 'Castro Street lunch spots',
    "Old place 07": 'Hayes Valley cafes',
    "Old place 08": "Koret Children's Quarter",
    "Old place 09": 'California Academy of Sciences',
    "Old place 10": 'Hayes Valley Playground',
    "Old place 11": 'Golden Gate Park',
    "Old place 12": 'Randall Museum',
    "Old place 13": 'Noe Valley Recreation Center',
    "Old place 14": 'Douglass Playground',
    "Old place 15": 'The Interval at Long Now',
    "Old place 16": 'The Brixton',
    "Old place 17": 'Absinthe Brasserie & Bar',
    "Old place 18": 'Valencia Street bars',
    "Old place 19": 'Embarcadero Center Cinema',
    "Old place 20": 'Firefly',
    "Old place 21": 'Marina Green brunch',
    "Old place 22": 'Golden Gate Park bike ride',
    "Old place 23": 'Dolores Park picnic',
    "Old place 24": 'Embarcadero waterfront walk',
    "Old place 25": 'Sausalito waterfront restaurants',
    "Old place 26": 'Marin Headlands',
    "Old place 27": "Swan's Market",
    "Old place 28": 'Shattuck Avenue cafes',
    "Old place 29": 'North Beach trattorias',
    "Old place 30": 'Vesuvio Cafe',
    "Old place 31": 'Exploratorium',
    "Old place 32": 'Serramonte Center food court',
}

# Old address -> new address, then first names. Longest first at run time.
# T280: the short old place words are gone from the public tree; the live run used them on 2/11.
WORDS = {}
NAMES = {"Dana Demo": "Diana Demo", "Avi Demo": "Adam Demo", "Dana": "Diana", "Avi": "Adam",
         "Tamar": "Emma", "Yaron": "Lucas", "Noa": "Priya", "Amir": "Mateo", "Shira": "Sofia",
         "Eitan": "Ethan", "Lior": "Jordan", "Maya": "Maria"}


def table(old_addresses):
    from planner import seed
    new_addresses = seed.ADDRESSES
    pairs = {}
    for old, new in old_addresses.items():
        if old in ACTIVITIES and new:
            pairs[new] = new_addresses[ACTIVITIES[old]]
    pairs.update(ACTIVITIES)
    pairs.update(AREAS)
    pairs.update(WORDS)
    pairs.update(NAMES)
    keys = sorted(pairs, key=len, reverse=True)
    rx = re.compile(r"(?<!\w)(" + "|".join(re.escape(k) for k in keys) + r")(?!\w)")
    return lambda s: rx.sub(lambda m: pairs[m.group(1)], s)


def fix_json(value, sub):
    """The same value with every text string fixed. A URL stays as it is: 0023 rebuilds the
    calendar links from the plan, and a word swap inside a URL breaks it."""
    if isinstance(value, dict):
        return {k: fix_json(v, sub) for k, v in value.items()}
    if isinstance(value, list):
        return [fix_json(v, sub) for v in value]
    if isinstance(value, str) and not value.startswith("http"):
        return sub(value)
    return value


def forward(apps, schema_editor):
    from planner import seed
    Area = apps.get_model("planner", "Area")
    Activity = apps.get_model("planner", "Activity")
    old_addresses = dict(Activity.objects.values_list("name", "address"))
    sub = table(old_addresses)

    area_rows = {r[0]: r for r in seed.AREAS}
    for old, new in AREAS.items():
        if Area.objects.filter(name=new).exists():
            continue
        _, city, lat, lon, aliases = area_rows[new]
        Area.objects.filter(name=old).update(name=new, city=city, lat=lat, lon=lon, aliases=aliases)

    act_rows = {r[0]: r for r in seed.ACTIVITIES}
    later = {"Hayes Valley cafes": "Arlequin Cafe"}  # T219: migration 0026 renames it; the seed holds the new name
    for old, new in ACTIVITIES.items():
        cur = later.get(new, new)
        _, kind, area, price, tags, note = act_rows[cur]
        area_obj = Area.objects.filter(name=area).first()
        fields = dict(name=new, kind=kind, price=price, tags=tags, note=note, address=seed.ADDRESSES[cur],
                      parking=seed.PARKING.get(cur, "Street parking"))
        if area_obj:
            fields["area"] = area_obj
        Activity.objects.filter(name=old).update(**fields)

    Person = apps.get_model("planner", "Person")
    for old, new in (("Dana Demo", "Diana Demo"), ("Avi Demo", "Adam Demo")):
        Person.objects.filter(name=old).update(name=new)

    for model, fields in (("Plan", ["raw_text"]), ("Offer", ["reason"]), ("ChatTurn", ["text"]), ("AgentMessage", ["sender", "receiver"])):
        for row in apps.get_model("planner", model).objects.all():
            changed = {f: sub(getattr(row, f)) for f in fields if getattr(row, f)}
            changed = {f: v for f, v in changed.items() if v != getattr(row, f)}
            if changed:
                type(row).objects.filter(pk=row.pk).update(**changed)
    for model in ("AgentMessage", "AgentEvent"):
        for row in apps.get_model("planner", model).objects.all():
            new = fix_json(row.payload, sub)
            if new != row.payload:
                type(row).objects.filter(pk=row.pk).update(payload=new)
    for row in apps.get_model("planner", "ChatTurn").objects.all():
        if row.buttons:
            new = fix_json(row.buttons, sub)
            if new != row.buttons:
                type(row).objects.filter(pk=row.pk).update(buttons=new)


class Migration(migrations.Migration):
    dependencies = [("planner", "0021_rename_seed_people")]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
