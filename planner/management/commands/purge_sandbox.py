"""Delete quick-demo people (is_sandbox) whose expires_at has passed, with their plans, offers,
log rows and events (M7a, T178). The tick runs it every minute. A person without is_sandbox is
never touched."""
import datetime as dt

from django.core.management.base import BaseCommand
from django.utils import timezone

from planner import sandbox


class Command(BaseCommand):
    help = "Delete expired quick-demo sessions (is_sandbox people past expires_at)."

    def add_arguments(self, parser):
        parser.add_argument("--now", help="ISO time to use instead of the clock (tests, a forced expiry)")
        parser.add_argument("--dry-run", action="store_true", help="print the handles only")

    def handle(self, *args, **opts):
        now = None
        if opts["now"]:
            now = dt.datetime.fromisoformat(opts["now"])
            if timezone.is_naive(now):
                now = timezone.make_aware(now)
        if opts["dry_run"]:
            people = sandbox.expired(now)
            self.stdout.write("Expired: " + (" ".join(p.handle for p in people) or "none"))
            return
        self.stdout.write(f"purge_sandbox: deleted {sandbox.purge_expired(now)} people")
