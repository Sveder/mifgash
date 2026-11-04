"""Finalize an outing: the exact time and place (brief item g). New hackathon work (29/10/2026).

One side of a confirmed plan proposes a time and place. When every other side sends the same time
and place, the plan is final (two sides: one yes; a group dinner: every member, G2). A different
time or place replaces the proposal and the yeses start again.
"""
import datetime as dt
import re

from django.conf import settings
from django.db import transaction

from . import calendar, messages

TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")

# T258 (F6c): the time Mifgash sets by itself when both sides are in. A time in the free text wins.
DEFAULT_TIMES = {"morning": "10:00", "lunch": "12:30", "afternoon": "15:30", "evening": "19:30"}
HOUR_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
              "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "noon": 12}
# '13:00', '1pm', '1:30 pm', 'at 1', 'at one', 'at noon'
CLOCK_RE = re.compile(r"\b([01]?\d|2[0-3])[:]([0-5]\d)\s*(am|pm)?\b")
AMPM_RE = re.compile(r"\b(1[0-2]|0?[1-9])\s*(am|pm)\b")
AT_RE = re.compile(r"\bat\s+(1[0-2]|0?[1-9]|" + "|".join(HOUR_WORDS) + r")\b(?!\s*(?:people|friends|km|min))")


def _hm(h, m=0, ampm=None, part=None):
    """24-hour 'HH:MM'. A bare hour with no am/pm reads as p.m. when the part says so:
    'lunch at 1' -> 13:00, 'drinks at 8' -> 20:00, 'coffee at 9' -> 09:00."""
    if ampm == "pm" and h < 12:
        h += 12
    elif ampm == "am" and h == 12:
        h = 0
    elif ampm is None and 1 <= h < 12:
        if (part == "lunch" and h <= 5) or (part in ("afternoon", "evening") and h <= 11):
            h += 12
    return f"{h:02d}:{m:02d}" if 0 <= h <= 23 else None


def read_time(text, part=None):
    """'HH:MM' for a clock time in the free text, or None. 'lunch at 1pm' -> '13:00'."""
    t = (text or "").lower()
    m = CLOCK_RE.search(t)
    if m:
        return _hm(int(m.group(1)), int(m.group(2)), m.group(3), part)
    m = AMPM_RE.search(t)
    if m:
        return _hm(int(m.group(1)), 0, m.group(2))
    m = AT_RE.search(t)
    if m:
        w = m.group(1)
        return _hm(HOUR_WORDS.get(w) or int(w), 0, None, part)
    return None


def default_time(plan):
    """The time of the plan's own text when it named one, else the part default."""
    raw = (plan.wants or {}).get("time") or DEFAULT_TIMES.get(plan.part, "12:30")
    return parse_time(raw)


class FinalizeError(Exception):
    def __init__(self, status, message, **extra):
        super().__init__(message)
        self.status, self.message, self.extra = status, message, extra


def parse_time(raw):
    m = TIME_RE.match(str(raw or "").strip())
    if not m:
        raise FinalizeError(400, "time must be HH:MM, for example 13:00")
    return dt.time(int(m.group(1)), int(m.group(2)))


def sides(plan):
    """The people on the outing: the owner and the friends who said yes."""
    return [plan.owner] + plan.guests()


def places(plan):
    """The places a side may pick: the plan options, and the chosen place."""
    rows = plan.option_list()
    if plan.chosen and plan.chosen.pk not in {a.pk for a in rows}:
        rows.insert(0, plan.chosen)
    return rows


def reply(plan, status, time, place, waiting_for):
    return {"plan_id": plan.pk, "status": status, "time": time.strftime("%H:%M"),
            "date": plan.date.isoformat(),
            "place": {"id": place.pk, "name": place.name, "address": place.address, "area": place.area.name},
            "address": place.address, "waiting_for": messages.names(waiting_for) if waiting_for else None}


def demo_agent(person):
    """A seeded demo friend whose agent the engine plays (MIFGASH_DEMO=1 only). It answers an
    offer in the same call, so it also agrees to a proposed time in the same call (T101)."""
    from .engine import api_agent
    from .seed import demo_friends
    return (settings.DEMO and person.has_agent and not api_agent(person)
            and demo_friends().filter(pk=person.pk).exists())


