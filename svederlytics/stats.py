"""Queries for the dashboard, the rollup command and the later API. All read-only."""
from datetime import datetime, time, timedelta

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from . import conf
from .models import Hit, Session, Visitor

DUR = ExpressionWrapper(F("last_seen") - F("started"), output_field=DurationField())


def day_range(start_day, end_day):
    """[start_day 00:00, end_day+1 00:00) in the site's time zone."""
    tz = timezone.get_current_timezone()
    a = timezone.make_aware(datetime.combine(start_day, time.min), tz)
    b = timezone.make_aware(datetime.combine(end_day + timedelta(days=1), time.min), tz)
    return a, b


def sessions_in(a, b, bots=False):
    return Session.objects.filter(started__gte=a, started__lt=b, is_bot=bots)


def hits_in(a, b, kind):
    return Hit.objects.filter(ts__gte=a, ts__lt=b, kind=kind, session__is_bot=False)


def _secs(td):
    return int(td.total_seconds()) if td else 0


def totals(a, b):
    s = sessions_in(a, b)
    agg = s.aggregate(n=Count("id"), v=Count("visitor", distinct=True), d=Avg(DUR),
                      bounce=Count("id", filter=Q(pageviews__lte=1, events=0)))
    # Returning = seen before this range, or more than one session in total. New = everyone else.
    returning = (Visitor.objects.filter(pk__in=s.values("visitor")).annotate(total=Count("sessions"))
                 .filter(Q(first_seen__lt=a) | Q(total__gt=1)).count())
    new = (agg["v"] or 0) - returning
    n = agg["n"] or 0
    return {
        "visitors": agg["v"] or 0,
        "new_visitors": new,
        "returning_visitors": returning,
        "sessions": n,
        "pageviews": hits_in(a, b, Hit.PAGE).count(),
        "events": hits_in(a, b, Hit.EVENT).count(),
        "bounce_rate": round(100.0 * agg["bounce"] / n, 1) if n else 0.0,
        "bounces": agg["bounce"] or 0,
        "avg_duration_s": _secs(agg["d"]),
        "bot_sessions": sessions_in(a, b, bots=True).count(),
    }


def daily(a, b):
    tz = timezone.get_current_timezone()
    rows = {}
    for r in (sessions_in(a, b).annotate(d=TruncDate("started", tzinfo=tz)).values("d")
              .annotate(sessions=Count("id"), visitors=Count("visitor", distinct=True))):
        rows[r["d"]] = {"sessions": r["sessions"], "visitors": r["visitors"], "pageviews": 0}
    for r in hits_in(a, b, Hit.PAGE).annotate(d=TruncDate("ts", tzinfo=tz)).values("d").annotate(n=Count("id")):
        rows.setdefault(r["d"], {"sessions": 0, "visitors": 0, "pageviews": 0})["pageviews"] = r["n"]
    out, day = [], timezone.localtime(a, tz).date()
    last = timezone.localtime(b - timedelta(seconds=1), tz).date()
    while day <= last:
        out.append({"day": day, **rows.get(day, {"sessions": 0, "visitors": 0, "pageviews": 0})})
        day += timedelta(days=1)
    return out


def _group(qs, field, label_blank="(none)", limit=50):
    rows = qs.values(field).annotate(sessions=Count("id"), visitors=Count("visitor", distinct=True)).order_by("-sessions")[:limit]
    return [{"key": r[field] or label_blank, "sessions": r["sessions"], "visitors": r["visitors"]} for r in rows]


def breakdowns(a, b):
    s = sessions_in(a, b)
    pages = [{"key": r["path"], "views": r["views"], "visitors": r["visitors"],
              "avg_time_s": int((r["t"] or 0) / 1000)}
             for r in hits_in(a, b, Hit.PAGE).values("path").annotate(
                 views=Count("id"), visitors=Count("session__visitor", distinct=True), t=Avg("duration_ms"))
             .order_by("-views")[:50]]
    events = [{"key": r["name"], "count": r["n"], "visitors": r["visitors"]}
              for r in hits_in(a, b, Hit.EVENT).values("name").annotate(
                  n=Count("id"), visitors=Count("session__visitor", distinct=True)).order_by("-n")[:50]]
    campaigns = [{"key": " / ".join(x for x in (r["utm_source"], r["utm_medium"], r["utm_campaign"]) if x),
                  "sessions": r["sessions"], "visitors": r["visitors"]}
                 for r in s.exclude(utm_source="", utm_medium="", utm_campaign="")
                 .values("utm_source", "utm_medium", "utm_campaign")
                 .annotate(sessions=Count("id"), visitors=Count("visitor", distinct=True)).order_by("-sessions")[:50]]
    return {
        "pages": pages,
        "entries": _group(s, "entry_path"),
        "referrers": _group(s, "referrer", "(direct)"),
        "campaigns": campaigns,
        "countries": _group(s, "country", "(unknown)"),
        "browsers": _group(s, "browser"),
        "os": _group(s, "os"),
        "devices": _group(s, "device"),
        "events": events,
    }


def top_visitors(a, b, limit=30):
    ever = dict(Session.objects.filter(visitor__in=sessions_in(a, b).values("visitor"), is_bot=False)
                .values_list("visitor").annotate(n=Count("id")))
    rows = (sessions_in(a, b).values("visitor_id", "visitor__vid", "visitor__user_id", "visitor__first_seen")
            .annotate(sessions=Count("id"), pageviews=Sum("pageviews"), events=Sum("events"))
            .order_by("-sessions", "-pageviews")[:limit])
    return [{"id": r["visitor_id"], "label": r["visitor__user_id"] or r["visitor__vid"][:8],
             "user": bool(r["visitor__user_id"]), "first_seen": r["visitor__first_seen"],
             "returning": r["visitor__first_seen"] < a or ever.get(r["visitor_id"], 0) > 1,
             "total_sessions": ever.get(r["visitor_id"], 0),
             "sessions": r["sessions"], "pageviews": r["pageviews"] or 0, "events": r["events"] or 0} for r in rows]


def live():
    since = timezone.now() - timedelta(minutes=conf.get("LIVE_MIN"))
    return list(Session.objects.filter(last_seen__gte=since, is_bot=False).select_related("visitor").order_by("-last_seen")[:50])


def recent_sessions(a, b, limit=50, visitor_id=None):
    qs = sessions_in(a, b).select_related("visitor")
    if visitor_id:
        qs = Session.objects.filter(visitor_id=visitor_id).select_related("visitor")
    return list(qs.order_by("-started")[:limit])
