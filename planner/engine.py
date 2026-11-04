"""The offer engine: random order, one offer at a time, gentle close.

step(plan) does ONE action, so the demo page can show the agents talk live.
"""
import copy
import datetime as dt
import random

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from . import fallback, llm, matching, messages, push
from .models import AgentMessage, ChatTurn, Offer, Plan

PROTOCOL = "mifgash/0.1"


def log(plan, sender, receiver, type_, **payload):
    payload = {"protocol": PROTOCOL, "type": type_, "plan_id": plan.pk, **payload}
    return AgentMessage.objects.create(plan=plan, sender=sender, receiver=receiver, type=type_, payload=payload)


def notify(person, event, plan, offer=None, role=None, **extra):
    """Push one event to a person's own agent (planner/push.py). The payload is what the API shows
    the same person, so a push never tells more than a GET would."""
    from .api import outing_json, proposal_json
    payload = {"plan_id": plan.pk, **extra}
    if offer is not None:
        payload["proposal"] = proposal_json(offer, role)
    if event in ("outing.confirmed", "outing.final"):
        payload["outing"] = outing_json(plan, viewer=person)
    push.push(person, event, payload, plan=plan)


def intent_payload(plan):
    return {
        "kind": plan.kind,
        "date": plan.date.isoformat(),
        "part": plan.part,
        "area": {"name": plan.area.name, "lat": plan.area.lat, "lon": plan.area.lon},
        "radius_km": plan.radius_km,
        "group_size": plan.group_size,
    }


def option_payload(a):
    return {"activity_id": a.pk, "name": a.name, "area": a.area.name, "price": a.price, "tags": a.tags}


@transaction.atomic
def start(plan, seed=None):
    """Find candidates, fix a random order, queue one offer per candidate."""
    plan.seed = seed if seed is not None else random.randrange(1, 10**6)
    plan.any_part = False  # a match fixes the part of the day (T79)
    people = fresh_candidates(plan)
    ordered = matching.random_order(people, plan.seed)
    for i, p in enumerate(ordered):
        Offer.objects.create(plan=plan, person=p, order=i)
    plan.status = "asking"
    plan.save()
    log(plan, plan.owner.address, "mifgash:directory", "find",
        intent=intent_payload(plan), candidates=len(ordered), order_seed=plan.seed,
        note="random order; no ranking by closeness or friendship")
    if not ordered:
        finish_no_match(plan)
    return plan


def try_match(plan, seed=None):
    """An open availability looks for friends. A match starts the random queue and sends the
    first offer. No match: the plan stays open and the owner gets one gentle log line.
    Returns 'matched', 'waiting' or the plan status when it is not open."""
    plan.refresh_from_db()
    if plan.status != "open":
        return plan.status
    if plan.any_part:  # 'open tomorrow' takes the first part of that day with a free friend (T102)
        hit = free_part(plan)
        if hit and hit != (plan.part, plan.kind):
            set_part(plan, *hit)
    if not fresh_candidates(plan):
        if not plan.log.filter(type="waiting").exists():
            log(plan, "mifgash:directory", plan.owner.address, "waiting",
                intent=intent_payload(plan), text=messages.waiting_text(plan))
        return "waiting"
    start(plan, seed)
    # Send the first offer, and let a simulated friend agent answer at once, until the plan
    # waits for a real agent, a human or the owner.
    advance(plan)
    return "matched"


def fresh_candidates(plan):
    """Candidates who were never in this plan's queue. Nobody is asked twice on one plan."""
    seen = set(plan.offers.values_list("person_id", flat=True)) if plan.pk else set()
    return [p for p in matching.candidates(plan) if p.pk not in seen and p.pk not in said_no(plan)]


def free_part(plan):
    """(part, kind) for a plan: the first part of its date where a friend is free to be asked now
    (an open plan or a weekly slot), or None. A plan with no part named (any_part) tries its own
    part first, then every other part in PARTS order; a plan with a part named tries only that one.
    The owner must be free at that part too. One helper for a new post and for rematch_open (T102)."""
    from .models import PARTS
    tries = [(plan.part, plan.kind)]
    if plan.any_part:
        for part, _ in PARTS:
            if part == plan.part:
                continue
            kind = matching.KIND_FOR_PART[part]
            if kind == "kids" and not plan.owner.kids_ages:
                continue
            tries.append((part, kind))
    for part, kind in tries:
        if busy(plan.owner, plan.date, part) or committed(plan.owner, plan.date, part):
            continue
        probe = plan
        if (part, kind) != (plan.part, plan.kind):
            probe = copy.copy(plan)
            probe.part, probe.kind = part, kind
        if any(not busy(c, plan.date, part) and not committed(c, plan.date, part)
               for c in fresh_candidates(probe)):
            return part, kind
    return None


