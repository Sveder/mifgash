"""Write daily totals into DailyStat. Run weekly (cron). Deletes nothing.
   manage.py svederlytics_rollup            the last 8 days (a weekly run with one day of overlap)
   manage.py svederlytics_rollup --all      every day since the first visitor
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Min
from django.utils import timezone

from svederlytics import stats
from svederlytics.models import DailyStat, Session


class Command(BaseCommand):
    help = "Write daily totals into DailyStat (deletes nothing)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=8)
        parser.add_argument("--all", action="store_true")

    def handle(self, days, all, **kw):
        today = timezone.localdate()
        start = today - timedelta(days=days)
        if all:
            first = Session.objects.aggregate(m=Min("started"))["m"]
            if first is None:
                self.stdout.write("No data.")
                return
            start = timezone.localtime(first).date()
        day, n = start, 0
        while day <= today:
            a, b = stats.day_range(day, day)
            t = stats.totals(a, b)
            DailyStat.objects.update_or_create(day=day, defaults={
                "visitors": t["visitors"], "new_visitors": t["new_visitors"], "sessions": t["sessions"],
                "pageviews": t["pageviews"], "events": t["events"], "bounces": t["bounces"],
                "duration_s": t["avg_duration_s"] * t["sessions"], "bot_sessions": t["bot_sessions"]})
            day += timedelta(days=1)
            n += 1
        self.stdout.write(f"Rolled up {n} days, {start} to {today}.")
