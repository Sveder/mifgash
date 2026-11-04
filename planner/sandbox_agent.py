"""M7b (T179): the quick-demo friend answers live. Maria (the sandbox friend from sandbox.py) has her
own agent key, so the engine never answers for her. This module plays her agent on the server, with
the same decision code as demo/friend_agent.py (planner/friend_brain.py) and the model of
settings.LLM_BACKEND (meta = Muse Spark Open on the public host; a model error falls back to the stub).

What she does, one pass of run():
  1. a pending offer to her: decide (accept or decline, pick the place) and answer it;
  2. a confirmed outing with her and no time yet: propose the usual time of the part (13:00 for lunch);
  3. a time the visitor proposed: confirm it, or counter ONE time with her preferred time.

The tick runs run() every minute. A sandbox post, a dashboard answer and a dashboard time also call
kick(): at once in this thread when PUSH_SYNC or SANDBOX_SYNC is on (tests), else in a background thread.
Only sandbox people with a live agent key are played. A real person is never touched.
"""
import logging
import threading

from django.conf import settings
from django.db import connection, transaction

from . import engine, finalize, friend_brain, llm
from .models import AgentMessage, Offer, Person, Plan

log = logging.getLogger(__name__)

# The usual start time of each part; Maria proposes it on a confirmed outing.
PART_TIMES = {"morning": "10:00", "lunch": "13:00", "afternoon": "16:00", "evening": "19:00"}


PERSONAS = {  # G3 (T229): each demo friend has an own taste; the model decides from it
    "Maria": "{name} works in {area} and likes a calm lunch near work, and a dinner with friends.",
    "Sam": "{name} lives near {area}, cooks a lot, and never says no to a group dinner with friends.",
    "Lena": "{name} works late in {area} and likes a relaxed dinner with a few friends after work.",
}


def prefs(person):
    """The demo friend's persona. Maria's lunch time is 13:00, so a visitor's 12:30 gets one counter."""
    area = person.work_area.name if person.work_area else "Hayes Valley"
    persona = PERSONAS.get(person.name, PERSONAS["Maria"]).format(name=person.name, area=area)
    return {"handle": person.handle, "persona": persona,
            "likes": list(person.likes or ["lunch"]), "dislikes": ["loud"], "areas": [area],
            "preferred_times": {"lunch": "13:00", "evening": "19:00"}}


def backend():
    b = settings.LLM_BACKEND
    if b == "meta":  # the same Baseten account and model as planner/llm.py
        friend_brain.META = {"key": settings.META_API_KEY, "model": settings.META_MODEL,
                             "base_url": settings.META_BASE_URL, "timeout": settings.LLM_TIMEOUT_S,
                             "max_tokens": settings.META_MAX_TOKENS}
    return b if b in ("stub", "claude", "meta") else "stub"


def tag(used):
    """The model name for the log row, only for a real model answer."""
    return used if used in llm.MODEL_LABELS else ""


def played():
    """The sandbox people whose agent this module plays: sandbox, with a live agent key."""
    # agent_keys__isnull=False: without it the join also matches a person with no key at all
    return Person.objects.filter(is_sandbox=True, has_agent=True, agent_keys__isnull=False,
                                 agent_keys__revoked_at__isnull=True).distinct()


def answer_offers():
    from .api import proposal_json
    done = 0
    rows = Offer.objects.filter(status="pending", plan__status="asking", person__in=played()).select_related(
        "person", "plan__owner", "plan__area")
    for offer in list(rows):
        proposal = proposal_json(offer, "candidate")
        d, used = friend_brain.decide(backend(), prefs(offer.person), proposal)  # outside the lock: a model call is slow
        with transaction.atomic():
            fresh = Offer.objects.select_for_update().filter(pk=offer.pk, status="pending",
                                                             plan__status="asking").first()
            if not fresh:
                continue  # answered or expired while the model thought
            yes = d["answer"] == "accept"
            choice = next((a for a in fresh.plan.option_list() if a.pk == d.get("choice_id")), None)
            engine.candidate_answer(fresh, yes, choice=choice, note=d.get("note") or "", backend=tag(used))
        done += 1
    return done


def countered(plan, person):
    """True when this person proposed a time on the plan before (so a second proposal is not new)."""
    return AgentMessage.objects.filter(plan=plan, sender=person.address, type="finalize_set").exists()