@transaction.atomic
def finalize(plan, person, raw_time, activity_id=None, backend=""):
    """Propose or confirm the exact time and place. Returns the reply dict.
    backend: the model that chose the time on the agent's side ('claude' or 'meta'); the log row
    shows it (T60, T70).
    Raises FinalizeError (403 not on the plan, 409 wrong status, 400 bad input)."""
    from .engine import api_agent, log, notify
    from .models import Plan
    plan = Plan.objects.select_for_update().get(pk=plan.pk)
    people = sides(plan)
    if person.pk not in {p.pk for p in people}:
        raise FinalizeError(403, "only the people on this outing can finalize it")
    if plan.status == "final":
        # The same time and place again is a safe retry: answer the final outing (T50).
        same_place = activity_id is None or str(activity_id) == str(plan.chosen_id)
        try:
            same_time = parse_time(raw_time) == plan.exact_time
        except FinalizeError:
            same_time = False
        if same_time and same_place and plan.chosen:
            return reply(plan, "final", plan.exact_time, plan.chosen, [])
        # T258 (F6c): Mifgash set the time by itself; any side may change it. The plan stays final.
        return change(plan, person, raw_time, activity_id, backend)
    if plan.status != "confirmed":
        raise FinalizeError(409, "only a confirmed outing can be finalized", plan_status=plan.status)
    time = parse_time(raw_time)
    options = places(plan)
    if activity_id is None:
        place = plan.chosen or (options[0] if options else None)
    else:
        place = next((a for a in options if str(a.pk) == str(activity_id)), None)
    if not place:
        raise FinalizeError(400, "activity_id must be one of the places",
                            places=[{"id": a.pk, "name": a.name} for a in options])
    others = [p for p in people if p.pk != person.pk]
    same = (plan.proposed_by_id is not None and plan.proposed_time == time
            and plan.proposed_activity_id == place.pk)
    tag = {"backend": backend} if backend else {}
    if not same:
        # A different time from the other side of a proposal is a counter (T70).
        counter_to = (plan.proposed_time if plan.proposed_by_id and plan.proposed_by_id != person.pk
                      and plan.proposed_time != time else None)
        plan.proposed_time, plan.proposed_activity, plan.proposed_by = time, place, person
        plan.agreed = [person.pk]  # a new time or place: every other side agrees again (G2, T228)
        plan.save(update_fields=["proposed_time", "proposed_activity", "proposed_by", "agreed"])
        log(plan, person.address, "mifgash:directory", "finalize_set", time=time.strftime("%H:%M"),
            place_id=place.pk, text=messages.finalize_set_text(time, place, others), **tag)
        if counter_to:
            ask = messages.finalize_counter_text(person, time, counter_to, place)
        else:
            ask = messages.finalize_ask_text(person, time, place)
        for p in others:
            log(plan, "mifgash:directory", p.address, "finalize_counter" if counter_to else "finalize_ask",
                time=time.strftime("%H:%M"), place_id=place.pk, text=ask, **tag)
            if api_agent(p):
                notify(p, "outing.proposed", plan, **reply(plan, "proposed", time, place, [p]), text=ask)
    elif person.pk not in (plan.agreed or [plan.proposed_by_id]):
        # The same time and place from another side is a yes. A group dinner waits for every
        # side (G2, T228); a plan of two is final at this first yes. A plan proposed before
        # migration 0028 has no list yet: the proposer counts.
        plan.agreed = list(plan.agreed or [plan.proposed_by_id]) + [person.pk]
        log(plan, person.address, "mifgash:directory", "finalize_agree", time=time.strftime("%H:%M"),
            place_id=place.pk, text=f"agrees {time.strftime('%H:%M')} at {place.name}", **tag)
    # The demo friends' agents agree at once, so the plan can be final in this call (T101).
    for sim in [p for p in others if demo_agent(p) and p.pk not in plan.agreed]:
        plan.agreed = list(plan.agreed) + [sim.pk]
        log(plan, sim.address, person.address, "finalize_agree", time=time.strftime("%H:%M"),
            place_id=place.pk, text=f"agrees {time.strftime('%H:%M')} at {place.name}")
    plan.agreed = list(plan.agreed or [plan.proposed_by_id])
    plan.save(update_fields=["agreed"])
    waiting = [p for p in people if p.pk not in plan.agreed]
    if waiting:
        return reply(plan, "proposed", time, place, waiting)
    plan.exact_time, plan.chosen, plan.status = time, place, "final"
    plan.save(update_fields=["exact_time", "chosen", "status"])
    final_push(plan, people, lambda p: messages.final_text(plan, [x for x in people if x.pk != p.pk]))
    return reply(plan, "final", time, place, [])


