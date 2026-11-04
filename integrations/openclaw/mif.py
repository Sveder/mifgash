#!/usr/bin/env python3
"""Mifgash agent client for OpenClaw. New hackathon work (29/10/2026).

Standard library only. Every command prints one short plain-English line for the chat;
--json prints the full API reply after it.

  mif.py signup NAME HANDLE --email EMAIL [--webhook URL --webhook-secret S --hook-format openclaw] [--home AREA]
  mif.py me                       | email ADDRESS  (the human's email, for the login link)
  mif.py hook URL [--format openclaw|mifgash]   | hook off    (where Mifgash wakes this agent)
  mif.py link                     (a fresh one-time Mifgash dashboard link for the human)
  mif.py friends [list]           | friends search Q | friends add HANDLE | friends accept HANDLE | friends import
  mif.py open "free text"         (or --date YYYY-MM-DD --part lunch --kind food --area NAME)
  mif.py open-list                | cancel ID
  mif.py proposals
  mif.py respond ID accept|decline [--choice PLACE_ID] [--note TEXT]
  mif.py finalize PLAN_ID --time HH:MM [--place PLACE_ID]
  mif.py outings [PLAN_ID]        (what is set; one outing also prints the calendar links)
  mif.py inbox [--wait N]         (what is new since the last call; prints nothing when nothing is new;
                                   --wait N holds up to N s, max 25, and answers when an event arrives)

The server URL comes from --url, else MIFGASH_URL, else https://mifgash.sveder.com.
The key comes from MIFGASH_KEY, else the key file (--key-file, default ~/.mifgash/key).
signup writes the key file with mode 600. The key is never printed.
The webhook secret (for the openclaw format: the gateway hooks.token) comes from --webhook-secret,
else MIFGASH_HOOK_TOKEN, so it need not be on the command line.
"""
import argparse
import datetime
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_URL = "https://mifgash.sveder.com"
DEFAULT_KEY_FILE = os.path.expanduser("~/.mifgash/key")


class UsageError(Exception):
    """A problem on this side: no key, a missing argument."""


class ApiError(Exception):
    def __init__(self, status, body):
        super().__init__(body.get("error") or f"HTTP {status}")
        self.status, self.body = status, body


def call(args, method, path, body=None, auth=True):
    """One API call. Returns the JSON reply; raises ApiError on an HTTP error."""
    url = args.url.rstrip("/") + "/api/v1/" + path.lstrip("/")
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if auth:
        headers["Authorization"] = "Bearer " + load_key(args)
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            reply = json.loads(e.read() or b"{}")
        except ValueError:
            reply = {}
        raise ApiError(e.code, reply)


def load_key(args):
    key = os.environ.get("MIFGASH_KEY", "").strip()
    if key:
        return key
    try:
        with open(args.key_file) as f:
            return f.read().strip()
    except FileNotFoundError:
        raise UsageError("No Mifgash key. Run 'mif.py signup' first, or set MIFGASH_KEY.")


