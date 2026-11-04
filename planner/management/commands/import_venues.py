"""Bigger venue list from OpenStreetMap (T265, F6b).

  manage.py import_venues                    fetch Overpass for every area, write the fixture, load it
  manage.py import_venues --dry-run          fetch and print counts, write nothing
  manage.py import_venues --file F           load a fixture only (deploy.sh; no network)
  manage.py import_venues --overpass-json F --area NAME   parse one saved Overpass answer (tests)

Each OSM place goes to the NEAREST area centre only, so two areas never share a row. Per area at most
40 places: 22 food places (restaurant, cafe), 10 drink places (bar, pub), 4 parks (2 rows each: kids and
weekend). A restaurant has 2 rows too: lunch, and evening with the tags 'dinner' and 'food' (T324), so a
dinner plan gets a restaurant, not only bars. OSM diet:vegetarian / diet:vegan (yes or only) become the
tags 'vegetarian' / 'vegan' (a vegan place is vegetarian too). Places with a cuisine tag and a street address come first. A load matches on name + area +
kind, so a second load updates rows and makes no duplicates. Hackathon seed rows are never changed.
The data is (c) OpenStreetMap contributors, ODbL.
"""
import json
import math
import time
import urllib.parse
import urllib.request
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from planner.models import Activity, Area
from planner import hours as hours_mod

OVERPASS = "https://overpass-api.de/api/interpreter"
FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "osm_venues.json"
RADIUS_M = 2000
CAPS = {"food": 22, "drink": 10, "park": 4, "fun": 4}
# T401: fast_food and ice_cream are lunch / kids places; a playground is a kids outing; a museum is a
# weekend outing and a kids outing.
KIND = {"restaurant": "lunch", "cafe": "lunch", "bar": "evening", "pub": "evening", "fast_food": "lunch",
        "ice_cream": "kids"}
PRICE = {"restaurant": 2, "cafe": 1, "bar": 2, "pub": 1, "park": 0, "fast_food": 1, "ice_cream": 1,
         "playground": 0, "museum": 2}
EXTRA_TAGS = {"cafe": ["cafe", "coffee"], "bar": ["bar"], "pub": ["bar", "beer"],
              "park": ["park", "free", "outdoor"], "fast_food": ["quick"], "ice_cream": ["ice cream", "dessert"],
              "playground": ["playground", "free", "outdoor"], "museum": ["museum", "indoor"]}
BUCKET = {"restaurant": "food", "cafe": "food", "fast_food": "food", "bar": "drink", "pub": "drink",
          "park": "park", "playground": "park", "ice_cream": "fun", "museum": "fun"}


def query(area, radius_m=RADIUS_M):
    around = f"around:{radius_m},{area.lat},{area.lon}"
    return (f'[out:json][timeout:50];'
            f'nwr["amenity"~"^(restaurant|cafe|fast_food)$"]["name"]({around});out center tags 120;'
            f'nwr["amenity"~"^(bar|pub)$"]["name"]({around});out center tags 60;'
            f'nwr["amenity"="ice_cream"]["name"]({around});out center tags 15;'
            f'nwr["leisure"~"^(park|playground)$"]["name"]({around});out center tags 30;'
            f'nwr["tourism"="museum"]["name"]({around});out center tags 15;')