def said_no(plan):
    """Both sides of a no for this date and part: friends who declined the owner's plan, and
    owners whose plan the owner declined. Two such people are never matched again for that meal."""
    q = Offer.objects.filter(status="declined", plan__date=plan.date, plan__part=plan.part)
    out = set(q.filter(plan__owner=plan.owner).values_list("person_id", flat=True))
    out |= set(q.filter(person=plan.owner).values_list("plan__owner_id", flat=True))
    return out


def rematch_open(date=None, part=None, now=None):
    """Open plans that can match now, but missed it: a new post goes to ONE older plan, so
    after a decline, an owner pass, a no match or an expiry, two other open friends can still
    fit each other. Oldest plan first. A plan is tried only when its owner holds no question
    for that meal and at least one new candidate is free to be asked.
    Returns the ids of the plans that started asking."""
    today = timezone.localdate(now or timezone.now())
    q = Plan.objects.filter(status="open", date__gte=today)
    if date is not None:
        q = q.filter(date=date)
    if part is not None:
        q = q.filter(Q(part=part) | Q(any_part=True))
    started = []
    for p in q.select_related("area", "owner").order_by("created", "pk"):
        p.refresh_from_db()
        if p.status != "open":
            continue
        if free_part(p) and try_match(p) == "matched":
            started.append(p.pk)
    return started


def busy(person, date, part, exclude_plan=None):
    """True when the person already holds a sent offer, or a yes that waits for an owner, for
    that date and part. One person gets one question at a time for one meal."""
    q = Offer.objects.filter(person=person, status__in=["pending", "owner_wait"],
                             plan__date=date, plan__part=part)
    if exclude_plan is not None:
        q = q.exclude(plan=exclude_plan)
    return q.exists()


def committed(person, date, part, exclude_plan=None):
    """True when the person's yes already counts in another plan for that date and part."""
    q = Offer.objects.filter(person=person, status="accepted", plan__date=date, plan__part=part,
                             plan__status__in=["asking", "confirmed", "final"])
    if exclude_plan is not None:
        q = q.exclude(plan=exclude_plan)
    return q.exists()


def set_part(plan, part, kind):
    """Fix the part of the day of a plan that named none (T79). A new kind gets new places."""
    plan.any_part = False
    plan.part = part
    if kind != plan.kind:
        plan.kind = kind
        plan.save()
        rows, _ = matching.place_options(plan, exclude_tags=plan.owner.dislikes or ())
        plan.options.set(rows)
    else:
        plan.save()


