"""Every sentence a human sees. Fixed templates, so the gentle rules are testable.

Rules (SPEC.md, "Gentle matching"):
1. The owner never sees who said no, who did not answer, or how many friends were asked.
2. A friend never sees that someone else was asked first.
3. A friend who was never asked hears nothing.
4. "Did not work out" names no person and gives no reason. It always ends with other options.
"""
from .models import WEEKDAYS

PART_WORDS = {"morning": "morning", "lunch": "at noon", "afternoon": "afternoon", "evening": "evening"}
KIND_WORDS = {"lunch": "lunch", "kids": "an outing with the kids", "evening": "an evening out",
              "weekend": "a weekend outing", "group_dinner": "a group dinner"}
# The kind word for a plan whose person named no kind (T112): it comes from the part of the day.
PART_KIND_WORDS = {"morning": "a morning meetup", "lunch": "lunch", "afternoon": "an afternoon meetup",
                   "evening": "an evening out"}


def kind_word(plan):
    """'a weekend outing' when the person said so, else the part's word: 'a morning meetup'."""
    return KIND_WORDS[plan.kind] if plan.kind_named else PART_KIND_WORDS[plan.part]

# Words that must never appear in a text to a human. Tested.
FORBIDDEN = ["declined", "rejected", "refused", "said no", "instead of", "first choice",
             "second choice", "preferred", "nobody wanted", "no one wanted", "busy with someone"]


def when(date, part):
    return f"{WEEKDAYS[date.weekday()]} {date.day}/{date.month} {PART_WORDS[part]}"


def plan_when(plan):
    """'Sun 1/11 at noon', or 'Sun 1/11' when the kind word already says the part (an evening out)."""
    if PART_WORDS[plan.part] in kind_word(plan):
        return day(plan.date)
    return when(plan.date, plan.part)


def kind_on(plan):
    """'lunch on Sun 1/11 at noon', 'an evening out on Sun 1/11': the part word only once."""
    return f"{kind_word(plan)} on {plan_when(plan)}"


def offer_text(owner, plan, options):
    """What the friend sees. Written as if this friend is the only person asked."""
    place = f"{options[0].name}, {options[0].address}" if options and options[0].address else (
        options[0].name if options else plan.area.name)
    group = "" if plan.group_size == 1 else " A few friends may join too."
    return (f"{owner.name} is free for {kind_on(plan)}, "
            f"near {plan.area.name}. You are open then too. Want to meet? "
            f"Idea: {place}.{group}")


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


def owner_ask_text(friend, plan, choice):
    """The owner's agent asks its human. The owner sees only this friend, never the queue."""
    place = choice.name if choice else plan.area.name
    return (f"{friend.name} is free for {kind_on(plan)} "
            f"and wants to meet at {place}. Does it work for you? Yes, or not this time.")


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


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
UI_PARTS = {"morning": "morning", "lunch": "lunch", "afternoon": "afternoon", "evening": "evening"}


def ui_day(date):
    """The date on a web page: 'Sun 8 Nov' (T120). Agent text keeps 'Sun 8/11'."""
    return f"{WEEKDAYS[date.weekday()]} {date.day} {MONTHS[date.month - 1]}"


def ui_when(date, part):
    """'Sun 8 Nov, lunch'."""
    return f"{ui_day(date)}, {UI_PARTS[part]}"


def card_when(plan, title=None):
    """ui_when for a card under a title (T318/T295): 'Thu 5 Nov' when the title already names the part
    ('Lunch'), so the card never reads 'Lunch · Thu 5 Nov, lunch'; else 'Thu 5 Nov, lunch'."""
    title = plan.title if title is None else title
    if UI_PARTS[plan.part] in str(title).lower():
        return ui_day(plan.date)
    return ui_when(plan.date, plan.part)


def when_exact(date, time):
    """'Fri 30/10 13:00'."""
    return f"{WEEKDAYS[date.weekday()]} {date.day}/{date.month} {time.strftime('%H:%M')}"


def names(people):
    """'Maria', 'Maria and Sam', 'Maria, Sam and Lee'."""
    words = [first_name(p) for p in people]
    return " and ".join(words) if len(words) < 3 else ", ".join(words[:-1]) + " and " + words[-1]


def finalize_set_text(time, place, waiting_for):
    """For the side that proposed the exact time and place."""
    return f"Set: {time.strftime('%H:%M')} at {place.name}. Waiting for {names(waiting_for)}."


def finalize_ask_text(proposer, time, place):
    """For the other side: the proposer's exact time and place, to confirm or change."""
    return (f"{first_name(proposer)} suggests {time.strftime('%H:%M')} at {place.name}, {place.address or place.area.name}. "
            "Send the same time and place to make it final, or send another one.")


def finalize_counter_text(proposer, time, old_time, place):
    """For the other side when a side answers a proposed time with another one (T70)."""
    who = f"{first_name(proposer)}'s agent" if proposer.has_agent else first_name(proposer)
    return (f"{who} suggests {time.strftime('%H:%M')} instead of {old_time.strftime('%H:%M')}, at {place.name}. "
            "Send the same time and place to make it final, or send another one.")


def day(date):
    """'Fri 30/10'."""
    return f"{WEEKDAYS[date.weekday()]} {date.day}/{date.month}"


def agree_time_text(proposer, plan, time, place):
    """For a side that has not agreed yet: the other side's time and place, with the command (T80)."""
    cmd = f"finalize {plan.pk} --time {time.strftime('%H:%M')}" + (f" --place {place.pk}" if place else "")
    at = f" at {place.name}" if place else ""
    return (f"{first_name(proposer)} proposes {time.strftime('%H:%M')}{at} for {kind_word(plan)} "
            f"on {day(plan.date)}. Agree: {cmd}. Or send another time.")


def set_time_text(plan, others):
    """For a side of a confirmed outing with no time on the table yet (T80)."""
    return (f"{kind_word(plan)[0].upper()}{kind_word(plan)[1:]} with {names(others)} on "
            f"{day(plan.date)} is set. Pick the exact time: finalize {plan.pk} --time HH:MM.")


def us_day(date):
    """'Tue Nov 3' (T258; US readers, the SF world)."""
    return f"{WEEKDAYS[date.weekday()]} {MONTHS[date.month - 1]} {date.day}"


def final_text(plan, others):
    """For each side when the plan is final. Names the other people, never the reader (T258)."""
    place = plan.chosen
    where = f"{place.name}, {place.address or place.area.name}" if place else plan.area.name
    return (f"Set: {kind_word(plan)} with {names(others)}, {us_day(plan.date)} "
            f"{plan.exact_time.strftime('%H:%M')} at {where}. Change it on your dashboard if the time does not fit.")


def auto_time_text(plan):
    """The one log row when Mifgash sets the time by itself (T258)."""
    place = plan.chosen.name if plan.chosen else plan.area.name
    return f"Set {plan.exact_time.strftime('%H:%M')} at {place}. Change it on your dashboard."


def moved_text(person, plan, old_place=None):
    """'Alex moved lunch to 13:00.' (T258) The place too when it changed."""
    where = f" at {plan.chosen.name}" if plan.chosen and old_place and plan.chosen.pk != old_place.pk else ""
    return f"{first_name(person)} moved {kind_word(plan)} to {plan.exact_time.strftime('%H:%M')}{where}."