def fetch(area, tries=3, pause=20, radius_m=RADIUS_M, timeout=90, pauses=None, retry=None):
    """One Overpass call per area. A 502/503/504/429 ('at capacity') gets 2 more tries.
    `pauses` gives the wait before each retry; `retry(e)` False stops at once (T401: only 429/502/504)."""
    data = urllib.parse.urlencode({"data": query(area, radius_m)}).encode()
    pauses = list(pauses) if pauses is not None else [pause] * (tries - 1)
    last = None
    for i in range(len(pauses) + 1):
        req = urllib.request.Request(OVERPASS, data=data, headers={"User-Agent": "Mifgash/1.0 (+https://mifgash.sveder.com)"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except Exception as e:  # HTTPError, timeout, bad JSON
            last = e
            if i < len(pauses) and (retry is None or retry(e)):
                time.sleep(pauses[i])
            else:
                break
    raise CommandError(f"Overpass failed for {area.name}: {last}")


def kind_key_of(t):
    """The OSM tag that picks the venue type, or None."""
    if t.get("amenity") in KIND:
        return t["amenity"]
    if t.get("leisure") in ("park", "playground"):
        return t["leisure"]
    if t.get("tourism") == "museum":
        return "museum"
    return None


def _dist(lat1, lon1, lat2, lon2):
    x = math.radians(lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(x, math.radians(lat2 - lat1)) * 6371.0


def _point(el):
    if "lat" in el:
        return el["lat"], el["lon"]
    c = el.get("center") or {}
    return c.get("lat"), c.get("lon")


def _words(raw):
    return [w.strip().replace("_", " ").lower() for w in str(raw or "").split(";") if w.strip()]


def diet_tags(t):
    """T324: OSM diet:* keys -> tags. 'yes' or 'only' counts; a vegan place is vegetarian too."""
    out = []
    if t.get("diet:vegan") in ("yes", "only"):
        out += ["vegan", "vegetarian"]
    if t.get("diet:vegetarian") in ("yes", "only") and "vegetarian" not in out:
        out.append("vegetarian")
    return out


def entries_from(data, area, areas=None, source="osm"):
    """Overpass JSON -> venue dicts for one area. With `areas`, a place nearer another area centre
    is dropped (that area's own query gets it)."""
    areas = list(areas or [area])
    picked = {b: [] for b in CAPS}
    seen = set()
    for el in data.get("elements", []):
        t = el.get("tags") or {}
        name = " ".join((t.get("name") or "").split())[:80]
        kind_key = kind_key_of(t)
        lat, lon = _point(el)
        if not name or not kind_key or lat is None or name.lower() in seen:
            continue
        nearest = min(areas, key=lambda a: _dist(lat, lon, a.lat, a.lon))
        if nearest.name != area.name:
            continue
        seen.add(name.lower())
        tags = []
        for w in _words(t.get("cuisine")) + EXTRA_TAGS.get(kind_key, []):
            if w not in tags:
                tags.append(w)
        if t.get("outdoor_seating") == "yes" and "outdoor" not in tags:
            tags.append("outdoor")
        for diet in diet_tags(t):
            if diet not in tags:
                tags.insert(0, diet)  # before the cap of 8 tags, so a diet tag is never cut
        street = t.get("addr:street", "")
        address = " ".join(x for x in (t.get("addr:housenumber", ""), street) if x)[:120]
        hours = t.get("opening_hours", "")
        note = (f"Hours: {hours}" if hours else "From OpenStreetMap")[:160]
        url = t.get("website", "")
        url = url if url.startswith(("http://", "https://")) and len(url) <= 200 else ""
        rank = (not t.get("cuisine"), not street, round(_dist(lat, lon, area.lat, area.lon), 2))
        bucket = BUCKET[kind_key]
        base = {"name": name, "area": area.name, "address": address, "tags": tags[:8], "note": note,
                "hours": hours if len(hours) <= 120 else "",
                "url": url, "price": PRICE[kind_key], "source": source, "osm": f"{el['type']}/{el['id']}"}
        picked[bucket].append((rank, base, kind_key))
    out = []
    for bucket, rows in picked.items():
        rows.sort(key=lambda r: r[0])
        for _, base, kind_key in rows[:CAPS[bucket]]:
            if kind_key in ("park", "museum"):  # a park or a museum is a kids outing and a weekend outing
                out.append({**base, "kind": "kids", "tags": base["tags"] + ["kids"]})
                out.append({**base, "kind": "weekend"})
            elif kind_key == "playground":
                out.append({**base, "kind": "kids", "tags": base["tags"] + ["kids"]})
            else:
                out.append({**base, "kind": KIND[kind_key]})
                if kind_key == "restaurant":  # T324: a restaurant serves dinner plans too
                    extra = [w for w in ("dinner", "food") if w not in base["tags"]]
                    out.append({**base, "kind": "evening", "tags": base["tags"] + extra})
    return out


@transaction.atomic
def load(entries):
    """Write venue dicts to Activity rows. Match on name + area + kind; a hackathon or seed row with
    that key is left as it is. Returns (made, updated, skipped)."""
    areas = {a.name: a for a in Area.objects.all()}
    made = updated = skipped = 0
    for e in entries:
        area = areas.get(e["area"])
        if area is None:
            skipped += 1
            continue
        row = Activity.objects.filter(name=e["name"], area=area, kind=e["kind"]).first()
        hours = e.get("hours") or hours_mod.hours_from_note(e.get("note", ""))  # T402: an old fixture has the note only
        fields = {"address": e.get("address", ""), "tags": e.get("tags", []), "note": e.get("note", "")[:160],
                  "hours": hours,
                  "url": e.get("url", ""), "price": e.get("price", 1), "source": e.get("source", "osm")}
        if row is None:
            Activity.objects.create(name=e["name"], area=area, kind=e["kind"], **fields)
            made += 1
        elif row.source in ("osm", "osm-live", "seed"):
            for k, v in fields.items():
                setattr(row, k, v)
            row.save()
            updated += 1
        else:
            skipped += 1
    return made, updated, skipped


class Command(BaseCommand):
    help = "Import SF bay venues from OpenStreetMap Overpass, or load the saved fixture."

    def add_arguments(self, parser):
        parser.add_argument("--file", help="load this fixture only, no network")
        parser.add_argument("--overpass-json", help="parse this saved Overpass answer (needs --area)")
        parser.add_argument("--area", help="area name for --overpass-json, or fetch this area only")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--out", default=str(FIXTURE), help="fixture path to write")

    def handle(self, *args, **o):
        if o["file"]:
            entries = json.loads(Path(o["file"]).read_text())["venues"]
            return self._load(entries, o["dry_run"])
        areas = list(Area.objects.all())
        if o["overpass_json"]:
            area = next((a for a in areas if a.name == o["area"]), None)
            if area is None:
                raise CommandError(f"unknown area: {o['area']}")
            entries = entries_from(json.loads(Path(o["overpass_json"]).read_text()), area, areas)
            return self._load(entries, o["dry_run"])
        todo = [a for a in areas if not o["area"] or a.name == o["area"]]
        entries, failed = [], []
        for i, area in enumerate(todo):
            if i:
                time.sleep(5)  # be kind to the public Overpass server
            try:
                rows = entries_from(fetch(area), area, areas)
            except CommandError as e:
                failed.append(area.name)
                self.stderr.write(str(e))
                continue
            entries += rows
            self.stdout.write(f"{area.name}: {len(rows)} rows from Overpass")
        if failed:
            self.stdout.write("Overpass failed for: " + ", ".join(failed))
        if not o["dry_run"]:
            out = Path(o["out"])
            if o["area"] and out.exists():  # one area: keep the other areas' rows in the fixture
                old = json.loads(out.read_text())
                if not failed:
                    entries = [e for e in old["venues"] if e["area"] != o["area"]] + entries
                    failed = [a for a in old.get("failed_areas", []) if a != o["area"]]
                else:
                    entries, failed = old["venues"], old.get("failed_areas", [])
            Path(o["out"]).parent.mkdir(parents=True, exist_ok=True)
            Path(o["out"]).write_text(json.dumps(
                {"source": "(c) OpenStreetMap contributors, ODbL; Overpass API",
                 "fetched": time.strftime("%Y-%m-%d"), "failed_areas": failed, "venues": entries},
                ensure_ascii=False, indent=1) + "\n")
            self.stdout.write(f"wrote {len(entries)} rows to {o['out']}")
        self._load(entries, o["dry_run"])

    def _load(self, entries, dry_run):
        if dry_run:
            self.stdout.write(f"dry run: {len(entries)} rows, nothing written")
            return
        made, updated, skipped = load(entries)
        self.stdout.write(f"loaded: {made} new, {updated} updated, {skipped} skipped")
