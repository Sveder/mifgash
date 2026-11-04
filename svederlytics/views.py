from datetime import date, timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from . import stats
from .models import Session, Visitor

PRESETS = (("1", "Today"), ("7", "7 days"), ("30", "30 days"), ("90", "90 days"), ("365", "1 year"))


def _parse_range(request):
    today = timezone.localdate()
    try:
        start = date.fromisoformat(request.GET.get("from", ""))
        end = date.fromisoformat(request.GET.get("to", ""))
        if end < start or (end - start).days > 3660:
            raise ValueError
        preset = ""
    except ValueError:
        preset = request.GET.get("r", "30")
        days = int(preset) if preset in dict(PRESETS) else 30
        preset = str(days)
        end, start = today, today - timedelta(days=days - 1)
    return start, end, preset


def _delta(cur, prev):
    if not prev:
        return None
    return round(100.0 * (cur - prev) / prev)


def _chart(days, width=900, height=160):
    """Server-side SVG data: bars = page views, line = visitors."""
    n = len(days) or 1
    top = max([d["pageviews"] for d in days] + [d["visitors"] for d in days] + [1])
    bw = width / n
    bars, pts = [], []
    for i, d in enumerate(days):
        h = d["pageviews"] / top * (height - 20)
        w = min(bw * 0.7, 40)
        bars.append({"x": round(i * bw + (bw - w) / 2, 1), "y": round(height - h, 1), "w": round(w, 1),
                     "h": round(h, 1), "d": d})
        pts.append(f"{round(i * bw + bw / 2, 1)},{round(height - d['visitors'] / top * (height - 20), 1)}")
    step = max(1, n // 8)
    labels = [{"x": round(i * bw + bw / 2, 1), "t": d["day"].strftime("%d/%m")} for i, d in enumerate(days) if i % step == 0]
    return {"w": width, "h": height, "bars": bars, "line": " ".join(pts), "labels": labels, "top": top}


@staff_member_required(login_url="/ops/login/")
def dashboard(request):
    start, end, preset = _parse_range(request)
    a, b = stats.day_range(start, end)
    length = end - start + timedelta(days=1)
    pa, pb = stats.day_range(start - length, start - timedelta(days=1))
    cur, prev = stats.totals(a, b), stats.totals(pa, pb)
    days = stats.daily(a, b)
    tiles = [
        ("Visitors", cur["visitors"], prev["visitors"], ""),
        ("New visitors", cur["new_visitors"], prev["new_visitors"], ""),
        ("Returning", cur["returning_visitors"], prev["returning_visitors"], ""),
        ("Sessions", cur["sessions"], prev["sessions"], ""),
        ("Page views", cur["pageviews"], prev["pageviews"], ""),
        ("Events", cur["events"], prev["events"], ""),
        ("Bounce rate", cur["bounce_rate"], prev["bounce_rate"], "%"),
        ("Avg session", cur["avg_duration_s"], prev["avg_duration_s"], "s"),
    ]
    ctx = {
        "start": start, "end": end, "preset": preset, "presets": PRESETS,
        "tiles": [{"label": t[0], "value": t[1], "prev": t[2], "unit": t[3], "delta": _delta(t[1], t[2]),
                   "lower_better": t[0] == "Bounce rate"} for t in tiles],
        "bots": cur["bot_sessions"],
        "chart": _chart(days), "days": days,
        "b": stats.breakdowns(a, b),
        "live": stats.live(),
        "visitors": stats.top_visitors(a, b),
        "recent": stats.recent_sessions(a, b),
        "qs": request.GET.urlencode(),
    }
    return render(request, "svederlytics/dashboard.html", ctx)


@staff_member_required(login_url="/ops/login/")
def session_detail(request, pk):
    s = get_object_or_404(Session.objects.select_related("visitor"), pk=pk)
    return render(request, "svederlytics/session.html", {"s": s, "hits": s.hits.order_by("ts"),
                                                         "others": s.visitor.sessions.exclude(pk=s.pk).order_by("-started")[:50]})


@staff_member_required(login_url="/ops/login/")
def visitor_detail(request, pk):
    v = get_object_or_404(Visitor, pk=pk)
    return render(request, "svederlytics/visitor.html", {"v": v, "sessions": v.sessions.order_by("-started")[:200]})