def outing_dict(plan):
    place = plan.proposed_activity or plan.chosen
    return {"plan_id": plan.pk, "status": "proposed", "kind": plan.kind, "date": plan.date.isoformat(),
            "part": plan.part, "proposed_time": plan.proposed_time.strftime("%H:%M"),
            "proposed_by": plan.proposed_by.name if plan.proposed_by else None,
            "proposed_place": {"id": place.pk, "name": place.name} if place else None}


def handle_outings():
    done = 0
    mine = played()
    plans = Plan.objects.filter(status="confirmed", offers__status="accepted",
                                offers__person__in=mine).distinct().select_related("proposed_by", "chosen")
    for plan in list(plans):
        friends = [p for p in finalize.sides(plan) if p.is_sandbox and mine.filter(pk=p.pk).exists()]
        if plan.kind == "group_dinner":
            done += group_outing(plan, friends)
            continue
        friend = friends[0] if friends else None
        if not friend or plan.proposed_by_id == friend.pk:
            continue  # her own proposal waits for the visitor
        if not plan.proposed_time:
            time, place, used = PART_TIMES.get(plan.part, "13:00"), plan.chosen_id, ""
        else:
            place = plan.proposed_activity_id or plan.chosen_id
            if countered(plan, friend):
                time, used = plan.proposed_time.strftime("%H:%M"), ""  # she counters once, then agrees
            else:
                d, used = friend_brain.decide_time(backend(), prefs(friend), outing_dict(plan))
                time = d["time"]
        if move(plan, friend, time, place, used):
            done += 1
    return done


def move(plan, friend, time, place, used=""):
    """Propose or agree the time for one demo friend. False when the plan moved meanwhile."""
    stamp = (plan.status, plan.proposed_time, plan.proposed_by_id, list(plan.agreed or []))
    with transaction.atomic():
        fresh = Plan.objects.select_for_update().get(pk=plan.pk)
        if (fresh.status, fresh.proposed_time, fresh.proposed_by_id, list(fresh.agreed or [])) != stamp:
            return False  # the visitor moved while the model thought; the next pass sees it
        try:
            finalize.finalize(fresh, friend, time, place, backend=tag(used))
        except finalize.FinalizeError as e:
            log.warning("sandbox friend finalize %s: %s", plan.pk, e.message)
            return False
    return True


def group_outing(plan, friends):
    """G3 (T229): a group dinner in the quick demo. The first demo friend proposes the usual dinner
    time when nobody did; then every demo friend agrees to the time on the table, so the visitor's
    one click (Agree, or a new time) makes the plan final. No counters: with three agents a counter
    would start the yeses again for everybody."""
    done = 0
    for friend in friends:
        plan.refresh_from_db()
        if plan.status != "confirmed":
            break
        if not plan.proposed_time:
            time, place = PART_TIMES.get(plan.part, "19:00"), plan.chosen_id
        elif friend.pk in set(plan.agreed or [plan.proposed_by_id]):
            continue
        else:
            time, place = plan.proposed_time.strftime("%H:%M"), plan.proposed_activity_id or plan.chosen_id
        if move(plan, friend, time, place):
            done += 1
    return done


MAX_PASSES = 6  # one pass per friend in a group of up to 6


def run():
    """One pass. Returns the number of answers and time moves. Never raises: the tick goes on."""
    total = 0
    for part in (answer_offers, handle_outings):
        # G3 (T229): a decline sends the next offer at once, so answer again until nothing new
        # waits; a group dinner does not wait a whole tick per friend.
        for _ in range(MAX_PASSES):
            try:
                n = part()
            except Exception:  # the demo must not break the tick or the visitor's click
                log.exception("sandbox friend %s failed", part.__name__)
                break
            total += n
            if not n:
                break
    return total


def _thread():
    try:
        run()
    finally:
        connection.close()  # a thread opens its own database connection


def kick(person):
    """Let the sandbox friend move now, after a sandbox person did something. Real people: nothing."""
    if not person.is_sandbox:
        return
    if settings.PUSH_SYNC or settings.SANDBOX_SYNC:
        run()
    else:
        transaction.on_commit(lambda: threading.Thread(target=_thread, daemon=True).start())
