#!/usr/bin/env python3
"""Plays the 28/10 demo scenario end to end in one command. New hackathon work (29/10/2026).

  python demo/scenario.py                      # against https://mifgash.sveder.com, friend agents on the stub
  python demo/scenario.py --url https://mifgash.sveder.com --backend claude

Steps, one printed line each with the elapsed seconds:
  1. reset the scenario people (POST /api/v1/demo/reset/; the server must run with MIFGASH_DEMO=1)
  2. sign up Leo (the owner) and the friends Alex and Sam, each with an own agent key
  3. Leo's agent adds Alex, Sam and Priya by their exact handles (there is no search, T256); Alex and Sam add Leo back (Priya has no agent: in the demo the request counts at once)
  4. Leo: 'open tomorrow for lunch near SoMa'   -> open, nobody fits yet
  5. Alex: 'open tomorrow lunch in Sausalito'      -> too far, stays open with the gentle line
  6. Sam: 'open tomorrow lunch near SoMa'      -> match: the site asks Sam's agent
  7. the friend agents poll once: Sam's agent accepts, Alex's agent gets nothing
  8. Leo's agent approves -> confirmed outing
  9. Leo's agent sets the exact time and place (finalize, 13:00 for lunch) -> proposed
 10. Sam's agent reads the proposed time; Sam prefers 13:30, so the agent counters once -> proposed
 11. Leo's agent reads Sam's counter and sends the same time and place back -> final
 12. each side gets its own .ics and Google Calendar link; the script fetches both .ics files
 13. Leo: 'open tomorrow evening near SoMa'   -> Priya (no agent, a weekly free evening) gets a
     /h/ link; the script answers it like the web page does; Leo's agent approves -> confirmed
Then it prints the outing, Leo's dashboard link and the agent log.

Every call goes through the public agent API, the same calls Kurt makes from Telegram.
Standard library only. The scenario people have handles scn_*, so a rerun starts clean.
Priya is made by the demo reset (she has no agent, so she cannot sign up through the API).
"""
import argparse
import datetime as dt
import io
import os
import re
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import friend_agent  # noqa: E402
from friend_agent import DEFAULT_URL, ApiError, FriendAgent  # noqa: E402

OWNER = ("Leo", "scn_leo", {"persona": "the owner; approves a friend who said yes"})
FRIENDS = [
    ("Alex", "scn_alex", {"likes": ["lunch"], "areas": ["Sausalito"], "persona": "works in Sausalito"}),
    ("Sam", "scn_sam", {"likes": ["lunch"], "areas": ["SoMa"], "persona": "likes a quick lunch",
                          "preferred_times": {"lunch": "13:30"}}),
]
# Priya has no agent. She is free every evening of the weekday of tomorrow, near SoMa.
HUMAN = ("Priya", "scn_priya", "SoMa", "evening")
HUMAN_TEXT = "I am open tomorrow evening near SoMa"
TEXTS = {
    "scn_leo": "I am open tomorrow for lunch near SoMa",
    "scn_alex": "I am open tomorrow for lunch in Sausalito",
    "scn_sam": "I am open tomorrow for lunch near SoMa",
}
TIMES = {"breakfast": "09:00", "morning": "10:00", "lunch": "13:00", "afternoon": "16:00", "evening": "19:30"}


