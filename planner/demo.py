"""The demo gate (T157, security review M1). New hackathon work (1/11/2026).

A demo endpoint (demo reset, demo links, the demo pages, the Facebook stub import) opens only when
BOTH are true:
  1. the server runs with MIFGASH_DEMO=1, and
  2. the request carries the demo admin token MIFGASH_DEMO_TOKEN: the header X-Mifgash-Demo-Token,
     or the cookie mifgash_demo. A browser sets the cookie once with ?demo_token=<token>.
A public deploy runs with MIFGASH_DEMO unset, so every demo endpoint is a 404 there.
"""
import hmac

from django.conf import settings

HEADER = "X-Mifgash-Demo-Token"
COOKIE = "mifgash_demo"


def given_token(request):
    return (request.headers.get(HEADER) or request.GET.get("demo_token")
            or request.COOKIES.get(COOKIE) or "")


def allowed(request):
    """True only with MIFGASH_DEMO=1 and the right demo admin token on this request."""
    token = settings.DEMO_TOKEN
    if not settings.DEMO or not token:
        return False
    return hmac.compare_digest(given_token(request).encode(), token.encode())


def remember(request, response):
    """A page opened with ?demo_token=<token> keeps the token in a cookie for the next pages."""
    if request.GET.get("demo_token") and allowed(request):
        response.set_cookie(COOKIE, settings.DEMO_TOKEN, httponly=True, samesite="Strict",
                            secure=request.is_secure())
    return response
