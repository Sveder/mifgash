"""Demo world: 14 areas, 1 owner, 8 friends, 33 activities.

All people are invented. Places are real public places in San Francisco, Sausalito,
Oakland, Berkeley and Daly City, typed in by hand during the hackathon (source='hackathon').
"""
from .models import Activity, AgentMessage, Area, ChatTurn, Friendship, Offer, Person, Plan, Slot

AREAS = [
    # name, city, lat, lon, aliases
    ("Noe Valley", "San Francisco", 37.7502, -122.4337, "noe valley,noe,home"),
    ("Financial District", "San Francisco", 37.7946, -122.3999, "financial district,fidi,embarcadero,ferry building"),
    ("Golden Gate Park", "San Francisco", 37.7694, -122.4862, "golden gate park,ggp,inner sunset"),
    ("Castro", "San Francisco", 37.7609, -122.4350, "castro,dolores,dolores park"),
    ("SoMa", "San Francisco", 37.7785, -122.4056, "soma,south of market,work,office,moscone"),
    ("Mission", "San Francisco", 37.7599, -122.4148, "mission,valencia,mission district"),
    ("Marina", "San Francisco", 37.8030, -122.4360, "marina,chestnut,cow hollow,palace of fine arts"),
    ("Hayes Valley", "San Francisco", 37.7759, -122.4245, "hayes valley,hayes,civic center"),
    ("Richmond", "San Francisco", 37.7800, -122.4650, "richmond,inner richmond,clement"),
] + [
    # Outside San Francisco (T31). Migration 0007 adds these rows to a live database; 0022 renames them.
    ("Sausalito", "Sausalito", 37.8591, -122.4853, "sausalito,marin"),
    ("Oakland - Downtown", "Oakland", 37.8044, -122.2712, "oakland,downtown oakland,jack london"),
    ("Berkeley - Downtown", "Berkeley", 37.8716, -122.2727, "berkeley,downtown berkeley,shattuck"),
    ("North Beach", "San Francisco", 37.8000, -122.4100, "north beach,little italy,columbus,telegraph hill,chinatown"),
    ("Daly City", "Daly City", 37.6879, -122.4702, "daly city,serramonte"),
]