def match_new_availability(plan, seed=None):
    """Called when an availability is posted. Friends' plans that were open first get the
    match, so two plans never ask each other. ONE older plan gets the new person: the nearest
    place, then the oldest plan. An older plan that is asking already puts the new person at the
    end of its queue, so a decline there asks the new person next.
    Returns 'joined' (an older open plan now asks), 'queued' (an asking plan queued the person),
    or what try_match(plan) returns."""
    from .models import Friendship
    me = plan.owner
    if plan.kind == "group_dinner":  # a group dinner asks its own friends; it never joins a 1:1 plan (T227)
        return try_match(plan, seed)
    older = Plan.objects.filter(owner__in=Friendship.friends_of(me.pk), status__in=["open", "asking"],
                                date=plan.date)
    if not plan.any_part:  # a friend's plan with no part named fits this part too (T79)
        older = older.filter(Q(part=plan.part, kind__in=matching.same_kinds(plan.kind)) | Q(any_part=True, status="open"))
    older = older.exclude(pk=plan.pk).select_related("area", "owner").order_by("created", "pk")
    fits = []
    for p in older:
        if p.offers.filter(person=me).exists():
            continue  # already in that queue
        probe = p
        if p.any_part and not plan.any_part:  # test the friend's plan at the part this post names
            probe = copy.copy(p)
            probe.part, probe.kind = plan.part, plan.kind
        if not matching.open_plan_for(me, probe):
            continue
        if p.status == "open" and not fresh_candidates(probe):
            continue
        # A friend who named the part comes before one who did not; then nearest, then oldest.
        fits.append((p.any_part, round(matching.km(p.area, plan.area), 3), p.created, p.pk, p))
    fits.sort(key=lambda r: r[:4])
    p = fits[0][4] if fits else None
    # The match takes the part the friend named; two plans with no part named meet on the older
    # plan's default part.
    part, kind = (p.part, p.kind) if p and (plan.any_part or not p.any_part) else (plan.part, plan.kind)
    if p and not busy(me, plan.date, part):
        before = (plan.part, plan.kind, plan.any_part, p.part, p.kind, p.any_part)
        if plan.any_part:
            set_part(plan, part, kind)
        if p.any_part:
            set_part(p, part, kind)
        if p.status == "open":
            if try_match(p, seed) == "matched":
                return "joined"
            # No match after all: both plans keep the part they had.
            for q, (pt, kd, ap) in ((plan, before[:3]), (p, before[3:])):
                if (q.part, q.kind, q.any_part) != (pt, kd, ap):
                    set_part(q, pt, kd)
                    q.any_part = ap
                    q.save(update_fields=["any_part"])
        else:
            last = p.offers.order_by("-order").first()
            Offer.objects.create(plan=p, person=me, order=(last.order + 1) if last else 0)
            log(p, "mifgash:directory", p.owner.address, "queued",
                candidates_added=1, note="a friend posted a fitting open time while this plan was asking")
            advance(p)
            return "queued"
    return try_match(plan, seed)


FILL_BY_HOUR = 15  # a group dinner stops asking at 15:00 on the day, so the group knows in time (T227)


def default_fill_by(date, now=None):
    """The deadline of a group dinner: 15:00 on the day, and at least one hour from now."""
    now = now or timezone.now()
    at = timezone.make_aware(dt.datetime.combine(date, dt.time(FILL_BY_HOUR)))
    return max(at, now + dt.timedelta(hours=1))


def deadline_passed(plan, now):
    return plan.fill_by is not None and plan.fill_by <= now


@transaction.atomic
def confirm_smaller(plan, now=None):
    """The owner confirms a group dinner before it is full (T227): at least one friend said yes.
    Open offers end quietly: a sent offer expires, a queued friend was never asked. Raises
    ValueError when there is nothing to confirm."""
    plan.refresh_from_db()
    if plan.status != "asking":
        raise ValueError("this plan is not asking friends now")
    if plan.offers.filter(status="owner_wait").exists():
        raise ValueError("a friend said yes and waits for your word first")
    n = len(accepted(plan))
    if n < 1:
        raise ValueError("no friend said yes yet")
    expire_open(plan, now or timezone.now())
    log(plan, plan.owner.address, "mifgash:directory", "owner_confirm", guests=n,
        group_size=plan.group_size, note="the owner confirmed a smaller group")
    confirm(plan)


def expire_open(plan, now):
    """A sent offer that nobody needs any more expires (private), so the friend's agent stops
    waiting. The friend never learns why."""
    for o in plan.offers.filter(status="pending"):
        o.status = "expired"
        o.answered_at = now
        o.save(update_fields=["status", "answered_at"])
        log(plan, "mifgash:clock", plan.owner.address, "expired", offer_id=o.pk)


def accepted(plan):
    return list(plan.offers.filter(status="accepted").select_related("person"))


def api_agent(person):
    """True when a real agent talks to us with a live key. Such an agent answers through the API,
    so the engine never answers for it, and as an owner it approves every match itself."""
    return person.has_agent and person.agent_keys.filter(revoked_at__isnull=True).exists()


def owner_approves(person):
    """The owner gives the word on a friend's yes: a real agent through the API, or a person with
    no agent on the dashboard (M6c, T177). Only a demo friend the engine plays skips the step."""
    # A quick-demo visitor (M7b, T179) approves with a real click too.
    return api_agent(person) or not person.has_agent or person.is_sandbox


