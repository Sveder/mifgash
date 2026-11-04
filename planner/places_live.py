"""Any-city places (T401): the live place lookup that the tick runs.

A free time in a city Mifgash does not cover makes a plan in status 'finding_places' and one queued
PlaceLookup row (T400). Each tick, run_queued():
  1. takes at most 2 queued lookups, oldest first;
  2. geocodes the city text with Nominatim (1 request a second, the Mifgash User-Agent, no email);
  3. asks Overpass for venues within 3 km and loads them as Activity rows with source 'osm-live';
  4. makes the Area and moves every waiting plan for that city to 'open', so matching goes on
     at the next rematch_open exactly as in San Francisco.
On a final failure the lookup is 'failed', and each waiting plan is cancelled with the ask-back text
pushed to the owner's agent. A city with a done lookup never calls the APIs again.
The data is (c) OpenStreetMap contributors, ODbL.
"""
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request

from django.db import transaction
from django.utils import timezone

from . import engine
from .management.commands import import_venues
from .models import Area, PlaceLookup, Plan

log = logging.getLogger(__name__)

NOMINATIM = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "Mifgash/1.0 (+https://mifgash.sveder.com)"
TIMEOUT = 25  # Nominatim
# Overpass: the query asks the server for up to 50 s ([timeout:50]); a live Flagstaff query took
# 28.6 s from the droplet on 4/11, so a 25 s read timeout failed all 3 tries (T396).
OVERPASS_TIMEOUT = 60
PAUSES = (5, 15)  # wait before retry 1 and retry 2
RETRY_CODES = (429, 502, 504)
RADIUS_M = 3000
PER_TICK = 2
MAX_TRIES = 3  # a failed lookup is queued again by a new free time until it failed this often
sleep = time.sleep  # tests replace it


class LookupFailed(Exception):
    pass


def _retry(e):
    if isinstance(e, urllib.error.HTTPError):
        return e.code in RETRY_CODES
    return isinstance(e, (TimeoutError, urllib.error.URLError))


def geocode(text):
    """The first Nominatim hit for the text: {'lat', 'lon', 'display_name', 'address'}, or None."""
    q = urllib.parse.urlencode({"q": text, "format": "json", "limit": 1, "addressdetails": 1})
    req = urllib.request.Request(f"{NOMINATIM}?{q}", headers={"User-Agent": USER_AGENT})
    last = None
    for i in range(len(PAUSES) + 1):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                rows = json.load(r)
            return rows[0] if rows else None
        except Exception as e:
            last = e
            if i < len(PAUSES) and _retry(e):
                sleep(PAUSES[i])
            else:
                break
    raise LookupFailed(f"Nominatim failed for {text}: {last}")


def area_fields(hit):
    """(name, city, lat, lon) from a Nominatim hit: 'Flagstaff, Arizona' for a US city."""
    parts = [p.strip() for p in (hit.get("display_name") or "").split(",") if p.strip()]
    addr = hit.get("address") or {}
    city = (addr.get("city") or addr.get("town") or addr.get("village") or (parts[0] if parts else "")).strip()
    region = (addr.get("state") or addr.get("country") or (parts[-1] if len(parts) > 1 else "")).strip()
    first = parts[0] if parts else city
    name = f"{first}, {region}" if region and region.lower() != first.lower() else first
    return name[:80], (city or first)[:40], float(hit["lat"]), float(hit["lon"])


def fetch_venues(area):
    """Overpass venues within 3 km of the area centre as import_venues entry dicts, source 'osm-live'."""
    try:
        data = import_venues.fetch(area, radius_m=RADIUS_M, timeout=OVERPASS_TIMEOUT, pauses=PAUSES, retry=_retry)
    except import_venues.CommandError as e:
        raise LookupFailed(str(e))
    return import_venues.entries_from(data, area, source="osm-live")


def look_up(lookup):
    """Geocode, make or reuse the Area, load the venues. Returns (area, venue count)."""
    hit = geocode(lookup.city_text)
    if hit is None:
        raise LookupFailed(f"no place called {lookup.city_text} on OpenStreetMap")
    name, city, lat, lon = area_fields(hit)
    area = Area.objects.filter(name=name).first()
    if area is not None and area.activity_set.exists():
        return area, area.activity_set.count()  # 'flagstaff az' after 'flagstaff': no Overpass call
    probe = area or Area(name=name, city=city, lat=lat, lon=lon)
    entries = fetch_venues(probe)
    if not entries:
        raise LookupFailed(f"no venues near {name} on OpenStreetMap")
    with transaction.atomic():
        if area is None:
            area = Area.objects.create(name=name, city=city, lat=lat, lon=lon, aliases=lookup.text_norm[:200])
        import_venues.load(entries)
    return area, area.activity_set.count()


def waiting(lookup):
    return [p for p in Plan.objects.filter(status="finding_places").select_related("owner").order_by("pk")
            if PlaceLookup.norm(p.place_text) == lookup.text_norm]


def found_text(n, city):
    return f"Found {n} places in {city}. Looking for friends."


def ask_back_text(plan):
    from .api import COVERS_TEXT, area_suggestions
    return (f"Mifgash could not find places in {plan.place_text}. {COVERS_TEXT} "
            f"Pick an area, for example {', '.join(area_suggestions(plan.owner))}, and post the free time again.")


def release(lookup):
    """Move the waiting plans for a done or failed lookup on. Returns the plan ids."""
    ids = []
    for plan in waiting(lookup):
        if lookup.status == "done" and lookup.area_id:
            n = lookup.area.activity_set.count()
            plan.area = lookup.area
            plan.status = "open"
            plan.save(update_fields=["area", "status"])
            text = found_text(n, lookup.area.city or plan.place_text)
            engine.log(plan, "mifgash:directory", plan.owner.address, "places_found",
                       area=lookup.area.name, places=n, text=text)
            engine.notify(plan.owner, "availability.open", plan, text=text)
        elif lookup.status == "failed":
            text = ask_back_text(plan)
            plan.status = "cancelled"
            plan.save(update_fields=["status"])
            engine.log(plan, "mifgash:directory", plan.owner.address, "places_failed",
                       error=lookup.error[:200], text=text)
            engine.notify(plan.owner, "outing.closed", plan, outcome="no_places", text=text,
                          needs=["where"], unknown_place=plan.place_text)
        else:
            continue
        ids.append(plan.pk)
    return ids


def run_queued(now=None):
    """The tick step: at most PER_TICK queued lookups, oldest first, then release every plan that
    waits on a lookup that is done or failed. Never raises. Returns {lookup text: status}."""
    out = {}
    for i, lookup in enumerate(PlaceLookup.objects.filter(status="queued").order_by("added", "pk")[:PER_TICK]):
        if i:
            sleep(1)  # Nominatim policy: at most 1 request a second
        lookup.tries += 1
        try:
            area, n = look_up(lookup)
            lookup.status, lookup.area, lookup.error = "done", area, ""
        except Exception as e:  # LookupFailed, bad JSON, a database error
            log.warning("place lookup %s failed: %s", lookup.text_norm, e)
            lookup.status, lookup.error = "failed", str(e)[:500]
        lookup.save()
        out[lookup.text_norm] = lookup.status
    if not Plan.objects.filter(status="finding_places").exists():
        return out
    for lookup in PlaceLookup.objects.filter(status__in=("done", "failed")).select_related("area"):
        try:
            release(lookup)
        except Exception:
            log.exception("release of lookup %s failed", lookup.text_norm)
    return out