# name, kind, area, price 0-3, tags, note
ACTIVITIES = [
    ("Ferry Building Marketplace", "lunch", "SoMa", 2, ["food hall", "asian", "sushi", "italian", "indoor"], "Many stalls, everyone finds something"),
    ("Souvla", "lunch", "Hayes Valley", 1, ["greek", "street food", "quick"], "Quick Greek wraps and salads"),
    ("La Taqueria", "lunch", "Mission", 1, ["mexican", "street food", "cheap"], "Famous burritos, quick"),
    ("Embarcadero Center lunch spots", "lunch", "Financial District", 1, ["food court", "indoor", "crowded"], "Indoor, many choices"),
    ("24th Street cafes", "lunch", "Noe Valley", 2, ["cafe", "coffee", "italian"], "Quiet cafes, good for talking"),
    ("Castro Street lunch spots", "lunch", "Castro", 1, ["cafe", "sandwich", "vegan"], "Neighbourhood lunch, short walk"),
    ("Arlequin Cafe", "lunch", "Hayes Valley", 1, ["cafe", "coffee", "outdoor", "sandwich", "quiet"], "Cafe with a quiet back garden"),
    ("Blue Bottle Coffee Hayes Valley", "lunch", "Hayes Valley", 1, ["coffee", "outdoor", "quick"], "Coffee and a pastry, sit in Patricia's Green"),

    ("Koret Children's Quarter", "kids", "Golden Gate Park", 0, ["park", "free", "playground"], "Free. Big playground and the carousel"),
    ("California Academy of Sciences", "kids", "Golden Gate Park", 3, ["museum", "paid", "animals"], "Paid entry, half a day"),
    ("Hayes Valley Playground", "kids", "Hayes Valley", 0, ["park", "free", "playground"], "Free, small playground"),
    ("Golden Gate Park", "kids", "Richmond", 0, ["park", "free", "bikes", "lake"], "Free. Lawns, boats on Stow Lake, bikes"),
    ("Randall Museum", "kids", "Castro", 1, ["municipal", "cheap", "science", "animals"], "City science museum with live animals"),
    ("Noe Valley Recreation Center", "kids", "Noe Valley", 1, ["municipal", "cheap", "indoor", "class"], "City classes and holiday activities"),
    ("Douglass Playground", "kids", "Noe Valley", 0, ["park", "free", "playground"], "Neighbourhood playground"),

    ("The Interval at Long Now", "evening", "Marina", 3, ["cocktails", "bar"], "Cocktail bar at Fort Mason"),
    ("The Brixton", "evening", "Marina", 3, ["cocktails", "bar", "loud"], "Bar and kitchen on Union St"),
    ("Absinthe Brasserie & Bar", "evening", "Hayes Valley", 2, ["bar", "food", "loud", "group"], "Busy brasserie and bar"),
    ("Valencia Street bars", "evening", "Mission", 1, ["bar", "beer", "cheap"], "Small cheap bars"),
    ("Embarcadero Center Cinema", "evening", "Financial District", 2, ["cinema", "indoor", "quiet"], "Movie, then a late bite"),
    ("Firefly", "evening", "Noe Valley", 2, ["wine", "dinner", "quiet"], "Quiet, close to home"),

    ("Marina Green brunch", "weekend", "Marina", 2, ["brunch", "outdoor", "sea"], "Brunch by the bay"),
    ("Golden Gate Park bike ride", "weekend", "Richmond", 0, ["bikes", "free", "outdoor"], "Rent a bike, ride the park"),
    ("Dolores Park picnic", "weekend", "Castro", 0, ["picnic", "free", "outdoor"], "Bring food, lie on the grass"),
    ("Embarcadero waterfront walk", "weekend", "SoMa", 1, ["walk", "coffee", "outdoor"], "Coffee and a slow walk"),
] + [
    # T31, also in migration 0007.
    ("Sausalito waterfront restaurants", "lunch", "Sausalito", 2, ["seafood", "sea", "outdoor"], "Lunch by the water"),
    ("Marin Headlands", "weekend", "Sausalito", 1, ["park", "sea", "walk"], "Cliff walk with a view of the bridge"),
    ("Swan's Market", "lunch", "Oakland - Downtown", 1, ["food hall", "cafe", "sandwich"], "Food hall lunch, quick"),
    ("Shattuck Avenue cafes", "lunch", "Berkeley - Downtown", 2, ["cafe", "coffee", "quiet"], "Quiet main-street cafes"),
    ("North Beach trattorias", "lunch", "North Beach", 1, ["italian", "pizza", "cheap"], "Small Italian places on Columbus Ave"),
    ("Vesuvio Cafe", "evening", "North Beach", 2, ["bar", "historic", "outdoor"], "Old bar next to City Lights"),
    # G2 (T228): dinner places with big tables, for a group dinner. Migration 0028 adds them live.
    ("The Stinking Rose", "evening", "North Beach", 2, ["dinner", "group", "italian", "garlic"], "The garlic restaurant, big tables"),
    ("Zuni Cafe", "evening", "Hayes Valley", 3, ["dinner", "group", "californian"], "Big room, takes group bookings"),
    ("Foreign Cinema", "evening", "Mission", 3, ["dinner", "group", "outdoor"], "Courtyard dinner, long tables"),
    ("Exploratorium", "kids", "Financial District", 3, ["museum", "paid", "indoor"], "Paid, book ahead"),
    ("Serramonte Center food court", "lunch", "Daly City", 1, ["food court", "indoor", "sandwich"], "Simple mall lunch"),
]

