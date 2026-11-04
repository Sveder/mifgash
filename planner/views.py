import datetime as dt
import re
from zoneinfo import ZoneInfo

from django.conf import settings
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import api, calendar, demo, engine, finalize, llm, matching, messages, sandbox_agent
from .models import AgentMessage, ChatTurn, Friendship, Invite, MagicLink, Offer, Person, Plan, Slot
from .seed import demo_friends


def owner():
    o = Person.objects.filter(is_owner=True).select_related("home_area", "work_area").first()
    if not o:
        raise Http404("Run: python3 manage.py seed_demo")
    return o


def home(request):
    """Landing page. People do not chat with the site: their own agent signs them up and plans.
    F2b (T252): an agent that asks for markdown or plain text (and not HTML) gets agents.md itself."""
    accept = request.headers.get("Accept", "").lower()
    if ("text/markdown" in accept or "text/plain" in accept) and "text/html" not in accept:
        return agents_guide(request)
    return render(request, "planner/landing.html", {"guide_host": guide_host(request),
                                                    "meta_model": settings.META_MODEL})


SETUP_PROMPT = ("Using {base} (remember it as {name}), set up a lunch meetup in SoMa tomorrow. "
                "Send me my {name} dashboard link.")


def setup(request):
    """F2a (T250): 'Set me up' — one line to paste into your own agent, then what happens next.
    The prompt uses the public base URL (MIFGASH_PUBLIC_URL), so the copy works from any host."""
    base = settings.PUBLIC_URL.rstrip("/")
    return render(request, "planner/setup.html", {
        "prompt": SETUP_PROMPT.format(base=base, name=settings.PRODUCT_NAME),
        "guide_url": base + "/agents.md", "skill_url": base + "/skill/"})


def faq(request):
    """F2c (T264): the FAQ is on the landing page now (collapsible details under #faq)."""
    return redirect("/#faq", permanent=True)


def privacy(request):
    """F2c (T264): what Mifgash stores, what it does not, who sees what."""
    return render(request, "planner/privacy.html")


def guide_host(request):
    """T122/T113: the host name shown in the agents.md chip. The page is often opened on a LAN or
    loopback address, and an IP must not show in the video or on a public page: then the chip
    shows the MIFGASH_PUBLIC_URL host when that is a name, else no host at all."""
    import ipaddress
    from urllib.parse import urlsplit

    def is_name(host):
        host = (host or "").strip("[]")
        if not host or host in calendar.LOOPBACK:
            return False
        try:
            ipaddress.ip_address(host)
            return False
        except ValueError:
            return True

    req = urlsplit("//" + request.get_host())
    if is_name(req.hostname):
        return request.get_host()
    pub = urlsplit(settings.PUBLIC_URL)
    return pub.netloc if is_name(pub.hostname) else ""


ICONS = {"favicon.ico": "image/x-icon", "favicon.svg": "image/svg+xml",
         "apple-touch-icon.png": "image/png", "favicon-32.png": "image/png"}


def icon(request, name):
    """T119: browsers and phones ask for the icons at the site root, not under /static/."""
    from pathlib import Path
    path = Path(__file__).resolve().parent / "static" / "planner" / name
    if name not in ICONS or not path.exists():
        raise Http404
    resp = HttpResponse(path.read_bytes(), content_type=ICONS[name])
    resp["Cache-Control"] = "public, max-age=86400"
    return resp


def agents_guide(request):
    """T99: the whole agent API in plain words, for an agent that cannot install the OpenClaw
    skill. One text, served at /agents.md and /llms.txt. Links use the public base URL."""
    from django.template.loader import render_to_string
    from .models import KINDS, PARTS
    text = render_to_string("planner/agents.md", {
        "PRODUCT_NAME": settings.PRODUCT_NAME, "base": calendar.public_base(request),
        "REPO_URL": settings.REPO_URL,
        "parts": ", ".join(k for k, _ in PARTS), "kinds": ", ".join(k for k, _ in KINDS),
        # T188: the fields example uses tomorrow's date, so it is never a past day.
        "example_date": (timezone.localdate() + dt.timedelta(days=1)).isoformat()})
    return HttpResponse(text.strip() + "\n", content_type="text/plain; charset=utf-8")


SKILL_FILES = ("SKILL.md", "mif.py", "relay.py", "mifgash-relay.service")


def skill_zip(request):
    """F7c (T263): the OpenClaw skill as one download. Built in memory from integrations/openclaw,
    flat names under mifgash/ (no absolute path), only the known files (no __pycache__)."""
    import io
    import zipfile
    from pathlib import Path
    folder = Path(settings.BASE_DIR) / "integrations" / "openclaw"
    files = [folder / n for n in SKILL_FILES if (folder / n).is_file()]
    if not (folder / "SKILL.md").is_file():
        raise Http404("skill folder is missing")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.writestr("mifgash/" + f.name, f.read_bytes())
    resp = HttpResponse(buf.getvalue(), content_type="application/zip")
    resp["Content-Disposition"] = 'attachment; filename="mifgash-skill.zip"'
    resp["Cache-Control"] = "public, max-age=300"
    return resp


def llms_txt(request):
    """F2b (T252): /llms.txt starts with a pointer to /agents.md, then holds the same guide."""
    base = calendar.public_base(request)
    head = f"# {settings.PRODUCT_NAME}\nAgents: read {base}/agents.md\n\n"
    return HttpResponse(head + agents_guide(request).content.decode(), content_type="text/plain; charset=utf-8")


def demo_only(view):
    """Demo pages open only with MIFGASH_DEMO=1 and the demo admin token (planner/demo.py); else 404."""
    def wrapped(request, *args, **kwargs):
        if not demo.allowed(request):
            raise Http404("demo pages are off")
        return demo.remember(request, view(request, *args, **kwargs))
    wrapped.__name__ = view.__name__
    return wrapped


def demo_people():
    """The seeded demo world: the demo owner and the seeded friends. Never a real signup."""
    return Person.objects.filter(is_owner=True) | demo_friends()


def can_see_plan(request, plan):
    """A plan page opens for a person on that plan (the dashboard session: the owner or a friend
    who got an offer). With MIFGASH_DEMO=1 it also opens for the plans of the seeded demo people."""
    p = dash_person(request)
    if p and (plan.owner_id == p.pk or plan.offers.filter(person=p).exists()):
        return True
    return demo.allowed(request) and demo_people().filter(pk=plan.owner_id).exists()


def visible_plan(request, uid, qs=None):
    """The plan, or 404 when this visitor may not see it (the same answer as an unknown id).
    F8a (T260): public URLs carry the uuid, never the integer id."""
    plan = get_object_or_404(qs if qs is not None else Plan.objects, uid=uid)
    if not can_see_plan(request, plan):
        raise Http404("unknown plan")
    return plan


