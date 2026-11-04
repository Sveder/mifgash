"""Fill the tables with fake visits, for screenshots and local tests. Refuses to run when DEBUG is off."""
import random
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from svederlytics.models import Hit, Session, Visitor


class Command(BaseCommand):
    help = "Fake visits for a demo (DEBUG only)."

    def add_arguments(self, parser):
        parser.add_argument("--visitors", type=int, default=180)
        parser.add_argument("--days", type=int, default=45)
        parser.add_argument("--paths", default="/,/try/,/join/,/faq/,/agents/,/dashboard/,/plan/,/friends/")
        parser.add_argument("--events", default="signup,try_demo,invite_sent,plan_created,friend_added")

    def handle(self, visitors, days, paths, events, **kw):
        if not settings.DEBUG:
            raise CommandError("DEBUG is off: svederlytics_demo writes fake rows, so it runs only on a dev box.")
        rnd = random.Random(7)
        paths, events = paths.split(","), events.split(",")
        now = timezone.now()
        refs = ["", "", "", "news.ycombinator.com", "www.google.com", "t.co", "www.reddit.com", "devpost.com", "www.linkedin.com"]
        countries = ["US", "US", "US", "IL", "IL", "GB", "DE", "IN", "CA", "FR", "BR"]
        devs = [("desktop", "macOS", "Chrome"), ("desktop", "Windows", "Chrome"), ("mobile", "iOS", "Safari"),
                ("mobile", "Android", "Chrome"), ("desktop", "Linux", "Firefox"), ("tablet", "iOS", "Safari")]
        names = ["ava", "liam", "noah", "emma", "olivia", "mason", "sophia", "lucas", "mia", "ethan"]
        for i in range(visitors):
            first = now - timedelta(days=rnd.random() ** 0.7 * days, minutes=rnd.randint(0, 1400))
            v = Visitor.objects.create(vid=secrets.token_urlsafe(16)[:22], first_seen=first, last_seen=first,
                                       user_id=(rnd.choice(names) + str(i)) if rnd.random() < .25 else "")
            t = first
            for _ in range(1 + int(rnd.expovariate(0.8))):
                if t > now:
                    break
                dev = rnd.choice(devs)
                s = Session.objects.create(visitor=v, started=t, last_seen=t, entry_path=rnd.choice(paths[:3]), current_path="/",
                                           referrer=rnd.choice(refs), country=rnd.choice(countries), device=dev[0], os=dev[1],
                                           browser=dev[2], utm_source="devpost" if rnd.random() < .08 else "",
                                           utm_medium="hackathon" if rnd.random() < .08 else "",
                                           utm_campaign="meta2026" if rnd.random() < .06 else "")
                ts, pv, ev, path = t, 0, 0, s.entry_path
                for k in range(1 + int(rnd.expovariate(0.45))):
                    path = path if k == 0 else rnd.choice(paths)
                    dur = int(rnd.expovariate(1 / 40000))
                    Hit.objects.create(session=s, ts=ts, kind="page", path=path, status=200, duration_ms=dur)
                    pv += 1
                    if rnd.random() < .22:
                        Hit.objects.create(session=s, ts=ts + timedelta(seconds=3), kind="event", path=path,
                                           name=rnd.choice(events), props={"source": rnd.choice(["hero", "nav", "footer"])})
                        ev += 1
                    ts += timedelta(milliseconds=dur + 500)
                Session.objects.filter(pk=s.pk).update(last_seen=ts, current_path=path, pageviews=pv, events=ev)
                Visitor.objects.filter(pk=v.pk).update(last_seen=ts)
                t = ts + timedelta(days=rnd.expovariate(0.3))
        for j in range(4):  # live now
            v = Visitor.objects.order_by("?").first()
            s = Session.objects.create(visitor=v, started=now - timedelta(minutes=3 + j), last_seen=now - timedelta(seconds=20 * j),
                                       entry_path="/", current_path=rnd.choice(paths), country=rnd.choice(countries),
                                       device="mobile", os="iOS", browser="Safari", referrer=rnd.choice(refs), pageviews=2 + j)
            Hit.objects.create(session=s, ts=s.started, kind="page", path="/", status=200)
        for j in range(30):  # bots
            v = Visitor.objects.create(vid=f"bot{j:05d}xxxxxxxxxxxxx", first_seen=now, last_seen=now)
            Session.objects.create(visitor=v, started=now - timedelta(days=rnd.random() * days), last_seen=now, entry_path="/",
                                   current_path="/", is_bot=True, browser="bot", device="bot", pageviews=1)
        self.stdout.write(f"Demo data: {Visitor.objects.count()} visitors, {Session.objects.count()} sessions, {Hit.objects.count()} hits.")
