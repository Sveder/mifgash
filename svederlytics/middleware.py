"""Records one page view per HTML document response. Fails open: an error here never breaks the page."""
import logging

from django.db.models import F
from django.utils import timezone

from . import conf, record
from .models import Hit, Session

log = logging.getLogger("svederlytics")


def _should_record(request, response):
    if request.method != "GET":
        return False
    path = request.path
    if any(path.startswith(p) for p in conf.get("EXCLUDE_PREFIXES")):
        return False
    if "text/html" not in response.get("Content-Type", ""):
        return False
    if response.status_code in (301, 302, 303, 307, 308, 304) or response.streaming:
        return False
    meta = request.META
    if meta.get("HTTP_SEC_FETCH_DEST", "document") != "document":
        return False
    if "prefetch" in (meta.get("HTTP_SEC_PURPOSE", "") + meta.get("HTTP_PURPOSE", "")).lower():
        return False
    if meta.get("HTTP_X_REQUESTED_WITH") == "XMLHttpRequest":
        return False
    if conf.get("RESPECT_DNT") and meta.get("HTTP_DNT") == "1":
        return False
    user = getattr(request, "user", None)
    if conf.get("SKIP_STAFF") and user is not None and getattr(user, "is_staff", False):
        return False
    return True


class AnalyticsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            if _should_record(request, response):
                self._record(request, response)
        except Exception:
            log.exception("svederlytics: page view not recorded")
        return response

    def _record(self, request, response):
        vid = record.read_vid(request)
        if not vid:
            vid = record.new_vid()
            response.set_cookie(conf.get("COOKIE_NAME"), vid, max_age=conf.get("COOKIE_AGE"),
                                httponly=True, samesite="Lax", secure=request.is_secure())
        now = timezone.now()
        path = record.clean_path(request.path)
        _, session = record.visitor_and_session(request, vid, path, now)
        Hit.objects.create(session=session, ts=now, kind=Hit.PAGE, path=path, status=response.status_code)
        Session.objects.filter(pk=session.pk).update(
            last_seen=now, current_path=path, pageviews=F("pageviews") + 1)