def save_key(path, key):
    os.makedirs(os.path.dirname(path) or ".", mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(key + "\n")
    os.chmod(path, 0o600)


def short_day(iso):
    """'2026-11-01' -> 'Sun Nov 1', the same form as the server's messages (T351). Bad input comes back as is."""
    try:
        d = datetime.date.fromisoformat(iso or "")
    except ValueError:
        return iso or "day not set"
    return f"{d.strftime('%a')} {d.strftime('%b')} {d.day}"


def clock(hm):
    """'13:00' -> '1:00 PM' (T351, the server's clock form). Anything else comes back as is."""
    try:
        h, m = (int(x) for x in str(hm).split(":")[:2])
    except (TypeError, ValueError):
        return hm
    return f"{(h % 12) or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"


def when(row):
    """'lunch on Fri Oct 30', or 'kids on Fri Oct 30 (morning)' when the part adds something."""
    kind, part = row.get("kind") or "", row.get("part") or ""
    if row.get("kind_named") is False:  # no kind the person did not say: 'Fri Oct 30 morning' (T112)
        return f"{short_day(row.get('date'))} {PART_PHRASE.get(part, part)}".strip()
    tail = f" ({part})" if part and part != kind else ""
    return f"{kind} on {short_day(row.get('date'))}{tail}".strip()


PART_PHRASE = {"morning": "morning", "lunch": "at lunch", "afternoon": "afternoon", "evening": "evening"}
KIND_PHRASE = {"kids": "with the kids", "weekend": "for a weekend outing"}


def free_when(row):
    """'you are free Fri Oct 30 morning'. The kind only when the person named it and the part does
    not already say it (T112): 'you are free Sat Oct 31 morning, with the kids'."""
    part = row.get("part") or ""
    text = f"you are free {short_day(row.get('date'))} {PART_PHRASE.get(part, part)}".strip()
    kind = KIND_PHRASE.get(row.get("kind")) if row.get("kind_named", True) else None
    return f"{text}, {kind}" if kind else text


def count(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def places(rows):
    return "; ".join(f"[{p['id']}] {p['name']}" for p in rows or [])


def why_line(p):
    """T78: the model's sentence on why the proposal fits, with the model name when a model wrote it."""
    if not p.get("reason"):
        return ""
    tag = f" ({p['reason_model']})" if p.get("reason_model") else ""
    return f" Why it fits: {p['reason']}{tag}"


def respond_step(p):
    """T130: the answer commands for one proposal. inbox and proposals both print this line, so
    the agent can act from either one with no second call."""
    pid = p.get("id")
    if p.get("role") == "owner":
        return f"Ask your human. Approve: 'respond {pid} accept'. Say no: 'respond {pid} decline'."
    opts = p.get("options") or []
    if not opts:
        return f"Ask your human. Yes: 'respond {pid} accept'. No: 'respond {pid} decline'."
    return (f"Places: {places(opts)}. Ask your human. Yes: 'respond {pid} accept --choice {opts[0]['id']}' "
            f"(or another place id). No: 'respond {pid} decline'.")


def agree_step(plan_id, time, place_id=None):
    """T130: the command that agrees to a time the other side proposed (inbox, proposals, outings)."""
    cmd = f"finalize {plan_id} --time {time}" + (f" --place {place_id}" if place_id else "")
    return f"Ask your human. Agree: '{cmd}'. Or send another time."


def day_label(row, time=None):
    """'Lunch, Fri Oct 30, 1:00 PM' -- the part only when it adds something, the time when known."""
    kind, part = row.get("kind") or "", row.get("part") or ""
    if kind == "group_dinner":  # G2 (T228): an evening by definition, no '(evening)'
        kind = part = "group dinner"
    title = row.get("title")
    if title:  # T377/T388: the same title as the card and the .ics ('Dinner', 'Playdate')
        low = title.lower()
        extra = part and not time and part not in low and low not in ("dinner", "group dinner")
        head = title + (f" ({part})" if extra else "")
    else:
        head = (kind or part or "Outing").capitalize() + (f" ({part})" if part and kind and part != kind else "")
    day = short_day(row.get("date"))
    return ", ".join(x for x in (head, day, clock(time) if time else None) if x)


def outing_line(o):
    """One outing in plain words: '[12] Final: Lunch, Fri Oct 30, 1:00 PM, Place, Address. With Alex.'"""
    place = o.get("place")
    time = o.get("time")
    status = o.get("status")
    gang = o.get("in") or []
    count = f"{len(gang)} of {o.get('wanted')} in" + (f" ({', '.join(gang)})" if gang else "")
    if status == "gathering":  # T327: a group dinner fills one friend at a time
        left = max((o.get("wanted") or 0) - len(gang), 0)
        state = (f"Asking: {count}, asking more" if o.get("role") == "owner"
                 else "You are in, " + count.split(" (")[0] + (f", waiting for {left} more" if left else ""))
    elif status == "waiting_for_owner":
        who = ", ".join(o.get("who") or []) or "your friend"
        state = (f"Asking: {who} said yes, waits for your OK" if o.get("role") == "owner"
                 else f"Asking: you said yes, waiting for {who}")
        if gang and o.get("role") == "owner":  # T327: the friends who are in already
            state += f"; {count}"
    elif status == "proposed":
        by = o.get("proposed_by")
        state = "Proposed by you" if by == "you" else f"Proposed by {by or 'a friend'}"
        state += f" for {clock(o.get('proposed_time'))}"
        if o.get("you_agreed") and o.get("waiting_for"):  # G2 (T228): a group agrees one by one
            state += f", waiting for {', '.join(o['waiting_for'])}"
        time = o.get("proposed_time")
        place = o.get("proposed_place") or place
    elif status == "confirmed":
        state = "Confirmed, no exact time yet"
    elif status == "final":
        state = "Final"
    else:
        state = (status or "unknown").capitalize()
    parts = [day_label(o, time)]
    if place:
        parts += [place["name"], place.get("address") or ""]
    text = ", ".join(x for x in parts if x)
    who = ", ".join(o.get("who") or [])
    if o.get("group_size") and status != "gathering":  # G2 (T228): 'Group dinner, 4 people'
        text += f" (group of {o['group_size']})"
    line = f"[{o['plan_id']}] {state}: {text}." + (f" With {who}." if who else "")
    ask = o.get("move_ask")  # T328: a guest asked the owner to move the time of a group
    if ask and ask.get("by") == "you":
        line += f" You asked to move it to {clock(ask['time'])}."
    elif ask:
        line += f" {ask['by']} asks to move it to {clock(ask['time'])}: '{ask['approve']}' to approve."
    return line


def calendar_links(r):
    """Short links for the chat; the long Google URL only when the server is too old to give one."""
    google = r.get("google_calendar_short") or r.get("google_calendar_url", "")
    ics = r.get("ics_short") or r.get("ics_url", "")
    return f"Add to calendar: {google} .ics: {ics}"


# One function per command: (args) -> (line, reply)

EMAIL_LINE = "Mifgash needs an email for the login link. Ask your human for one, then run signup again with --email."


def cmd_signup(args):
    # F3a (T259): the email is required. Without it the human cannot log in again.
    if not (args.email or "").strip():
        raise UsageError(EMAIL_LINE)
    body = {"name": args.name, "handle": args.handle, "email": args.email.strip()}
    if args.webhook:
        body.update(webhook_url=args.webhook, webhook_secret=hook_secret(args),
                    webhook_format=args.hook_format)
    if args.home:
        body["home_area"] = args.home
    if args.invite:  # F4a (T253): a friend link from a friend; that friend is a friend at once
        body["invite"] = args.invite
    try:
        reply = call(args, "POST", "signup/", body, auth=False)
    except ApiError as e:
        if "email" in (e.body.get("needs") or []):
            return (f"Not signed up yet. {EMAIL_LINE}", e.body)
        if e.status == 409 and e.body.get("error") == "email in use":
            return ("Not signed up yet. Somebody uses this email already. Ask your human for a different one.", e.body)
        if "where" not in (e.body.get("needs") or []):
            raise
        areas = e.body.get("areas") or []
        head = "" if e.body.get("error") == "which home_area?" else f"'{args.home}' is not covered. "
        if len(areas) > 3:  # the full list: name the cities, short enough for a chat line
            areas = list(dict.fromkeys(a.split(" - ")[0] for a in areas))
        return (f"Not signed up yet. Ask your human: which area? {head}{', '.join(areas)}.", e.body)
    save_key(args.key_file, reply.pop("api_key"))
    print(poll_hint(args), file=sys.stderr)
    line = f"Signed up as @{reply['handle']}. Mifgash dashboard link (one-time): {reply['dashboard_url']}"
    if reply.get("friend"):
        line += f"\nYou and @{reply['friend']['handle']} ({reply['friend']['name']}) are friends now."
    return (line, reply)


POLL_HOURS = 2


def inbox_command(args):
    """The exact 'mif.py inbox' line for the agent's polling job: full path, and the URL and key
    file only when they differ from the defaults (T98 part 2)."""
    cmd = f"python3 {os.path.abspath(__file__)}"
    if args.url != DEFAULT_URL:
        cmd += f" --url {args.url}"
    if os.path.abspath(args.key_file) != DEFAULT_KEY_FILE:
        cmd += f" --key-file {os.path.abspath(args.key_file)}"
    return cmd + " inbox"


def poll_hint(args):
    """A note for the agent, on stderr, so the owner's chat line stays one line."""
    return (f"For the agent, not the owner: make a scheduled job now that runs '{inbox_command(args)}' "
            f"every {POLL_HOURS} hours. Send each output line to the owner as it is. "
            "No output: send nothing. A hook ('mif.py hook') only makes the news come sooner.")


def hook_secret(args):
    return args.webhook_secret or os.environ.get("MIFGASH_HOOK_TOKEN", "")


def cmd_hook(args):
    if args.url_or_off == "off":
        r = call(args, "PATCH", "me/", {"webhook_url": ""})
        return "Push is off. Mifgash keeps every event for 'mif.py inbox'.", r
    r = call(args, "PATCH", "me/", {"webhook_url": args.url_or_off, "webhook_secret": hook_secret(args),
                                    "webhook_format": args.format})
    return f"Mifgash now wakes this agent at {args.url_or_off} ({r['webhook_format']} format).", r


def cmd_me(args):
    r = call(args, "GET", "me/")
    return f"You are @{r['handle']} ({r['name']}).", r


def cmd_email(args):
    """F3a (T259): set the human's email (PATCH /me/), for the login link."""
    r = call(args, "PATCH", "me/", {"email": args.address})
    return "Email saved. Your human can log in again with it.", r


def cmd_link(args):
    r = call(args, "GET", "me/dashboard-link/")
    return f"Your Mifgash dashboard link (one-time, valid 24 hours): {r['dashboard_url']}", r


def cmd_invite(args):
    r = call(args, "GET", "me/invite-link/")
    return f"Your friend link: {r['url']}\nSend this link to a friend. Who opens it and joins becomes your friend at once.", r


def cmd_friends(args):
    if args.action in (None, "list"):
        r = call(args, "GET", "friends/")
        names = ", ".join(f"@{f['handle']}" for f in r["friends"]) or "none yet"
        line = f"{count(len(r['friends']), 'friend')}: {names}."
        if r.get("requests"):
            asked = ", ".join(f"@{f['handle']} ({f['name']})" for f in r["requests"])
            line += f" Asked to be your friends: {asked}. Ask your human, then: friends accept HANDLE."
        if r.get("sent"):
            line += f" Waiting for: {', '.join('@' + f['handle'] for f in r['sent'])}."
        return line, r
    if args.action == "search":
        if not args.value:
            raise UsageError("friends search needs a search word")
        try:
            r = call(args, "GET", "friends/search/?" + urllib.parse.urlencode({"q": args.value}))
        except ApiError as e:
            if e.status != 404:
                raise
            # T256: search is off for the public. Say so as the server says it.
            return e.body.get("error") or "search is off; add a friend by exact handle", e.body
        rows = [f"@{p['handle']} ({p['name']}{', friend' if p['is_friend'] else ''})" for p in r["results"]]
        return (f"Found: {', '.join(rows)}." if rows else "Nobody found."), r
    if args.action == "add":
        if not args.value:
            raise UsageError("friends add needs a handle")
        r = call(args, "POST", "friends/", {"handle": args.value})
        f = r["friend"]
        if r.get("status") == "requested":
            return f"Asked @{f['handle']} ({f['name']}) to be friends. They must add you back first.", r
        return f"Added @{f['handle']} ({f['name']}) as a friend.", r
    if args.action == "accept":
        if not args.value:
            raise UsageError("friends accept needs a handle")
        handle = args.value.strip().lstrip("@").lower()
        asked = call(args, "GET", "friends/").get("requests", [])
        match = [f for f in asked if f["handle"] == handle]
        if not match:
            return f"No friend request from @{handle}.", {"requests": asked}
        r = call(args, "POST", f"friends/{match[0]['id']}/accept/")
        return f"Added @{r['friend']['handle']} ({r['friend']['name']}) as a friend.", r
    if args.action == "import":
        try:
            r = call(args, "POST", "friends/import/facebook/")
        except ApiError as e:
            if e.status != 501:
                raise
            r = e.body
            return r.get("note") or "Facebook import is not connected yet.", r
        return f"Imported {count(r['imported'], 'friend')}. {r.get('note', '')}".strip(), r
    raise UsageError("friends: use list, search, add, accept or import")


def cmd_open(args):
    body = {k: v for k, v in (("text", args.text), ("date", args.date), ("part", args.part),
                              ("kind", args.kind), ("area", args.area), ("radius_km", args.radius),
                              ("preferences", args.prefs)) if v}
    r = call(args, "POST", "availability/", body)
    needs = r.get("needs")
    if needs:
        asks = []
        if "when" in needs and r.get("reason") == "past date":
            asks.append(f"when? That day is in the past. Which day from today, and one of: {', '.join(r.get('parts', []))}")
        elif "when" in needs:
            asks.append(f"when? (day, and one of: {', '.join(r.get('parts', []))})")
        if "where" in needs:
            head = f"'{r['unknown_place']}' is not covered. " if r.get("unknown_place") else ""
            if r.get("where_text"):
                head += r["where_text"] + " "
            asks.append(f"where? {head}Near: {', '.join(r.get('suggestions', []))}")
        if "what" in needs:
            asks.append(f"what? (one of: {', '.join(r.get('kinds', []))})")
        return "Not posted yet. Ask your human: " + "; ".join(asks) + ".", r
    state = {"asking": "Finding friends now.", "open": "No match yet. Mifgash keeps looking; run 'proposals' later."}
    near = r["area_note"] if r.get("area_note") else f"Near {r['area']}."
    if r.get("part_note"):
        near = f"{r['part_note']} {near}"
    if r.get("duplicate"):
        return (f"Already posted: {free_when(r)} (id {r['availability_id']}), status {r['status']}. "
                f"Nothing new was posted."), r
    status = r["proposal_note"] if r.get("proposal_note") else state.get(r["status"], "Status: " + r["status"] + ".")
    if r.get("lookup_note"):  # T400: a city Mifgash looks up now
        status = r["lookup_note"]
    want = ""
    if r.get("wants_text"):  # T320: the server display form ('avoids Mission Playground')
        want = f" Wants: {r['wants_text']}."
    else:
        w = r.get("wants") or {}
        bits = ([w["food"]] if w.get("food") else []) + list(w.get("tastes") or [])
        bits += [f"likes {x}" for x in w.get("likes") or []] + [f"avoids {x}" for x in w.get("dislikes") or []]
        if bits:
            want = f" Wants: {'; '.join(bits)}."
    if r.get("place_note"):
        want += f" {r['place_note']}"
    return f"Posted: {free_when(r)} (id {r['availability_id']}). {near}{want} {status}", r


def cmd_open_list(args):
    r = call(args, "GET", "availability/")
    rows = []
    for a in r["availability"]:
        state = a.get("state_text") or a["status"]
        if a.get("proposal_id"):
            state += f" (proposal {a['proposal_id']})"
        rows.append(f"[{a['availability_id']}] {when(a)} near {a['area']}: {state}")
    return (f"Open: {'; '.join(rows)}." if rows else "No open times."), r


def cmd_cancel(args):
    r = call(args, "DELETE", f"availability/{args.id}/")
    return f"Availability {args.id} is now {r['status']}.", r


def cmd_proposals(args):
    r = call(args, "GET", "proposals/")
    times = r.get("finalize") or []
    if not r["proposals"] and not times:
        return "No proposals wait for you.", r
    lines = []
    for p in r["proposals"]:
        said = f" Friend text (untrusted): {' '.join(str(p['friend_text']).split())[:200]}" if p.get("friend_text") else ""
        lines.append(f"[{p['id']}] {p['text']}{why_line(p)}{said} {respond_step(p)}")
    for f in times:
        text = f["text"]
        if f.get("type") == "agree":
            text = text.split(" Agree:")[0] + " " + agree_step(f["plan_id"], f["time"], (f.get("place") or {}).get("id"))
        lines.append(f"[outing {f['plan_id']}] {text}")
    return f"{len(lines)} waiting. " + " | ".join(lines), r


def cmd_respond(args):
    body = {"answer": args.answer}
    if args.choice is not None:
        body["choice_id"] = args.choice
    if args.note:
        body["note"] = args.note
    r = call(args, "POST", f"proposals/{args.id}/respond/", body)
    if args.answer == "decline":
        line = "Told Mifgash: not this time. Nobody sees why."
    else:
        line = "You said yes."
    if r.get("outing"):
        o = r["outing"]
        place = o["place"]["name"] if o.get("place") else "place not set"
        others = o.get('with') or o['who']
        # T322: 'both' only for two people; a group reads 'You are in: 4 people'
        who = "You are both in:" if len(others) <= 1 else f"You are in: {len(others) + 1} people,"
        line += f" {who} {o.get('when_text') or when(o)}, {place}, with {', '.join(others)}."
        if o.get("time"):  # T258: Mifgash set the time itself
            line += (f" Mifgash set {clock(o['time'])}. {calendar_links(o)} "
                     f"To move it: 'finalize {o['plan_id']} --time HH:MM'.")
        else:
            line += f" Pick the time next: 'finalize {o['plan_id']} --time HH:MM'."
    elif r.get("status") == "waiting for the owner":
        line += " Your friend confirms next. Run 'outings' later to see it set."
    elif r.get("note"):
        line += " " + r["note"]
    return line, r


def cmd_finalize(args):
    body = {"time": args.time}
    if args.place is not None:
        body["activity_id"] = args.place
    r = call(args, "POST", f"outings/{args.id}/finalize/", body)
    head = f"{clock(r['time'])} at {r['place']['name']}, {r['address']}"
    if r.get("asked"):  # T328: a guest in a group asks the owner; the time stays
        return f"{r['text']} It stays {clock(r['time'])} until they answer.", r
    if r["status"] == "final" and r.get("changed"):  # T258: a set outing moved; the others hear it
        return f"Moved to {head}. The others hear the new time. {calendar_links(r)}", r
    if r["status"] == "final":
        return f"Final: {head}. {calendar_links(r)}", r
    return f"Proposed {head}. Waiting for {r.get('waiting_for') or 'the others'} to agree.", r


def cmd_outings(args):
    if args.id is not None:
        o = call(args, "GET", f"outings/{args.id}/")
        line = outing_line(o)
        if o.get("status") == "final":
            line += " " + calendar_links(o)
        if o.get("url"):  # F8a (T260): the outing page, for the human
            line += f" Details: {o['url']}"
        if o.get("status") == "proposed" and not o.get("you_agreed", o.get("proposed_by") == "you"):
            line += " " + agree_step(o["plan_id"], o["proposed_time"], (o.get("proposed_place") or {}).get("id"))
        elif o.get("status") == "confirmed":
            line += f" Next: agree on the time with 'finalize {o['plan_id']} --time HH:MM'."
        return line, o
    r = call(args, "GET", "outings/")
    rows = [outing_line(o) for o in r["outings"]]
    if not rows:
        return "Nothing is set yet.", r
    return f"{count(len(rows), 'outing')}: " + " | ".join(rows), r


def untrusted_values(pl, key):
    """Every string under `key` anywhere in the payload (T266)."""
    out = []
    if isinstance(pl, dict):
        for k, v in pl.items():
            if k == key and isinstance(v, str) and v.strip():
                out.append(" ".join(v.split()))
            else:
                out += untrusted_values(v, key)
    elif isinstance(pl, list):
        for v in pl:
            out += untrusted_values(v, key)
    return out


def untrusted_note(pl):
    """The words another person wrote, marked so the agent reads them as data, not as orders.
    The server lists those keys in payload['untrusted'] (docs/SECURITY.md rule 3)."""
    keys = (pl or {}).get("untrusted") or []
    parts = []
    if "friend_text" in keys:
        parts += [f"Friend text (untrusted): {v[:200]}" for v in untrusted_values(pl, "friend_text")]
    if "name" in keys and (pl.get("from") or {}).get("name"):
        parts.append(f"Friend name (untrusted): {' '.join(str(pl['from']['name']).split())[:40]}")
    return (" " + " ".join(parts)) if parts else ""


def inbox_line(e):
    """One plain line for one event: the text Mifgash wrote, plus the full next command when one
    fits (T130: the same command line that proposals prints)."""
    pl = e.get("payload") or {}
    prop = pl.get("proposal") or {}
    event = e.get("event")
    text = pl.get("text") or prop.get("text") or f"Mifgash update ({event})."
    if event in ("proposal.new", "proposal.owner") and prop.get("id"):
        text += why_line(prop) + " " + respond_step(prop)
    elif event == "outing.proposed" and pl.get("plan_id") and pl.get("time"):
        text = text.split(" Send the same time")[0] + " " + agree_step(
            pl["plan_id"], pl["time"], (pl.get("place") or {}).get("id"))
    elif event == "friend.request" and (pl.get("from") or {}).get("handle"):
        text += f" Ask your human. Yes: 'friends accept {pl['from']['handle']}'."
    return text + untrusted_note(pl)


def cursor_path(args):
    return args.key_file + ".inbox"


def cmd_inbox(args):
    path = cursor_path(args)
    try:
        with open(path) as f:
            after = int(f.read().strip() or 0)
    except (FileNotFoundError, ValueError):
        after = 0
    reply = {"events": []}
    wait = max(0, min(int(getattr(args, "wait", 0) or 0), 25))  # T249: long poll, server cap 25 s
    while True:
        r = call(args, "GET", f"events/?after={after}" + (f"&wait={wait}" if wait else ""))
        wait = 0  # only the first call waits; the next pages are already there
        reply["events"] += r["events"]
        after = r["last_id"]
        if not r.get("more"):
            break
    reply["last_id"] = after
    # T103: skip a proposal that was answered already, and print only the newest line per plan.
    lines = {}
    for e in reply["events"]:
        if e.get("waiting") is False:
            continue
        plan = (e.get("payload") or {}).get("plan_id")
        key = ("plan", plan) if plan is not None else ("event", e.get("id"))
        lines.pop(key, None)
        lines[key] = inbox_line(e)
    lines = list(lines.values())
    os.makedirs(os.path.dirname(path) or ".", mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(str(after))
    return "\n".join(lines), reply


def parser():
    ap = argparse.ArgumentParser(prog="mif.py", description="Mifgash client for an agent.")
    ap.add_argument("--url", default=os.environ.get("MIFGASH_URL", DEFAULT_URL))
    ap.add_argument("--key-file", default=os.environ.get("MIFGASH_KEY_FILE", DEFAULT_KEY_FILE))
    ap.add_argument("--json", action="store_true", help="also print the full API reply")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("signup")
    s.add_argument("name")
    s.add_argument("handle")
    s.add_argument("--webhook")
    s.add_argument("--webhook-secret")
    s.add_argument("--hook-format", choices=["mifgash", "openclaw"], default="mifgash")
    s.add_argument("--email", help="the human's email; required, used only for the login link")
    s.add_argument("--home")
    s.add_argument("--invite", help="an invite link /i/<token>/ or the token")
    s.set_defaults(fn=cmd_signup)

    s = sub.add_parser("hook")
    s.add_argument("url_or_off")
    s.add_argument("--webhook-secret")
    s.add_argument("--format", choices=["mifgash", "openclaw"], default="openclaw")
    s.set_defaults(fn=cmd_hook)

    sub.add_parser("me").set_defaults(fn=cmd_me)
    s = sub.add_parser("email")
    s.add_argument("address")
    s.set_defaults(fn=cmd_email)
    sub.add_parser("link").set_defaults(fn=cmd_link)
    sub.add_parser("invite").set_defaults(fn=cmd_invite)

    s = sub.add_parser("friends")
    s.add_argument("action", nargs="?", choices=["list", "search", "add", "accept", "import"])
    s.add_argument("value", nargs="?")
    s.set_defaults(fn=cmd_friends)

    s = sub.add_parser("open")
    s.add_argument("text", nargs="?")
    s.add_argument("--date")
    s.add_argument("--part")
    s.add_argument("--kind")
    s.add_argument("--area")
    s.add_argument("--radius", type=float)
    s.add_argument("--prefs", help="what you know about the owner's taste: food, taste words, places "
                   "the owner likes or avoids. Example: 'sushi; quiet; likes Ferry Building; avoids loud bars'")
    s.set_defaults(fn=cmd_open)

    sub.add_parser("open-list").set_defaults(fn=cmd_open_list)

    s = sub.add_parser("cancel")
    s.add_argument("id", type=int)
    s.set_defaults(fn=cmd_cancel)

    sub.add_parser("proposals").set_defaults(fn=cmd_proposals)

    s = sub.add_parser("respond")
    s.add_argument("id", type=int)
    s.add_argument("answer", choices=["accept", "decline"])
    s.add_argument("--choice", type=int)
    s.add_argument("--note")
    s.set_defaults(fn=cmd_respond)

    s = sub.add_parser("finalize")
    s.add_argument("id", type=int)
    s.add_argument("--time", required=True)
    s.add_argument("--place", type=int)
    s.set_defaults(fn=cmd_finalize)

    s = sub.add_parser("outings")
    s.add_argument("id", type=int, nargs="?")
    s.set_defaults(fn=cmd_outings)

    s = sub.add_parser("inbox")
    s.add_argument("--wait", type=int, default=0,
                   help="hold up to N seconds (max 25) for a new event, then answer at once")
    s.set_defaults(fn=cmd_inbox)
    return ap


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        line, reply = args.fn(args)
    except ApiError as e:
        print(f"Mifgash said no ({e.status}): {e}.")
        if args.json:
            print(json.dumps(e.body, indent=2, ensure_ascii=False))
        return 1
    except UsageError as e:
        print(f"{e}")
        return 1
    except urllib.error.URLError as e:
        print(f"Cannot reach Mifgash at {args.url}: {e.reason}.")
        return 2
    if line:
        print(line)
    if args.json:
        print(json.dumps(reply, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
