"""Agent API, version 1 (mounted at /api/v1/). New hackathon work (28/10/2026).

Every reply is JSON. An agent sends 'Authorization: Bearer mif_...'. Only an HMAC of the key
is stored (AgentKey); the plain key is in the signup reply once and never again.
"""
import datetime as dt
import functools
import json
import logging
import re
import time
import types

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from . import calendar, demo, engine, finalize, llm, matching, messages, push, ratelimit
from .ratelimit import limit
from .agent import infer
from .models import GROUP_MAX, KINDS, PARTS, AgentEvent, AgentKey, AgentMessage, Area, Friendship, Invite, MagicLink, Offer, Person, Plan, Slot, EMAIL_NEEDED, clean_email, clean_handle, clean_name
from .seed import demo_friends

log = logging.getLogger(__name__)


def error(status, message, **extra):
    return JsonResponse({"error": message, **extra}, status=status)


def json_body(request):
    """The request body as a dict. Raises ValueError on bad JSON."""
    if not request.body:
        return {}
    data = json.loads(request.body)
    if not isinstance(data, dict):
        raise ValueError("body must be a JSON object")
    return data


def api_view(methods):
    """JSON in, JSON out: 405 on a wrong method, 400 on bad JSON, 500 as JSON, never an HTML page."""
    def wrap(view):
        @csrf_exempt
        @functools.wraps(view)
        def inner(request, *args, **kwargs):
            if request.method not in methods:
                return error(405, "method not allowed", allowed=methods)
            slow = ratelimit.check(request, "api", ip=(settings.RATE_API_PER_MIN, 60))
            if slow:
                return slow
            try:
                return view(request, *args, **kwargs)
            except ValueError as e:
                return error(400, f"bad request: {e}")
            except Exception:
                log.exception("api error on %s", request.path)
                return error(500, "server error")
        return inner
    return wrap