def plan_view(request, uid):
    plan = visible_plan(request, uid, Plan.objects.select_related("owner", "area", "chosen__area"))
    return render(request, "planner/plan.html", {"plan": plan, **plan_state(plan)})


def plan_state(plan):
    guests = [o.person for o in plan.offers.filter(status="accepted").select_related("person")]
    last = ChatTurn.objects.filter(plan=plan, role="agent").last()
    waiting_human = plan.offers.filter(status="pending", person__has_agent=False).select_related("person").first()
    owner_wait = plan.offers.filter(status="owner_wait").select_related("person", "choice").first()
    return {
        "owner_wait": owner_wait,
        "owner_wait_text": messages.owner_ask_text(owner_wait.person, plan, owner_wait.choice) if owner_wait else "",
        "status": plan.status,
        "guests": guests,
        "owner_text": last.text if last else "",
        "buttons": last.buttons if last else [],
        "waiting_human": waiting_human,
    }


@require_POST
def plan_step(request, uid):
    plan = visible_plan(request, uid)
    result = engine.step(plan)
    plan.refresh_from_db()
    st = plan_state(plan)
    return JsonResponse({
        "result": result, "status": plan.status, "owner_text": st["owner_text"],
        "guests": [g.name for g in st["guests"]],
        "waiting_human": bool(st["waiting_human"]),
        "owner_wait": bool(st["owner_wait"]),
        "human_link": f"/h/{st['waiting_human'].token}/" if st["waiting_human"] else "",
        "log": [log_row(m) for m in AgentMessage.objects.filter(plan=plan)],
    })


def friend_first(p):
    """First name of the friend on an ask_owner or owner_approve row; old rows look it up by offer."""
    f = p.get("friend") or {}
    if f.get("name") or f.get("handle"):
        return (f.get("name") or "").split()[0] if (f.get("name") or "").strip() else f["handle"]
    o = Offer.objects.filter(pk=p.get("offer_id")).select_related("person").first()
    return messages.first_name(o.person) if o else "your friend"


def log_row(m):
    """One log row in plain words. The order seed stays in the payload (operator view), not in the
    words. A click on the dashboard (payload via='dashboard') is credited to the person (T96)."""
    p = m.payload
    sender = m.sender
    if p.get("via") == "dashboard" and ":" in sender:
        sender = f"person:{sender.split(':', 1)[1]} (on the dashboard)"
    summary = {
        "find": f"looking for friends open {p.get('intent', {}).get('part')} near {p.get('intent', {}).get('area', {}).get('name')}: {p.get('candidates')} found, random order",
        "offer": p.get("text", ""),
        "accept": "yes" + (f", picks {p['choice']['name']}" if p.get("choice") else ""),
        "decline": "not this time (reason stays private)",
        "expired": "no answer in time; moving on quietly",
        "confirm": p.get("text", ""),
        "close": p.get("text", ""),
        "no_match": "did not work out; the other options go to you only",
        "push": f"pushed {p.get('event')} to the agent, try {p.get('attempt')}: HTTP {p.get('http_status') or 'no answer'}",
        "push_skip": f"{p.get('event')}: {p.get('text', '')}",
        "push_refused": f"{p.get('event')}: not sent, {p.get('text', '')}",
        "email_stub": p.get("text", ""),
        "email_sent": p.get("text", ""),
        "ask_owner": f"{friend_first(p)} said yes. Your call." if m.type == "ask_owner" else "",
        "owner_approve": f"You approved {friend_first(p)}." if m.type == "owner_approve" else "",
        "owner_pass": "You passed (the reason stays private).",
        # G3 (T229): the group dinner rows in plain words, counts only
        "owner_confirm": f"go with the {p.get('guests')} who said yes" if m.type == "owner_confirm" else "",
        "fill_by": f"deadline: the group goes with the {p.get('guests')} who said yes" if m.type == "fill_by" else "",
        "group_place": f"picked {p.get('options', ['a place'])[0]} for the group, nearest the middle of everybody" if m.type == "group_place" else "",
    }.get(m.type) or p.get("text") or m.type
    return {"t": m.created.astimezone().strftime("%H:%M:%S"), "from": sender, "to": m.receiver,
            "type": m.type, "summary": summary, "json": p, "model": llm.model_label(p.get("backend"))}


def local_today():
    """Today in the product's home time zone (the SF bay area), not the server's."""
    return timezone.now().astimezone(ZoneInfo(calendar.TZID)).date()


def viewer_rows(p, plan):
    """The rows a dashboard person sees for one plan: the same as the dashboard Activity, so on the
    owner's own plan the offers and declines stay private."""
    msgs = AgentMessage.objects.filter(plan=plan)
    mine = msgs.filter(sender=p.address) | msgs.filter(receiver=p.address)
    if plan.owner_id == p.pk:
        mine = mine.exclude(type__in=PRIVATE_TO_OWNER)
    return dash_rows(mine, viewer=p)


def plan_log(request, uid):
    plan = visible_plan(request, uid)
    if request.GET.get("format") == "json" or "application/json" in request.headers.get("Accept", ""):
        return plan_log_json(request, plan)
    p = dash_person(request)
    if p:  # F5a (T254): a person sees the activity rows in words, never the raw payload
        return render(request, "planner/log.html", {"plan": plan, "viewer": p, "rows": viewer_rows(p, plan)})
    rows = [log_row(m) for m in AgentMessage.objects.filter(plan=plan)]  # MIFGASH_DEMO operator view
    offers = plan.offers.select_related("person").all()
    return render(request, "planner/log.html", {"plan": plan, "rows": rows, "offers": offers})


def plan_log_json(request, plan):
    """M7b (T179): the dashboard poller. 'stamp' changes when the plan moves (a new log row, a new
    status or a new proposed time), so the page re-renders only then. Rows are the ones the viewer's
    dashboard shows for this plan: on the owner's own plan, offers and declines stay private."""
    p = dash_person(request)
    msgs = AgentMessage.objects.filter(plan=plan)
    last = msgs.order_by("-pk").values_list("pk", flat=True).first() or 0
    if p:
        rows = viewer_rows(p, plan)
    else:  # MIFGASH_DEMO operator view of a seeded plan
        rows = [log_row(m) for m in msgs]
    for r in rows:
        r.pop("json", None)
    proposed = plan.proposed_time.strftime("%H:%M") if plan.proposed_time else ""
    return JsonResponse({"plan_id": plan.pk, "status": plan.status, "proposed_time": proposed or None,
                         "stamp": f"{last}-{plan.status}-{proposed}-{plan.proposed_by_id or ''}",
                         "rows": rows})


@require_POST
@demo_only
def plan_expire(request, uid):
    """Demo button: move the clock past the pending human's expiry."""
    plan = visible_plan(request, uid)
    plan.offers.filter(status="pending").update(expires_at=timezone.now() - dt.timedelta(seconds=1))
    return redirect("plan", uid=plan.uid)


