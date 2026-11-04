import datetime as dt

from django.core.management.base import BaseCommand
from django.utils import timezone

from planner import engine, places_live, sandbox, sandbox_agent


class Command(BaseCommand):
    help = "Expire due offers and move every asking plan on. A timer runs it every minute."

    def add_arguments(self, parser):
        parser.add_argument("--now", help="ISO time to use instead of the clock (tests)")

    def handle(self, *args, **opts):
        now = None
        if opts["now"]:
            now = dt.datetime.fromisoformat(opts["now"])
            if timezone.is_naive(now):
                now = timezone.make_aware(now)
        looked = places_live.run_queued(now)  # T401: live place lookups for cities Mifgash did not cover
        moved = engine.tick(now)
        played = sandbox_agent.run()  # M7b (T179): the quick-demo friend answers
        gone = sandbox.purge_expired(now)  # M7a (T178): quick-demo sessions end after 24 h
        self.stdout.write(f"tick: moved {moved or 'none'}"
                          + (f", place lookups {looked}" if looked else "") + (f", sandbox friend moved {played}" if played else "")
                          + (f", purged {gone} sandbox people" if gone else ""))