def advance(plan, now=None, max_steps=50):
    """Step until the plan waits for somebody (a friend, the owner) or ends."""
    for _ in range(max_steps):
        r = step(plan, now)
        if r not in ("sent", "answered", "expired"):
            return r
    return "max_steps"


def tick(now=None):
    """The clock. Expire offers that are due, move every asking plan on, then start the open
    plans that can match now (rematch_open). Run by
    `manage.py tick` from a timer every minute. Returns {plan id: result} for the plans that
    moved (a new log row); a plan that still waits for the same person is left out."""
    now = now or timezone.now()
    moved = {}
    for p in Plan.objects.filter(status="asking").order_by("pk"):
        before = p.log.count()
        r = advance(p, now)
        if p.log.count() != before:
            moved[p.pk] = r
    for pk in rematch_open(now=now):
        moved[pk] = "matched"
    fallback.sweep(now)  # T98: email the human when the agent heard nothing for 24 h
    return moved


def step(plan, now=None):
    """Advance the plan by one action. Returns a short word for the caller."""
    now = now or timezone.now()
    plan.refresh_from_db()
    if plan.status != "asking":
        return "done"
    if len(accepted(plan)) >= plan.group_size:
        confirm(plan)
        return "confirmed"
    if plan.offers.filter(status="owner_wait").exists():
        return "waiting"  # a friend said yes; the owner's word comes next
    if deadline_passed(plan, now):  # a group dinner asks nobody new after its deadline (T227)
        expire_open(plan, now)
        if len(accepted(plan)) >= plan.min_guests:
            log(plan, "mifgash:clock", plan.owner.address, "fill_by", guests=len(accepted(plan)),
                group_size=plan.group_size, note="deadline: the group goes with the yeses it has")
            confirm(plan)
            return "confirmed"
        finish_no_match(plan)
        return "no_match"

    pending = plan.offers.filter(status="pending").select_related("person").first()
    if pending:
        if pending.person.has_agent and not api_agent(pending.person):
            simulate_friend_agent(pending, now)
            return "answered"
        if pending.expires_at and pending.expires_at <= now:
            pending.status = "expired"
            pending.answered_at = now
            pending.save()
            log(plan, "mifgash:clock", plan.owner.address, "expired", offer_id=pending.pk)
            return "expired"
        return "waiting"

    queued = list(plan.offers.filter(status="queued").select_related("person"))
    for nxt in queued:
        if committed(nxt.person, plan.date, plan.part, plan):
            nxt.status = "not_sent"  # the friend is already going with somebody else; never asked
            nxt.save(update_fields=["status"])
            continue
        if busy(nxt.person, plan.date, plan.part, plan):
            continue
        send_offer(nxt, now)
        return "sent"
    if plan.offers.filter(status="queued").exists():
        return "waiting"  # every friend left in the queue is asked by another plan now
    if plan.fill_by is not None and accepted(plan):
        # A group dinner keeps its yeses until the deadline (T227): a friend who posts a fitting
        # time later joins the queue (match_new_availability), and so does a friend whose weekly
        # slot fits now.
        fresh = fresh_candidates(plan)
        last = plan.offers.order_by("-order").first()
        for i, p in enumerate(matching.random_order(fresh, plan.seed)):
            Offer.objects.create(plan=plan, person=p, order=(last.order if last else 0) + 1 + i)
        if fresh:
            log(plan, "mifgash:directory", plan.owner.address, "queued", candidates_added=len(fresh),
                note="the group dinner waits for more friends until its deadline")
            return "sent"  # advance() steps again and sends the first new offer
        return "waiting"

    if len(accepted(plan)) >= plan.min_guests:
        confirm(plan)
        return "confirmed"
    if keeps_open(plan, now):
        reopen(plan)
        return "reopened"
    finish_no_match(plan)
    return "no_match"


