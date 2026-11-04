"""Simple fixed-window rate limits per client IP and per agent key (go/no-go review, 1/11/2026).

The counters live in the Django cache (local memory by default). The public deploy runs ONE
gunicorn worker with threads, so all requests share one counter. A limit hit is HTTP 429 JSON
with retry_after_s. MIFGASH_RATE_LIMITS=0 turns every limit off (the test suite does that).
"""
import functools
import time

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse


def client_ip(request):
    """REMOTE_ADDR, or the X-Real-IP header when a trusted local proxy (nginx) sets it."""
    if settings.TRUST_PROXY and request.META.get("REMOTE_ADDR") in ("127.0.0.1", "::1"):
        return request.headers.get("X-Real-IP") or request.META.get("REMOTE_ADDR", "")
    return request.META.get("REMOTE_ADDR", "")


def hit(bucket, limit, seconds):
    """Count one request in this window. Returns seconds to wait, or 0 when under the limit."""
    window = int(time.time() // seconds)
    key = f"rl:{bucket}:{window}"
    cache.add(key, 0, seconds + 5)
    try:
        n = cache.incr(key)
    except ValueError:
        cache.set(key, 1, seconds + 5)
        n = 1
    return int(seconds - time.time() % seconds) + 1 if n > limit else 0


def too_many(wait):
    r = JsonResponse({"error": "too many requests, slow down", "retry_after_s": wait}, status=429)
    r["Retry-After"] = str(wait)
    return r


def wait_for(request, scope, ip=None):
    """Count one request against the per-IP limit. Returns seconds to wait, or 0 (T317: for HTML pages)."""
    if not settings.RATE_LIMITS or not ip:
        return 0
    return hit(f"{scope}:ip:{client_ip(request)}", *ip)


def check(request, scope, ip=None, key=None):
    """ip / key: (limit, seconds). Returns a 429 response or None."""
    if not settings.RATE_LIMITS:
        return None
    if ip:
        wait = hit(f"{scope}:ip:{client_ip(request)}", *ip)
        if wait:
            return too_many(wait)
    person = getattr(request, "person", None)
    if key and person is not None:
        wait = hit(f"{scope}:p:{person.pk}", *key)
        if wait:
            return too_many(wait)
    return None


def limit(scope, ip=None, key=None, methods=None):
    """Decorator. Put it under @agent_required so the per-key limit knows the person."""
    def wrap(view):
        @functools.wraps(view)
        def inner(request, *args, **kwargs):
            if methods is None or request.method in methods:
                r = check(request, scope, ip=ip, key=key)
                if r:
                    return r
            return view(request, *args, **kwargs)
        return inner
    return wrap
