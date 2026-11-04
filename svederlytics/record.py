"""Shared logic: client IP, visitor, session. The raw IP is used for the country lookup only and is never stored."""
import logging
import re
import secrets
from datetime import timedelta
from functools import lru_cache
from urllib.parse import parse_qs, urlsplit

from django.utils import timezone
from django.utils.module_loading import import_string

from . import conf, ua
from .models import Session, Visitor

log = logging.getLogger("svederlytics")
VID_RE = re.compile(r"^[A-Za-z0-9_-]{16,32}$")


def client_ip(request):
    if conf.get("TRUST_PROXY"):
        ip = request.META.get("HTTP_X_REAL_IP") or request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0]
        if ip.strip():
            return ip.strip()
    return request.META.get("REMOTE_ADDR", "")


@lru_cache(maxsize=1)
def _geo_reader(path):
    try:
        import geoip2.database
        return geoip2.database.Reader(path)
    except Exception:  # no geoip2 package or no file: no country
        return None


def country(ip):
    path = conf.get("GEOIP_PATH")
    if not path or not ip:
        return ""
    reader = _geo_reader(path)
    if reader is None:
        return ""
    try:
        return (reader.country(ip).country.iso_code or "")[:2]
    except Exception:
        return ""


def user_id(request):
    func = conf.get("USER_ID_FUNC")
    try:
        if func:
            uid = import_string(func)(request)
        else:
            user = getattr(request, "user", None)
            uid = user.pk if user is not None and user.is_authenticated else None
    except Exception:
        log.exception("svederlytics USER_ID_FUNC failed")
        uid = None
    return "" if uid is None else str(uid)[:64]


def read_vid(request):
    vid = request.COOKIES.get(conf.get("COOKIE_NAME"), "")
    return vid if VID_RE.match(vid) else ""


def new_vid():
    return secrets.token_urlsafe(16)[:22]


def referrer_host(request):
    ref = request.META.get("HTTP_REFERER", "")
    if not ref:
        return ""
    try:
        host = (urlsplit(ref).hostname or "").lower()
    except ValueError:
        return ""
    if host and host == request.get_host().split(":")[0].lower():
        return ""  # an internal click is not a referrer
    return host[:255]


def utm(request):
    q = parse_qs(request.META.get("QUERY_STRING", ""))
    return {k: (q.get(k, [""])[0])[:100] for k in ("utm_source", "utm_medium", "utm_campaign")}


TOKENISH = re.compile(r"^[A-Za-z0-9_-]+$")


def _secretish(seg, n):
    return len(seg) >= n and TOKENISH.match(seg) and any(c.isdigit() for c in seg) and any(c.isalpha() for c in seg)


def clean_path(path):
    """Never store a secret from the URL: long token-like segments become :token, then PATH_MASKS apply."""
    n = conf.get("MASK_TOKEN_MIN")
    path = "/".join(":token" if _secretish(s, n) else s for s in (path or "/").split("/"))
    for rx, repl in conf.get("PATH_MASKS"):
        path = re.sub(rx, repl, path)
    return path[:500]


def visitor_and_session(request, vid, path, now=None, create=True):
    """Find or make the visitor and the open session. Returns (visitor, session) or (None, None)."""
    now = now or timezone.now()
    uid = user_id(request)
    visitor = Visitor.objects.filter(vid=vid).first()
    if visitor is None:
        if not create:
            return None, None
        visitor, _ = Visitor.objects.get_or_create(vid=vid, defaults={"first_seen": now, "last_seen": now, "user_id": uid})
    upd = {"last_seen": now}
    if uid and visitor.user_id != uid:
        upd["user_id"] = uid  # a login ties the browser to the site's own user
    Visitor.objects.filter(pk=visitor.pk).update(**upd)
    gap = now - timedelta(minutes=conf.get("SESSION_GAP_MIN"))
    session = visitor.sessions.filter(last_seen__gte=gap).order_by("-last_seen").first()
    if session is None:
        if not create:
            return visitor, None
        info = ua.parse(request.META.get("HTTP_USER_AGENT", ""))
        session = Session.objects.create(
            visitor=visitor, started=now, last_seen=now, entry_path=path, current_path=path,
            referrer=referrer_host(request), country=country(client_ip(request)),
            browser=info["browser"], os=info["os"], device=info["device"], is_bot=info["is_bot"],
            **utm(request))
    return visitor, session