def send_offer(offer, now):
    """Send one queued offer. Returns False when another thread sent it first: the tick and a
    dashboard click can step the same plan at once, and the reason is a slow model call. Without
    the check the second send wrote 'pending' over the friend's yes (live 2/11, T229)."""
    plan = offer.plan
    ttl = dt.timedelta(minutes=settings.OFFER_TTL_MINUTES)
    start_at = timezone.make_aware(dt.datetime.combine(plan.date, dt.time(12)))
    reason_cause = ""
    if not offer.reason:  # one model call per offer (T78), outside the lock
        offer.reason, offer.reason_backend, reason_cause = llm.match_reason_detail(
            plan, offer.person, (plan.option_list() or [None])[0])
    with transaction.atomic():
        if not Offer.objects.select_for_update().filter(pk=offer.pk, status="queued").exists():
            return False
        offer.status = "pending"
        offer.sent_at = now
        offer.expires_at = min(now + ttl, start_at - dt.timedelta(hours=2)) if start_at > now + dt.timedelta(hours=3) else now + ttl
        offer.save()
    _sent(offer, plan, reason_cause)  # after the commit: a webhook push must not hold the lock
    return True


def _sent(offer, plan, reason_cause):
    options = plan.option_list()
    log(plan, plan.owner.address, offer.person.address, "offer",
        offer_id=offer.pk, intent=intent_payload(plan),
        options=[option_payload(a) for a in options],
        expires_at=offer.expires_at.isoformat(),
        visibility={"others_asked": False, "order_shown": False},
        text=messages.offer_text(plan.owner, plan, options),
        reason=offer.reason, reason_backend=offer.reason_backend or None,
        **({"reason_fallback": reason_cause} if reason_cause else {}),
        link=None if offer.person.has_agent else f"/h/{offer.token}/")
    if api_agent(offer.person):
        notify(offer.person, "proposal.new", plan, offer, "candidate")
    elif not offer.person.has_agent:
        deliver_human_link(offer, options)


def human_link(offer):
    return f"{settings.PUBLIC_URL.rstrip('/')}/h/{offer.token}/"


def deliver_human_link(offer, options):
    """A friend with no agent gets the offer as a link on the friend's OWN channel (email or
    Telegram; a stub row for now). The row goes to the friend only, so the owner never sees it."""
    p = offer.person
    channel = "email" if p.email else "telegram" if p.telegram else "link"
    text = f"Your friend {messages.first_name(offer.plan.owner)} asks: {messages.human_invite_text(offer.plan, options)} Open {human_link(offer)}"
    log(offer.plan, "mifgash:directory", p.address, "invite_link", offer_id=offer.pk, channel=channel,
        delivered=False, note="stub: no real email or Telegram send yet", text=text)


def candidate_answer(offer, yes, choice=None, note="", backend="", via=""):
    """A candidate's answer to an offer, from the API or from the human page. One path for both,
    so the owner's approval step applies the same way. Returns what advance() returns."""
    plan = offer.plan
    if yes:
        record_answer(offer, True, choice=choice or (plan.option_list() or [None])[0], backend=backend, via=via,
                      note=note)
    else:
        record_answer(offer, False, private_reason=note or "declined", backend=backend, via=via)
    r = advance(plan)
    if not yes:
        rematch_open(plan.date, plan.part)  # the friend is free again; other open plans may fit now
    return r


def simulate_friend_agent(offer, now):
    """A friend's agent answers by its owner's rules. A real deployment asks the
    friend with one tap when the rules do not cover the case."""
    plan = offer.plan
    decision, detail = matching.friend_decision(offer.person, plan, plan.option_list())
    if decision == "accept":
        record_answer(offer, True, choice=detail, now=now)
    else:
        record_answer(offer, False, private_reason=detail, now=now)


def clean_note(note):
    """T323: a friend's own words on a yes, one line, 200 characters at most. Stored as friend_text
    (untrusted, docs/SECURITY.md rule 3) and shown to the other side as the friend's words."""
    return " ".join(str(note or "").split())[:200]


def answer_note(offer):
    """The words the friend sent with the yes on this offer, or ''."""
    row = AgentMessage.objects.filter(plan_id=offer.plan_id, type="accept", payload__offer_id=offer.pk).last()
    return (row.payload.get("friend_text") or "") if row else ""


