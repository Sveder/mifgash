"""Every sentence a human sees. Fixed templates, so the gentle rules are testable.

Rules (SPEC.md, "Gentle matching"):
1. The owner never sees who said no, who did not answer, or how many friends were asked.
2. A friend never sees that someone else was asked first.
3. A friend who was never asked hears nothing.
4. "Did not work out" names no person and gives no reason. It always ends with other options.
"""
import re

from .models import WEEKDAYS

# T258 (F6c) + T319: the time Mifgash sets by itself when both sides are in. ONE source: the
# finalize step, the card's time field and the lunch words below all read it. API times stay HH:MM.
DEFAULT_TIMES = {"morning": "10:00", "lunch": "12:30", "afternoon": "15:30", "evening": "19:30"}


def clock(t):
    """'12:30 PM', '9:00 AM' (T319: 12-hour times for US readers, the SF world). Takes a time or 'HH:MM'."""
    if isinstance(t, str):
        h, m = map(int, t.split(":")[:2])
    else:
        h, m = t.hour, t.minute
    return f"{(h % 12) or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"


# T319: lunch names the exact clock time Mifgash will set ('at 12:30 PM'), never 'at noon'.
PART_WORDS = {"morning": "morning", "lunch": f"at {clock(DEFAULT_TIMES['lunch'])}", "afternoon": "afternoon",
              "evening": "evening"}
KIND_WORDS = {"lunch": "lunch", "kids": "an outing with the kids", "evening": "an evening out",
              "weekend": "a weekend outing", "group_dinner": "a group dinner"}
# The kind word for a plan whose person named no kind (T112): it comes from the part of the day.
PART_KIND_WORDS = {"morning": "a morning meetup", "lunch": "lunch", "afternoon": "an afternoon meetup",
                   "evening": "an evening out"}


def kind_label(kind):
    """The kind without the article, for a log line: 'group dinner', never 'group_dinner' (T354)."""
    return re.sub(r"^(?:a|an) ", "", KIND_WORDS.get(kind, str(kind).replace("_", " ")))


def kind_word(plan):
    """'a weekend outing' when the person said so, else the part's word: 'a morning meetup'.
    T377: a typed 'dinner' is 'dinner', the same word as the card title."""
    if getattr(plan, "is_dinner", False):
        return "dinner"
    return KIND_WORDS[plan.kind] if plan.kind_named else PART_KIND_WORDS[plan.part]

# Words that must never appear in a text to a human. Tested.
FORBIDDEN = ["declined", "rejected", "refused", "said no", "instead of", "first choice",
             "second choice", "preferred", "nobody wanted", "no one wanted", "busy with someone"]


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def fmt_day(date):
    """'Wed Nov 4' (T351): the ONE date form in every human line (agent text, log rows, cards, pages).
    The .ics file and the Google Calendar link keep their machine forms."""
    return f"{WEEKDAYS[date.weekday()]} {MONTHS[date.month - 1]} {date.day}"


def fmt_when(date, time):
    """'Wed Nov 4, 12:30 PM' (T351). Takes a time or 'HH:MM'."""
    return f"{fmt_day(date)}, {clock(time)}"


def when(date, part):
    return f"{fmt_day(date)} {PART_WORDS[part]}"


def plan_time(plan):
    """The clock time the plan will get: the set time, else the time in its own text, else the part
    default (T319). A 'HH:MM' string."""
    if getattr(plan, "exact_time", None):
        return plan.exact_time.strftime("%H:%M")
    wanted = str((plan.wants or {}).get("time") or "")
    if len(wanted) == 5 and wanted[2] == ":" and wanted.replace(":", "").isdigit():
        return wanted
    return DEFAULT_TIMES.get(plan.part, DEFAULT_TIMES["lunch"])


def plan_when(plan):
    """'Sun Nov 1 at 12:30 PM' for a lunch (its own time), or 'Sun Nov 1' when the kind word already
    says the part (an evening out)."""
    if PART_WORDS[plan.part] in kind_word(plan) or getattr(plan, "is_dinner", False):  # T377: no 'dinner ... evening'
        return day(plan.date)
    if plan.part == "lunch":
        return f"{day(plan.date)} at {clock(plan_time(plan))}"
    return when(plan.date, plan.part)


def kind_on(plan):
    """'lunch on Sun Nov 1 at 12:30 PM', 'an evening out on Sun Nov 1': the part word only once."""
    return f"{kind_word(plan)} on {plan_when(plan)}"