# Street address per activity (T45; San Francisco world since T192). Public places only.
# A street with no number means the place spans the street. Migration 0022 writes these to a live database.
ADDRESSES = {
    "Ferry Building Marketplace": "1 Ferry Building, San Francisco",
    "Souvla": "517 Hayes St, San Francisco",
    "La Taqueria": "2889 Mission St, San Francisco",
    "Embarcadero Center lunch spots": "4 Embarcadero Center, San Francisco",
    "24th Street cafes": "24th St, Noe Valley, San Francisco",
    "Castro Street lunch spots": "Castro St at 18th St, San Francisco",
    "Arlequin Cafe": "384 Hayes St, San Francisco",
    "Blue Bottle Coffee Hayes Valley": "315 Linden St, San Francisco",
    "Koret Children's Quarter": "320 Bowling Green Dr, Golden Gate Park, San Francisco",
    "California Academy of Sciences": "55 Music Concourse Dr, San Francisco",
    "Hayes Valley Playground": "Hayes St at Buchanan St, San Francisco",
    "Golden Gate Park": "Golden Gate Park, John F Kennedy Dr, San Francisco",
    "Randall Museum": "199 Museum Way, San Francisco",
    "Noe Valley Recreation Center": "295 Day St, San Francisco",
    "Douglass Playground": "Douglass St at 26th St, San Francisco",
    "The Interval at Long Now": "2 Marina Blvd, Fort Mason, San Francisco",
    "The Brixton": "2140 Union St, San Francisco",
    "Absinthe Brasserie & Bar": "398 Hayes St, San Francisco",
    "Valencia Street bars": "Valencia St, San Francisco",
    "Embarcadero Center Cinema": "1 Embarcadero Center, San Francisco",
    "Firefly": "4288 24th St, San Francisco",
    "Marina Green brunch": "Marina Blvd, San Francisco",
    "Golden Gate Park bike ride": "Golden Gate Park, John F Kennedy Dr, San Francisco",
    "Dolores Park picnic": "Dolores St at 19th St, San Francisco",
    "Embarcadero waterfront walk": "Embarcadero at Market St, San Francisco",
    "Sausalito waterfront restaurants": "Bridgeway, Sausalito",
    "Marin Headlands": "Marin Headlands Visitor Center, Field Rd, Sausalito",
    "Swan's Market": "510 9th St, Oakland",
    "Shattuck Avenue cafes": "Shattuck Ave, Berkeley",
    "North Beach trattorias": "Columbus Ave, San Francisco",
    "Vesuvio Cafe": "255 Columbus Ave, San Francisco",
    "The Stinking Rose": "325 Columbus Ave, San Francisco",
    "Zuni Cafe": "1658 Market St, San Francisco",
    "Foreign Cinema": "2534 Mission St, San Francisco",
    "Exploratorium": "Pier 15, The Embarcadero, San Francisco",
    "Serramonte Center food court": "3 Serramonte Center, Daly City",
}

# Parking line per activity for the calendar invite (T7). Only facts known for sure; any other
# place says 'Street parking'. Migration 0022 writes these to a live database.
PARKING = {
    "Ferry Building Marketplace": "Paid garage at Embarcadero Center",
    "Embarcadero Center lunch spots": "Paid garage at Embarcadero Center",
    "Embarcadero Center Cinema": "Paid garage at Embarcadero Center",
    "Embarcadero waterfront walk": "Paid garage at Embarcadero Center",
    "California Academy of Sciences": "Paid Music Concourse garage",
    "Koret Children's Quarter": "Paid Music Concourse garage",
    "Golden Gate Park": "Paid Music Concourse garage",
    "Golden Gate Park bike ride": "Paid Music Concourse garage",
    "Exploratorium": "Paid lots on the Embarcadero",
    "Sausalito waterfront restaurants": "Paid lot at the ferry terminal",
    "Serramonte Center food court": "Free parking lot at the mall",
    # T219: the Hayes Valley lunch places; migration 0026 writes these to a live database.
    "Souvla": "Street parking, or the paid Performing Arts Garage at 360 Grove St",
    "Arlequin Cafe": "Street parking, or the paid Performing Arts Garage at 360 Grove St",
    "Blue Bottle Coffee Hayes Valley": "Street parking, or the paid Performing Arts Garage at 360 Grove St",
    # G2 (T228); migration 0028 writes these to a live database.
    "The Stinking Rose": "Street parking is hard; the paid North Beach Garage at 735 Vallejo St",
    "Zuni Cafe": "Street parking, or the paid Performing Arts Garage at 360 Grove St",
}