def record_answer(offer, yes, choice=None, private_reason="", now=None, backend="", via="", note=""):
    """The candidate's answer. When the owner has a real agent, a yes waits for the owner's word
    (status owner_wait, see owner_answer); a person with no agent approves on the dashboard (T177);
    else it counts at once. via='dashboard' marks a click
    by the person, so the log credits the human, not the agent (T96)."""
    now = now or timezone.now()
    plan = offer.plan
    two_step = yes and owner_approves(plan.owner)
    offer.status = ("owner_wait" if two_step else "accepted") if yes else "declined"
    offer.answered_at = now
    offer.choice = choice
    offer.save()
    words = clean_note(note) if yes else ""
    said = {"friend_text": words} if words else {}
    if yes:
        log(plan, offer.person.address, plan.owner.address, "accept",
            offer_id=offer.pk, choice=option_payload(choice) if choice else None, **said,
            **({"backend": backend} if backend else {}), **({"via": via} if via else {}))
        join_own_plan(offer)
        if two_step:
            log(plan, "mifgash:directory", plan.owner.address, "ask_owner",
                offer_id=offer.pk, friend={"handle": offer.person.handle, "name": offer.person.name},
                choice=option_payload(choice) if choice else None, **said,
                text=messages.owner_ask_text(offer.person, plan, choice))
            notify(plan.owner, "proposal.owner", plan, offer, "owner")
    else:
        # The reason stays with the friend's agent. The owner's agent gets a bare "decline".
        log(plan, offer.person.address, plan.owner.address, "decline",
            offer_id=offer.pk, reason_shared=False, private_reason_kept_local=private_reason or "-",
            **({"backend": backend} if backend else {}), **({"via": via} if via else {}))


def join_own_plan(offer):
    """A candidate who says yes inside a friend's plan does not need an own open plan for the
    same date and part any more. It becomes 'joined' (reopened if the owner says no)."""
    plan = offer.plan
    for own in Plan.objects.filter(Q(part=plan.part) | Q(any_part=True), owner=offer.person,
                                   status="open", date=plan.date):
        if own.any_part:  # 'open tomorrow' joins at the friend's part (T79)
            set_part(own, plan.part, plan.kind)
        own.status = "joined"
        own.save(update_fields=["status"])
        log(own, "mifgash:directory", offer.person.address, "joined",
            offer_id=offer.pk, text=messages.joined_text(plan))


@transaction.atomic
def owner_answer(offer, yes, choice=None, note="", now=None, via=""):
    """The owner's word on a friend's yes. Yes: the friend counts, and the plan confirms when it
    is full. No: the friend hears the neutral 'did not come together' line, the friend's own plan
    opens again, and the next friend in the random order is asked. Nobody learns who said no."""
    now = now or timezone.now()
    plan = offer.plan
    if offer.status != "owner_wait":
        raise ValueError("this proposal does not wait for the owner")
    if yes:
        offer.status = "accepted"
        if choice:
            offer.choice = choice
        offer.save()
        log(plan, plan.owner.address, "mifgash:directory", "owner_approve", offer_id=offer.pk,
            friend={"handle": offer.person.handle, "name": offer.person.name},
            choice=option_payload(offer.choice) if offer.choice else None, note=note[:200],
            **({"via": via} if via else {}))
        return
    offer.status = "closed"
    offer.save()
    log(plan, plan.owner.address, "mifgash:directory", "owner_pass", offer_id=offer.pk,
        reason_shared=False, private_note_kept_local=note[:200] or "-", **({"via": via} if via else {}))
    log(plan, "mifgash:directory", offer.person.address, "close",
        outcome="did_not_come_together", text=messages.group_closed_text(plan))
    notify(offer.person, "outing.closed", plan, outcome="did_not_come_together",
           text=messages.group_closed_text(plan))
    for own in Plan.objects.filter(owner=offer.person, status="joined", log__type="joined",
                                   log__payload__offer_id=offer.pk).distinct():
        own.status = "open"
        own.save(update_fields=["status"])
        log(own, "mifgash:directory", offer.person.address, "reopened", text=messages.reopened_text(own))