def offer_text(owner, plan, options):
    """What the friend sees. Written as if this friend is the only person asked."""
    place = f"{options[0].name}, {options[0].address}" if options and options[0].address else (
        options[0].name if options else plan.area.name)
    # T321: the group line only when more than 2 friends are asked (a playdate of 2-3 families is no group)
    group = f" {group_ask_line(plan)}" if is_group(plan) else ""
    return (f"{owner.name} is free for {kind_on(plan)}, "
            f"near {plan.area.name}. You are open then too. Want to meet? "
            f"Idea: {place}.{group}")


def is_group(plan):
    """T321: a group line only when more than 2 friends are asked, or for a group dinner."""
    return plan.group_size > 2 or plan.kind == "group_dinner"


def group_in(plan):
    """T327: the friends who are in on a group plan (an accepted yes), in the order they said yes.
    Only yeses: a friend who declined or was not asked yet is never in this list (gentle rule)."""
    return [o.person for o in plan.offers.filter(status="accepted").select_related("person").order_by(
        "answered_at", "pk")]


def group_count(plan, people=None):
    """T327: '2 of 3 in (Noah, Sofia)', or '0 of 3 in'. The count is of friends; the owner is not counted."""
    people = group_in(plan) if people is None else people
    who = f" ({', '.join(first_name(p) for p in people)})" if people else ""
    return f"{len(people)} of {plan.group_size} in{who}"


def group_ask_line(plan, people=None):
    """T327: the group line in an ask: 'Noah is coming, 1 place left.' No yes yet: the old line."""
    people = group_in(plan) if people is None else people
    if not people:
        return "A few friends may join too."
    left = plan.group_size - len(people)
    verb = "is" if len(people) == 1 else "are"
    room = f", {left} place{'s' if left != 1 else ''} left" if left > 0 else ""
    return f"{names(people)} {verb} coming{room}."


def group_owner_text(plan, people=None):
    """T327: the owner's line while a group dinner still asks: 'Group dinner: 2 of 3 in (Noah, Sofia), asking more'."""
    return f"{plan.title}: {group_count(plan, people)}, asking more"


def group_guest_text(plan, people=None):
    """T327: a guest who is in, while the group still fills: 'You are in. 2 of 3 in, waiting for 1 more.'"""
    people = group_in(plan) if people is None else people
    left = max(plan.group_size - len(people), 0)
    more = f", waiting for {left} more" if left else ""
    return f"You are in. {len(people)} of {plan.group_size} in{more}."


def human_invite_text(plan, options):
    """The invite line for a friend with no agent: kind, day, part and area. The owner's first name
    goes in front of it, so it never says who else was asked."""
    return f"{kind_on(plan)}, near {plan.area.name}."


def asking_text(plan):
    """Owner view while the queue runs. No counts, no names."""
    return "I am checking with friends who are open then. I ask one at a time, so nobody feels rushed."


def confirmed_text(plan, guests):
    names = " and ".join(g.name for g in guests)
    place = plan.chosen.name if plan.chosen else plan.area.name
    return f"Done. {names} will meet you for {kind_on(plan)} at {place}."


def first_name(person):
    return (person.name or "").split()[0] if (person.name or "").strip() else person.handle


def said_yes_text(offer):
    """The friend's card while the owner decides. Owner's first name only; no word on other friends."""
    plan = offer.plan
    place = offer.choice or (plan.option_list() or [None])[0]
    where = f", {place.name}" if place else f", near {plan.area.name}"
    return (f"You said yes to {kind_word(plan)} with {first_name(plan.owner)}, "
            f"{plan_when(plan)}{where}. Waiting for the final word.")


def friend_confirmed_text(plan, viewer=None, guests=None):
    """The confirm line for ONE side. It names the other people on the outing, never the viewer."""
    place = plan.chosen.name if plan.chosen else plan.area.name
    people = [plan.owner] + list(guests if guests is not None else plan.guests())
    others = [p for p in people if viewer is None or p.pk != viewer.pk] or [plan.owner]
    # G3 (T229): 'both' only for two people; a group reads 'You are all in', names as 'A, B and C'
    who = "both" if len(others) == 1 else "all"
    return f"You are {who} in: {kind_word(plan)} with {names(others)}, {plan_when(plan)}, {place}."


def no_match_text(plan):
    """Owner view after the queue ends with too few yeses. Neutral, no names, no reason."""
    return (f"This time {kind_on(plan)} did not work out. "
            "That is normal: free times often do not line up. Here are other options.")


def group_closed_text(plan):
    """For a friend who said yes to a group plan that did not come together."""
    return (f"The plan for {when(plan.date, plan.part)} did not come together this time. "
            "You do not need to do anything. I will tell you about the next one.")


