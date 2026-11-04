"""F8c (T262): read-only staff ops page /ops/ and its login /ops/login/.

One page, five tables (people, plans, offers, outings, the last 200 log rows), newest first, one
search box (?q=) that filters all five. Staff only (Django auth, is_staff); everyone else goes to
/ops/login/. Emails are masked (a***@example.com). Edits happen in the Django admin at /ops/admin/.
"""
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.views import LoginView
from django.db.models import Count, Min, Q
from django.shortcuts import render

from . import ratelimit
from .models import AgentMessage, Offer, Person, Plan

LOGIN_URL = "/ops/login/"
LOGIN_RATE_IP = (10, 600)  # 10 login posts per 10 minutes per IP
ROWS = 200


def mask_email(email):
    """'alice@example.com' -> 'a***@example.com'. Empty stays empty."""
    if not email or "@" not in email:
        return ""
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


def _one_line(payload, limit=140):
    text = payload if isinstance(payload, str) else ", ".join(f"{k}={v}" for k, v in (payload or {}).items())
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _plan_q(q, prefix=""):
    f = (Q(**{f"{prefix}owner__handle__icontains": q}) | Q(**{f"{prefix}owner__name__icontains": q})
         | Q(**{f"{prefix}kind__icontains": q}) | Q(**{f"{prefix}status__icontains": q})
         | Q(**{f"{prefix}area__name__icontains": q}) | Q(**{f"{prefix}raw_text__icontains": q}))
    if q.isdigit():
        f |= Q(**{f"{prefix}pk": int(q)})
    return f


@staff_member_required(login_url=LOGIN_URL)
def ops(request):
    q = (request.GET.get("q") or "").strip()[:80]

    people = Person.objects.annotate(keys=Count("agent_keys", distinct=True),
                                      first_seen=Min("magic_links__created")).order_by("-pk")
    plans = Plan.objects.select_related("owner", "area").order_by("-pk")
    offers = Offer.objects.select_related("plan", "person").order_by("-pk")
    outings = Plan.objects.filter(status="final").select_related("owner", "area", "chosen").order_by("-date", "-pk")
    log = AgentMessage.objects.order_by("-pk")
    if q:
        people = people.filter(Q(handle__icontains=q) | Q(name__icontains=q) | Q(city__icontains=q))
        plans = plans.filter(_plan_q(q))
        offers = offers.filter(Q(person__handle__icontains=q) | Q(person__name__icontains=q)
                               | Q(status__icontains=q) | _plan_q(q, "plan__"))
        outings = outings.filter(_plan_q(q) | Q(chosen__name__icontains=q))
        lf = (Q(sender__icontains=q) | Q(receiver__icontains=q) | Q(type__icontains=q)
              | Q(payload__icontains=q))
        if q.isdigit():
            lf |= Q(plan_id=int(q))
        log = log.filter(lf)

    people = list(people[:ROWS])
    for p in people:
        p.email_masked = mask_email(p.email)
    log = list(log[:ROWS])
    for m in log:
        m.line = _one_line(m.payload)
    ctx = {"q": q, "people": people, "plans": list(plans[:ROWS]), "offers": list(offers[:ROWS]),
           "outings": list(outings[:ROWS]), "log": log, "rows": ROWS}
    return render(request, "planner/ops/ops.html", ctx)


class OpsLogin(LoginView):
    """Django LoginView with a plain template and 10 POSTs per 10 minutes per IP."""
    template_name = "planner/ops/login.html"
    redirect_authenticated_user = False

    def post(self, request, *args, **kwargs):
        slow = ratelimit.check(request, "ops-login", ip=LOGIN_RATE_IP)
        if slow:
            return slow
        return super().post(request, *args, **kwargs)

    def get_default_redirect_url(self):
        return "/ops/"


def limit_admin_login(site):
    """T278: the Django admin login (/ops/admin/login/) shares the 'ops-login' cap with /ops/login/."""
    if getattr(site.login, "rate_limited", False):
        return
    original = site.login

    def login(request, extra_context=None):
        if request.method == "POST":
            slow = ratelimit.check(request, "ops-login", ip=LOGIN_RATE_IP)
            if slow:
                return slow
        return original(request, extra_context)

    login.rate_limited = True
    site.login = login