def human_offer(request, token):
    """Friend with no agent. No login: the link is the key. The answer goes through the same engine
    path as POST /api/v1/proposals/<id>/respond/, so an owner with an agent still approves."""
    offer = get_object_or_404(Offer.objects.select_related("plan__owner", "plan__area", "person"), token=token)
    plan = offer.plan
    opts = plan.option_list()
    if request.method == "POST" and offer.status == "pending" and plan.status == "asking":
        if request.POST.get("answer") == "yes":
            pick = next((a for a in opts if str(a.pk) == request.POST.get("choice")), None)
            engine.candidate_answer(offer, True, choice=pick)
        else:
            engine.candidate_answer(offer, False, note="human tapped 'not this time'")
        return redirect("human_offer", token=token)
    error = None
    if request.method == "POST" and offer.status == "accepted" and plan.status in ("confirmed", "final") and (request.POST.get("time") or request.POST.get("other")):
        # T121: the friend with no agent sets or agrees the exact time here, the same code as the
        # dashboard and POST /api/v1/outings/<id>/finalize/. The link is the key.
        try:
            finalize.finalize(plan, offer.person, (request.POST.get("time") or request.POST.get("other")), request.POST.get("activity_id") or None)
            return redirect("human_offer", token=token)
        except finalize.FinalizeError as e:
            error = e.message[:1].upper() + e.message[1:] + "."
        plan.refresh_from_db()
    offer.refresh_from_db()
    state = {"pending": "pending", "owner_wait": "waiting", "accepted": "waiting", "declined": "declined",
             "closed": "closed"}.get(offer.status, "expired")
    if offer.status == "pending" and plan.status != "asking":
        state = "expired"
    m = None
    if offer.status == "accepted" and plan.status in ("confirmed", "final"):
        state = "set"
        # T121: the same outing ticket as the dashboard, seen by the friend. No time form and no
        # dashboard links: this person has no session. A final plan carries the calendar links.
        m = match_row(plan, offer.person, request.build_absolute_uri("/"))
        m["action"] = request.path
    who = messages.first_name(plan.owner)
    return render(request, "planner/human.html", {
        "offer": offer, "plan": plan, "state": state, "options": opts, "m": m, "error": error,
        "reason_model": llm.model_label(offer.reason_backend),
        "who": who, "initial": who[:1].upper(), "me_name": messages.first_name(offer.person),
        "kind": messages.kind_word(plan), "when": messages.ui_when(plan.date, plan.part),
        "expired_text": messages.expired_text(plan.owner),
        "closed_text": messages.group_closed_text(plan),
    })


@demo_only
def dev_links(request):
    """Demo only: the open human-page links, so the demo can open what a friend got by email."""
    rows = [{"offer": o, "url": f"/h/{o.token}/", "when": messages.when(o.plan.date, o.plan.part)}
            for o in Offer.objects.filter(status="pending", plan__status="asking", person__has_agent=False)
            .select_related("person", "plan__owner").order_by("-sent_at", "-pk")]
    return render(request, "planner/dev_links.html", {"rows": rows})


def open_slots(o, viewer=None, days=7):
    """The owner's open times for the next week, each with one activity idea.
    When the viewer is known, mark the times when the viewer is open too."""
    today = dt.date.today()
    out = []
    for i in range(1, days + 1):
        d = today + dt.timedelta(days=i)
        for s in Slot.objects.filter(person=o, weekday=d.weekday()).select_related("area"):
            kind = matching.KIND_FOR_PART[s.part]
            if s.part == "morning" and d.weekday() not in (4, 5):
                continue
            idea = matching.suggest_activities(kind, s.where(), 3.0, limit=1)
            both = bool(viewer and Slot.objects.filter(person=viewer, weekday=d.weekday(), part=s.part).exists())
            out.append({"date": d, "part": s.part, "kind": kind, "area": s.where(), "idea": idea[0] if idea else None,
                        "both": both, "label": messages.when(d, s.part),
                        "line": messages.human_slot_text(o, d, s.part) if both else ""})
    out.sort(key=lambda r: (not r["both"], r["date"]))
    return out


@demo_only
def open_page(request, token):
    """Calendly-like page: the owner's open times. For friends without an agent."""
    o = get_object_or_404(Person, token=token, is_owner=True)
    viewer = demo_people().filter(pk=request.GET.get("me")).first() if request.GET.get("me") else None
    if request.method == "POST":
        viewer = get_object_or_404(demo_people(), pk=request.POST.get("me"))
        d = dt.date.fromisoformat(request.POST["date"])
        part = request.POST["part"]
        slot = Slot.objects.filter(person=o, weekday=d.weekday(), part=part).first()
        if not slot:
            raise Http404("That time is no longer open")
        kind = matching.KIND_FOR_PART[part]
        plan = Plan.objects.create(owner=o, raw_text=f"{viewer.name} picked an open time", kind=kind, date=d,
                                   part=part, area=slot.where(), group_size=1, min_guests=1, status="asking")
        plan.options.set(matching.suggest_activities(kind, slot.where(), 3.0, limit=3))
        offer = Offer.objects.create(plan=plan, person=viewer, order=0, status="pending", sent_at=timezone.now())
        engine.log(plan, viewer.address, o.address, "join", slot={"date": d.isoformat(), "part": part})
        engine.record_answer(offer, True, choice=(plan.option_list() or [None])[0])
        engine.confirm(plan)  # the owner said this time is open; the owner's agent accepts at once
        return redirect("outing", uid=plan.uid)
    return render(request, "planner/open.html", {
        "owner": o, "viewer": viewer, "slots": open_slots(o, viewer),
        "humans": demo_friends().order_by("name"),
    })


def outing(request, uid):
    """The outing ticket alone: the same partial and data as the dashboard card (T120)."""
    plan = visible_plan(request, uid, Plan.objects.select_related("owner", "chosen__area", "area",
                                                                  "proposed_activity__area", "proposed_by"))
    if plan.status not in ("confirmed", "final"):
        return redirect("plan", uid=plan.uid)
    p = dash_person(request)
    side = p if p and p.pk in {x.pk for x in finalize.sides(plan)} else None
    # A demo visitor who is not on the plan sees the owner's ticket, with no forms.
    m = match_row(plan, side or plan.owner, request.build_absolute_uri("/"), forms=bool(side))
    return render(request, "planner/outing.html", {"plan": plan, "m": m})


def short_side(token):
    """(plan, person) for a short calendar token of a final plan, else 404 (T82)."""
    ids = calendar.read_short(token)
    if not ids:
        raise Http404("unknown invite")
    plan = get_object_or_404(Plan.objects.select_related("owner", "chosen__area", "area"), pk=ids[0], status="final")
    person = next((p for p in [plan.owner] + plan.guests() if p.pk == ids[1]), None)
    if not person:
        raise Http404("unknown invite")
    return plan, person