class Scenario:
    def __init__(self, url=DEFAULT_URL, backend="stub", out=None):
        self.url, self.backend = url.rstrip("/"), backend
        self.out = out or sys.stdout
        self.t0 = time.monotonic()
        self.agent_log = io.StringIO()  # every agent's own API lines, printed at the end
        self.agents = {}
        self.result = {}

    def say(self, line):
        print(f"[{time.monotonic() - self.t0:5.1f}s] {line}", file=self.out, flush=True)

    def agent(self, name, handle, prefs):
        a = FriendAgent(name, handle, prefs=prefs, url=self.url, backend=self.backend, out=self.agent_log)
        self.agents[handle] = a
        return a

    def reset(self):
        probe = FriendAgent("reset", "reset", url=self.url, out=self.agent_log)
        self.probe = probe
        name, handle, area, part = HUMAN
        weekday = (dt.date.today() + dt.timedelta(days=1)).weekday()
        humans = [{"name": name, "handle": handle, "area": area, "slots": [{"weekday": weekday, "part": part}]}]
        try:
            r = probe.call("POST", "demo/reset/", {"humans": humans}, auth=False)
        except ApiError as e:
            if e.status == 404:
                raise SystemExit("The server is not in demo mode. Start it with MIFGASH_DEMO=1; I stop here.")
            raise
        self.say(f"reset: removed {r['deleted_people']} scenario people (handles {r['prefix']}*);"
                 f" made {name}, a friend with no agent, free {part}s near {area.split(' - ')[-1]}")

    def run(self):
        self.reset()
        owner = self.agent(*OWNER)
        signup = owner.signup()
        self.result["dashboard_url"] = signup.get("dashboard_url")
        friends = [self.agent(*f) for f in FRIENDS]
        for f in friends:
            f.signup()
        self.say(f"signed up {owner.name} (owner), {', '.join(f.name for f in friends)}; each has its own agent key")
        for name, handle in [(f.name, f.handle) for f in friends] + [HUMAN[:2]]:
            self.search_and_add(owner, name, handle)
        for f in friends:  # a friend request counts only after the other side adds back
            if f.add_friend(owner.handle).get("status") != "friends":
                raise SystemExit(f"{f.name} added {owner.name} back, but they are not friends")
        self.say(f"{' and '.join(f.name for f in friends)} added {owner.name} back; {HUMAN[0]} has no agent,"
                 " so her friendship counts at once in the demo")

        plans = {}
        for a in [owner] + friends:
            r = a.post_availability(TEXTS[a.handle])
            if r.get("needs"):
                raise SystemExit(f"{a.name}: the server asks for {', '.join(r['needs'])}; the scenario cannot go on")
            plans[a.handle] = r
            self.say(f"{a.name}: '{TEXTS[a.handle]}' -> {r['date']} {r['part']} {r['area']}, {r['status']}"
                     + (f" ({r['note']})" if r.get("note") else ""))

        answers = {}
        for f in friends:
            answers[f.handle] = f.poll()
        alex, sam = friends
        self.say(f"friend agents polled once ({self.backend}): {sam.name} answered "
                 + (", ".join(f"{x['answer']} -> {x['status']}" for x in answers[sam.handle]) or "nothing")
                 + f"; {alex.name} got {len(answers[alex.handle])} proposals")

        approved = 0
        for p in owner.call("GET", "proposals/")["proposals"]:
            if p["role"] != "owner":
                continue
            r = owner.call("POST", f"proposals/{p['id']}/respond/", {"answer": "accept"})
            owner.log(f"proposal {p['id']} (owner, {p['friend']['name']} said yes) -> accept -> {r.get('status')}")
            approved += 1
            if r.get("outing"):
                self.result["outing_reply"] = r["outing"]
        self.say(f"{owner.name} said yes on Telegram; the agent approved {approved} proposal(s)")
        self.finalize(owner, sam)
        self.human_step(owner)
        self.result.update(plans=plans, answers=answers,
                           alex_open=alex.call("GET", "availability/")["availability"],
                           alex_proposals=alex.call("GET", "proposals/")["proposals"])

    def search_and_add(self, owner, name, handle):
        """Brief item b: the human tells the agent the friend's exact handle and the agent adds it.
        T256: there is no public search, so a wrong handle stops the scenario."""
        r = owner.add_friend(handle)
        owner.log(f"POST friends/ {{handle: {handle}}} -> {r.get('status')}")
        self.say(f"{owner.name}'s agent: friends add @{handle} ({name}) -> {r.get('status')}")

    def human_step(self, owner):
        """Brief item f: a friend with no agent gets a /h/ link and answers on the web page.
        Then the owner's agent approves, and the outing is confirmed."""
        name, handle = HUMAN[:2]
        r = owner.post_availability(HUMAN_TEXT)
        self.say(f"{owner.name}: '{HUMAN_TEXT}' -> {r.get('date')} {r.get('part')} {r.get('area')}, {r.get('status')}")
        self.result["human_plan_id"] = r.get("availability_id")
        links = self.probe.call("GET", f"demo/links/?handle={handle}", auth=False)["links"]
        if not links:
            self.say(f"{name} got no link; the evening plan is {r.get('status')}")
            return
        link = self.url + links[0]["path"]
        self.say(f"{name} has no agent. Mifgash sent her a web link: {link}")
        code = self.answer_human_page(link)
        self.say(f"{name} accepted on the web page (HTTP {code})")
        for p in owner.call("GET", "proposals/")["proposals"]:
            if p["role"] == "owner" and p["friend"]["handle"] == handle:
                a = owner.call("POST", f"proposals/{p['id']}/respond/", {"answer": "accept"})
                owner.log(f"proposal {p['id']} (owner, {name} said yes on the web page) -> accept -> {a.get('status')}")
        mine = next((x for x in owner.call("GET", "outings/")["outings"] if x["plan_id"] == links[0]["plan_id"]), {})
        self.result["human_outing"] = mine
        self.say(f"{owner.name}'s agent approved {name} -> {mine.get('status', 'no outing')}")

    def answer_human_page(self, link):
        """GET the /h/ page, then POST 'Yes, I am in' with the first place, the way a browser does
        (CSRF cookie and form token included)."""
        req = friend_agent.urllib.request.Request(link)
        with friend_agent.urllib.request.urlopen(req, timeout=30) as r:
            html = r.read().decode("utf-8", "replace")
            headers = getattr(r, "headers", None) or {}
            cookie = headers.get("Set-Cookie") or ""
        form = {"answer": "yes"}
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html)
        if token:
            form["csrfmiddlewaretoken"] = token.group(1)
        choice = re.search(r'name="choice"[^>]*value="(\d+)"', html)
        if choice:
            form["choice"] = choice.group(1)
        hdrs = {"Content-Type": "application/x-www-form-urlencoded", "Referer": link}
        m = re.search(r"csrftoken=([^;]+)", cookie)
        if m:
            hdrs["Cookie"] = f"csrftoken={m.group(1)}"
        post = friend_agent.urllib.request.Request(link, data=urllib.parse.urlencode(form).encode(),
                                                   headers=hdrs, method="POST")
        try:
            with friend_agent.urllib.request.urlopen(post, timeout=30) as r:
                return getattr(r, "status", 200)
        except friend_agent.urllib.error.HTTPError as e:
            if e.code in (302, 303):
                return e.code
            raise ApiError(e.code, {"error": "the web page refused the answer"})

    def finalize(self, owner, friend):
        """Brief items g and h: the owner's agent proposes the exact time and place, the friend's
        agent confirms the same, and each side gets its calendar links."""
        outings = owner.call("GET", "outings/")["outings"]
        rows = [o for o in outings if o["status"] == "confirmed"]
        final = [o for o in outings if o["status"] == "final"]
        if not rows and final:
            # T258 (F6c): Mifgash set the time itself when both sides were in. No finalize call.
            o = final[0]
            self.result["plan_id"] = o["plan_id"]
            self.say(f"Mifgash set {o.get('time')} at {(o.get('place') or {}).get('name', 'the place')} by itself -> final")
            friend.poll()
            self.result["calendar"] = {}
            for a in (owner, friend):
                mine = next((x for x in a.call("GET", "outings/")["outings"] if x["plan_id"] == o["plan_id"]), {})
                self.result["calendar"][a.name] = mine
            for name, mine in self.result["calendar"].items():
                code, ctype = self.fetch(mine.get("ics_url"))
                mine["ics_check"] = (code, ctype)
                self.say(f"calendar for {name}: .ics {mine.get('ics_url') or 'none'} -> {code} {ctype}")
                self.say(f"calendar for {name}: Google {mine.get('google_calendar_url') or 'none'}")
            return
        if not rows:
            self.say("no confirmed outing to finalize")
            return
        o = rows[0]
        self.result["plan_id"] = o["plan_id"]
        time_ = TIMES.get(o["part"], "13:00")
        body = {"time": time_}
        if o.get("place"):
            body["activity_id"] = o["place"]["id"]
        r = owner.call("POST", f"outings/{o['plan_id']}/finalize/", body)
        owner.log(f"finalize {o['plan_id']} {time_} {(o.get('place') or {}).get('name', '')} -> {r.get('status')}")
        self.say(f"{owner.name}'s agent set {time_} at {(r.get('place') or {}).get('name', 'the place')} -> {r['status']},"
                 f" waiting for {r.get('waiting_for') or 'nobody'}")
        friend.poll()
        mine = next((x for x in owner.call("GET", "outings/")["outings"] if x["plan_id"] == o["plan_id"]), {})
        if mine.get("status") == "proposed" and mine.get("proposed_by") not in (None, "you"):
            # Brief item g, a second turn: the friend's agent countered. Leo's agent takes the counter.
            self.result["counter"] = {"by": mine["proposed_by"], "time": mine["proposed_time"]}
            self.say(f"{friend.name}'s agent read {time_} and suggests {mine['proposed_time']} instead -> proposed")
            body = {"time": mine["proposed_time"]}
            if mine.get("proposed_place"):
                body["activity_id"] = mine["proposed_place"]["id"]
            r = owner.call("POST", f"outings/{o['plan_id']}/finalize/", body)
            owner.log(f"finalize {o['plan_id']} {mine['proposed_time']} (the counter of {mine['proposed_by']}) -> {r.get('status')}")
            self.say(f"{owner.name}'s agent took {friend.name}'s time {mine['proposed_time']} -> {r.get('status')}")
            friend.poll()
        self.result["calendar"] = {}
        for a in (owner, friend):
            mine = next((x for x in a.call("GET", "outings/")["outings"] if x["plan_id"] == o["plan_id"]), {})
            self.result["calendar"][a.name] = mine
        if not self.result.get("counter"):
            status = self.result["calendar"][friend.name].get("status")
            self.say(f"{friend.name}'s agent read the proposed time and sent the same back -> {status}")
        for name, mine in self.result["calendar"].items():
            code, ctype = self.fetch(mine.get("ics_url"))
            mine["ics_check"] = (code, ctype)
            self.say(f"calendar for {name}: .ics {mine.get('ics_url') or 'none'} -> {code} {ctype}")
            self.say(f"calendar for {name}: Google {mine.get('google_calendar_url') or 'none'}")

    def fetch(self, url):
        """(HTTP code, content type) of a GET, or (0, error) when the call fails."""
        if not url:
            return 0, "no link"
        try:
            with friend_agent.urllib.request.urlopen(friend_agent.urllib.request.Request(url), timeout=30) as r:
                headers = getattr(r, "headers", None) or {}
                return getattr(r, "status", 200), (headers.get("Content-Type") or "").split(";")[0]
        except friend_agent.urllib.error.HTTPError as e:
            return e.code, "error"
        except OSError as e:
            return 0, str(e)

    def report(self):
        res = self.result
        detail = self.owner_outing()
        if detail:
            self.say(f"outing: {detail}")
        alex = res["alex_open"]
        self.say(f"Alex: {len(alex)} open plan(s)"
                 + (f", '{alex[0].get('note', '')}'" if alex else "")
                 + f"; proposals for Alex: {len(res['alex_proposals'])}")
        h = res.get("human_outing") or {}
        if h:
            self.say(f"outing with {HUMAN[0]} (web page, no agent): {outing_line(h)}")
        self.say(f"dashboard for Leo (one-time link, open it once): {res['dashboard_url']}")
        print("\nAgent log (what each agent sent and got):", file=self.out)
        print(self.agent_log.getvalue().rstrip(), file=self.out)
        self.say("done")

    def owner_outing(self):
        """The confirmed outing: GET /api/v1/outings/ when the server has it (T50), else the
        outing in the approve reply."""
        owner = self.agents[OWNER[1]]
        try:
            rows = owner.call("GET", "outings/").get("outings", [])
        except ApiError:
            rows = []
        o = next((x for x in rows if x["plan_id"] == self.result.get("plan_id")), None) or self.result.get("outing_reply")
        if not o:
            return ""
        self.result["outing"] = o
        return outing_line(o)


