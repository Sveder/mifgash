#!/usr/bin/env python3
"""The live run for the v2 video (M13b, T184, 3/11/2026).

  python demo/video_run.py [--url https://mifgash.sveder.com] [--backend meta] --out demo/video-run.json

Four test personas (handles zz_*, international names) use the PUBLIC agent API, the same calls
Kurt makes from Telegram:
  Chris (the owner)  'I am free Thursday evening for dinner near North Beach'
  Sam                'free Thursday evening in the Mission, I want to stay there'  -> no match
  Maria              'free Thursday evening near Chinatown'                         -> match
  Chris's agent approves, proposes 19:30 at The Stinking Rose; Maria's agent agrees -> final
  Lena               an open Saturday lunch that matches Chris's second post, and her agent never
                     answers: the cut films her pending /h/ page (a clean page for a person).
The script writes the ids and the agent log lines to --out (no key, no dashboard link). The /h/ token and the plan log JSON are read later (see demo/VIDEO.md).
Run `manage.py purge_test_people` on the server after the cut.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from friend_agent import DEFAULT_URL, FriendAgent  # noqa: E402

PLACE = "The Stinking Rose"
TIME = "19:30"
OWNER = ("Chris", "zz_chris", {"persona": "the owner; likes a long dinner"})
SAM = ("Sam", "zz_sam", {"likes": ["evening"], "areas": ["Mission"], "persona": "stays in the Mission"})
MARIA = ("Maria", "zz_maria", {"likes": ["evening", "dinner"], "areas": ["Chinatown", "North Beach"],
                              "persona": "works in Chinatown, likes Italian food",
                              "preferred_times": {"evening": TIME}})
LENA = ("Lena", "zz_lena", {"persona": "busy, answers late"})
TEXTS = {
    "zz_chris": "I am free Thursday evening for dinner near North Beach",
    "zz_sam": "I am free Thursday evening in the Mission, and I want to stay in the Mission",
    "zz_maria": "I am free Thursday evening near Chinatown",
}
SECOND = {"zz_chris": "I am free Saturday for lunch near North Beach",
          "zz_lena": "I am free Saturday for lunch near North Beach"}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="video_run.py")
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--backend", default="meta", choices=["stub", "claude", "meta"])
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    t0 = time.monotonic()
    lines = []

    def say(s):
        s = f"[{time.monotonic() - t0:5.1f}s] {s}"
        print(s, flush=True)
        lines.append(s)

    class Log:
        def write(self, s):
            if s.strip():
                lines.append("  agent: " + s.strip())

        def flush(self):
            pass

    mk = lambda p: FriendAgent(*p[:2], prefs=p[2], url=a.url, backend=a.backend, out=Log())  # noqa: E731
    chris, sam, maria, lena = mk(OWNER), mk(SAM), mk(MARIA), mk(LENA)
    chris.signup()  # the dashboard link is a key: not written to the file (the cut makes fresh links)
    res = {}
    for f in (sam, maria, lena):
        f.signup()
        chris.add_friend(f.handle)
        st = f.add_friend(chris.handle).get("status")
        if st != "friends":
            raise SystemExit(f"{f.name} and Chris are not friends: {st}")
    say("signed up Chris, Sam, Maria and Lena; all are friends of Chris")
    plans = {}
    for ag in (chris, sam, maria):
        r = ag.post_availability(TEXTS[ag.handle])
        if r.get("needs"):
            raise SystemExit(f"{ag.name}: needs {r['needs']}")
        plans[ag.handle] = r
        say(f"{ag.name}: '{TEXTS[ag.handle]}' -> {r['date']} {r['part']} {r['area']}, {r['status']}"
            + (f" ({r['note']})" if r.get("note") else ""))
    for ag in (sam, maria):
        ans = ag.poll()
        say(f"{ag.name}'s agent polled: " + (", ".join(f"{x['answer']} -> {x['status']}" for x in ans) or "nothing"))
    for p in chris.call("GET", "proposals/")["proposals"]:
        if p["role"] == "owner":
            r = chris.call("POST", f"proposals/{p['id']}/respond/", {"answer": "accept"})
            say(f"Chris approves {p['friend']['name']} -> {r.get('status')}")
    rows = [o for o in chris.call("GET", "outings/")["outings"] if o["status"] == "confirmed"]
    if len(rows) != 1 or rows[0].get("who") != ["Maria"]:
        raise SystemExit(f"expected one confirmed outing with Maria, got {rows}")
    o = rows[0]
    res["plan_id"] = o["plan_id"]
    places = {}
    try:
        chris.call("POST", f"outings/{o['plan_id']}/finalize/", {"time": TIME, "activity_id": -1})
    except Exception as e:  # the 400 lists the places of the plan
        places = {x["name"]: x["id"] for x in (getattr(e, "body", {}) or {}).get("places", [])}
    if PLACE not in places:
        raise SystemExit(f"{PLACE} is not a place of the plan: {sorted(places)}")
    r = chris.call("POST", f"outings/{o['plan_id']}/finalize/",
                   {"time": TIME, "activity_id": places[PLACE], "backend": a.backend})
    say(f"Chris's agent proposes {TIME} at {PLACE} -> {r.get('status')}")
    maria.poll()
    mine = next(x for x in chris.call("GET", "outings/")["outings"] if x["plan_id"] == o["plan_id"])
    say(f"Maria's agent answers -> {mine['status']} {mine.get('time')} {(mine.get('place') or {}).get('name')}")
    if mine["status"] != "final" or (mine.get("place") or {}).get("name") != PLACE:
        raise SystemExit("the outing is not final at the place")
    res["calendar_url"] = mine.get("google_calendar_url")
    res["ics_url"] = mine.get("ics_url")
    res["calendar_short"] = mine.get("google_calendar_short")
    res["outing"] = mine
    res["plan_uid"] = mine["url"].rstrip("/").rsplit("/", 1)[-1]  # F8a (T260): public URLs use the uuid
    for ag in (chris, lena):
        r = ag.post_availability(SECOND[ag.handle])
        say(f"{ag.name}: '{SECOND[ag.handle]}' -> {r.get('date')} {r.get('part')} {r.get('area')}, {r.get('status')}")
        if ag is lena:
            res["lena_plan"] = r.get("availability_id")
    res["handles"] = [x.handle for x in (chris, sam, maria, lena)]
    res["lines"] = lines
    with open(a.out, "w") as f:
        json.dump(res, f, indent=1)
    say(f"wrote {a.out}")


if __name__ == "__main__":
    main()
