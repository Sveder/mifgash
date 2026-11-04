"""Email fallback for a person whose agent does not hear about events. New hackathon work (29/10/2026, T98).

Layer 3 of the agent wake-up: (1) a webhook push, (2) the agent's own polling job on
GET /api/v1/events/, (3) this. An event goes to the human by email when all of these hold:
- the person has an agent, no webhook URL, and an email address;
- the event is older than EMAIL_FALLBACK_HOURS (24);
- the agent did not poll the events since the event was made (Person.last_polled_at).
One email per person per sweep lists every such event. Each event is handled once
(AgentEvent.fallback_at), also when it needs no email, so the sweep stays small.

Mail route (M10, T170): settings.EMAIL_BACKEND_NAME (env MIFGASH_EMAIL). "stub" (default) writes one
log line and one AgentMessage row (type email_stub, no address in it) and sends nothing. "ses" sends a
plain-text mail through AWS SES (sesv2) from MIFGASH_SES_FROM and writes a row of type email_sent; a
failed SES call falls back to the stub row. engine.tick runs sweep() every minute.
"""
import datetime as dt
import logging

from django.conf import settings
from django.utils import timezone

from .messages import fmt_when
from .models import AgentEvent, AgentMessage

log = logging.getLogger(__name__)
SENDER = "mifgash:email"


def event_line(e):
    text = str((e.payload or {}).get("text") or "").strip()
    t = timezone.localtime(e.created)
    return f"- {text or e.event} ({fmt_when(t.date(), t.time())})"


def compose(person, events):
    """(subject, body) in plain words."""
    n = len(events)
    subject = f"Mifgash: {n} update{'s' if n != 1 else ''} your agent did not pick up"
    body = "\n".join([
        f"Hi {person.name},",
        "",
        f"Your agent did not check Mifgash for {settings.EMAIL_FALLBACK_HOURS:g} hours, so we write to you.",
        "",
        *[event_line(e) for e in events],
        "",
        f"Open your dashboard: {settings.PUBLIC_URL.rstrip('/')}/d/ (ask your agent for a login link).",
        "Tell your agent to run 'mif.py inbox', or to make its 2-hour polling job again.",
    ])
    return subject, body


def email_live():
    """True when a real mail route is set: MIFGASH_EMAIL=ses and a From address."""
    return settings.EMAIL_BACKEND_NAME == "ses" and bool(settings.SES_FROM)


def ses_client():
    import boto3
    return boto3.client("sesv2", region_name=settings.SES_REGION)


def deliver(to, subject, body):
    """Send one plain-text mail. True only when SES took it. Never raises."""
    if not (email_live() and to and "@" in to):
        return False
    try:
        ses_client().send_email(
            FromEmailAddress=settings.SES_FROM,
            Destination={"ToAddresses": [to]},
            Content={"Simple": {"Subject": {"Data": subject, "Charset": "UTF-8"},
                                "Body": {"Text": {"Data": body, "Charset": "UTF-8"}}}})
        return True
    except Exception as exc:  # botocore ClientError, no credentials, network
        log.warning("SES send failed: %s", type(exc).__name__)
        return False


def send_email(person, subject, body, events):
    """The fallback email. One log line and one AgentMessage row (email_sent, or email_stub when
    no mail route is set or SES refused). No address in the row. Returns True when sent."""
    sent = deliver(person.email, subject, body)
    log.info("email fallback (%s): to %s, %s", "sent" if sent else "not sent", person.handle, subject)
    text = (f"Your agent did not check in for {settings.EMAIL_FALLBACK_HOURS:g} hours. "
            + ("We emailed you the updates." if sent else
               "An email to you is written but not sent: no mail route yet."))
    AgentMessage.objects.create(
        plan=events[-1].plan, sender=SENDER, receiver=f"human:{person.handle}",
        type="email_sent" if sent else "email_stub",
        payload={"plan_id": events[-1].plan_id, "event_ids": [e.pk for e in events], "subject": subject,
                 "lines": len(body.splitlines()), "text": text})
    return sent


def send_link_email(person, link_url, valid_for="24 hours"):
    """M5 (T165): a dashboard login link by email. One log line and one AgentMessage row
    (email_sent or email_stub; no address and no link in it). Returns True when sent."""
    name = settings.PRODUCT_NAME
    subject = f"Your {name} dashboard link"
    body = "\n".join([
        f"Hi {person.name},", "",
        f"Somebody asked for a {name} dashboard link for this address on the website.",
        f"Open your dashboard: {link_url}", "",
        f"The link works one time, for {valid_for}. If you did not ask for it, do nothing."])
    sent = deliver(person.email, subject, body)
    log.info("dashboard link email (%s): to %s", "sent" if sent else "not sent", person.handle)
    AgentMessage.objects.create(
        plan=None, sender=SENDER, receiver=f"human:{person.handle}",
        type="email_sent" if sent else "email_stub",
        payload={"subject": subject,
                 "text": "A dashboard link was asked for on the website. "
                         + ("We emailed it to you." if sent else
                            "The email is written but not sent: no mail route yet.")})
    return sent


def sweep(now=None):
    """Handle every event that is due. Returns the handles of the people we wrote to."""
    now = now or timezone.now()
    cutoff = now - dt.timedelta(hours=settings.EMAIL_FALLBACK_HOURS)
    due = (AgentEvent.objects.filter(fallback_at__isnull=True, created__lte=cutoff)
           .select_related("person", "plan").order_by("person_id", "pk"))
    by_person = {}
    for e in due:
        by_person.setdefault(e.person_id, (e.person, []))[1].append(e)
    wrote = []
    for person, events in by_person.values():
        polled = person.last_polled_at
        unread = [e for e in events if not (polled and polled >= e.created)]
        if unread and person.has_agent and not person.webhook_url and person.email:
            send_email(person, *compose(person, unread), unread)
            wrote.append(person.handle)
        AgentEvent.objects.filter(pk__in=[e.pk for e in events]).update(fallback_at=now)
    return wrote