def outing_line(o):
    """'Lunch, Fri Oct 30, 1:00 PM, Place, Address, with Sam (final)'."""
    try:
        d = dt.date.fromisoformat(o.get("date") or "")
        day = f"{d:%a} {d:%b} {d.day}"
    except ValueError:
        day = o.get("date") or "day not set"
    place = o.get("place") or {}
    hm = o.get("time")
    if hm:
        h, m = (int(x) for x in hm.split(":")[:2])
        hm = f"{(h % 12) or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"
    parts = [str(o.get("kind") or "outing").capitalize(), day, hm or "time not set",
             place.get("name", "place not set")]
    if place.get("address"):
        parts.append(place["address"])
    return ", ".join(parts) + f", with {', '.join(o.get('who') or []) or 'nobody yet'} ({o.get('status')})"


def is_final(result):
    """True for a final outing with an exact time and a working .ics link for every side."""
    o = result.get("outing") or {}
    cal = result.get("calendar") or {}
    return (o.get("status") == "final" and bool(o.get("time")) and len(cal) == 2
            and all(c.get("ics_check") == (200, "text/calendar") for c in cal.values()))


def counter_taken(result):
    """True when the friend's agent countered and the final time is the counter (T70)."""
    c = result.get("counter") or {}
    return bool(c) and (result.get("outing") or {}).get("time") == c.get("time")


def human_confirmed(result):
    """True when the friend with no agent said yes on the web page and the owner approved."""
    h = result.get("human_outing") or {}
    return h.get("status") in ("confirmed", "final") and HUMAN[0] in (h.get("who") or [])


def main(argv=None):
    ap = argparse.ArgumentParser(prog="scenario.py", description="Play the Mifgash demo scenario in one command.")
    ap.add_argument("--url", default=os.environ.get("MIFGASH_URL", DEFAULT_URL))
    ap.add_argument("--backend", default="stub", choices=["stub", "claude", "meta"],
                    help="how the friend agents decide (the server parses text with its own backend)")
    args = ap.parse_args(argv)
    s = Scenario(args.url, args.backend)
    try:
        s.run()
    except ApiError as e:
        s.say(f"API error {e.status}: {e}")
        return 1
    s.report()
    ok = is_final(s.result) and counter_taken(s.result) and human_confirmed(s.result) and not s.result["alex_proposals"]
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