@transaction.atomic
def confirm(plan):
    guests = accepted(plan)
    first = guests[0] if guests else None
    plan.chosen = (first.choice if first and first.choice else None) or (plan.option_list() or [None])[0]
    if plan.kind == "group_dinner" and guests:
        # G2 (T228): one place for all. A dinner place with big tables, nearest the centre of
        # every member's area, not the owner's area alone. The finalize step may pick another.
        centre, rows = matching.group_places(plan, [plan.owner] + [o.person for o in guests])
        if rows:
            plan.options.set(rows)
            plan.chosen = rows[0]
            log(plan, "mifgash:directory", plan.owner.address, "group_place", place_id=rows[0].pk,
                centre={"lat": round(centre.lat, 4), "lon": round(centre.lon, 4)},
                options=[a.name for a in rows], note="the dinner place nearest the centre of the group")
    plan.status = "confirmed"
    plan.save()
    # Friends still in the queue were never asked. They hear nothing.
    plan.offers.filter(status__in=["queued", "pending"]).update(status="not_sent")
    people = [o.person for o in guests]
    # One row and one push per side. Each names the OTHER people, so nobody reads their own name.
    pushes = []
    for p in [plan.owner] + people:
        text = messages.friend_confirmed_text(plan, viewer=p, guests=people)
        log(plan, "mifgash:directory", p.address, "confirm",
            when={"date": plan.date.isoformat(), "part": plan.part},
            where=option_payload(plan.chosen) if plan.chosen else None,
            who=[x.name for x in [plan.owner] + people if x != p], text=text)
        pushes.append((p, text))
    ChatTurn.objects.create(owner=plan.owner, role="agent", plan=plan,
                            text=messages.confirmed_text(plan, people))
    # T258 (F6c): Mifgash sets the time itself and the outing is final at once (outing.final to
    # every side, with each side's calendar links). Only a plan with no place left keeps the
    # old 'pick the time' step, so it still gets outing.confirmed.
    from . import finalize
    if settings.AUTO_TIME and finalize.auto_final(plan):
        return
    for p, text in pushes:
        if api_agent(p):
            notify(p, "outing.confirmed", plan, text=text)


def keeps_open(plan, now=None):
    """An open time an agent posted stays open when its queue runs out (brief item d: no match
    'for now'). A past date, or a plan from the old site chat, ends in no_match."""
    today = timezone.localdate(now or timezone.now())
    return plan.date >= today and api_agent(plan.owner)


@transaction.atomic
def reopen(plan):
    """The queue ran out before enough yeses. The plan goes back to open. The old offers stay,
    so fresh_candidates never asks the same friend twice; a friend's later post can still match.
    The owner gets the gentle waiting line, with no names and no count."""
    for o in plan.offers.filter(status="accepted").select_related("person"):
        o.status = "closed"
        o.save()
        log(plan, plan.owner.address, o.person.address, "close",
            outcome="did_not_come_together", text=messages.group_closed_text(plan))
        if api_agent(o.person):
            notify(o.person, "outing.closed", plan, outcome="did_not_come_together",
                   text=messages.group_closed_text(plan))
    plan.offers.filter(status__in=["queued", "pending"]).update(status="not_sent")
    plan.status = "open"
    plan.save(update_fields=["status"])
    text = messages.still_open_text(plan)
    log(plan, "mifgash:directory", plan.owner.address, "waiting", intent=intent_payload(plan), text=text)
    notify(plan.owner, "availability.open", plan, text=text)


@transaction.atomic
def finish_no_match(plan):
    plan.status = "no_match"
    plan.save()
    for o in plan.offers.filter(status="accepted").select_related("person"):
        o.status = "closed"
        o.save()
        log(plan, plan.owner.address, o.person.address, "close",
            outcome="did_not_come_together", text=messages.group_closed_text(plan))
        if api_agent(o.person):
            notify(o.person, "outing.closed", plan, outcome="did_not_come_together",
                   text=messages.group_closed_text(plan))
    plan.offers.filter(status__in=["queued", "pending"]).update(status="not_sent")
    alts = matching.other_options(plan)
    buttons = [{"label": f"{messages.when(d, part)}: {messages.KIND_WORDS[kind]}",
                "action": f"alt:{d.isoformat()}:{part}:{kind}"} for d, part, kind, _n in alts]
    buttons.append({"label": "Post it as an open slot", "action": f"openslot:{plan.pk}"})
    ChatTurn.objects.create(owner=plan.owner, role="agent", plan=plan,
                            text=messages.no_match_text(plan), buttons=buttons)
    log(plan, plan.owner.address, plan.owner.address, "no_match", alternatives=len(alts))


def run_to_end(plan, now=None, max_steps=200):
    """For tests and for the 'skip animation' button. Stops at a human who must answer."""
    for _ in range(max_steps):
        r = step(plan, now)
        if r in ("done", "confirmed", "no_match", "waiting", "reopened"):
            return r
    return "max_steps"