def expired_text(owner):
    """A friend opens an old link. No blame on either side."""
    return (f"This plan is already closed. No problem. "
            f"Below are other times {owner.name} is open, if one fits you.")


def human_slot_text(owner, slot_date, part):
    return f"I see you are open on {when(slot_date, part)}. {owner.name} can join you then."


def check(text):
    """Return the forbidden phrases found in a text. Used by tests and by the engine."""
    low = text.lower()
    return [w for w in FORBIDDEN if w in low]


def waiting_text(plan):
    """Owner view when no friend fits an open availability yet. No names, no counts."""
    return ("Nobody is open near there yet. Your time stays open, and I will try again "
            "when a friend posts a time that fits.")


def still_open_text(plan):
    """Owner view when the friends asked for an open time did not fit. No names, no counts."""
    return (f"Nobody fits yet for {when(plan.date, plan.part)}. Your time stays open, "
            "and I will tell you when a friend fits.")


def owner_ask_text(friend, plan, choice, offer=None):
    """The owner's agent asks its human. The owner sees only this friend, never the queue.
    T329: in a group, a guest's own place pick reads as a vote next to the group's votes so far."""
    place = choice.name if choice else plan.area.name
    vote = group_vote_line(plan, offer) if offer is not None and is_group(plan) else ""
    if vote:
        return f"{friend.name} is free for {kind_on(plan)}. {vote} Does it work for you? Yes, or not this time."
    return (f"{friend.name} is free for {kind_on(plan)} "
            f"and wants to meet at {place}. Does it work for you? Yes, or not this time.")


def group_vote_line(plan, offer):
    """T329: 'Mia votes Zuni Cafe; the group so far: Foreign Cinema (2).' The votes of the guests who
    are in (engine.group_vote, T350), never a name of a friend who said no. '' when no pick."""
    from .engine import accepted, group_vote, picked_place
    pick = picked_place(offer)
    if not pick:
        return ""
    _, votes = group_vote(plan, [o for o in accepted(plan) if o.pk != offer.pk])
    line = f"{first_name(offer.person)} votes {pick.name}"
    if votes:
        so_far = ", ".join(f"{n} ({c})" for n, c in sorted(votes.items(), key=lambda kv: (-kv[1], kv[0])))
        line += f"; the group so far: {so_far}"
    return line + "."


def vote_lost_line(plan, person):
    """T329: for a guest whose own place pick lost the group vote: ' Most of the group picked X.'"""
    from .engine import picked_place
    if not (is_group(plan) and plan.chosen):
        return ""
    offer = plan.offers.filter(person=person, status="accepted").first()
    pick = picked_place(offer) if offer else None
    if pick and pick.pk != plan.chosen.pk:
        return f" Most of the group picked {plan.chosen.name}."
    return ""


def owner_reason(offer):
    """T329: the 'why it fits' line the owner reads next to a friend's yes. The line was written for
    Mifgash's own first idea; when the friend picked another place it names the wrong place, so the
    owner gets no why line then (the ask names the friend's place)."""
    reason = offer.reason or ""
    choice = offer.choice
    if not reason or not choice or choice.name in reason:
        return reason or None
    if any(a.name in reason for a in offer.plan.option_list() if a.pk != choice.pk):
        return None
    return reason


def joined_text(plan):
    """The candidate said yes inside a friend's plan; the own open time is used."""
    return (f"You said yes to {kind_word(plan)} with {plan.owner.name} on {plan_when(plan)}. "
            "I wait for the final word and keep your time for it.")


def reopened_text(plan):
    """The friend's plan did not come together; the own time is open again."""
    return f"Your time on {when(plan.date, plan.part)} is open again. I will tell you when a friend fits."


# M13b (T184): one light conversation hint per place, on the outing card. One place only for now.
PLACE_HINTS = {"The Stinking Rose": "Garlic: yes."}


def place_hint(place):
    """The conversation hint of a place, or ''."""
    return PLACE_HINTS.get(getattr(place, "name", ""), "")


UI_PARTS = {"morning": "morning", "lunch": "lunch", "afternoon": "afternoon", "evening": "evening"}


def ui_day(date):
    """The date on a web page: 'Sun Nov 8' (T120, T351: the same form as the agent text)."""
    return fmt_day(date)


def ui_when(date, part):
    """'Sun Nov 8, lunch'."""
    return f"{ui_day(date)}, {UI_PARTS[part]}"


