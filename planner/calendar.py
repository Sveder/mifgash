"""Calendar invite for a final outing (brief item h). New hackathon work (29/10/2026).

Two links per person on the outing: a signed .ics file and a Google Calendar 'add event' link.
Nothing is written to any real calendar: the person's own calendar app fetches the file.
"""
import datetime as dt
import hashlib
import hmac
from urllib.parse import quote, urlencode

from django.conf import settings
from django.urls import reverse

from . import messages

TZID = "America/Los_Angeles"
LENGTH = dt.timedelta(minutes=90)

# US Pacific: PDT from the second Sunday of March 02:00, PST from the first Sunday of November 02:00.
VTIMEZONE = [
    "BEGIN:VTIMEZONE", f"TZID:{TZID}",
    "BEGIN:DAYLIGHT", "DTSTART:19700308T020000", "TZOFFSETFROM:-0800", "TZOFFSETTO:-0700", "TZNAME:PDT",
    "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU", "END:DAYLIGHT",
    "BEGIN:STANDARD", "DTSTART:19701101T020000", "TZOFFSETFROM:-0700", "TZOFFSETTO:-0800", "TZNAME:PST",
    "RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU", "END:STANDARD",
    "END:VTIMEZONE",
]


def sign(plan_id, person_id):
    msg = f"ics:{plan_id}:{person_id}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()[:20]


def check(plan_id, person_id, sig):
    return hmac.compare_digest(sign(plan_id, person_id), str(sig or ""))


def short_token(plan_id, person_id):
    """'120-7-<10 hex>': the short calendar link token for one side of one plan (T82)."""
    msg = f"cal:{plan_id}:{person_id}".encode()
    sig = hmac.new(settings.SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()[:10]
    return f"{plan_id}-{person_id}-{sig}"


def read_short(token):
    """(plan_id, person_id) for a valid short token, else None."""
    parts = str(token or "").split("-")
    if len(parts) != 3 or not parts[0].isdigit() or not parts[1].isdigit():
        return None
    plan_id, person_id = int(parts[0]), int(parts[1])
    if not hmac.compare_digest(short_token(plan_id, person_id), token):
        return None
    return plan_id, person_id


def base_url():
    return settings.PUBLIC_URL.rstrip("/")


LOOPBACK = {"localhost", "127.0.0.1", "[::1]", "::1"}


def public_base(request):
    """The base URL for a link a person opens. An agent on the same server calls localhost, and
    a localhost link does not open on the owner's phone, so a loopback request gets PUBLIC_URL."""
    if request.get_host().rsplit(":", 1)[0] in LOOPBACK:
        return base_url()
    return request.build_absolute_uri("/").rstrip("/")


def start_end(plan):
    start = dt.datetime.combine(plan.date, plan.exact_time)
    return start, start + LENGTH


def details(plan, person):
    """Title, location and description for one side. The title names the OTHER people."""
    people = [plan.owner] + plan.guests()
    others = [p for p in people if p.pk != person.pk] or [plan.owner]
    place = plan.chosen
    address = (place.address or place.area.name) if place else plan.area.name
    title = f"{plan.title} with {messages.names(others)}"  # T321: one title for the card and the .ics
    location = f"{place.name}, {address}" if place else address
    lines = [f"When: {messages.us_day(plan.date)}, {messages.clock(plan.exact_time)}"] if plan.exact_time else []
    lines += [f"Map: https://maps.google.com/?q={quote(address)}",
             f"Parking: {(place.parking if place else '') or 'Street parking'}",
             "Planned by Mifgash."]
    if plan.kind == "group_dinner":  # G2 (T228): the invite names every person at the table
        lines.insert(0, f"Group dinner for {len(people)}: {messages.names(people)}")
    return title, location, "\n".join(lines)


def links(plan, person, base=None):
    """{ics_url, google_calendar_url, google_calendar_short, ics_short} for a final plan, or {}
    for any other status. The short links fit in a chat line; /c/<token> redirects to Google."""
    if plan.status != "final" or not plan.exact_time:
        return {}
    base = (base or base_url()).rstrip("/")
    path = reverse("outing_ics", args=[plan.uid, sign(plan.pk, person.pk)])
    title, location, text = details(plan, person)
    start, end = start_end(plan)
    fmt = "%Y%m%dT%H%M%S"
    google = "https://calendar.google.com/calendar/render?" + urlencode({
        "action": "TEMPLATE", "text": title, "dates": f"{start.strftime(fmt)}/{end.strftime(fmt)}",
        "ctz": TZID, "location": location, "details": text})
    short = f"{base}{reverse('calendar_short', args=[short_token(plan.pk, person.pk)])}"
    return {"ics_url": f"{base}{path}?for={person.pk}", "google_calendar_url": google,
            "google_calendar_short": short, "ics_short": short + ".ics"}


def escape(value):
    return (str(value).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def fold(line):
    """RFC 5545: lines of 75 octets at most, a continuation line starts with one space."""
    out, raw = [], line.encode()
    while len(raw) > 75:
        cut = 75 if not out else 74
        while cut > 0 and (raw[cut] & 0xC0) == 0x80:  # do not split a UTF-8 character
            cut -= 1
        out.append(raw[:cut].decode())
        raw = raw[cut:]
    out.append(raw.decode())
    return "\r\n ".join(out)


def ics(plan, person, now=None):
    title, location, text = details(plan, person)
    start, end = start_end(plan)
    stamp = (now or dt.datetime.now(dt.timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    fmt = "%Y%m%dT%H%M%S"
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Mifgash//Outing invite//EN", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", *VTIMEZONE,
             "BEGIN:VEVENT", f"UID:mifgash-{plan.pk}@mifgash", f"DTSTAMP:{stamp}",
             f"DTSTART;TZID={TZID}:{start.strftime(fmt)}", f"DTEND;TZID={TZID}:{end.strftime(fmt)}",
             f"SUMMARY:{escape(title)}", f"LOCATION:{escape(location)}", f"DESCRIPTION:{escape(text)}",
             "END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(fold(x) for x in lines) + "\r\n"
