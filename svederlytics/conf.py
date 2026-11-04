"""Settings for svederlytics. Every name has a default; set SVEDERLYTICS = {...} in settings.py to change one."""
from django.conf import settings

DEFAULTS = {
    # Paths that the middleware never records (prefix match).
    "EXCLUDE_PREFIXES": ("/admin/", "/ops/", "/static/", "/media/", "/_sl/", "/favicon.ico", "/robots.txt",
                         "/sitemap.xml", "/.well-known/", "/apple-touch-icon"),
    # Visitor cookie: a random ID, so the same visitor keeps one ID across days.
    "COOKIE_NAME": "sl_vid",
    "COOKIE_AGE": 2 * 365 * 24 * 3600,
    # A new session starts after this many minutes with no hit.
    "SESSION_GAP_MIN": 30,
    # "Live now" = a hit or a heartbeat in the last N minutes.
    "LIVE_MIN": 5,
    # Collect endpoint limits.
    "MAX_BODY": 2048,
    "RATE_PER_MIN": 60,
    "MAX_PROPS": 10,
    # Extra origins allowed to post events (the site's own host is always allowed).
    "ALLOWED_ORIGINS": (),
    # Read the client IP from X-Real-IP / X-Forwarded-For (only behind your own proxy).
    "TRUST_PROXY": False,
    # Path to a GeoLite2-Country.mmdb file. Empty = no country.
    "GEOIP_PATH": "",
    # Honour the Do Not Track header.
    "RESPECT_DNT": True,
    # Do not record staff users (request.user.is_staff).
    "SKIP_STAFF": True,
    # Path segments that look like a secret (long random tokens in magic links) become ":token".
    "MASK_TOKEN_MIN": 20,
    # Extra (regex, replacement) pairs applied to every stored path, e.g. (r"^/d/[^/]+/", "/d/:token/").
    "PATH_MASKS": (),
    # Dotted path to f(request) -> str | None, the site's own user ID. Default: request.user.pk.
    "USER_ID_FUNC": "",
}


def get(name):
    return getattr(settings, "SVEDERLYTICS", {}).get(name, DEFAULTS[name])
