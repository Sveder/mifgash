"""Matching rules. Plain Python, no model calls, so every rule has a unit test.

The LLM only reads the owner's words. Who gets asked, in which order, and what is
said to whom is decided here, by code that a judge can read and test.
"""
import math
import random

from django.db.models import Q

from . import hours as hours_mod
from . import wants as wants_mod
from .models import BASE_KIND, Activity, Friendship, Plan, Slot

# Default part of the day for each kind of plan.
# The demo world is San Francisco: the weekend is Saturday and Sunday (date.weekday() 5 and 6),
# the work week Monday to Friday (T395).
WEEKEND = (5, 6)

DEFAULT_PART = {"lunch": "lunch", "kids": "afternoon", "evening": "evening", "weekend": "morning",
                "group_dinner": "evening"}

# Kinds that a weekend / evening slot can host, for "other options".
KIND_FOR_PART = {"morning": "weekend", "lunch": "lunch", "afternoon": "kids", "evening": "evening"}


def base_kind(kind):
    """The kind a person's likes and the place list use: a group dinner is an evening (T227)."""
    return BASE_KIND.get(kind, kind)


def same_kinds(kind):
    """Kinds that fit each other in a match: an open evening fits a group dinner, and back (T227)."""
    base = base_kind(kind)
    return {base} | {k for k, b in BASE_KIND.items() if b == base}