def agent_required(view):
    """Check the bearer key. Sets request.person and request.agent_key."""
    @functools.wraps(view)
    def inner(request, *args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth:
            return error(401, "no key")
        scheme, _, plain = auth.partition(" ")
        row = AgentKey.authenticate(plain.strip()) if scheme.lower() == "bearer" else None
        if not row:
            return error(401, "bad key")
        request.agent_key = row
        request.person = row.person
        return view(request, *args, **kwargs)
    return inner


def find_area(text):
    """An Area by exact name or by one alias word, or None."""
    t = (text or "").strip().lower()
    if not t:
        return None
    for a in Area.objects.all():
        if a.name.lower() == t or t in [w.strip().lower() for w in a.aliases.split(",") if w.strip()]:
            return a
    return None


def area_fits(text):
    """Areas for a typed place: [the one area] for an exact name or alias, else every area whose
    name or city holds the text as whole words ('Downtown' -> the 2 Downtown areas,
    'San Francisco' -> the San Francisco areas), by name."""
    exact = find_area(text)
    if exact:
        return [exact]
    t = " ".join((text or "").lower().split())
    if len(t) < 3:
        return []
    word = re.compile(r"(?<!\w)" + re.escape(t) + r"(?!\w)")
    return [a for a in Area.objects.order_by("name") if word.search(a.name.lower()) or word.search(a.city.lower())]


def person_json(p):
    """What the agent may see about its own person. Never the webhook secret."""
    return {
        "person_id": p.pk,
        "handle": p.handle,
        "name": p.name,
        "has_agent": p.has_agent,
        "home_area": p.home_area.name if p.home_area else None,
        "work_area": p.work_area.name if p.work_area else None,
        "webhook": bool(p.webhook_url),
        "webhook_format": p.webhook_format,
        "has_email": bool(p.email),
    }


HOOK_FORMATS = ("mifgash", "openclaw")


def hook_fields(data):
    """The agent's push settings from a signup or PATCH /me/ body: (fields, None) or (None, error reply).
    hook_url, hook_token and hook_format are aliases of webhook_url, webhook_secret and webhook_format
    (T98). Only the keys the body names go into fields; an empty url turns the push off."""
    def pick(*keys):
        for k in keys:
            if k in data:
                return str(data.get(k) or "").strip()
        return None
    url, secret, fmt = pick("webhook_url", "hook_url"), pick("webhook_secret", "hook_token"), pick("webhook_format", "hook_format")
    fields = {}
    if fmt is not None:
        if fmt not in HOOK_FORMATS:
            return None, error(400, "unknown webhook_format", allowed=list(HOOK_FORMATS))
        fields["webhook_format"] = fmt
    if url is not None:
        if url:
            try:
                push.check_url(url)
            except push.Refused as e:
                return None, error(400, "webhook_url must be a public https URL", reason=str(e))
            if secret is None or len(secret) < 8:
                return None, error(400, "webhook_secret (8 characters or more) is required with webhook_url; "
                                        "we sign every push with it (format openclaw: the gateway hook token)")
            fields.update(webhook_url=url, webhook_secret=secret)
        else:
            fields.update(webhook_url="", webhook_secret="")
    elif secret is not None:
        if len(secret) < 8:
            return None, error(400, "webhook_secret must be 8 characters or more")
        fields["webhook_secret"] = secret
    return fields, None


POLL_HOURS = 2
POLL_NOTE = (f"Make a scheduled job now: every {POLL_HOURS} hours, GET /api/v1/events/?after=<last_id> and tell "
             "your human each new event. No new events: tell your human nothing. A webhook only makes the news "
             "come sooner.")


def dashboard_url(request, token):
    return calendar.public_base(request) + reverse("dashboard_link", args=[token])


@api_view(["POST"])
@limit("signup", ip=(10, 3600))
def signup(request):
    data = json_body(request)
    try:
        name = clean_name(data.get("name"))
    except ValidationError as e:
        return error(400, e.messages[0])
    try:
        handle = clean_handle(data.get("handle"))
    except ValidationError as e:
        return error(400, e.messages[0])
    # F3a (T259): an email is required; it is the only way back in when the link is lost.
    if not str(data.get("email") or "").strip():
        return error(400, "email is required: " + EMAIL_NEEDED, needs=["email"])
    try:
        email = clean_email(data.get("email"))
    except ValueError:
        return error(400, "bad email: " + EMAIL_NEEDED, needs=["email"])
    home = None
    if data.get("home_area"):
        fits = area_fits(data["home_area"])
        if len(fits) == 1:
            home = fits[0]
        elif fits:  # a city name or a word in several area names: the agent asks its human (T62)
            return error(400, "which home_area?", needs=["where"], areas=[a.name for a in fits[:3]])
        else:
            return error(400, "unknown home_area", needs=["where"],
                         areas=list(Area.objects.order_by("name").values_list("name", flat=True)))
    hook, bad = hook_fields(data)
    if bad:
        return bad
    inv = None
    if data.get("invite"):  # F4a (T253): the friend link; the inviter is a friend at once
        inv = Invite.find(invite_token(data["invite"]))
        if not inv or inv.used_up():
            return error(400, "unknown invite")
    if Person.objects.filter(handle=handle).exists():
        return error(409, "handle taken")
    if Person.by_email(email):
        return error(409, "email in use")
    try:
        with transaction.atomic():
            p = Person.objects.create(
                name=name, handle=handle, has_agent=True, home_area=home,
                email=email, telegram=str(data.get("telegram") or "").strip(),
                **hook)
            _, key = AgentKey.issue(p, label="signup")
            _, token = MagicLink.issue(p)
            if inv:
                inv.accept(p)
    except IntegrityError:
        return error(409, "handle taken")
    extra = {"friend": {"handle": inv.person.handle, "name": inv.person.name}} if inv else {}
    return JsonResponse({**person_json(p), **extra, "api_key": key, "dashboard_url": dashboard_url(request, token),
                         "poll_every_hours": POLL_HOURS, "next_step": POLL_NOTE}, status=201)


INVITE_IN_URL = re.compile(r"/i/([A-Za-z0-9_-]{1,64})/?(?:[?#].*)?$")


def invite_token(value):
    """F4a (T253): an invite token, or a full /i/<token>/ link -> the token."""
    value = str(value or "").strip()
    m = INVITE_IN_URL.search(value)
    return m.group(1) if m else value


@api_view(["GET"])
@limit("invite", ip=(60, 3600))
def invite_info(request, token):
    """F4a (T253): who sent this friend link. No key needed. Only the handle and the name."""
    inv = Invite.find(invite_token(token))
    if not inv or inv.used_up():
        return error(404, "unknown invite")
    return JsonResponse({"handle": inv.person.handle, "name": inv.person.name})


@api_view(["GET", "PATCH"])
@agent_required
def me(request):
    """GET: the agent's own person. PATCH: change the push settings (webhook_url / hook_url,
    webhook_secret / hook_token, webhook_format / hook_format) or the email (F3a, T259). Other keys: 400 (T98)."""
    p = request.person
    if request.method == "PATCH":
        data = json_body(request)
        allowed = ("webhook_url", "hook_url", "webhook_secret", "hook_token", "webhook_format", "hook_format", "email")
        unknown = sorted(set(data) - set(allowed))
        if unknown:
            return error(400, f"unknown field: {', '.join(unknown)}", allowed=list(allowed))
        if "webhook_secret" in data or "hook_token" in data:
            if not ("webhook_url" in data or "hook_url" in data) and not p.webhook_url:
                return error(400, "give webhook_url with the secret; this agent has no webhook yet")
        fields, bad = hook_fields(data)
        if bad:
            return bad
        if "email" in data:
            try:
                fields["email"] = clean_email(data["email"])
            except ValueError:
                return error(400, "bad email: " + EMAIL_NEEDED, needs=["email"])
            other = Person.by_email(fields["email"])
            if other and other.pk != p.pk:
                return error(409, "email in use")
        for k, v in fields.items():
            setattr(p, k, v)
        p.save()
    return JsonResponse(person_json(p))


@api_view(["GET"])
@agent_required
def dashboard_link(request):
    """A fresh one-time dashboard link for the agent's person. Older unused links stop working (T30)."""
    row, token = MagicLink.reissue(request.person)
    return JsonResponse({"dashboard_url": dashboard_url(request, token), "expires_at": row.expires_at.isoformat(),
                         "note": "One-time link, valid 24 hours. Earlier unused links no longer work."})


def invite_url(invite):
    return calendar.base_url() + reverse("invite_landing", args=[invite.token])


@api_view(["GET"])
@agent_required
def invite_link(request):
    """M11b (T224): the person's invite link. The same link every time until it has MAX_USES friends.
    A friend who opens it and signs up (or is logged in) becomes a friend at once, with no request."""
    inv = Invite.current(request.person)
    return JsonResponse({"url": invite_url(inv), "uses": inv.uses, "max_uses": Invite.MAX_USES,
                         "note": "Send this link to a friend. Who opens it and joins becomes your friend at once."})


def friend_json(p):
    """What another person may see. Never email, phone, Telegram or webhook data."""
    return {"id": p.pk, "handle": p.handle, "name": p.name, "has_agent": p.has_agent}


def friend_row(p, status):
    return {**friend_json(p), "status": status}


@api_view(["GET", "POST"])
@agent_required
def friends(request):
    """GET: friends, requests to me, requests I sent. POST {handle|id}: a friend request.
    The other side must add back (or accept) before matching uses the friendship."""
    me_ = request.person
    if request.method == "GET":
        return JsonResponse({
            "friends": [friend_row(p, "friends") for p in Friendship.friends_of(me_.pk).order_by("name", "pk")],
            "requests": [friend_row(p, "asked_you") for p in Friendship.requests_to(me_.pk).order_by("name", "pk")],
            "sent": [friend_row(p, "requested") for p in Friendship.requests_from(me_.pk).order_by("name", "pk")],
        })
    data = json_body(request)
    if data.get("id") is not None:
        try:
            other = Person.objects.filter(pk=int(data["id"])).first()
        except (TypeError, ValueError):
            return error(400, "id must be a number")
        # T256 (F4b): an id works only for someone you already know (a friend, a request either
        # way). A stranger's id answers 404 with no data, so ids cannot be walked for names.
        if other and other.pk != me_.pk and not Friendship.objects.filter(Q(person=me_, friend=other) | Q(person=other, friend=me_)).exists():
            other = None
    elif data.get("handle"):
        other = Person.objects.filter(handle=str(data["handle"]).strip().lstrip("@").lower()).first()
    else:
        return error(400, "send handle or id")
    if not other:
        return error(404, "no such person")
    return add_friend(me_, other)


def add_friend(me_, other):
    if other.pk == me_.pk:
        return error(400, "you cannot add yourself")
    if Friendship.exists(me_, other):
        return error(409, "already friends", friend=friend_row(other, "friends"))
    if Friendship.objects.filter(person=me_, friend=other).exists():
        return error(409, "request already sent; the other side must add you back",
                     friend=friend_row(other, "requested"))
    # A seeded demo person has no agent to answer, so in the demo it says yes at once.
    # The same holds for a scenario person with no agent (demo/scenario.py, T63).
    auto = settings.DEMO and (demo_friends().filter(pk=other.pk).exists()
                              or (other.handle.startswith(SCENARIO_PREFIX) and not other.has_agent))
    status = Friendship.request(me_, other, auto_accept=auto)
    if status == "requested":
        push.push(other, "friend.request", {"from": friend_json(me_),
                                            "text": f"{me_.name} (@{me_.handle}) wants to be friends on Mifgash."})
        note = f"Request sent. You and {other.name} become friends when {other.name} adds you back."
    else:
        note = f"You and {other.name} are friends now."
    return JsonResponse({"friend": friend_row(other, status), "status": status, "note": note}, status=201)


@api_view(["POST"])
@agent_required
def friends_accept(request, person_id):
    """Accept a friend request from person_id. Same as adding that person back."""
    me_ = request.person
    if not Friendship.objects.filter(person_id=person_id, friend=me_, status="requested").exists():
        return error(404, "no friend request from that person")
    return add_friend(me_, Person.objects.get(pk=person_id))


@api_view(["GET"])
@agent_required
@limit("search", ip=(60, 60), key=(30, 60))
def friends_search(request):
    """T256 (F4b): off for the public. Add a friend by exact handle. A zz_ test person, or a site
    with MIFGASH_SEARCH=1, may still search."""
    if not (settings.FRIEND_SEARCH or request.person.handle.startswith("zz_")):
        return error(404, "search is off; add a friend by exact handle")
    rows = search_people(request.person, request.GET.get("q", ""))
    if rows is None:
        return error(400, "q needs 3 characters or an exact handle")
    mine = set(Friendship.objects.filter(person=request.person, status="friends").values_list("friend_id", flat=True))
    return JsonResponse({"results": [{"id": p.pk, "handle": p.handle, "name": p.name, "is_friend": p.pk in mine}
                                     for p in rows]})


def search_people(me_, q):
    """People for a search box: prefix match on handle or name, 10 at most. Prefix only, so a short
    query cannot list every user; under 3 characters only an exact handle matches (None = no match)."""
    q = (q or "").strip().lstrip("@")
    people = Person.objects.exclude(pk=me_.pk).exclude(is_sandbox=True)  # quick-demo people stay hidden (T178)
    if len(q) < 3:
        rows = list(people.filter(handle=q.lower()))
        return rows or None
    return list(people.filter(Q(handle__istartswith=q) | Q(name__istartswith=q)).order_by("handle")[:10])


@api_view(["POST"])
@agent_required
def friends_import_facebook(request):
    """STUB. The real Facebook OAuth comes later. With MIFGASH_DEMO=1 the import links the
    seeded demo friends to the caller, so the demo can show the step. Outside the demo it links
    nobody: a real user must never get strangers as friends."""
    if not demo.allowed(request):
        return JsonResponse({"status": "not_connected", "imported": 0,
                             "note": "Facebook import is not connected yet. Add friends by handle: "
                                     "friends search, then friends add."}, status=501)
    n = 0
    for p in demo_friends().exclude(pk=request.person.pk):
        n += Friendship.link(request.person, p, source="facebook")
    return JsonResponse({"status": "stub", "imported": n,
                         "note": "Facebook login is not connected yet; demo friends were linked."})


OFFICE_RE = re.compile(r"\b(the office|office|work)\b", re.I)
HOME_RE = re.compile(r"\b(home|my place)\b", re.I)


def own_place(text, person):
    """'near the office' / 'near home' point to the person's own areas.
    Returns (matched, area): matched is True when the words name one of them, area is None when
    that area is not set, so the agent must ask."""
    if OFFICE_RE.search(text):
        return True, person.work_area
    if HOME_RE.search(text):
        return True, person.home_area
    return False, None


def area_suggestions(person, n=3, near=None):
    """n Area names near a point: `near` (lat/lon) when given, else the person's home area,
    else the first n areas."""
    rows = list(Area.objects.order_by("pk"))
    near = near or person.home_area
    if near:
        rows.sort(key=lambda a: matching.km(a, near))
    return [a.name for a in rows[:n]]


# Cities Mifgash does not cover yet, with a centre point, so the ask-back can offer the nearest
# areas. Only a city within NEAR_KM of a known area counts as nearby.
OTHER_CITIES = {
    "Alameda": (37.7652, -122.2416), "Emeryville": (37.8313, -122.2852), "Mill Valley": (37.9060, -122.5450),
    "Pacifica": (37.6138, -122.4869), "Brisbane": (37.6808, -122.3999), "Tiburon": (37.8735, -122.4566),
    "San Rafael": (37.9735, -122.5311), "Walnut Creek": (37.9101, -122.0652), "San Mateo": (37.5630, -122.3255),
    "Redwood City": (37.4852, -122.2364), "Palo Alto": (37.4419, -122.1430), "San Jose": (37.3382, -121.8863),
    "Sacramento": (38.5816, -121.4944), "Los Angeles": (34.0522, -118.2437), "Seattle": (47.6062, -122.3321),
}
NEAR_KM = 15.0
PLACE_RE = re.compile(r"\b(?:in|near|at|around|by)\s+((?:[A-Z][\w'-]*)(?:\s+[A-Z][\w'-]*){0,2})")
NOT_PLACES = {"the", "my", "home", "work", "office", "today", "tomorrow", "tonight", "lunch",
              "morning", "afternoon", "evening", "noon"} | set(llm.DAY_WORDS)


def unknown_place(text):
    """The place word in the text that names no known area, or None.
    A city from OTHER_CITIES wins (any case); else a capitalised word after in/near/at/around/by."""
    t = (text or "").lower()
    for city in OTHER_CITIES:
        if re.search(r"\b" + re.escape(city.lower()) + r"\b", t):
            return city
    for m in PLACE_RE.finditer(text or ""):
        word = m.group(1).strip()
        if word.split()[0].lower() not in NOT_PLACES and not find_area(word):
            return word
    return None


def where_reply(person, place):
    """The ask-back fields for needs=['where']: the unknown place, when one was named, and 3 areas.
    The 3 areas are the nearest to the named city when Mifgash knows that city and it is close,
    else the ones near the person's home."""
    reply = {}
    near = None
    if place:
        reply["unknown_place"] = place
        if place in OTHER_CITIES:
            lat, lon = OTHER_CITIES[place]
            point = types.SimpleNamespace(lat=lat, lon=lon)
            if min(matching.km(a, point) for a in Area.objects.all()) <= NEAR_KM:
                near = point
    reply["suggestions"] = area_suggestions(person, near=near)
    return reply


def default_area(person, fields):
    """(area, 'home'|'work') when the text names no place: the work area for a weekday lunch
    (Sun-Thu) when it is set, else the home area. (None, None) when neither is set."""
    date = fields.get("date")
    if fields.get("part") == "lunch" and person.work_area and (date is None or date.weekday() not in (4, 5)):
        return person.work_area, "work"
    if person.home_area:
        return person.home_area, "home"
    return None, None


def default_part(person, date):
    """(part, 'slot'|'weekday') for a text with a day and no part of the day (T61): the person's weekly
    slot for that weekday (the first in PARTS order when there are several), else evening on Fri and
    Sat and lunch on Sun-Thu."""
    have = set(person.slots.filter(weekday=date.weekday()).values_list("part", flat=True))
    for key, _ in PARTS:
        if key in have:
            return key, "slot"
    return ("evening" if date.weekday() in (4, 5) else "lunch"), "weekday"


def part_note(part, any_part=True):
    """The line for a text with no part of the day (T61, T79). While the plan waits, a friend who
    named a part of that day still matches, and the friend's part wins."""
    others = [k for k, _ in PARTS if k != part]
    change = f"Say {', '.join(others[:-1])} or {others[-1]} to change it."
    if any_part:
        return f"I took {part}. A friend free at another part of that day still fits, and their part wins. {change}"
    return f"A friend is free for {part} that day, so I took {part}. {change}"


def area_note(which, area):
    return f"Near your {which} area, {area.name}. Say another place to change it."


def place_pick_json(plan):
    """T265: the venue the model picked and its one-line why, for the owner's agent."""
    pick = (plan.wants or {}).get("pick") or {}
    place = next((a for a in plan.option_list() if a.pk == pick.get("id")), None) if pick else None
    if place is None:
        return {}
    return {"place_pick": {"id": place.pk, "name": place.name, "why": pick.get("why", ""),
                           "model": llm.model_label(pick.get("backend"))}}


def own_wants(plan):
    """T325: the owner's own wants, never the friend's tastes the place step also used."""
    from . import wants as wants_mod
    return wants_mod.own(plan.wants)


def wants_summary(wants):
    """T320: the display line ('avoids Mission Playground'), so an agent relays names in title case."""
    from . import wants as wants_mod
    return wants_mod.summary({k: v for k, v in (wants or {}).items() if k not in ("note", "pick", "time")})


def plan_json(request, plan):
    return {
        "availability_id": plan.pk,
        "status": plan.status,
        "date": plan.date.isoformat(),
        "part": plan.part,
        "kind": plan.kind,
        "kind_named": plan.kind_named,
        "area": plan.area.name,
        "radius_km": plan.radius_km,
        "group_size": plan.group_size,
        **({"fill_by": plan.fill_by.isoformat()} if plan.fill_by else {}),
        "text": plan.raw_text,
        **({"wants": {k: v for k, v in own_wants(plan).items() if k not in ("note", "pick")}} if plan.wants else {}),
        **({"wants_text": wants_summary(plan.wants)} if wants_summary(plan.wants) else {}),
        **place_pick_json(plan),
        **({"place_note": plan.wants["note"]} if (plan.wants or {}).get("note") else {}),
        **({"note": messages.waiting_text(plan)}
           if plan.status == "open" and plan.log.filter(type="waiting").exists() else {}),
    }


def waiting_for_me(plan):
    """The offer from a friend's plan that waits for this plan's owner, for the same date and part."""
    return (Offer.objects.filter(person=plan.owner, status="pending", plan__date=plan.date, plan__part=plan.part)
            .exclude(plan=plan).order_by("pk").first())


def plan_state(plan):
    """Where an open or asking plan stands, for the owner's agent (T64). Never names a friend who is
    asked: the owner learns a name only when that friend said yes."""
    if plan.status == "open":
        offer = waiting_for_me(plan)
        if offer:  # a friend's plan asks this owner for the same meal (T68)
            return {"state": "proposal_waiting", "state_text": "a friend is free then too, your answer is needed",
                    "proposal_id": offer.pk}
        return {"state": "open", "state_text": "open"}
    wait = plan.offers.filter(status="owner_wait").order_by("pk").first()
    if wait:
        return {"state": "owner_wait", "state_text": "a friend said yes, your call", "proposal_id": wait.pk}
    return {"state": "asking", "state_text": "finding friends"}


def read_availability(data, person, today):
    """Free text and/or structured fields -> (fields dict, parsed dict for the reply, needs list).
    A structured field wins over the same field read from the text."""
    text = str(data.get("text") or "").strip()[:500]
    fields = {"kind": None, "date": None, "part": None, "area": None, "group_size": None, "food": None,
              "tastes": [], "time": None}
    parsed = {}
    past = False
    if text:
        got = llm.parse_intent(text, person, today)
        fields.update({k: got.get(k) for k in fields})
        past = bool(got.get("past"))
        fields["backend"] = got.get("backend", "")
        matched, own = own_place(text, person)
        if matched:  # the person's own place beats an alias word such as 'office'
            fields["area"] = own
    if data.get("kind"):
        if data["kind"] not in dict(KINDS):
            raise ValueError(f"kind must be one of {', '.join(dict(KINDS))}")
        fields["kind"] = data["kind"]
    if data.get("part"):
        if data["part"] not in dict(PARTS):
            raise ValueError(f"part must be one of {', '.join(dict(PARTS))}")
        fields["part"] = data["part"]
    if data.get("date"):
        try:
            fields["date"] = dt.date.fromisoformat(str(data["date"]))
        except ValueError:
            raise ValueError("date must be YYYY-MM-DD")
        if fields["date"] < today:  # asks back when, the same as 'yesterday' in the text (T28)
            fields["date"], past = None, True
        else:
            past = False
    if data.get("area"):
        matched, own = own_place(str(data["area"]), person)
        fields["area"] = own if matched else find_area(data["area"])
        if not fields["area"]:  # an unknown name asks back, the same as free text
            fields["area"] = None
    if data.get("group_size") is not None:
        fields["group_size"] = max(1, min(int(data["group_size"]), GROUP_MAX))
    fields["kind"], fields["group_size"] = llm.group_rule(fields["kind"], fields["group_size"], text)
    fields["part_default"] = None
    fields["kind_named"] = bool(fields["kind"])  # infer() below may set a kind from the part (T112)
    if fields["date"] and not fields["part"] and not fields["kind"]:  # 'open tomorrow' asks nothing back (T61)
        fields["part"], fields["part_default"] = default_part(person, fields["date"])
    fields = infer(person, fields)
    parsed = {"kind": fields["kind"], "date": fields["date"].isoformat() if fields["date"] else None,
              "part": fields["part"], "area": fields["area"].name if fields["area"] else None,
              "group_size": fields["group_size"]}
    fields["area_default"] = None
    named = own_place(text, person)[0] or bool(data.get("area")) or bool(unknown_place(text))
    if not fields["area"] and not named:
        fields["area"], fields["area_default"] = default_area(person, fields)
    parsed = {**parsed, "area": fields["area"].name if fields["area"] else None}
    needs = []
    if not fields["date"] or not fields["part"]:
        needs.append("when")
    if not fields["area"]:
        needs.append("where")
    if not fields["kind"] and "when" not in needs:
        needs.append("what")
    fields["past"] = past and not fields["date"]
    fields["wants"] = read_wants(data, text, fields)
    # T258 (F6c): a time the agent sends ('time': '13:00') or the text names ('lunch at 1pm') is the
    # time Mifgash sets when both sides are in; else the part default.
    if data.get("time"):
        t = llm.clean_time(data["time"])
        if not t:
            raise ValueError("time must be HH:MM, for example 13:00")
        fields["time"] = t
    elif text and fields["part"]:  # the parse ran before the part was known: read it again with the part
        fields["time"] = finalize.read_time(text, fields["part"]) or fields.get("time")
    if fields.get("time"):
        fields["wants"] = {**fields["wants"], "time": fields["time"]}
    return fields, parsed, needs, text


def read_wants(data, text, fields):
    """T255: food and taste words from the parse, likes and dislikes from the text, then the API
    fields 'preferences' (free text, 300 chars) and 'tastes' (a list of short words)."""
    from . import wants as wants_mod
    prefs = str(data.get("preferences") or "").strip()[:300]
    tastes = data.get("tastes") or []
    if isinstance(tastes, str):
        tastes = [w for w in tastes.split(",")]
    if not isinstance(tastes, list):
        raise ValueError("tastes must be a list of short words")
    return wants_mod.merge(
        {"food": fields.get("food"), "tastes": fields.get("tastes") or []},
        wants_mod.read(text), wants_mod.read(prefs),
        {"tastes": [str(w)[:20] for w in tastes[:8]], "text": prefs})


def read_as_text(plan, fields):
    """The 'Read as' line for the dashboard log: what Mifgash made of the agent's post (T87)."""
    notes = []
    if fields.get("part_default") == "slot":
        notes.append("part from your weekly time")
    elif fields.get("part_default"):
        notes.append("default part")
    if fields.get("area_default"):
        notes.append(f"{fields['area_default']} area taken")
    tail = f" ({', '.join(notes)})" if notes else ""
    # not 'evening, Fri 30/10 evening', and no kind the person did not name (T112)
    kind = "" if plan.kind == plan.part or not plan.kind_named else f"{messages.kind_label(plan.kind)}, "
    from . import wants as wants_mod
    want = wants_mod.summary(plan.wants)
    want = f". Wants: {want}" if want else ""
    note = f". {plan.wants['note']}" if (plan.wants or {}).get("note") else ""
    return f"Read as: {kind}{messages.when(plan.date, plan.part)}, near {plan.area.name}{tail}{want}{note}"


def log_post(plan, said, fields):
    """Two log rows per post (T87): the agent's own words, then what Mifgash read from them. Written
    before matching, so they come first in the plan's log."""
    if not isinstance(said, str):  # structured fields only: show them as the agent sent them
        said = ", ".join(f"{k} {said[k]}" for k in ("date", "part", "kind", "area") if said.get(k))
    AgentMessage.objects.create(plan=plan, sender=plan.owner.address, receiver="mifgash:directory",
                                type="availability", payload={"text": said})
    AgentMessage.objects.create(plan=plan, sender="mifgash:directory", receiver=plan.owner.address,
                                type="read_as", payload={
                                    "text": read_as_text(plan, fields), "backend": fields.get("backend", ""),
                                    "date": plan.date.isoformat(), "part": plan.part, "kind": plan.kind,
                                    "area": plan.area.name})


@api_view(["GET", "POST"])
@agent_required
@limit("availability", ip=(40, 3600), key=(20, 3600), methods=("POST",))
def availability(request):
    """POST 'I am open ...' as text or fields. GET the caller's open availabilities."""
    me_ = request.person
    if request.method == "GET":
        rows = (Plan.objects.filter(owner=me_, status__in=("open", "asking"))
                .select_related("area").order_by("date", "pk"))
        return JsonResponse({"availability": [{**plan_json(request, p), **plan_state(p)} for p in rows]})
    from .availability import post
    reply, status = post(me_, json_body(request), request)
    return JsonResponse(reply, status=status)


@api_view(["GET", "DELETE"])
@agent_required
def availability_one(request, plan_id):
    plan = Plan.objects.filter(pk=plan_id, owner=request.person).select_related("area").first()
    if not plan:  # also another person's plan: 404, so ids do not leak
        return error(404, "no such availability")
    if request.method == "DELETE":
        if plan.status == "asking":  # a friend is asked now; T22 adds the cancel path for that
            return error(409, "Mifgash is finding friends now; this availability cannot be cancelled yet")
        if plan.status in ("open", "draft"):
            plan.status = "cancelled"
            plan.save(update_fields=["status"])
    return JsonResponse(plan_json(request, plan))


@api_view(["POST"])
@agent_required
def availability_confirm(request, plan_id):
    """The owner takes a group dinner as it is now, before it is full (T227). The reply names no
    friend who said no and no friend still in the queue."""
    plan = Plan.objects.filter(pk=plan_id, owner=request.person).select_related("area").first()
    if not plan:
        return error(404, "no such availability")
    try:
        engine.confirm_smaller(plan)
    except ValueError as e:
        return error(409, str(e))
    plan.refresh_from_db()
    return JsonResponse({**plan_json(request, plan), "outing": outing_json(plan, viewer=request.person)})


def place_json(a):
    return {"id": a.pk, "name": a.name, "address": a.address, "area": a.area.name, "tags": list(a.tags or [])}


def proposal_json(offer, role):
    """One proposal as the caller may see it. A candidate never learns about other friends or the
    order; an owner sees only the friend who said yes."""
    plan = offer.plan
    row = {
        "id": offer.pk,
        "role": role,
        "kind": plan.kind,
        "date": plan.date.isoformat(),
        "part": plan.part,
        "area": plan.area.name,
        "options": [place_json(a) for a in plan.option_list()],
        "expires_at": offer.expires_at.isoformat() if offer.expires_at else None,
        "reason": offer.reason or None,  # T78: one sentence 'why this fits'
        "reason_model": llm.model_label(offer.reason_backend) or None,
    }
    if role == "candidate":
        row["from"] = {"handle": plan.owner.handle, "name": plan.owner.name}
        row["text"] = messages.offer_text(plan.owner, plan, plan.option_list())
    else:
        row["friend"] = {"handle": offer.person.handle, "name": offer.person.name}
        row["choice"] = place_json(offer.choice) if offer.choice else None
        row["text"] = messages.owner_ask_text(offer.person, plan, offer.choice, offer)
        row["reason"] = messages.owner_reason(offer)  # T329: the why line names the same place
        said = engine.answer_note(offer)
        if said:  # T323: the friend's own words with the yes, untrusted data
            row["friend_text"] = said
    return row


def my_proposals(person):
    """(offer, role) pairs that wait for this person's answer, oldest first."""
    rel = ("plan__owner", "plan__area", "person", "choice__area")
    asked = Offer.objects.filter(person=person, status="pending", plan__status="asking").select_related(*rel)
    owned = Offer.objects.filter(plan__owner=person, status="owner_wait", plan__status="asking").select_related(*rel)
    rows = [(o, "candidate") for o in asked] + [(o, "owner") for o in owned]
    return sorted(rows, key=lambda r: (r[0].sent_at or r[0].plan.created, r[0].pk))


def finalize_rows(person):
    """T80: confirmed outings that wait for this person on the exact time: a time and place the
    other side proposed (type 'agree'), or no time on the table yet (type 'set_time'). A time the
    person proposed is not listed: that waits for the others."""
    from .messages import first_name
    rows = []
    for plan, _ in my_outings(person):
        if plan.status != "confirmed":
            continue
        others = [p for p in [plan.owner] + plan.guests() if p.pk != person.pk]
        row = {"type": "set_time", "plan_id": plan.pk, "kind": plan.kind, "date": plan.date.isoformat(),
               "part": plan.part, "time": None, "place": place_json(plan.chosen) if plan.chosen else None,
               "proposed_by": None, "who": [first_name(p) for p in others]}
        if plan.proposed_time:
            if plan.proposed_by_id == person.pk:
                continue
            place = plan.proposed_activity or plan.chosen
            row.update(type="agree", time=plan.proposed_time.strftime("%H:%M"),
                       place=place_json(place) if place else None,
                       proposed_by=first_name(plan.proposed_by) if plan.proposed_by else None,
                       command=f"finalize {plan.pk} --time {plan.proposed_time.strftime('%H:%M')}"
                               + (f" --place {place.pk}" if place else ""),
                       text=messages.agree_time_text(plan.proposed_by or others[0], plan, plan.proposed_time, place))
        else:
            row.update(command=f"finalize {plan.pk} --time HH:MM", text=messages.set_time_text(plan, others))
        rows.append(row)
    return rows


@api_view(["GET"])
@agent_required
def proposals(request):
    """Offers that wait for the caller's answer, and (T80) outings that wait for the caller to
    agree on or set the exact time."""
    me_ = request.person
    return JsonResponse({"proposals": [proposal_json(o, role) for o, role in my_proposals(me_)],
                         "finalize": finalize_rows(me_)})


def outing_json(plan, viewer=None):
    """'who' keeps every full name; 'with' holds the first names of the OTHER people (the viewer
    left out); 'when_text' is 'Sun 1/11 evening' (T65)."""
    from .messages import first_name, plan_when
    people = [plan.owner] + plan.guests()
    return {"plan_id": plan.pk, "kind": plan.kind, "date": plan.date.isoformat(), "part": plan.part,
            "when_text": plan_when(plan),
            "status": plan.status, "time": plan.exact_time.strftime("%H:%M") if plan.exact_time else None,
            "place": place_json(plan.chosen) if plan.chosen else None,
            "who": [p.name for p in people],
            "with": [first_name(p) for p in people if viewer is None or p.pk != viewer.pk],
            # F8a (T260): the human page for this outing; the public URL holds the uuid only
            "url": calendar.base_url().rstrip("/") + reverse("outing", args=[plan.uid])}


def my_outings(person):
    """(plan, my offer or None) for every outing the person is on, soonest first: the owner's
    confirmed and final plans and asking plans with a friend's yes to approve; a friend's plans
    where the friend said yes (waiting for the owner) or was accepted."""
    rows = {}
    for plan in Plan.objects.filter(owner=person, status__in=("asking", "confirmed", "final")):
        # T327: a group dinner that still fills is on the owner's list once one friend is in.
        if plan.status != "asking" or plan.offers.filter(status__in=("owner_wait", "accepted")).exists():
            rows[plan.pk] = (plan, None)
    for offer in Offer.objects.filter(person=person, status__in=("owner_wait", "accepted"),
                                      plan__status__in=("asking", "confirmed", "final")).select_related("plan"):
        rows[offer.plan_id] = (offer.plan, offer)
    return sorted(rows.values(), key=lambda r: (r[0].date, r[0].pk))


def outing_status(plan, person=None, offer=None):
    if plan.status == "asking":
        # T327: a group dinner that fills one by one: the owner has no yes to approve, or the
        # caller is a guest who is in already. Both wait for more friends, not for the owner.
        mine_in = offer is not None and offer.status == "accepted"
        owner_free = offer is None and not plan.offers.filter(status="owner_wait").exists()
        return "gathering" if mine_in or owner_free else "waiting_for_owner"
    if plan.status == "confirmed" and plan.proposed_time:
        return "proposed"
    return plan.status


def my_outing_json(request, plan, person, offer):
    """One outing as the caller sees it. Names are first names; an owner sees only the friend
    who said yes; a friend never learns about other friends who were asked."""
    from .messages import first_name
    status = outing_status(plan, person, offer)
    group_in = messages.group_in(plan) if messages.is_group(plan) else []
    if status == "gathering":  # T327: the owner and the friends who are in; never who declined
        people = [plan.owner] + group_in
        place = (offer.choice if offer else None) or (plan.option_list() or [None])[0]
    elif plan.status == "asking":
        waiting = offer or plan.offers.filter(status="owner_wait").select_related("person", "choice").first()
        people = [plan.owner, waiting.person]
        place = waiting.choice or (plan.option_list() or [None])[0]
    else:
        people = [plan.owner] + plan.guests()
        place = plan.chosen
    row = {
        "plan_id": plan.pk,
        "role": "owner" if plan.owner_id == person.pk else "friend",
        "status": status,
        "kind": plan.kind,
        "date": plan.date.isoformat(),
        "part": plan.part,
        "area": plan.area.name,
        "place": place_json(place) if place else None,
        "address": place.address if place else None,
        "who": [first_name(p) for p in people if p.pk != person.pk],
        "group_size": 1 + len(plan.guests()) if plan.kind == "group_dinner" else None,  # people in, owner too
        "time": plan.exact_time.strftime("%H:%M") if plan.exact_time else None,
        "proposed_time": None, "proposed_place": None, "proposed_by": None,
        # T327: while a group still fills: the friends who are in (first names) and the friends wanted
        "in": [first_name(p) for p in group_in] if plan.status == "asking" else [],
        "wanted": plan.group_size if messages.is_group(plan) else None,
        "progress": None,
        # T268: the human page of the outing (uuid URL, F8a); demo/video_run.py prints it
        "url": calendar.base_url().rstrip("/") + reverse("outing", args=[plan.uid]),
    }
    if plan.status == "asking" and messages.is_group(plan):
        if plan.owner_id == person.pk:
            row["progress"] = messages.group_owner_text(plan, group_in)
        elif status == "gathering":
            row["progress"] = messages.group_guest_text(plan, group_in)
    if plan.status == "confirmed" and plan.proposed_time:
        row["proposed_time"] = plan.proposed_time.strftime("%H:%M")
        row["proposed_place"] = place_json(plan.proposed_activity) if plan.proposed_activity else None
        by = plan.proposed_by
        row["proposed_by"] = "you" if by and by.pk == person.pk else (first_name(by) if by else None)
        # G2 (T228): a group dinner is final when every side agrees; these say who still has to.
        agreed = set(plan.agreed or [plan.proposed_by_id])
        row["you_agreed"] = person.pk in agreed
        row["waiting_for"] = [first_name(p) for p in people if p.pk not in agreed and p.pk != person.pk]
    if plan.status == "final":
        row.update(calendar.links(plan, person, calendar.public_base(request)))
        # T268: Mifgash set the time itself (T258). Once a side moved it, a friend agent leaves it.
        moved = plan.log.filter(type="time_change").order_by("pk").first()
        row["time_moved"] = moved is not None
        # T328: a guest's ask to move the time of a group (only the owner and the asker see it)
        row["move_ask"] = None
        if plan.proposed_time and plan.proposed_by_id and person.pk in (plan.owner_id, plan.proposed_by_id):
            row["move_ask"] = {"by": "you" if plan.proposed_by_id == person.pk else first_name(plan.proposed_by),
                               "time": plan.proposed_time.strftime("%H:%M"),
                               "approve": f"finalize {plan.pk} --time {plan.proposed_time.strftime('%H:%M')}"
                               if person.pk == plan.owner_id else None}
        row["moved_by"] = None
        if moved:
            by = next((p for p in people if p.address == moved.sender), None)
            row["moved_by"] = "you" if by and by.pk == person.pk else (first_name(by) if by else None)
    return row


EVENTS_MAX = 50
EVENTS_WAIT_STEP = 1.0  # T249: seconds between two looks during a long poll


@api_view(["GET"])
@agent_required
def events(request):
    """The caller's own push events after the id cursor, oldest first (T93). The same payloads a
    webhook gets, so an agent without a public URL can poll. Reply: events, last_id (the cursor for
    the next call; equal to after when nothing is new), more (true when the page was full).
    ?wait=S (T249): with nothing new, hold the request up to S seconds (cap EVENTS_WAIT_MAX) and
    answer as soon as a new event exists. "waited" says how many seconds the server held it."""
    try:
        after = int(request.GET.get("after", 0) or 0)
    except ValueError:
        raise ValueError("after must be a whole number")
    try:
        wait = float(request.GET.get("wait", 0) or 0)
    except ValueError:
        raise ValueError("wait must be a number of seconds")
    wait = max(0.0, min(wait, settings.EVENTS_WAIT_MAX))  # T249: long poll, capped
    Person.objects.filter(pk=request.person.pk).update(last_polled_at=timezone.now())  # T98: the agent is awake
    query = AgentEvent.objects.filter(person=request.person, pk__gt=after).order_by("pk")
    start = time.monotonic()
    rows = list(query[:EVENTS_MAX + 1])
    # T249: nothing new and the agent asked to wait -> look again each second until the wait ends.
    # One long poll is one request, so it counts once against the rate limit.
    while not rows and time.monotonic() - start < wait:
        time.sleep(min(EVENTS_WAIT_STEP, max(0.0, wait - (time.monotonic() - start))))
        rows = list(query[:EVENTS_MAX + 1])
    waited = round(time.monotonic() - start, 1)
    more = len(rows) > EVENTS_MAX
    rows = rows[:EVENTS_MAX]
    # T103: a proposal event also says if that proposal still waits for the caller, so a poller
    # does not ask its human a second time about a proposal that was answered already.
    waiting = {o.pk for o, _ in my_proposals(request.person)}

    def row(e):
        r = {"id": e.pk, "event": e.event, "created": e.created.isoformat(), "payload": e.payload}
        prop = (e.payload or {}).get("proposal") or {}
        if prop.get("id") is not None:
            r["waiting"] = prop["id"] in waiting
        return r
    return JsonResponse({
        "events": [row(e) for e in rows],
        "last_id": rows[-1].pk if rows else after,
        "more": more,
        "waited": waited,
    })


@api_view(["GET"])
@agent_required
def outings(request):
    """The caller's outings: waiting for the owner, confirmed, proposed (a time is on the table)
    and final (with the caller's own calendar links)."""
    me_ = request.person
    return JsonResponse({"outings": [my_outing_json(request, p, me_, o) for p, o in my_outings(me_)]})


@api_view(["GET"])
@agent_required
def outing_one(request, plan_id):
    me_ = request.person
    found = [(p, o) for p, o in my_outings(me_) if p.pk == plan_id]
    if not found:  # also a plan the caller is not on: 404, so ids do not leak
        return error(404, "no such outing")
    plan, offer = found[0]
    return JsonResponse(my_outing_json(request, plan, me_, offer))


@api_view(["POST"])
@agent_required
def proposal_respond(request, offer_id):
    """{answer: 'accept'|'decline', choice_id?, note?}. A candidate answers an offer; an owner
    answers a friend's yes. Another person's proposal is a 404, so ids do not leak."""
    me_ = request.person
    found = [(o, role) for o, role in my_proposals(me_) if o.pk == offer_id]
    if not found:
        return error(404, "no such proposal, or it does not wait for you")
    offer, role = found[0]
    data = json_body(request)
    answer = data.get("answer")
    if answer not in ("accept", "decline"):
        return error(400, "answer must be accept or decline")
    plan = offer.plan
    options = plan.option_list()
    choice = None
    if data.get("choice_id") is not None:
        choice = next((a for a in options if str(a.pk) == str(data["choice_id"])), None)
        if not choice:
            return error(400, "choice_id must be one of the options", options=[place_json(a) for a in options])
    note = str(data.get("note") or "")[:200]
    yes = answer == "accept"
    if role == "candidate":
        # A friend agent may say which model decided, so the log can show it (T60). Known names only.
        backend = data.get("backend") if data.get("backend") in llm.MODEL_LABELS else ""
        # T323: a yes carries the note to the owner; a no keeps it private (gentle rule).
        engine.candidate_answer(offer, yes, choice=choice, note=note if yes else (note or "declined by the agent"),
                                backend=backend)
    else:
        engine.owner_answer(offer, yes, choice=choice, note=note)
        engine.advance(plan)
        if not yes:
            engine.rematch_open(plan.date, plan.part)
    plan.refresh_from_db()
    offer.refresh_from_db()
    reply = {"proposal_id": offer.pk, "role": role, "answer": answer, "plan_status": plan.status}
    if role == "candidate":
        reply["status"] = {"owner_wait": "waiting for the owner", "accepted": "accepted"}.get(offer.status, "answered")
    else:
        reply["status"] = "approved" if yes else "closed"
        if not yes:
            reply["note"] = "Thanks. I keep looking for a friend who is open then."
    if plan.status in ("confirmed", "final") and offer.status == "accepted":
        reply["outing"] = outing_json(plan, viewer=me_)
        if plan.status == "final":  # T258: the time is set at once; the caller's own calendar links
            reply["outing"].update(calendar.links(plan, me_, calendar.public_base(request)))
    return JsonResponse(reply)


@api_view(["POST"])
@agent_required
def outing_finalize(request, plan_id):
    """{time: 'HH:MM', activity_id?}. The owner or a friend on a confirmed outing proposes the exact
    time and place; the other side sends the same to make it final. place_id and choice are aliases."""
    plan = Plan.objects.filter(pk=plan_id).first()
    if not plan:
        return error(404, "no such outing")
    data = json_body(request)
    activity = next((data[k] for k in ("activity_id", "place_id", "choice") if data.get(k) is not None), None)
    try:
        # The model that picked the time, known names only, so the log can tag the row (T70).
        backend = data.get("backend") if data.get("backend") in llm.MODEL_LABELS else ""
        reply = finalize.finalize(plan, request.person, data.get("time"), activity, backend=backend)
    except finalize.FinalizeError as e:
        return error(e.status, e.message, **e.extra)
    if reply["status"] == "final":
        plan.refresh_from_db()
        reply.update(calendar.links(plan, request.person, calendar.public_base(request)))
    return JsonResponse(reply)


@api_view(["POST"])
@agent_required
def webhook_test(request):
    """Send a signed 'ping' to the caller's own webhook now, and say how it went."""
    p = request.person
    if not p.webhook_url:
        return error(400, "no webhook_url on this agent; give one at signup")
    before = AgentMessage.objects.filter(receiver=p.address, type="push").count()
    ok = push.deliver(p, "ping", {"text": "Mifgash push test"}, delays=())  # one try, the agent waits
    tries = AgentMessage.objects.filter(receiver=p.address, type="push").order_by("pk")[before:]
    reply = {"event": "ping", "delivered": ok,
             "attempts": [{"attempt": t.payload["attempt"], "http_status": t.payload["http_status"]} for t in tries]}
    if not tries:
        refused = AgentMessage.objects.filter(receiver=p.address, type="push_refused").order_by("-pk").first()
        if refused:
            reply["refused"] = refused.payload["text"]
    return JsonResponse(reply)


# demo/scenario.py signs up its people with this handle prefix and wipes them before each run.
SCENARIO_PREFIX = "scn_"


@api_view(["POST"])
def demo_reset(request):
    """Demo only (MIFGASH_DEMO=1, else 404): delete the scenario people (handle scn_...) with
    their plans, offers and log rows. Seeded people, places and real signups stay.
    Needs the demo admin token too (planner/demo.py)."""
    if not demo.allowed(request):
        return error(404, "not found")
    people = list(Person.objects.filter(handle__startswith=SCENARIO_PREFIX))
    addresses = [p.address for p in people]
    with transaction.atomic():
        AgentMessage.objects.filter(Q(sender__in=addresses) | Q(receiver__in=addresses)).delete()
        Plan.objects.filter(Q(owner__in=people) | Q(offers__person__in=people)).distinct().delete()
        n = Person.objects.filter(pk__in=[p.pk for p in people]).delete()[1].get("planner.Person", 0)
        made = [make_human(h) for h in (json_body(request).get("humans") or [])]
    return JsonResponse({"reset": True, "deleted_people": n, "prefix": SCENARIO_PREFIX,
                         "humans": [friend_json(p) for p in made]})


def make_human(row):
    """A scenario person with NO agent: {name, handle scn_..., area, slots: [{weekday, part}]}.
    Such a friend answers on the /h/ web page only (brief item f, T63)."""
    try:
        handle = clean_handle(str(row.get("handle") or ""))
    except ValidationError as e:
        raise ValueError(e.messages[0])
    if not handle.startswith(SCENARIO_PREFIX):
        raise ValueError(f"a scenario handle starts with {SCENARIO_PREFIX}")
    area = Area.objects.filter(name=row.get("area")).first()
    if not area:
        raise ValueError(f"unknown area: {row.get('area')}")
    try:
        name = clean_name(row.get("name") or handle)
    except ValidationError as e:
        raise ValueError(e.messages[0])
    p = Person.objects.create(name=name, handle=handle, has_agent=False,
                              home_area=area, likes=list(row.get("likes") or []))
    for s in row.get("slots") or []:
        Slot.objects.create(person=p, weekday=int(s["weekday"]), part=s["part"])
    return p


@api_view(["GET"])
def demo_links(request):
    """Demo only: the open /h/ links of one scenario person with no agent, so demo/scenario.py can
    open what that friend got by email. Never for a real person: the handle must start with scn_."""
    handle = request.GET.get("handle", "")
    if not demo.allowed(request) or not handle.startswith(SCENARIO_PREFIX):
        return error(404, "not found")
    rows = Offer.objects.filter(person__handle=handle, person__has_agent=False, status="pending",
                                plan__status="asking").order_by("pk")
    return JsonResponse({"links": [{"offer_id": o.pk, "plan_id": o.plan_id, "path": f"/h/{o.token}/"} for o in rows]})


@api_view(["GET", "POST", "PUT", "PATCH", "DELETE"])
def not_found(request, rest=""):
    return error(404, "not found")