def calendar_short(request, token):
    """Short chat link: 302 to the Google Calendar 'add event' page for this side."""
    plan, person = short_side(token)
    return redirect(calendar.links(plan, person)["google_calendar_url"])


def calendar_short_ics(request, token):
    plan, person = short_side(token)
    resp = HttpResponse(calendar.ics(plan, person), content_type="text/calendar; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="mifgash-{str(plan.uid)[:8]}.ics"'
    return resp


def outing_ics(request, uid, sig):
    """The calendar file for one side of a final outing. No session: the link is signed for the
    plan and the person (?for=<person id>), so a calendar app can fetch it. Wrong sig = 404."""
    pid = request.GET.get("for", "")
    plan = Plan.objects.select_related("owner", "chosen__area", "area").filter(uid=uid, status="final").first()
    if not plan or not pid.isdigit() or not calendar.check(plan.pk, int(pid), sig):
        raise Http404("unknown invite")
    person = next((p for p in [plan.owner] + plan.guests() if p.pk == int(pid)), None)
    if not person:
        raise Http404("unknown invite")
    resp = HttpResponse(calendar.ics(plan, person), content_type="text/calendar; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="mifgash-{str(plan.uid)[:8]}.ics"'
    return resp


@demo_only
def friends(request):
    people = demo_people().select_related("home_area", "work_area").prefetch_related("slots__area").order_by("-is_owner", "name")
    pending = {o.person_id: o for o in Offer.objects.filter(status="pending", person__in=people).select_related("plan")}
    return render(request, "planner/friends.html", {"people": people, "pending": pending, "me": owner()})


@demo_only
def friend_view(request, pk):
    """What one friend's agent received and answered. Only this friend's own messages."""
    p = get_object_or_404(demo_people(), pk=pk)
    msgs = AgentMessage.objects.filter(receiver=p.address) | AgentMessage.objects.filter(sender=p.address)
    rows = [log_row(m) for m in msgs.order_by("created", "pk")]
    return render(request, "planner/friend.html", {"p": p, "rows": rows})


DASH_KEY = "person_id"
# 'queued' too: it would show that a second friend stands in line (T75).
PRIVATE_TO_OWNER = ("offer", "decline", "expired", "invite_link", "queued")


def actor_word(address, viewer, names, start=False):
    """A log address in words for the viewer's dashboard (T111): 'Mifgash', 'your agent', 'you',
    "Maria's agent", 'Maria'. The raw address stays in the payload, the plan log and --json."""
    kind, _, rest = address.partition(":")
    on_dash = rest.endswith(" (on the dashboard)")
    handle = rest.removesuffix(" (on the dashboard)")
    if kind == "mifgash":
        return "Mifgash"
    own = handle == viewer.handle
    if own:
        word = "you" if kind in ("person", "human") else "your agent"
        word = word[:1].upper() + word[1:] if start else word
    else:
        friend = names.get(handle)
        name = messages.first_name(friend) if friend else handle
        word = f"{name}'s agent" if kind == "agent" else name
    return word + (" (on the dashboard)" if on_dash else "")


STRUCTURED_POST = re.compile(r"^(?:date|part|kind|area) [^,]+(?:, (?:date|part|kind|area) [^,]+)*$")
H_LINK = re.compile(r"\s*Open \S*/h/\S+")
AGENT_TIME_ASK = "Send the same time and place to make it final, or send another one."


def human_summary(m, summary, viewer):
    """M6d (T200): log words for a person with no agent. They answer on /d/, so no /h/ link, no
    agent command words and no raw post fields. Agent owners keep the old words."""
    plan = m.plan
    if m.type == "availability" and plan is not None and plan.owner_id == viewer.pk:
        said = (m.payload.get("text") or "").strip()
        words = f"You posted: {messages.ui_when(plan.date, plan.part)}, near {plan.area.name}"
        if said and not STRUCTURED_POST.match(said):
            words += f' ("{said}")'
        return words
    summary = H_LINK.sub(" Answer above.", summary)
    return summary.replace(AGENT_TIME_ASK, "Press Agree, or pick another time.")


def dash_rows(msgs, viewer=None):
    """Dashboard log rows, newest first. A push_skip row stays in the database but not here; a push
    that worked is a small 'sent to your agent' tag on the row before it for the same plan (T75).
    With a viewer, each row gets 'who' in words for that person (T111)."""
    rows = []
    for m in reversed(list(msgs.select_related("plan__area").order_by("-created", "-pk")[:80])):
        if m.type == "push_skip":
            continue
        if m.type == "push" and m.payload.get("ok"):
            prev = next((r for r in reversed(rows) if r["plan_id"] == m.plan_id), None)
            if prev:
                prev["sent"] = True
                continue
        r = log_row(m)
        r["plan_id"] = m.plan_id
        if viewer is not None and not viewer.has_agent:
            r["summary"] = human_summary(m, r["summary"], viewer)
        rows.append(r)
    rows = rows[::-1][:60]
    if viewer is not None:
        handles = {a.partition(":")[2].removesuffix(" (on the dashboard)") for r in rows for a in (r["from"], r["to"])}
        names = {p.handle: p for p in Person.objects.filter(handle__in=handles)}
        for r in rows:
            r["who"] = f"{actor_word(r['from'], viewer, names, start=True)} → {actor_word(r['to'], viewer, names)}"
    return rows


def dashboard_link(request, token):
    """Magic-link entry. GET only shows a button, so a link preview (Telegram, mail scanners) does not
    spend the link. The POST spends it once and logs the person in. Used, expired or unknown = plain 410 page."""
    link = MagicLink.find(token)
    if not link or link.used_at or link.expired():
        return render(request, "planner/link_used.html", {"expired": bool(link and not link.used_at)}, status=410)
    if request.method != "POST":
        return render(request, "planner/link_open.html", {"first": link.person.name.split()[0]})
    link.used_at = timezone.now()
    link.save(update_fields=["used_at"])
    request.session[DASH_KEY] = link.person_id
    return redirect("dashboard")


EMAIL_ANSWER = "Email is not live yet. Ask your agent for the link."
EMAIL_ANSWER_LIVE = "If this address belongs to a {name} account, a link is on its way. Check your inbox."


def dashboard_visitor(request):
    """M5 (T165): /d/ with no session. One page: the agent gives you the link, a demo button, and a
    'get a link by email' form. The answer to the form is the same for a known and an unknown
    address, so the page never tells if an account exists."""
    from . import fallback, ratelimit
    ctx = {"email_answer": None}
    if request.method == "POST":
        slow = ratelimit.check(request, "dash_email", ip=(10, 3600))
        if slow:
            return slow
        email = (request.POST.get("email") or "").strip()
        sent = False
        person = Person.by_email(email) if "@" in email and len(email) <= 254 else None
        if person:
            _, token = MagicLink.issue(person)
            sent = fallback.send_link_email(person, request.build_absolute_uri(f"/d/{token}/"))
        ctx["email_answer"] = (EMAIL_ANSWER_LIVE.format(name=settings.PRODUCT_NAME)
                               if fallback.email_live() else EMAIL_ANSWER)
        ctx["sent"] = sent
    return render(request, "planner/dashboard_visitor.html", ctx)



LOGIN_ANSWER = "If that email is on {name}, the link is on its way."
LOGIN_TTL = dt.timedelta(minutes=30)
LOGIN_RATE_EMAIL = (5, 3600)   # tries per email per hour
LOGIN_RATE_IP = (20, 3600)     # tries per client IP per hour


def login_page(request):
    """F3b (T261): log in again by email. POST an email; a known address gets a 30-minute, one-use
    dashboard link by email. The answer is the same for a known and an unknown address, so the page
    never tells if an account exists. 5 tries per email per hour, 20 per IP. With MIFGASH_DEBUG=1 and
    no mail route the page shows the link (local testing only)."""
    from . import fallback, ratelimit
    from .models import email_digest
    ctx = {"answer": None, "debug_link": None, "email": ""}
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip()
        slow = ratelimit.check(request, "login", ip=LOGIN_RATE_IP)
        if not slow and settings.RATE_LIMITS and email:
            wait = ratelimit.hit(f"login:e:{email_digest(email)}", *LOGIN_RATE_EMAIL)
            slow = ratelimit.too_many(wait) if wait else None
        if slow:
            return slow
        person = Person.by_email(email) if "@" in email and len(email) <= 254 else None
        if person:
            _, token = MagicLink.issue(person, ttl=LOGIN_TTL)
            url = request.build_absolute_uri(f"/d/{token}/")
            sent = fallback.send_link_email(person, url, valid_for="30 minutes")
            if settings.DEBUG and not sent:
                ctx["debug_link"] = url
        ctx["answer"] = LOGIN_ANSWER.format(name=settings.PRODUCT_NAME)
        ctx["email"] = email
    return render(request, "planner/login.html", ctx)

JOIN_RATE = (10, 3600)


def join(request):
    """M6a (T175): web signup for a person with no agent. Name, handle, email (required, F3a T259),
    an optional free-text main city.
    The POST makes Person(has_agent=False) with no AgentKey, logs the browser in and opens /d/."""
    from django.core.exceptions import ValidationError
    from django.db import IntegrityError
    from . import ratelimit
    from .models import clean_email, clean_handle, clean_name
    form = {"name": "", "handle": "", "email": "", "city": ""}
    errors = {}
    if request.method == "POST":
        slow = ratelimit.check(request, "join", ip=JOIN_RATE)
        if slow:
            return slow
        form = {k: (request.POST.get(k) or "").strip() for k in form}
        name = ""
        if not form["name"]:
            errors["name"] = "Write your name."
        else:
            try:
                name = clean_name(form["name"])
            except ValidationError as e:
                errors["name"] = ("Use at most 40 characters." if "at most" in e.messages[0]
                                  else "Use letters, digits, spaces and . ' - only.")
        handle = ""
        try:
            handle = clean_handle(form["handle"])
        except ValidationError:
            errors["handle"] = "Use 2 to 32 characters: letters, digits and underscore."
        if handle and Person.objects.filter(handle=handle).exists():
            errors["handle"] = "Somebody has this handle. Pick a different one."
        # F3a (T259): the email is required. It is the only way back in when the link is lost.
        email = ""
        if not form["email"]:
            errors["email"] = "Write your email. You need it to log in again."
        else:
            try:
                email = clean_email(form["email"])
            except ValueError:
                errors["email"] = "Write a full email address, for example you@example.com."
            else:
                if Person.by_email(email):
                    errors["email"] = "Somebody uses this email already."
        city = " ".join(form["city"].split())[:40]
        if not errors:
            try:
                p = Person.objects.create(name=name, handle=handle, has_agent=False, city=city, email=email)
            except IntegrityError:
                errors["handle"] = "Somebody has this handle. Pick a different one."
            else:
                invite_token = request.session.get(INVITE_KEY)
                request.session.cycle_key()
                request.session[DASH_KEY] = p.pk
                accept_invite(request, invite_token, p)
                return redirect("dashboard")
    return render(request, "planner/join.html", {"form": form, "errors": errors})


INVITE_KEY = "invite_token"


def accept_invite(request, token, person):
    """After a /join/ signup: the invite kept in the session makes the inviter a friend (T224)."""
    request.session.pop(INVITE_KEY, None)
    inv = Invite.find(token) if token else None
    if not inv or inv.used_up():
        return None
    if inv.accept(person) == "friends":
        request.session["dash_note"] = f"You and {inv.person.name} are friends now."
    return inv


def invite_landing(request, token):
    """M11b (T224): /i/<token>/. A logged-in visitor becomes the inviter's friend at once. A visitor
    with no session sees 'Join <name>' and the token waits in the session for the /join/ signup.
    An unknown or used-up token: 404 with a plain line."""
    inv = Invite.find(token)
    if not inv or inv.used_up():
        return render(request, "planner/invite.html", {"bad": True}, status=404)
    first = inv.person.name.split()[0]
    ctx = {"first": first, "handle": inv.person.handle}
    viewer = dash_person(request)
    if viewer:
        state = inv.accept(viewer)
        if state == "friends":
            request.session["dash_note"] = f"You and {inv.person.name} are friends now."
            return redirect("dashboard")
        return render(request, "planner/invite.html", {**ctx, "state": state})
    request.session[INVITE_KEY] = token
    # F4a (T253), T288: the friend link. 'I have an agent' shows one line to paste into the agent.
    link = api.invite_url(inv)
    prompt = INVITE_PROMPT.format(link=link, name=settings.PRODUCT_NAME, handle=inv.person.handle)
    return render(request, "planner/invite.html", {**ctx, "state": "join", "prompt": prompt})


INVITE_PROMPT = "Using {link} (remember it as {name}), sign me up and join @{handle} as a friend."


def try_demo(request):
    """M7a (T178): GET shows one button. POST makes a sandbox owner and three sandbox friends (Maria,
    Sam and Lena, each with an own agent), logs the browser in and opens /d/. T317: a browser that
    already holds a live sandbox person goes back to /d/ and does not count. About 20 sessions an
    hour per IP; the cap answer is the try page with a friendly line (429). A full sandbox is 503."""
    from . import ratelimit, sandbox
    if request.method != "POST":
        return render(request, "planner/try.html", {"busy": False})
    me = dash_person(request)
    if me and me.is_sandbox and me.expires_at and me.expires_at > timezone.now():
        return redirect("dashboard")
    wait = ratelimit.wait_for(request, "try", ip=sandbox.IP_RATE)
    if wait:
        r = render(request, "planner/try.html", {"busy": False, "cap_minutes": max(1, -(-wait // 60))}, status=429)
        r["Retry-After"] = str(wait)
        return r
    try:
        p = sandbox.create_session()
    except sandbox.Busy:
        return render(request, "planner/try.html", {"busy": True}, status=503)
    request.session.cycle_key()
    request.session[DASH_KEY] = p.pk
    return redirect("dashboard")


def dash_person(request):
    pid = request.session.get(DASH_KEY)
    return Person.objects.filter(pk=pid).first() if pid else None


def dashboard(request):
    """The person's own view of what the agent did: open outings, matches, the agent log.
    Only messages the person sent or got, so declines and the ask order stay private."""
    p = dash_person(request)
    if not p:
        return dashboard_visitor(request)
    plans = Plan.objects.filter(owner=p).select_related("area", "chosen__area")
    open_rows = []
    # A plan where a friend said yes waits for the owner under Matches, so it leaves this block (T83).
    for pl in plans.filter(status__in=["open", "asking"]).exclude(offers__status="owner_wait").order_by("date", "pk"):
        state, ask = ("asking a friend" if pl.status == "asking" else "waiting for a match"), None
        if pl.status == "open":
            # The same state as mif.py open-list (T95): a friend's ask for this time waits below.
            ask = api.waiting_for_me(pl)
            if ask:
                state = f"{messages.first_name(ask.plan.owner)} is free too. Answer above."
        group = group_progress(pl)
        open_rows.append({"plan": pl, "when": messages.card_when(pl), "state": state, "ask": ask,
                          "group": group, "go_with": group and go_with(pl)})
    waiting = []
    for o in Offer.objects.filter(plan__owner=p, status="owner_wait", plan__status="asking").select_related(
            "person", "choice__area", "plan__area"):
        waiting.append({"offer": o, "reason_model": llm.model_label(o.reason_backend), "when": messages.card_when(o.plan),
                        "place": o.choice or (o.plan.option_list() or [None])[0], "group": group_progress(o.plan)})
    # The friend's side of an owner_wait offer: they said yes, the owner has not decided yet.
    said_yes = []
    for o in Offer.objects.filter(person=p, status="owner_wait", plan__status="asking").select_related(
            "plan__owner", "plan__area", "choice__area").order_by("plan__date", "pk"):
        place = o.choice or (o.plan.option_list() or [None])[0]
        said_yes.append({"offer": o, "text": messages.said_yes_text(o), "place": place,
                         "owner": messages.first_name(o.plan.owner)})
    # Offers that wait for this person's own answer, and open friend requests. A person whose agent
    # has no webhook answers here; the push log says 'waiting on the dashboard'.
    asks = []
    for o in Offer.objects.filter(person=p, status="pending", plan__status="asking").select_related(
            "plan__owner", "plan__area").order_by("plan__date", "pk"):
        asks.append({"offer": o, "reason_model": llm.model_label(o.reason_backend), "who": messages.first_name(o.plan.owner), "when": messages.card_when(o.plan, messages.kind_word(o.plan)),
                     "kind": messages.kind_word(o.plan), "options": o.plan.option_list()})
    requests = list(Friendship.requests_to(p.pk).order_by("name", "pk"))
    done = ("confirmed", "final")
    mine = Plan.objects.filter(status__in=done).filter(owner=p) | Plan.objects.filter(
        status__in=done, offers__person=p, offers__status="accepted")
    matches = [match_row(pl, p, request.build_absolute_uri("/"))
               for pl in mine.distinct().select_related("owner", "area", "chosen__area", "proposed_activity__area",
                                                        "proposed_by").order_by("date", "pk")]
    # F5a (T254): a final meetup whose day is over (San Francisco time) moves to the Past meetups tab.
    today = local_today()
    past = [m for m in matches if m["plan"].status == "final" and m["plan"].date < today][::-1]
    matches = [m for m in matches if not any(m is x for x in past)]
    msgs = (AgentMessage.objects.filter(sender=p.address) | AgentMessage.objects.filter(receiver=p.address))
    # On the person's own plans, the offers to single friends and their answers stay private:
    # they would show who was asked first and who said no.
    msgs = msgs.exclude(plan__owner=p, type__in=PRIVATE_TO_OWNER)
    rows = dash_rows(msgs, viewer=p)
    # T110: a plan that left Open outings for Matches is not 'no open time'; the empty line says where it went.
    moved = bool(waiting or said_yes or any(m["plan"].status == "confirmed" for m in matches))
    ctx = {"p": p, "open_rows": open_rows, "waiting": waiting, "moved": moved,
           "said_yes": said_yes, "matches": matches, "past": past, "rows": rows,
           "asks": asks, "requests": requests,
           # M6e (T201): an ask or a match waits, so its cards come before the forms
           "busy": bool(asks or requests or waiting or said_yes or matches),
           "error": request.session.pop("dash_error", None)}
    # F3a (T259): a person with no email cannot log in again; the dashboard asks for one.
    ctx["needs_email"] = not p.email and not p.is_sandbox
    if not p.has_agent:  # M6b (T176): a person with no agent posts free times and adds friends here
        ctx.update(human_forms(request, p))
    if not p.is_sandbox:  # M11c (T225): the invite card; a demo session has no real friends to invite
        ctx["invite_url"] = api.invite_url(Invite.current(p))
    if p.is_sandbox:  # M7a (T178): the quick demo. The box stands in for the visitor's own agent.
        from . import sandbox
        ctx["sandbox"] = {"hours": sandbox.hours_left(p), "prefill": sandbox.PREFILL, "group": sandbox.GROUP_HINT}
        # M7b (T179): the page polls the newest plan that still moves, so the friend's answer shows live
        live = plans.filter(status__in=["open", "asking", "confirmed"]).order_by("-pk").first()
        if live:
            ctx["sandbox"]["poll"] = reverse("plan_log", args=[live.uid]) + "?format=json"
        ctx["note"] = request.session.pop("dash_note", None)
    elif p.has_agent:  # F3a (T259): the add-email card answers with a note or an error here too
        ctx["note"] = request.session.pop("dash_note", None)
    return render(request, "planner/dashboard.html", ctx)


def group_progress(plan):
    """G3 (T229): '2 of 3 in' for a group dinner that still asks. It counts the yeses only, so it
    never shows who said no or who was asked. None for a plan of two."""
    if plan.kind != "group_dinner" or plan.status != "asking":
        return None
    n = plan.offers.filter(status="accepted").count()
    return f"{n} of {plan.group_size} in"


def go_with(plan):
    """G3 (T229): the yes count for the 'Go with the N who said yes' button, once nobody is left
    to ask (no offer out, nobody in line). 0 hides the button."""
    if plan.offers.filter(status__in=["pending", "queued", "owner_wait"]).exists():
        return 0
    return plan.offers.filter(status="accepted").count()


FREE_AHEAD = 60  # F5b (T257): the date picker offers today and the next 59 days


def month_grids(today, picked=None):
    """F5b (T257): the 'Set up a meetup' date picker. One 6-week grid (Sun-Sat) per month from
    today to today + FREE_AHEAD - 1. A cell is None outside the month; a past day or a day past the
    range is off. dashboard.js shows one month at a time."""
    import calendar as cal
    import datetime as dt
    last = today + dt.timedelta(days=FREE_AHEAD - 1)
    grid = cal.Calendar(firstweekday=6)  # Sunday first
    months, y, m = [], today.year, today.month
    while (y, m) <= (last.year, last.month):
        weeks = grid.monthdatescalendar(y, m)
        while len(weeks) < 6:  # a steady 6-week block, so the modal does not jump between months
            weeks.append([weeks[-1][-1] + dt.timedelta(days=i) for i in range(1, 8)])
        cells = [[None if d.month != m else {
            "v": d.isoformat(), "day": d.day, "off": not (today <= d <= last), "today": d == today,
            "picked": d.isoformat() == picked, "label": messages.ui_day(d)} for d in w] for w in weeks]
        months.append({"label": f"{cal.month_name[m]} {y}", "weeks": cells})
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return months


MEET_EXAMPLES = ["Lunch near SoMa, sushi, no loud places",
                 "Playdate Saturday morning, a park with something on, kids 4 and 6",
                 "Group dinner Friday with 3 friends in Hayes Valley, in the mood for a new place"]


def human_forms(request, p):
    """The 'Set up a meetup' modal and the 'Add a friend' form on the dashboard of a person with
    no agent. F5b (T257): a post that missed a fact comes back in the session as dash_free; the
    modal then opens again with the text, the day and the error line."""
    import datetime as dt
    back = request.session.pop("dash_free", None) or {}
    today = dt.date.today()
    return {"free": {"months": month_grids(today, back.get("date")), "examples": MEET_EXAMPLES,
                     "text": back.get("text", ""), "error": back.get("error"),
                     "date": back.get("date", ""), "open": bool(back)},
            "sent": list(Friendship.requests_from(p.pk).order_by("name", "pk")),
            "fb_url": fb_login_url(),
            "note": request.session.pop("dash_note", None)}


def fb_login_url():
    """M11a (T171): the Facebook Login dialog link for 'Import from Facebook', or None when
    MIFGASH_FB_APP_ID is not set (the page then shows a disabled button)."""
    from urllib.parse import urlencode
    if not settings.FB_APP_ID:
        return None
    return "https://www.facebook.com/dialog/oauth?" + urlencode({
        "client_id": settings.FB_APP_ID, "scope": "user_friends", "response_type": "code",
        "redirect_uri": settings.PUBLIC_URL.rstrip("/") + "/friends/facebook/callback/"})


def needs_text(reply):
    """The ask-back of the availability code as one dashboard line."""
    words = {"when": "a day and a part of the day", "where": "an area", "what": "what you want to do"}
    return "Pick " + " and ".join(words[n] for n in reply["needs"] if n in words) + "."


@require_POST
def dashboard_free(request):
    """M6b (T176): 'I am free' from the dashboard. The same code as POST /api/v1/availability/."""
    from . import ratelimit
    from .availability import post
    from .models import Area
    p = dash_person(request)
    if not p:
        return redirect("home")
    slow = ratelimit.check(request, "availability", ip=(40, 3600))
    if slow:
        return slow
    data = {k: (request.POST.get(k) or "").strip() for k in ("date", "part", "kind", "text")}
    data["text"] = data["text"][:500]
    a = Area.objects.filter(pk=request.POST.get("area")).first() if (request.POST.get("area") or "").isdigit() else None
    if a:
        data["area"] = a.name
    data = {k: v for k, v in data.items() if v}

    def again(error):
        # F5b (T257): the modal opens again with the text and the day kept, the error under the box.
        # The demo box (an agent stands in) keeps the page-top error line.
        if p.has_agent:
            request.session["dash_error"] = error
            return redirect("dashboard")
        request.session["dash_free"] = {"error": error, "text": data.get("text", ""), "date": data.get("date", "")}
        return redirect("dashboard")
    try:
        reply, status = post(p, data, request)
    except ValueError as e:
        return again(str(e)[:1].upper() + str(e)[1:] + ".")
    if "error" in reply:
        return again("Pick a day and write a line: what, where, who.")
    if "needs" in reply:
        return again(needs_text(reply))
    if reply.get("duplicate"):
        request.session["dash_note"] = "You posted this time already. It is under Open outings."
    else:
        request.session["dash_note"] = f"Posted. {settings.PRODUCT_NAME} asks your friends one at a time."
    return redirect("dashboard")


@require_POST
@require_POST
def dashboard_email(request):
    """F3a (T259): the 'Add your email' card. Stored encrypted; the digest is kept for the login lookup."""
    from .models import clean_email
    p = dash_person(request)
    if not p:
        return redirect("home")
    try:
        email = clean_email(request.POST.get("email"))
    except ValueError:
        request.session["dash_error"] = "Write a full email address, for example you@example.com."
        return redirect("dashboard")
    other = Person.by_email(email)
    if other and other.pk != p.pk:
        request.session["dash_error"] = "Somebody uses this email already."
        return redirect("dashboard")
    p.email = email
    p.save(update_fields=["email", "email_digest"])
    request.session["dash_note"] = "Email saved. You can log in again with it."
    return redirect("dashboard")


def dashboard_friend_add(request):
    """M6b (T176): send a friend request from the dashboard. The same code as POST /api/v1/friends/.
    T256 (F4b): exact nickname only, no search list."""
    import json
    from .api import add_friend
    p = dash_person(request)
    if not p:
        return redirect("home")
    handle = (request.POST.get("handle") or "").strip().lstrip("@").lower()
    other = Person.objects.filter(handle=handle).first() if handle else None
    if not other:
        shown = "@" + handle if handle else "that"
        request.session["dash_error"] = f"No such nickname: {shown}. Ask your friend for the exact one."
        return redirect("dashboard")
    r = add_friend(p, other)
    body = json.loads(r.content)
    if r.status_code == 201:
        # T256 (F4b): name the handle the person typed, nothing more about the other side.
        request.session["dash_note"] = (f"You and @{other.handle} are friends now." if body["status"] == "friends"
                                        else f"Request sent to @{other.handle}.")
    else:
        msg = body.get("error", "That did not work")
        request.session["dash_error"] = msg[:1].upper() + msg[1:] + "."
    return redirect("dashboard")


def match_row(pl, viewer, base=None, forms=True):
    """One outing ticket (dashboard Matches and /outing/<uid>/): confirmed, then a proposed exact
    time, then final. forms=False drops the time form (a viewer who is not on the plan)."""
    row = {"plan": pl, "when": messages.card_when(pl), "place": pl.chosen,
           "with": [x.name for x in [pl.owner] + pl.guests() if x.pk != viewer.pk],
           "date": {"w": messages.WEEKDAYS[pl.date.weekday()], "d": pl.date.day,
                    "mo": messages.MONTHS[pl.date.month - 1], "t": "time?"},
           "status_word": "Pick the time", "status_cls": "you"}
    row["hint"] = messages.place_hint(pl.chosen)  # M13b (T184): 'Garlic: yes.' at The Stinking Rose
    if pl.kind == "group_dinner":  # G2 (T228): the card says how many sit at the table
        row["group"] = len([pl.owner] + pl.guests())
    if pl.status == "final":
        row["when"] = f"{messages.ui_day(pl.date)}, {pl.exact_time.strftime('%H:%M')}"
        row["date"]["t"] = pl.exact_time.strftime("%H:%M")
        row["status_word"], row["status_cls"] = "It is set", "set"
        row["calendar"] = calendar.links(pl, viewer, base)
    elif pl.proposed_time:
        by = "you" if pl.proposed_by_id == viewer.pk else messages.first_name(pl.proposed_by) if pl.proposed_by else "a friend"
        row["proposed"] = f"{pl.proposed_time.strftime('%H:%M')} at {pl.proposed_activity.name if pl.proposed_activity else pl.area.name}"
        row["proposed_by"] = by
        # G2 (T228): who still has to agree. In a plan of two that is the other side.
        agreed = set(pl.agreed or [pl.proposed_by_id])
        people = [pl.owner] + pl.guests()
        row["waiting"] = [messages.first_name(x) for x in people if x.pk not in agreed and x.pk != viewer.pk]
        row["you_agreed"] = viewer.pk in agreed
    if pl.status == "final" and forms and pl.exact_time:
        # T258 (F6c): Mifgash set the time itself; three half-hour chips around it and an Other
        # select change it (the same finalize call, so the other side hears it).
        row["change"] = change_chips(pl.exact_time.strftime("%H:%M"))
        row["times"] = time_choices(pl.exact_time.strftime("%H:%M"))
        row["default_time"] = pl.exact_time.strftime("%H:%M")
        row["pick"] = pl.chosen_id
    if pl.status == "confirmed" and forms:
        # T94: a person without an agent sets or agrees the exact time here.
        row["places"] = finalize.places(pl)
        row["pick"] = pl.proposed_activity_id or pl.chosen_id
        row["default_time"] = (pl.proposed_time.strftime("%H:%M") if pl.proposed_time
                               else PART_TIMES.get(pl.part, "13:00"))
        row["times"] = time_choices(row["default_time"])
        if pl.proposed_time and viewer.pk not in set(pl.agreed or [pl.proposed_by_id]):
            row["agree"] = {"time": pl.proposed_time.strftime("%H:%M"), "place": pl.proposed_activity_id or pl.chosen_id}
    return row


# The usual start time of each part; the time field on a Confirmed card starts here.
PART_TIMES = {"morning": "10:00", "lunch": "13:00", "afternoon": "16:00", "evening": "19:00"}

# T202: the time select lists every half hour, 00:00 to 23:30, in 24-hour form. A browser
# <input type=time> follows the locale and shows AM/PM, so the ticket does not use one.
HALF_HOURS = [f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 30)]


def change_chips(set_time):
    """T258: the 3 half-hour chips around the set time: 30 min before, 30 and 60 min after."""
    h, m = map(int, set_time.split(":"))
    base = h * 60 + m
    return [f"{(t // 60) % 24:02d}:{t % 60:02d}" for t in (base - 30, base + 30, base + 60) if 0 <= t < 24 * 60]


def time_choices(default):
    """The half-hour list; a proposed time off the grid (13:15) is added in its place."""
    return HALF_HOURS if default in HALF_HOURS else sorted(HALF_HOURS + [default])


@require_POST
def dashboard_finalize(request, plan_id):
    """Set or agree the exact time and place from the dashboard (T94). The same code as
    POST /api/v1/outings/<id>/finalize/. A plan the person is not on is 404."""
    p = dash_person(request)
    if not p:
        return redirect("home")
    plan = get_object_or_404(Plan, pk=plan_id, status__in=["confirmed", "final"])
    if p.pk not in {x.pk for x in finalize.sides(plan)}:
        raise Http404
    try:
        finalize.finalize(plan, p, (request.POST.get("time") or request.POST.get("other")), request.POST.get("activity_id") or None)
    except finalize.FinalizeError as e:
        request.session["dash_error"] = e.message[:1].upper() + e.message[1:] + "."
    sandbox_agent.kick(p)  # M7b (T179): the demo friend confirms or counters the time
    return redirect("dashboard")


@require_POST
def dashboard_group_confirm(request, plan_id):
    """G3 (T229): the owner goes with the friends who said yes so far, the same engine call as
    POST /api/v1/availability/<id>/confirm/. Only the owner's own asking group dinner."""
    p = dash_person(request)
    if not p:
        return redirect("home")
    plan = get_object_or_404(Plan, pk=plan_id, owner=p, kind="group_dinner", status="asking")
    try:
        engine.confirm_smaller(plan)
    except ValueError as e:
        request.session["dash_error"] = str(e)[:1].upper() + str(e)[1:] + "."
    sandbox_agent.kick(p)  # the demo friends propose and agree the time
    return redirect("dashboard")


@require_POST
def dashboard_answer(request, offer_id):
    """Answer from the dashboard (session auth). The asked friend answers a pending offer, the same
    engine call as POST /api/v1/proposals/<id>/respond/; the owner approves or declines a friend's yes."""
    p = dash_person(request)
    if not p:
        return redirect("home")
    yes = request.POST.get("answer") == "accept"
    asked = Offer.objects.filter(pk=offer_id, person=p, status="pending", plan__status="asking").first()
    if asked:
        pick = next((a for a in asked.plan.option_list() if str(a.pk) == request.POST.get("choice")), None)
        engine.candidate_answer(asked, yes, choice=pick, note="answered on the dashboard", via="dashboard")
        return redirect("dashboard")
    offer = get_object_or_404(Offer, pk=offer_id, plan__owner=p, status="owner_wait", plan__status="asking")
    engine.owner_answer(offer, yes, note="answered on the dashboard", via="dashboard")
    engine.advance(offer.plan)
    if not yes:
        engine.rematch_open(offer.plan.date, offer.plan.part)
    sandbox_agent.kick(p)  # M7b (T179): the demo friend proposes the time
    return redirect("dashboard")


@require_POST
def dashboard_friend_accept(request, person_id):
    """Accept a friend request from the dashboard. Same as POST /api/v1/friends/<id>/accept/."""
    p = dash_person(request)
    if not p:
        return redirect("home")
    get_object_or_404(Friendship, person_id=person_id, friend=p, status="requested")
    from .api import add_friend
    add_friend(p, Person.objects.get(pk=person_id))
    return redirect("dashboard")


def dashboard_logout(request):
    request.session.pop(DASH_KEY, None)
    return redirect("home")