def card_when(plan, title=None):
    """ui_when for a card under a title (T318/T295): 'Thu 5 Nov' when the title already names the part
    ('Lunch'), so the card never reads 'Lunch · Thu 5 Nov, lunch'; else 'Thu 5 Nov, lunch'."""
    title = plan.title if title is None else title
    if UI_PARTS[plan.part] in str(title).lower():
        return ui_day(plan.date)
    return ui_when(plan.date, plan.part)


def when_exact(date, time):
    """'Fri Oct 30, 1:00 PM'."""
    return fmt_when(date, time)


def names(people):
    """'Maria', 'Maria and Sam', 'Maria, Sam and Lee'."""
    words = [first_name(p) for p in people]
    return " and ".join(words) if len(words) < 3 else ", ".join(words[:-1]) + " and " + words[-1]


def finalize_set_text(time, place, waiting_for):
    """For the side that proposed the exact time and place."""
    return f"Set: {clock(time)} at {place.name}. Waiting for {names(waiting_for)}."


def finalize_ask_text(proposer, time, place):
    """For the other side: the proposer's exact time and place, to confirm or change."""
    return (f"{first_name(proposer)} suggests {clock(time)} at {place.name}, {place.address or place.area.name}. "
            "Send the same time and place to make it final, or send another one.")


def finalize_counter_text(proposer, time, old_time, place):
    """For the other side when a side answers a proposed time with another one (T70)."""
    who = f"{first_name(proposer)}'s agent" if proposer.has_agent else first_name(proposer)
    return (f"{who} suggests {clock(time)} instead of {clock(old_time)}, at {place.name}. "
            "Send the same time and place to make it final, or send another one.")


def day(date):
    """'Fri Oct 30'."""
    return fmt_day(date)


def agree_time_text(proposer, plan, time, place):
    """For a side that has not agreed yet: the other side's time and place, with the command (T80)."""
    cmd = f"finalize {plan.pk} --time {time.strftime('%H:%M')}" + (f" --place {place.pk}" if place else "")
    at = f" at {place.name}" if place else ""
    return (f"{first_name(proposer)} proposes {clock(time)}{at} for {kind_word(plan)} "
            f"on {day(plan.date)}. Agree: {cmd}. Or send another time.")


def set_time_text(plan, others):
    """For a side of a confirmed outing with no time on the table yet (T80)."""
    return (f"{kind_word(plan)[0].upper()}{kind_word(plan)[1:]} with {names(others)} on "
            f"{day(plan.date)} is set. Pick the exact time: finalize {plan.pk} --time HH:MM.")


def us_day(date):
    """'Tue Nov 3' (T258; US readers, the SF world)."""
    return fmt_day(date)


def final_text(plan, others):
    """For each side when the plan is final. Names the other people, never the reader (T258)."""
    place = plan.chosen
    where = f"{place.name}, {place.address or place.area.name}" if place else plan.area.name
    # T353: the ONE row a side reads for a set outing: who, day and time, place. 'both' for two people.
    who = "both" if len(others) == 1 else "all"
    return (f"You are {who} in: {kind_word(plan)} with {names(others)}, {fmt_when(plan.date, plan.exact_time)}, "
            f"{where}. Change the time on your dashboard.")


def auto_time_text(plan):
    """The one log row when Mifgash sets the time by itself (T258)."""
    place = plan.chosen.name if plan.chosen else plan.area.name
    return f"Set {clock(plan.exact_time)} at {place}. Change it on your dashboard."


def moved_text(person, plan, old_place=None):
    """'Alex moved lunch to 1:00 PM.' (T258) The place too when it changed."""
    where = f" at {plan.chosen.name}" if plan.chosen and old_place and plan.chosen.pk != old_place.pk else ""
    return f"{first_name(person)} moved {kind_word(plan)} to {clock(plan.exact_time)}{where}."

def move_ask_text(person, plan, time, place=None):
    """T328: 'Sofia asks to move the group dinner to 8:00 PM (now 7:30 PM).' To the owner only."""
    where = f" at {place.name}" if place and plan.chosen and place.pk != plan.chosen.pk else ""
    return (f"{first_name(person)} asks to move the {re.sub(r'^(?:a|an) ', '', kind_word(plan))} to {clock(time)}{where} "
            f"(now {clock(plan.exact_time)}). Approve it or keep the time on your dashboard.")


def move_keep_text(owner, plan):
    """T328: to the guest who asked: the owner keeps the set time."""
    return f"{first_name(owner)} keeps the {re.sub(r'^(?:a|an) ', '', kind_word(plan))} at {clock(plan.exact_time)}."
