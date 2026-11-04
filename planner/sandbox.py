"""M7a (T178): the quick demo. POST /try/ makes a sandbox owner ('You') and three sandbox friends
(Maria, Sam and Lena, each with her or his own agent key), friends with the owner only, and logs
the browser in. Maria is free for lunch and dinner every day; Sam and Lena for dinner only, so a
lunch asks Maria and a group dinner (G3, T229) asks all three.

Sandbox people are hidden from friend search, and purge_expired() deletes them 24 hours later
with everything that hangs on them. purge_expired() never touches a person without is_sandbox.
"""
import datetime as dt
import math
import secrets

from django.db import transaction
from django.utils import timezone

from .models import AgentKey, Area, Friendship, Person, Slot

TTL = dt.timedelta(hours=24)
MAX_ROWS = 400  # open sandbox Person rows; four per session
IP_RATE = (20, 3600)  # new sessions per IP per hour (T317: judges share one network)
AREA = "Hayes Valley"
PREFILL = "free for lunch Thursday near Hayes Valley"
GROUP_HINT = "dinner Friday with 3 friends near Hayes Valley"  # G3 (T229): the second line to try

# The demo friends: (name, handle suffix, likes, parts with a weekly slot). Maria keeps the old
# handle suffix '_friend', so older sessions and links still work.
FRIENDS = [
    ("Maria", "_friend", ["lunch", "evening", "group_dinner"], ["lunch", "evening"]),
    ("Sam", "_sam", ["evening", "group_dinner"], ["evening"]),
    ("Lena", "_lena", ["evening", "group_dinner"], ["evening"]),
]


class Busy(Exception):
    pass


def open_rows(now=None):
    return Person.objects.filter(is_sandbox=True, expires_at__gt=now or timezone.now()).count()


def hours_left(person, now=None):
    if not person.expires_at:
        return 0
    s = (person.expires_at - (now or timezone.now())).total_seconds()
    return max(1, math.ceil(s / 3600)) if s > 0 else 0


@transaction.atomic
def create_session(now=None):
    """Make the owner, the friend and the friendship. Returns the owner. Busy when full."""
    now = now or timezone.now()
    if open_rows(now) + 1 + len(FRIENDS) > MAX_ROWS:
        raise Busy()
    area = Area.objects.filter(name=AREA).first()
    tag = secrets.token_hex(4)
    while Person.objects.filter(handle=f"try_{tag}").exists():
        tag = secrets.token_hex(4)
    until = now + TTL
    owner = Person.objects.create(name="You", handle=f"try_{tag}", has_agent=True, is_sandbox=True,
                                  expires_at=until, home_area=area, work_area=area,
                                  likes=["lunch", "evening", "weekend", "kids"], max_km=5)
    for name, suffix, likes, parts in FRIENDS:
        friend = Person.objects.create(name=name, handle=f"try_{tag}{suffix}", has_agent=True, is_sandbox=True,
                                       expires_at=until, home_area=area, work_area=area, likes=likes, max_km=5)
        AgentKey.issue(friend, label="sandbox friend agent")
        # Free every day for these parts in Hayes Valley, so the visitor's post finds them.
        Slot.objects.bulk_create([Slot(person=friend, weekday=d, part=part, area=area)
                                  for d in range(7) for part in parts])
        Friendship.link(owner, friend, source="sandbox")
    return owner


def expired(now=None):
    return list(Person.objects.filter(is_sandbox=True, expires_at__lt=now or timezone.now()).order_by("pk"))


def purge_expired(now=None):
    """Delete expired sandbox people and their plans, offers, messages and events. Returns the count."""
    from .management.commands.purge_test_people import delete
    people = [p for p in expired(now) if p.is_sandbox]  # belt and braces: never a real person
    if not people:
        return 0
    with transaction.atomic():
        delete(people)
    return len(people)
