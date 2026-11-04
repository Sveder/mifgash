"""Remove test signups from the database, so friend search shows the demo world only (T89).

A test person has a handle that starts with zz_, zz<letter>_ or crit_, ends with _c29, or is a seeded handle
plus _ and 4 hex characters (maria_250b). --all removes every person who is not seeded, except
the handles named with --keep. Seeded demo people are never removed.

With each person go their plans, the offers on both sides, slots, agent keys, magic links,
events, chat, friend links and log rows. A seeded person's plan that a test person took part
in goes too, so a seeded friend is free again for that time.
"""
import re

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from planner.models import (AgentEvent, AgentKey, AgentMessage, ChatTurn, Friendship, MagicLink, Offer,
                            Person, Plan, Slot)
from planner.seed import OWNER, PEOPLE

SEEDED = {OWNER[0].lower()} | {row[0].lower() for row in PEOPLE}


def is_test_handle(handle):
    if handle in SEEDED:
        return False
    if handle.startswith(("zz_", "crit_")) or handle.endswith("_c29"):
        return True
    # night and critic runs: zzc_ava, zzr_jamie255
    if re.match(r"zz[a-z]_", handle):
        return True
    # a demo first name plus a run tag: maria_250b, sam_e605
    return bool(re.fullmatch(r"[a-z]+_(?=[0-9a-f]*[0-9])[0-9a-f]{4}", handle))


def test_people(everyone=False, keep=()):
    keep = {h.lower().lstrip("@") for h in keep}
    out = []
    for p in Person.objects.order_by("pk"):
        if p.handle in SEEDED or p.handle in keep:
            continue
        if everyone or is_test_handle(p.handle):
            out.append(p)
    return out


def purge(people):
    """Delete the people and everything that hangs on them. Returns row counts."""
    ids = [p.pk for p in people]
    addresses = [a for p in people for a in (f"agent:{p.handle}", f"human:{p.handle}", f"person:{p.handle}")]
    own_plans = Plan.objects.filter(owner_id__in=ids)
    # Plans of other people that a test person took part in: an offer to the test person, or a
    # plan that joined through an offer inside a test person's plan.
    test_offer_ids = list(Offer.objects.filter(plan__in=own_plans).values_list("pk", flat=True))
    joined = [m.plan_id for m in AgentMessage.objects.filter(type="joined", plan__isnull=False)
              .exclude(plan__owner_id__in=ids) if m.payload.get("offer_id") in test_offer_ids]
    touched = Plan.objects.exclude(owner_id__in=ids).filter(Q(offers__person_id__in=ids) | Q(pk__in=joined)).distinct()
    plans = Plan.objects.filter(Q(owner_id__in=ids) | Q(pk__in=list(touched.values_list("pk", flat=True))))
    plan_ids = list(plans.values_list("pk", flat=True))
    addr_q = Q()
    for a in addresses:
        addr_q |= Q(sender__startswith=a) | Q(receiver__startswith=a)
    counts = {
        "people": len(ids),
        "plans": len(plan_ids),
        "other people's plans": touched.count(),
        "offers": Offer.objects.filter(Q(plan_id__in=plan_ids) | Q(person_id__in=ids)).count(),
        "slots": Slot.objects.filter(person_id__in=ids).count(),
        "agent keys": AgentKey.objects.filter(person_id__in=ids).count(),
        "magic links": MagicLink.objects.filter(person_id__in=ids).count(),
        "events": AgentEvent.objects.filter(Q(person_id__in=ids) | Q(plan_id__in=plan_ids)).count(),
        "chat turns": ChatTurn.objects.filter(owner_id__in=ids).count(),
        "friend links": Friendship.objects.filter(Q(person_id__in=ids) | Q(friend_id__in=ids)).count(),
        "log rows": AgentMessage.objects.filter(Q(plan_id__in=plan_ids) | (Q(plan__isnull=True) & addr_q)).count()
                    if ids else 0,
    }
    return counts, plan_ids, addr_q


def delete(people, plan_ids=None, addr_q=None):
    """Delete the people and all that purge() counted. Call inside a transaction."""
    if plan_ids is None:
        _, plan_ids, addr_q = purge(people)
    ids = [p.pk for p in people]
    AgentMessage.objects.filter(Q(plan_id__in=plan_ids) | (Q(plan__isnull=True) & addr_q)).delete()
    AgentEvent.objects.filter(plan_id__in=plan_ids).delete()
    Plan.objects.filter(pk__in=plan_ids).delete()
    Friendship.objects.filter(Q(person_id__in=ids) | Q(friend_id__in=ids)).delete()
    Person.objects.filter(pk__in=ids).delete()  # cascades: offers, slots, keys, links, events, chat


class Command(BaseCommand):
    help = "Delete test signups (zz_*, zz<letter>_*, crit_*, *_c29, <name>_<4 hex>) and everything they own."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="print the handles and row counts only")
        parser.add_argument("--all", action="store_true", help="every person who is not seeded")
        parser.add_argument("--keep", nargs="*", default=[], help="handles to keep with --all")

    def handle(self, *args, **opts):
        people = test_people(everyone=opts["all"], keep=opts["keep"])
        if not people:
            self.stdout.write("No test people.")
            return
        with transaction.atomic():
            counts, plan_ids, addr_q = purge(people)
            self.stdout.write("Handles: " + " ".join(p.handle for p in people))
            for k, v in counts.items():
                self.stdout.write(f"  {k}: {v}")
            if opts["dry_run"]:
                self.stdout.write("Dry run: nothing deleted.")
                return
            delete(people, plan_ids, addr_q)
        self.stdout.write(f"Deleted {len(people)} test people.")
