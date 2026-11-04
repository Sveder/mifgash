"""Post a free time (M6b, T176). One code path for the agent API (POST /api/v1/availability/) and the
dashboard form of a person with no agent (POST /d/free/), so matching, the random ask order and the
agent log work the same for both."""
import datetime as dt

from django.conf import settings

from . import engine, matching
from .models import GROUP_MIN, KINDS, PARTS, Plan


def post(person, data, request):
    """data: 'text' and/or date, part, kind, area, radius_km, group_size. Returns (reply dict, http status).
    A reply with 'error' is a bad request; a reply with 'needs' asks back. Raises ValueError on a bad field."""
    from .api import (area_note, own_place, part_note, plan_json, read_availability, unknown_place,
                      waiting_for_me, where_reply, log_post)
    if not data.get("text") and not any(data.get(k) for k in ("date", "part", "kind", "area")):
        return {"error": "send text, or date, part, kind and area"}, 400
    try:
        radius = float(data.get("radius_km") or settings.DEFAULT_RADIUS_KM)
    except (TypeError, ValueError):
        raise ValueError("radius_km must be a number")
    radius = max(0.5, min(radius, 25.0))
    fields, parsed, needs, text = read_availability(data, person, dt.date.today())
    if needs:
        reply = {"needs": needs, "parsed": parsed}
        if "where" in needs:
            given = str(data.get("area") or "").strip()[:60]
            place = (None if own_place(given, person)[0] else given) if given else unknown_place(text)
            reply.update(where_reply(person, place))
        if "when" in needs:
            reply["parts"] = [k for k, _ in PARTS]
            if fields["past"]:
                reply["reason"] = "past date"
        if "what" in needs:
            reply["kinds"] = [k for k, _ in KINDS]
        return reply, 200
    same = (Plan.objects.filter(owner=person, date=fields["date"], part=fields["part"],
                                status__in=("open", "asking", "confirmed", "final"))
            .select_related("area").order_by("pk").first())
    if same:  # an agent that retries after a timeout gets the first plan back, not a second one (T28)
        return {**plan_json(request, same), "duplicate": True}, 200
    group = fields["group_size"] or 1
    group_dinner = fields["kind"] == "group_dinner"
    plan = Plan.objects.create(
        owner=person, raw_text=text, kind=fields["kind"], date=fields["date"], part=fields["part"],
        area=fields["area"], radius_km=radius, group_size=group,
        min_guests=GROUP_MIN if group_dinner else 1 if group <= 2 else 2,
        fill_by=engine.default_fill_by(fields["date"]) if group_dinner else None,
        status="open", llm_backend=fields.get("backend", ""), any_part=bool(fields["part_default"]),
        kind_named=fields["kind_named"], wants=fields["wants"])
    note = []  # T255: the place step ranks on the wants; the owner's own dislikes are never offered
    options, pick = matching.place_options(plan, exclude_tags=person.dislikes or (), note=note)
    if note:
        plan.wants = {**plan.wants, "note": note[0]}
        plan.save(update_fields=["wants"])
    plan.options.set(options)
    log_post(plan, text or data, fields)
    log_pick(plan, pick)
    engine.match_new_availability(plan)
    if person.is_sandbox:  # M7b (T179): the quick-demo friend answers now, not at the next tick
        from . import sandbox_agent
        sandbox_agent.kick(person)
    plan.refresh_from_db()
    reply = plan_json(request, plan)
    if fields["area_default"]:
        reply["area_note"] = area_note(fields["area_default"], plan.area)
    if fields["part_default"]:
        reply["part_note"] = part_note(plan.part, plan.any_part)
    offer = waiting_for_me(plan) if plan.status == "open" else None
    if offer:  # the post joined a friend's older plan: the agent must not say 'nothing yet' (T68)
        reply["proposal_id"] = offer.pk
        reply["proposal_note"] = f"A friend is free then too: proposal {offer.pk} waits for your answer."
    return reply, 201


def log_pick(plan, pick):
    """T265: one log row for the venue pick, with the why and the model tag."""
    from .engine import log
    place = pick.get("place")
    if place is None:
        return
    text = f"picked {place.name}" + (f": {pick['why']}" if pick.get("why") else "")
    log(plan, "mifgash:directory", plan.owner.address, "place_pick", place_id=place.pk, text=text,
        backend=pick.get("backend", ""), **({"cause": pick["cause"]} if pick.get("cause") else {}))