# name, has_agent, home, work, likes, dislikes, max_km, one_on_one, kids, slots[(weekday, part, area or None)]
# weekday: 0 Mon ... 3 Thu, 4 Fri, 5 Sat, 6 Sun
PEOPLE = [
    ("Alex", True, "Castro", "SoMa", ["lunch", "kids"], ["crowded"], 4, False, [4, 7],
     [(6, "lunch", "SoMa"), (1, "lunch", "SoMa"), (3, "evening", None), (4, "morning", None), (1, "afternoon", None)]),
    ("Lucas", True, "Marina", "SoMa", ["lunch", "evening"], [], 5, False, [],
     [(6, "lunch", "SoMa"), (0, "lunch", "SoMa"), (2, "evening", None), (3, "evening", None)]),
    ("Priya", True, "Financial District", "Financial District", ["lunch", "evening", "weekend"], ["cheap"], 5, False, [],
     [(6, "lunch", None), (3, "evening", None), (5, "morning", None), (1, "lunch", None)]),
    ("Mateo", False, "Mission", "Hayes Valley", [], [], 6, False, [],
     [(3, "evening", None), (5, "morning", None), (6, "lunch", "Hayes Valley")]),
    ("Sofia", True, "Golden Gate Park", None, ["kids", "weekend"], ["paid"], 4, False, [5],
     [(4, "morning", None), (5, "morning", None), (1, "afternoon", None), (3, "afternoon", None)]),
    ("Ethan", True, "Marina", "SoMa", ["lunch"], ["loud"], 4, True, [],
     [(6, "lunch", "SoMa"), (2, "lunch", "SoMa")]),
    ("Jordan", False, "Richmond", None, [], [], 5, False, [6],
     [(6, "lunch", None), (5, "morning", None), (4, "morning", None)]),
    ("Maria", True, "Castro", None, ["evening", "kids", "weekend"], [], 5, False, [7],
     [(3, "evening", None), (5, "morning", None), (6, "lunch", None), (4, "morning", None)]),
]

# The demo owner is an invented person, never the real user (T114: the real user signs up as himself).
OWNER = ("Emma", "Noe Valley", "SoMa", ["lunch", "kids", "evening", "weekend"], [5, 8],
         [(6, "lunch", "SoMa"), (3, "evening", None), (4, "morning", None), (5, "morning", None),
          (1, "afternoon", None), (2, "lunch", "SoMa")])


def reset_demo():
    """Delete plans and chat only. People, places and slots stay."""
    AgentMessage.objects.all().delete()
    Offer.objects.all().delete()
    Plan.objects.all().delete()
    ChatTurn.objects.all().delete()


def seed(wipe=False):
    if wipe:
        reset_demo()
        Slot.objects.all().delete()
        Person.objects.all().delete()
        Activity.objects.all().delete()
        Area.objects.all().delete()
    areas = {}
    for name, city, lat, lon, aliases in AREAS:
        areas[name], _ = Area.objects.update_or_create(
            name=name, defaults={"city": city, "lat": lat, "lon": lon, "aliases": aliases})
    for name, kind, area, price, tags, note in ACTIVITIES:
        Activity.objects.update_or_create(
            name=name, defaults={"kind": kind, "area": areas[area], "price": price, "tags": tags, "note": note,
                                 "address": ADDRESSES[name],
                                 "parking": PARKING.get(name, "Street parking")})

    def person(name, has_agent, home, work, likes, dislikes, max_km, one, kids, slots, owner=False):
        p, _ = Person.objects.update_or_create(handle=name.lower(), defaults=dict(name=name,
            is_owner=owner, has_agent=has_agent, home_area=areas[home], work_area=areas[work] if work else None,
            likes=likes, dislikes=dislikes, max_km=max_km, one_on_one_only=one, kids_ages=kids))
        p.slots.all().delete()
        for wd, part, a in slots:
            Slot.objects.create(person=p, weekday=wd, part=part, area=areas[a] if a else None)
        return p

    oname, ohome, owork, olikes, okids, oslots = OWNER
    owner = person(oname, True, ohome, owork, olikes, [], 6, False, okids, oslots, owner=True)
    for row in PEOPLE:
        Friendship.link(owner, person(*row), source="seed")
    return owner


def demo_friends():
    """The seeded demo friends (not the owner). The Facebook import stub links these."""
    return Person.objects.filter(handle__in=[row[0].lower() for row in PEOPLE])