def final_push(plan, people, text_for, changed_by=None):
    """One 'final' log row and one outing.final push per side, each with that side's own
    calendar links (T212: both sides get them, not only the side that sent the last call)."""
    from .engine import api_agent, log, notify
    time, place = plan.exact_time, plan.chosen
    for p in people:
        text = text_for(p)
        log(plan, "mifgash:directory", p.address, "final", time=time.strftime("%H:%M"),
            place_id=place.pk if place else None, text=text)
        if api_agent(p):
            extra = {"changed_by": messages.first_name(changed_by)} if changed_by else {}
            notify(p, "outing.final", plan, **reply(plan, "final", time, place, []), text=text,
                   **extra, **calendar.links(plan, p))


def auto_final(plan):
    """T258 (F6c): both sides are in, so Mifgash sets the time and the place itself and the outing
    is final at once: the part default (lunch 12:30) or the time the owner typed ('lunch at 1pm').
    The place is the confirmed place, else the first option. No proposal round."""
    from .engine import log
    place = plan.chosen or (places(plan) or [None])[0]
    if not place:  # no place known: the old two-step finalize on the dashboard picks one
        return False
    plan.exact_time, plan.chosen, plan.status = default_time(plan), place, "final"
    plan.proposed_time = plan.proposed_activity = plan.proposed_by = None
    plan.agreed = []
    plan.save(update_fields=["exact_time", "chosen", "status", "proposed_time", "proposed_activity",
                             "proposed_by", "agreed"])
    log(plan, "mifgash:directory", plan.owner.address, "auto_time", time=plan.exact_time.strftime("%H:%M"),
        place_id=place.pk, source="text" if (plan.wants or {}).get("time") else "part default",
        text=messages.auto_time_text(plan))
    people = sides(plan)
    final_push(plan, people, lambda p: messages.final_text(plan, [x for x in people if x.pk != p.pk]))
    return True


def change(plan, person, raw_time, activity_id=None, backend=""):
    """T258: a side moves the time (or the place) of a final outing. The outing stays final; the
    other sides hear it with their new calendar links. One log row for the change."""
    from .engine import log
    time = parse_time(raw_time)
    options = places(plan)
    if activity_id is None:
        place = plan.chosen
    else:
        place = next((a for a in options if str(a.pk) == str(activity_id)), None)
        if not place:
            raise FinalizeError(400, "activity_id must be one of the places",
                                places=[{"id": a.pk, "name": a.name} for a in options])
    old_time, old_place = plan.exact_time, plan.chosen
    plan.exact_time, plan.chosen = time, place
    plan.save(update_fields=["exact_time", "chosen"])
    tag = {"backend": backend} if backend else {}
    log(plan, person.address, "mifgash:directory", "time_change", time=time.strftime("%H:%M"),
        old_time=old_time.strftime("%H:%M") if old_time else None, place_id=place.pk,
        text=messages.moved_text(person, plan, old_place), **tag)
    people = sides(plan)
    final_push(plan, [p for p in people if p.pk != person.pk],
               lambda p: messages.moved_text(person, plan, old_place) + " "
               + messages.final_text(plan, [x for x in people if x.pk != p.pk]), changed_by=person)
    return {**reply(plan, "final", time, place, []), "changed": True, "old_time": old_time.strftime("%H:%M") if old_time else None}