def km(a, b):
    """Great-circle distance in km between two objects with .lat and .lon."""
    r = 6371.0
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp = p2 - p1
    dl = math.radians(b.lon - a.lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def slot_for(person, weekday, part):
    return Slot.objects.filter(person=person, weekday=weekday, part=part).select_related("area", "person__home_area").first()


def open_plan_for(person, plan):
    """The person's own open availability that fits the plan, or None.
    Fits = same date and part, same kind, and the two areas are within the smaller of the two radii.
    A plan with no part named (any_part, T79) fits every part of that date; a plan with the part
    named first. A 'not too far' place outside both radii is no match for now (brief item d)."""
    rows = (Plan.objects.filter(owner=person, status="open", date=plan.date)
            .filter(Q(part=plan.part, kind__in=same_kinds(plan.kind)) | Q(any_part=True))
            .exclude(pk=getattr(plan, "pk", None)).select_related("area").order_by("any_part", "created", "pk"))
    for q in rows:
        if km(q.area, plan.area) <= min(plan.radius_km, q.radius_km):
            return q
    return None


def meeting_area(p, q):
    """Where two matched availabilities meet. With two points each one is as near to both as
    the other (the sum of distances is the same), so the plan that was posted first wins: P."""
    return p.area


class Point:
    """A plain lat/lon point, for km()."""
    def __init__(self, lat, lon):
        self.lat, self.lon = lat, lon


def member_area(person, plan):
    """Where one member of a group dinner comes from on that day (G2, T228): the owner's plan
    area; a friend's own open time that fits; else the friend's weekly slot; else home."""
    if person.pk == plan.owner_id:
        return plan.area
    q = open_plan_for(person, plan)
    if q:
        return q.area
    slot = slot_for(person, plan.date.weekday(), plan.part)
    if slot and slot.where() is not None:
        return slot.where()
    return person.home_area or plan.area


def group_centre(plan, people):
    """The centre of the members' areas: the mean of the area centre points. Neighbourhood
    centres only, never a home address."""
    pts = [member_area(p, plan) for p in people]
    return Point(sum(a.lat for a in pts) / len(pts), sum(a.lon for a in pts) / len(pts))


def group_places(plan, people, limit=3):
    """Dinner places that take a group (tag 'group'), nearest to the centre of the members'
    areas first, then cheapest. With no such place, any evening place that serves food."""
    centre = group_centre(plan, people)
    when = plan_when(plan)
    every = [a for a in Activity.objects.filter(kind=base_kind(plan.kind)).select_related("area")
             if not is_closed(a, when)]  # T402
    rows = [a for a in every if "group" in (a.tags or [])]
    if not rows:
        rows = [a for a in every if {"dinner", "food"} & set(a.tags or [])]
    def dislikes(a):  # how many members dislike a tag of this place ('loud'): fewer first
        return sum(1 for p in people if set(p.dislikes or []) & set(a.tags or []))
    rows.sort(key=lambda a: (dislikes(a), round(km(a.area, centre), 1), a.price, a.name))
    return centre, rows[:limit]


def check_candidate(person, plan):
    """Return (ok, reason). The reason is for the operator log only.
    Two routes: the friend posted a fitting open availability, or a standing open slot fits."""
    if person.pk == plan.owner_id:
        return False, "owner"
    q = open_plan_for(person, plan)
    if q:
        return True, f"posted an open time, {km(q.area, plan.area):.1f} km away"
    slot = slot_for(person, plan.date.weekday(), plan.part)
    if not slot:
        return False, "not open at that time"
    if slot.where() is None:
        return False, "no area known"
    dist = km(slot.where(), plan.area)
    if dist > max(plan.radius_km, 0.1) or dist > person.max_km:
        return False, f"too far ({dist:.1f} km)"
    if person.has_agent and base_kind(plan.kind) not in person.likes:
        return False, f"does not want '{plan.kind}' plans"
    if plan.kind == "kids" and person.has_agent and not person.kids_ages:
        return False, "no kids"
    return True, f"open, {dist:.1f} km away"


def candidates(plan, people=None):
    """Friends (Friendship rows) who are open at that time, near that place, and want this kind of plan."""
    if people is None:
        people = Friendship.friends_of(plan.owner_id).select_related("home_area")
    out = []
    for p in people:
        ok, _ = check_candidate(p, plan)
        if ok:
            out.append(p)
    return out


def random_order(people, seed):
    """Uniform random order. No ranking by closeness or by 'best friend':
    a ranking would mean 'they preferred someone else'. The seed is kept for replay."""
    ordered = sorted(people, key=lambda p: p.pk)
    random.Random(seed).shuffle(ordered)
    return ordered


def plan_when(plan):
    """T402: (date, part) for the opening-hours check, or None. A plan with no part named
    ('I'm open tomorrow', any_part) fits any part, so no place is dropped for its hours."""
    if getattr(plan, "any_part", False) or not getattr(plan, "date", None):
        return None
    return plan.date, plan.part


def is_closed(a, when):
    """T402: True only when the hours say the place is surely closed then. Unknown = open."""
    return bool(when) and hours_mod.open_at(a.hours, *when) is False


def _near(kind, area, radius_km, exclude_tags, dislikes, when=None):
    rows = []
    group = kind != base_kind(kind)  # a group dinner wants a place that serves dinner (T227)
    for a in Activity.objects.filter(kind=base_kind(kind)).select_related("area"):
        if set(a.tags) & set(exclude_tags) or wants_mod.is_disliked(a, dislikes) or is_closed(a, when):
            continue
        d = km(a.area, area)
        if d <= radius_km + 1.0:
            food = bool({"dinner", "food"} & set(a.tags))
            # T265: a hackathon seed place comes before an imported OSM place at the same distance
            rows.append((group and not food, round(d, 1), a.source != "hackathon", a.price, a.name, a))
    rows.sort(key=lambda r: r[:5])
    return [r[5] for r in rows]


WIDE_KM = 6.0  # T255: no place with the asked food in the radius -> look this far


def place_options(plan, exclude_tags=(), note=None, limit=3):
    """T265: the place step for a new or changed plan. The top 8 candidates (wants, distance, price)
    go to the model, which picks ONE with a one-line why (llm.pick_place). The pick comes first, then
    the next best. The pick is kept in plan.wants['pick'] so option_list keeps it first.
    Saves plan.wants; the caller sets plan.options."""
    from . import llm
    rows = suggest_activities(plan.kind, plan.area, plan.radius_km, limit=llm.PICK_MAX,
                              exclude_tags=exclude_tags, wants=plan.wants, note=note, when=plan_when(plan))
    liked = next((a for a in rows if wants_mod.is_liked(a, plan.wants)), None)
    if liked is not None:
        # T376: a place one side named as liked goes first. A place the other side avoids is
        # already out of rows (_near drops the disliked), so no model call is needed here.
        res = {"place": liked, "why": "", "backend": "", "cause": "liked place"}
    else:
        res = llm.pick_place(plan, rows)
    place = res["place"]
    wants = {k: v for k, v in (plan.wants or {}).items() if k != "pick"}
    if place is not None:
        wants["pick"] = {"id": place.pk, "why": res["why"], "backend": res["backend"]}
        rows = [place] + [a for a in rows if a.pk != place.pk]
    plan.wants = wants
    if plan.pk:
        plan.save(update_fields=["wants"])
    return rows[:limit], res


def suggest_activities(kind, area, radius_km=3.0, limit=3, exclude_tags=(), wants=None, note=None, when=None):
    """Activities of that kind near the area. A place that fits the wants (liked place, food, taste
    words) comes first, then nearest, then cheapest. A disliked place never comes back (T255).
    note: a list; when the food asked for has no place even at WIDE_KM, one line is appended."""
    wants = wants or {}
    rows = _near(kind, area, radius_km, exclude_tags, wants.get("dislikes"), when)
    food = wants.get("food")
    if food and not any(wants_mod.food_match(a, food) for a in rows):
        wide = _near(kind, area, max(radius_km, WIDE_KM), exclude_tags, wants.get("dislikes"), when)
        hits = [a for a in wide if wants_mod.food_match(a, food)]
        if hits:
            rows = hits + [a for a in rows if a not in hits]
        elif note is not None:
            names = ", ".join(a.name for a in rows[:2])
            note.append(f"No {food} place near {area.name} yet" + (f"; nearest: {names}." if names else "."))
    if wants:
        rows.sort(key=lambda a: -wants_mod.score(a, wants))  # stable: distance order stays inside a score
    return rows[:limit]


def friend_decision(person, plan, options):
    """Simulated friend agent. Returns ('accept', activity) or ('decline', private_reason).
    The private reason never leaves the friend's agent."""
    if plan.group_size > 1 and person.one_on_one_only:
        return "decline", "prefers one on one"
    liked = [a for a in options if not (set(a.tags) & set(person.dislikes))]
    if not liked:
        return "decline", "none of the places fit"
    return "accept", liked[0]


def other_options(plan, horizon_days=7):
    """After 'did not work out': other times in the next week where at least one
    friend is open near the plan area. Returns [(date, part, kind, count)]. No names."""
    import datetime as dt
    out = []
    for i in range(1, horizon_days + 1):
        day = plan.date + dt.timedelta(days=i)
        for part in ("lunch", "evening", "morning", "afternoon"):
            kind = plan.kind if part == plan.part else KIND_FOR_PART[part]
            if kind == "kids" and not plan.owner.kids_ages:
                continue
            probe = type("Probe", (), {})()
            probe.owner_id, probe.date, probe.part = plan.owner_id, day, part
            probe.kind, probe.area, probe.radius_km, probe.group_size = kind, plan.area, plan.radius_km, 1
            n = len(candidates(probe))
            if n:
                out.append((day, part, kind, n))
    out.sort(key=lambda r: (r[1] != plan.part, r[0]))
    return out[:3]
