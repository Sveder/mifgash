"""POST /_sl/ - the one public endpoint. Takes events and heartbeats from sl.js. Writes analytics rows only."""
import json
import re
from urllib.parse import urlsplit

from django.core.cache import cache
from django.db.models import F
from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from . import conf, record
from .models import Hit, Session

NAME_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
KEY_RE = re.compile(r"^[A-Za-z0-9_]{1,32}$")
FIELDS = {"t", "n", "p", "path"}


def _bad(code=400):
    return HttpResponse(status=code)


def origin_ok(request):
    origin = request.META.get("HTTP_ORIGIN", "")
    if not origin or origin == "null":
        return False
    if origin in conf.get("ALLOWED_ORIGINS"):
        return True
    try:
        netloc = urlsplit(origin).netloc.lower()
    except ValueError:
        return False
    return netloc == request.get_host().lower()


def rate_ok(key):
    ckey = "sl:rl:" + key + ":" + str(int(timezone.now().timestamp() // 60))
    if cache.add(ckey, 1, 70):
        return True
    try:
        return cache.incr(ckey) <= conf.get("RATE_PER_MIN")
    except ValueError:
        return True


def clean_props(raw):
    if raw in (None, ""):
        return {}
    if not isinstance(raw, dict) or len(raw) > conf.get("MAX_PROPS"):
        raise ValueError("props")
    out = {}
    for k, v in raw.items():
        if not isinstance(k, str) or not KEY_RE.match(k):
            raise ValueError("prop key")
        if isinstance(v, bool) or v is None:
            out[k] = v
        elif isinstance(v, (int, float)):
            out[k] = v if abs(v) < 1e15 else None
        elif isinstance(v, str):
            out[k] = v[:200]
        else:
            raise ValueError("prop value")
    return out


@csrf_exempt  # anonymous visitors post here; the view only writes analytics rows (see README, Security)
def collect(request):
    if request.method != "POST":
        return _bad(405)
    try:
        length = int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        return _bad()
    if length <= 0 or length > conf.get("MAX_BODY"):
        return _bad(413 if length > 0 else 400)
    if not origin_ok(request):
        return _bad(403)
    vid = record.read_vid(request)
    if not vid:
        return HttpResponse(status=204)  # no visitor cookie = no page view first: drop quietly
    if not rate_ok(vid):
        return _bad(429)
    try:
        data = json.loads(request.body[: conf.get("MAX_BODY")].decode("utf-8"))
        if not isinstance(data, dict) or set(data) - FIELDS:
            raise ValueError("fields")
        kind = data.get("t")
        path = data.get("path") or "/"
        if not isinstance(path, str) or not path.startswith("/"):
            raise ValueError("path")
        path = record.clean_path(path.split("?")[0].split("#")[0])
        if kind == "e":
            name = data.get("n")
            if not isinstance(name, str) or not NAME_RE.match(name):
                raise ValueError("name")
            props = clean_props(data.get("p"))
        elif kind != "h":
            raise ValueError("kind")
    except (ValueError, UnicodeDecodeError):
        return _bad()

    now = timezone.now()
    _, session = record.visitor_and_session(request, vid, path, now, create=(kind == "e"))
    if session is None:
        return HttpResponse(status=204)
    if kind == "e":
        Hit.objects.create(session=session, ts=now, kind=Hit.EVENT, path=path, name=name, props=props)
        Session.objects.filter(pk=session.pk).update(last_seen=now, events=F("events") + 1)
    else:
        Session.objects.filter(pk=session.pk).update(last_seen=now)
        page = session.hits.filter(kind=Hit.PAGE, path=path).order_by("-ts").first()
        if page is not None:
            ms = int((now - page.ts).total_seconds() * 1000)
            Hit.objects.filter(pk=page.pk).update(duration_ms=min(ms, 6 * 3600 * 1000))
    return HttpResponse(status=204)
