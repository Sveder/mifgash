"""T45: a street address for every demo activity. Frozen copy of seed.ADDRESSES.

T280: written with the San Francisco names and addresses (the demo world since T192). A live
database applied this migration long ago, so the new text changes nothing there."""
from django.db import migrations

ADDRESSES = {
    'Ferry Building Marketplace': '1 Ferry Building, San Francisco',
    'Souvla': '517 Hayes St, San Francisco',
    'La Taqueria': '2889 Mission St, San Francisco',
    'Embarcadero Center lunch spots': '4 Embarcadero Center, San Francisco',
    '24th Street cafes': '24th St, Noe Valley, San Francisco',
    'Castro Street lunch spots': 'Castro St at 18th St, San Francisco',
    'Hayes Valley cafes': '384 Hayes St, San Francisco',
    "Koret Children's Quarter": '320 Bowling Green Dr, Golden Gate Park, San Francisco',
    'California Academy of Sciences': '55 Music Concourse Dr, San Francisco',
    'Hayes Valley Playground': 'Hayes St at Buchanan St, San Francisco',
    'Golden Gate Park': 'Golden Gate Park, John F Kennedy Dr, San Francisco',
    'Randall Museum': '199 Museum Way, San Francisco',
    'Noe Valley Recreation Center': '295 Day St, San Francisco',
    'Douglass Playground': 'Douglass St at 26th St, San Francisco',
    'The Interval at Long Now': '2 Marina Blvd, Fort Mason, San Francisco',
    'The Brixton': '2140 Union St, San Francisco',
    'Absinthe Brasserie & Bar': '398 Hayes St, San Francisco',
    'Valencia Street bars': 'Valencia St, San Francisco',
    'Embarcadero Center Cinema': '1 Embarcadero Center, San Francisco',
    'Firefly': '4288 24th St, San Francisco',
    'Marina Green brunch': 'Marina Blvd, San Francisco',
    'Golden Gate Park bike ride': 'Golden Gate Park, John F Kennedy Dr, San Francisco',
    'Dolores Park picnic': 'Dolores St at 19th St, San Francisco',
    'Embarcadero waterfront walk': 'Embarcadero at Market St, San Francisco',
    'Sausalito waterfront restaurants': 'Bridgeway, Sausalito',
    'Marin Headlands': 'Marin Headlands Visitor Center, Field Rd, Sausalito',
    "Swan's Market": '510 9th St, Oakland',
    'Shattuck Avenue cafes': 'Shattuck Ave, Berkeley',
    'North Beach trattorias': 'Columbus Ave, San Francisco',
    'Vesuvio Cafe': '255 Columbus Ave, San Francisco',
    'Exploratorium': 'Pier 15, The Embarcadero, San Francisco',
    'Serramonte Center food court': '3 Serramonte Center, Daly City',
}


def fill(apps, schema_editor):
    Activity = apps.get_model("planner", "Activity")
    for name, address in ADDRESSES.items():
        Activity.objects.filter(name=name, address="").update(address=address)


def clear(apps, schema_editor):
    Activity = apps.get_model("planner", "Activity")
    Activity.objects.filter(name__in=list(ADDRESSES)).update(address="")


class Migration(migrations.Migration):

    dependencies = [
        ("planner", "0008_agentmessage_plan_optional"),
    ]

    operations = [
        migrations.RunPython(fill, clear),
    ]
