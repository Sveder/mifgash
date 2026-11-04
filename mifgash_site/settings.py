"""Settings for the Mifgash hackathon POC (Meta Global AI Developer Hackathon, Oct-Nov 2026)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Secrets live in .env (chmod 600, gitignored). Real environment variables win.
from .envfile import load as _load_env  # noqa: E402
_load_env(BASE_DIR / ".env")

# The product name. Change it here and nowhere else.
PRODUCT_NAME = os.environ.get("MIFGASH_PRODUCT_NAME", "Mifgash")
# T283: the public source repo (one squashed commit; the dated history stays private)
REPO_URL = os.environ.get("MIFGASH_REPO_URL", "https://github.com/Sveder/mifgash")

DEV_SECRET_KEY = "dev-only-not-secret"
SECRET_KEY = os.environ.get("MIFGASH_SECRET_KEY", DEV_SECRET_KEY)
# DEBUG is OFF unless MIFGASH_DEBUG=1 (T158, security review H1).
DEBUG = os.environ.get("MIFGASH_DEBUG", "0") == "1"
if not DEBUG and (SECRET_KEY == DEV_SECRET_KEY or len(SECRET_KEY) < 32):
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured(
        "MIFGASH_SECRET_KEY is missing, too short or the dev value, and DEBUG is off. "
        "Set a random MIFGASH_SECRET_KEY of 32+ characters in .env (or MIFGASH_DEBUG=1 on your own machine).")
# Demo endpoints (planner/demo.py) need MIFGASH_DEMO=1 AND the demo admin token MIFGASH_DEMO_TOKEN
# on each request. Never set MIFGASH_DEMO on a host that the internet can reach (T157).
DEMO = os.environ.get("MIFGASH_DEMO", "0") == "1"
# T258 (F6c): Mifgash sets the exact time itself when both sides are in. 0 = the old two-step
# time round (kept for the tests of that round and for a quick fallback).
AUTO_TIME = os.environ.get("MIFGASH_AUTO_TIME", "1") != "0"
DEMO_TOKEN = os.environ.get("MIFGASH_DEMO_TOKEN", "") if DEMO else ""
# Comma list, for example "mifgash.example.com". With DEBUG on and no list: localhost names only.
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("MIFGASH_ALLOWED_HOSTS", "").split(",") if h.strip()] \
    or (["localhost", "127.0.0.1", "[::1]", "testserver"] if DEBUG else [])
CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get("MIFGASH_TRUSTED_ORIGINS", "").split(",") if o]

# Behind an https proxy (nginx + certbot): secure cookies, HSTS, the proxy's scheme header.
HTTPS = os.environ.get("MIFGASH_HTTPS", "0") == "1"
if HTTPS:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.environ.get("MIFGASH_HSTS_SECONDS", "31536000"))
    SECURE_SSL_REDIRECT = False  # nginx redirects http to https
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "SAMEORIGIN"  # the same value as the nginx default header, so no conflict
# Rate limits (planner/ratelimit.py). TRUST_PROXY: read X-Real-IP from nginx on localhost.
RATE_LIMITS = os.environ.get("MIFGASH_RATE_LIMITS", "1") == "1"
RATE_API_PER_MIN = int(os.environ.get("MIFGASH_RATE_API_PER_MIN", "240"))
# T249: the longest long poll on GET /api/v1/events/?wait=S, in seconds.
# T256 (F4b): public friend search is off; add a friend by exact handle. zz_ test people may still search.
FRIEND_SEARCH = os.environ.get("MIFGASH_SEARCH", "0") == "1"
EVENTS_WAIT_MAX = float(os.environ.get("MIFGASH_EVENTS_WAIT_MAX", "25"))
TRUST_PROXY = os.environ.get("MIFGASH_TRUST_PROXY", "0") == "1"

INSTALLED_APPS = [
    "django.contrib.admin",  # svederlytics: staff login for the analytics dashboard
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "planner",
    "svederlytics",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "svederlytics.middleware.AnalyticsMiddleware",
]
# svederlytics (vendored app, svederlytics/README.md): page views, events, live visitors.
# Dashboard /_sl/dashboard/ for staff users (manage.py createsuperuser). MIFGASH_ANALYTICS=0 turns recording off.
SVEDERLYTICS = {
    "TRUST_PROXY": TRUST_PROXY,
    "GEOIP_PATH": os.environ.get("MIFGASH_GEOIP_PATH", ""),
    "USER_ID_FUNC": "planner.analytics.person_handle",
    # Secret links: keep the route, drop the token (also short ones the generic rule misses).
    "PATH_MASKS": (
        (r"^/(c|h|open|i)/[^/]+", r"/\1/:token"),
        (r"^/d/(?!answer/|group/|finalize/|friend/)[^/]+/", "/d/:token/"),
        (r"/invite-[^/]+\.ics$", "/invite-:sig.ics"),
    ),
}
if os.environ.get("MIFGASH_ANALYTICS", "1") == "0":
    MIDDLEWARE.remove("svederlytics.middleware.AnalyticsMiddleware")
ROOT_URLCONF = "mifgash_site.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],  # admin/base_site.html: Ops + Analytics links
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "planner.context.product",
    ]},
}]
WSGI_APPLICATION = "mifgash_site.wsgi.application"
# PostgreSQL only, on localhost. The role and password come from .env.
DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": os.environ.get("MIFGASH_DB_NAME", "mifgash"),
    "USER": os.environ.get("MIFGASH_DB_USER", "mifgash"),
    "PASSWORD": os.environ.get("MIFGASH_DB_PASSWORD", ""),
    "HOST": os.environ.get("MIFGASH_DB_HOST", "127.0.0.1"),
    "PORT": os.environ.get("MIFGASH_DB_PORT", "5432"),
    # One test database per checkout, so parallel worktrees do not drop each other's test DB.
    "TEST": {"NAME": os.environ.get("MIFGASH_TEST_DB_NAME")
             or "test_mifgash_" + __import__("hashlib").sha1(str(BASE_DIR).encode()).hexdigest()[:8]},
}}

# Encryption at rest (planner/crypto.py). FIELD_KEYS: Fernet keys, newest first. HASH_KEY: HMAC key.
FIELD_KEYS = os.environ.get("MIFGASH_FIELD_KEYS", "")
HASH_KEY = os.environ.get("MIFGASH_HASH_KEY", "")
SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/Los_Angeles"
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = os.environ.get("MIFGASH_STATIC_ROOT") or str(BASE_DIR / "staticfiles")
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- LLM adapter (planner/llm.py). One setting switches the backend. ---
# claude = Claude through the local `claude -p` CLI (no API key on this box)
# meta   = Muse Spark Open on Baseten (OpenAI-compatible), needs BASETEN_API_KEY
# stub   = deterministic keyword parser, no network
LLM_BACKEND = os.environ.get("MIFGASH_LLM_BACKEND", "claude")
CLAUDE_MODEL = os.environ.get("MIFGASH_CLAUDE_MODEL", "claude-sonnet-5-5")
CLAUDE_CLI = os.environ.get("MIFGASH_CLAUDE_CLI", "claude")
# MIFGASH_META_ENV names an optional env file outside the repo with BASETEN_API_KEY,
# BASETEN_BASE_URL and BASETEN_MODEL. The key never goes into the repo.
if os.environ.get("MIFGASH_META_ENV"):
    _load_env(os.environ["MIFGASH_META_ENV"])
META_BASE_URL = os.environ.get("MIFGASH_META_BASE_URL",
                               os.environ.get("BASETEN_BASE_URL", "https://inference.baseten.co/v1"))
META_MODEL = os.environ.get("MIFGASH_META_MODEL",
                            os.environ.get("BASETEN_MODEL", "meta-models/muse-spark-open-1026"))
META_API_KEY = os.environ.get("BASETEN_API_KEY", "")
META_MAX_TOKENS = int(os.environ.get("MIFGASH_META_MAX_TOKENS", "4000"))
LLM_TIMEOUT_S = int(os.environ.get("MIFGASH_LLM_TIMEOUT", "60"))

# --- Matching rules (planner/engine.py) ---
OFFER_TTL_MINUTES = int(os.environ.get("MIFGASH_OFFER_TTL_MINUTES", "180"))
DEFAULT_RADIUS_KM = 3.0

# Base URL for links the server sends with no request at hand (webhook payloads: the calendar invite).
PUBLIC_URL = os.environ.get("MIFGASH_PUBLIC_URL", "http://localhost:8095")

# M11a (T171): the Facebook app id for 'Import from Facebook'. Empty = the button shows disabled.
# The real Facebook Login (OAuth callback, user_friends) comes later; see docs/FACEBOOK.md.
FB_APP_ID = os.environ.get("MIFGASH_FB_APP_ID", "").strip()

# Webhook push to agents (planner/push.py). Tries: 1 + number of delays.
PUSH_TIMEOUT_S = 5
PUSH_RETRY_DELAYS = (2, 4, 8)
PUSH_SYNC = os.environ.get("MIFGASH_PUSH_SYNC", "0") == "1"
# M7b (T179): 1 = the quick-demo friend answers inside the visitor's request (tests); 0 = a background thread.
SANDBOX_SYNC = os.environ.get("MIFGASH_SANDBOX_SYNC", "0") == "1"
# A webhook must be a public https URL. Hosts in MIFGASH_WEBHOOK_ALLOW (comma list) may use http and a
# local address, but only when MIFGASH_DEMO=1 (a demo agent on this machine). See planner/push.py check_url.
WEBHOOK_ALLOW = tuple(h.strip().lower() for h in os.environ.get("MIFGASH_WEBHOOK_ALLOW", "").split(",") if h.strip())
# Exact webhook URLs (comma list) allowed past the public-https guard also without MIFGASH_DEMO, for
# one agent on this machine, for example an OpenClaw gateway at http://127.0.0.1:18789/hooks/wake (T98).
# Email fallback (planner/fallback.py, T98): an event that no webhook carried and no agent poll read
# for this many hours goes to the human by email. The send is a stub that only logs until a mail route exists.
EMAIL_FALLBACK_HOURS = float(os.environ.get("MIFGASH_EMAIL_FALLBACK_HOURS", "24"))
# Mail route (M10, T170): "stub" (default) writes a log row and sends nothing; "ses" sends through
# AWS SES (boto3 sesv2) from MIFGASH_SES_FROM. The AWS key comes from the usual AWS_* env vars.
EMAIL_BACKEND_NAME = os.environ.get("MIFGASH_EMAIL", "stub").strip().lower() or "stub"
SES_FROM = os.environ.get("MIFGASH_SES_FROM", "").strip()
SES_REGION = os.environ.get("MIFGASH_SES_REGION", os.environ.get("AWS_DEFAULT_REGION", "eu-central-1"))
LOCAL_HOOKS = tuple(u.strip() for u in os.environ.get("MIFGASH_LOCAL_HOOKS", "").split(",") if u.strip())
