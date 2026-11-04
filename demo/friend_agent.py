#!/usr/bin/env python3
"""Simulated friend agents for the Mifgash demo. New hackathon work (29/10/2026).

Each friend agent is a small program with its own persona. It uses the public agent API
(/api/v1/) with its own key, the same way the owner's agent does. No webhook server:
it polls. Standard library only (YAML config only when PyYAML is installed).

  friend_agent.py --config demo/friends.json --once
  friend_agent.py --config demo/friends.json --interval 5
  friend_agent.py --handle sam --key-file ~/.mifgash/sam.key --persona "likes quiet lunch" --once

Config (JSON or YAML): {"agents": [{"name", "handle", "key" | "key_file", "likes": [...],
"dislikes": [...], "max_km": 4, "areas": [...], "persona": "one line",
"preferred_times": {"lunch": "13:30"}}]}. preferred_times is per part: when the other side
proposes a time 30 minutes or more away from it, the agent counters once with its own time (T70).

The decision on a proposal comes from --backend:
  stub   - deterministic, from likes, dislikes and favourite areas (no network)
  claude - the local `claude -p` CLI
  meta   - Muse Spark Open on Baseten (BASETEN_API_KEY, BASETEN_BASE_URL, BASETEN_MODEL)
A model error falls back to the stub, so the demo never stops. The decision code lives in
planner/friend_brain.py (stdlib only), shared with the quick-demo friend on the server (T179).
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from planner import friend_brain as brain  # noqa: E402  (stdlib only, no Django)
from planner.friend_brain import (decide, decide_time, stub_decide, stub_time)  # noqa: E402,F401

DEFAULT_URL = "https://mifgash.sveder.com"
class ApiError(Exception):
    def __init__(self, status, body):
        super().__init__(body.get("error") or f"HTTP {status}")
        self.status, self.body = status, body


class FriendAgent:
    def __init__(self, name, handle, api_key=None, prefs=None, url=DEFAULT_URL, backend="stub", out=None):
        self.name, self.handle, self.api_key = name, handle, api_key
        self.prefs = dict(prefs or {}, handle=handle)
        self.url, self.backend = url.rstrip("/"), backend
        self.out = out or sys.stdout
        self.seen = {}  # plan id -> last outing status logged
        self.has_outings = True
        self.countered = set()  # plan ids this agent countered once already (T70)

    def log(self, line):
        print(f"[{self.handle}] {line}", file=self.out, flush=True)

    def call(self, method, path, body=None, auth=True):
        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if auth:
            headers["Authorization"] = "Bearer " + (self.api_key or "")
        if path.startswith("demo/") and os.environ.get("MIFGASH_DEMO_TOKEN"):
            headers["X-Mifgash-Demo-Token"] = os.environ["MIFGASH_DEMO_TOKEN"]  # T157 demo gate
        req = urllib.request.Request(f"{self.url}/api/v1/{path.lstrip('/')}", data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                reply = json.loads(e.read() or b"{}")
            except ValueError:
                reply = {}
            raise ApiError(e.code, reply)

    def signup(self):
        # F3a (T259): signup needs an email; a demo agent uses a reserved example.com address
        r = self.call("POST", "signup/", {"name": self.name, "handle": self.handle,
                                          "email": f"{self.handle}@example.com"}, auth=False)
        self.api_key = r.pop("api_key")
        self.log(f"POST signup -> @{r['handle']}")
        return r

    def add_friend(self, handle):
        r = self.call("POST", "friends/", {"handle": handle})
        self.log(f"POST friends {handle} -> {r.get('status', 'added')}")
        return r

    def post_availability(self, text):
        r = self.call("POST", "availability/", {"text": text})
        if r.get("needs"):
            self.log(f"POST availability '{text}' -> needs {', '.join(r['needs'])}")
        else:
            self.log(f"POST availability '{text}' -> {r.get('status')} (id {r.get('availability_id')})")
        return r

    def poll(self):
        """Answers every waiting proposal once, then logs outing changes. Returns the answers."""
        answers = []
        for p in self.call("GET", "proposals/")["proposals"]:
            if p["role"] == "owner":
                d, used = {"answer": "accept", "choice_id": None, "note": ""}, "rule"
            else:
                d, used = brain.decide(self.backend, self.prefs, p)
            body = {"answer": d["answer"]}
            if d.get("choice_id") is not None:
                body["choice_id"] = d["choice_id"]
            if d.get("note"):
                body["note"] = d["note"]
            if used in ("claude", "meta"):  # the dashboard log tags the row with the model (T60)
                body["backend"] = used
            try:
                r = self.call("POST", f"proposals/{p['id']}/respond/", body)
                status = r.get("status")
            except ApiError as e:
                status = f"error {e.status}: {e}"
            place = next((o["name"] for o in p.get("options") or [] if o["id"] == d.get("choice_id")), "")
            self.log(f"proposal {p['id']} ({p['role']}, {p['kind']} {p['date']}) -> {d['answer']}"
                     f"{' ' + place if place else ''}{' (' + d['note'] + ')' if d.get('note') else ''}"
                     f" [{used}] -> {status}")
            answers.append({"proposal": p["id"], **d, "status": status})
        self.poll_outings()
        return answers

    def poll_outings(self):
        if not self.has_outings:
            return
        try:
            rows = self.call("GET", "outings/").get("outings", [])
        except ApiError as e:
            if e.status in (404, 405):
                self.has_outings = False  # the server has no outings list yet
                return
            raise
        for o in rows:
            key = o.get("plan_id")
            if o.get("status") == "proposed" and o.get("proposed_by") not in (None, "you"):
                o = self.confirm_proposed(o)
            elif o.get("status") == "final" and o.get("time") and not o.get("time_moved"):
                o = self.move_final(o)
            if o.get("status") not in ("confirmed", "final") or self.seen.get(key) == o.get("status"):
                continue
            self.seen[key] = o["status"]
            place = (o.get("place") or {}).get("name", "place not set")
            line = f"outing {key} {o['status']}: {o.get('date')} {place}"
            if o["status"] == "final":
                line += f" {o.get('time') or ''} ics {o.get('ics_url', '')} gcal {o.get('google_calendar_url', '')}"
            self.log(line)


    def move_final(self, o):
        """T268: Mifgash set the time of the outing by itself (T258), so the outing is final at once.
        When that time is 30 min or more away from the persona's time, move it ONE time with
        finalize. Nobody moves it again: the server says time_moved after the first move, and this
        agent never moves one plan twice. Returns the outing as it is after the call."""
        if o["plan_id"] in self.countered:
            return o
        d, used = brain.decide_time(self.backend, self.prefs, dict(o, proposed_time=o["time"]))
        if d["decision"] != "counter" or d["time"] == o["time"]:
            return o
        self.countered.add(o["plan_id"])
        body = {"time": d["time"]}
        if used in ("claude", "meta"):
            body["backend"] = used
        try:
            r = self.call("POST", f"outings/{o['plan_id']}/finalize/", body)
        except ApiError as e:
            self.log(f"outing {o['plan_id']} final {o['time']} -> move to {d['time']} -> error {e.status}: {e}")
            return o
        self.log(f"outing {o['plan_id']} final {o['time']} set by Mifgash -> moved to {r.get('time') or d['time']}"
                 f" [{used}] -> {r.get('status')}")
        return dict(o, time=r.get("time") or d["time"], time_moved=True, moved_by="you",
                    ics_url=r.get("ics_url", o.get("ics_url")),
                    google_calendar_url=r.get("google_calendar_url", o.get("google_calendar_url")))

    def confirm_proposed(self, o):
        """The other side proposed an exact time and place: send the same back to make the
        outing final (brief item g). When the time is 30 min or more away from the persona's
        preferred time, counter ONE time with that time instead (T70); never twice on one plan.
        Returns the outing as it is after the call."""
        body = {"time": o["proposed_time"]}
        if o.get("proposed_place"):
            body["activity_id"] = o["proposed_place"]["id"]
        if o["plan_id"] not in self.countered:
            d, used = brain.decide_time(self.backend, self.prefs, o)
            if d["decision"] == "counter":
                self.countered.add(o["plan_id"])
                body["time"] = d["time"]
                if used in ("claude", "meta"):
                    body["backend"] = used
                try:
                    r = self.call("POST", f"outings/{o['plan_id']}/finalize/", body)
                except ApiError as e:
                    self.log(f"outing {o['plan_id']} proposed {o['proposed_time']} -> counter {d['time']} -> error {e.status}: {e}")
                    return o
                self.log(f"outing {o['plan_id']} proposed {o['proposed_time']} by {o['proposed_by']} -> counter"
                         f" {d['time']} [{used}] -> {r.get('status')}")
                return dict(o, proposed_time=d["time"], proposed_by="you")
        try:
            r = self.call("POST", f"outings/{o['plan_id']}/finalize/", body)
        except ApiError as e:
            self.log(f"outing {o['plan_id']} proposed {o['proposed_time']} by {o['proposed_by']} -> error {e.status}: {e}")
            return o
        self.log(f"outing {o['plan_id']} proposed {o['proposed_time']} by {o['proposed_by']} -> same time and place -> {r.get('status')}")
        if r.get("status") == "final":
            return dict(o, status="final", time=r.get("time"), place=r.get("place"),
                        ics_url=r.get("ics_url"), google_calendar_url=r.get("google_calendar_url"))
        return o


def load_config(path):
    with open(path) as f:
        text = f.read()
    if path.endswith((".yaml", ".yml")):
        import yaml
        return yaml.safe_load(text)
    return json.loads(text)


def read_key(spec):
    if spec.get("key"):
        return spec["key"]
    if spec.get("key_env") and os.environ.get(spec["key_env"]):
        return os.environ[spec["key_env"]]
    if spec.get("key_file"):
        with open(os.path.expanduser(spec["key_file"])) as f:
            return f.read().strip()
    return None


def build_agents(args):
    specs = []
    if args.config:
        specs = load_config(args.config).get("agents", [])
    if args.handle:
        specs.append({"name": args.name or args.handle, "handle": args.handle, "key_file": args.key_file,
                      "persona": args.persona, "likes": args.likes or [], "dislikes": args.dislikes or []})
    agents = []
    for s in specs:
        prefs = {k: s.get(k) for k in ("likes", "dislikes", "max_km", "areas", "persona", "preferred_times") if s.get(k) is not None}
        agents.append(FriendAgent(s.get("name") or s["handle"], s["handle"], read_key(s), prefs,
                                  url=args.url, backend=args.backend))
    return agents


def main(argv=None):
    ap = argparse.ArgumentParser(prog="friend_agent.py", description="Simulated Mifgash friend agents.")
    ap.add_argument("--url", default=os.environ.get("MIFGASH_URL", DEFAULT_URL))
    ap.add_argument("--config", help="JSON or YAML file with an 'agents' list")
    ap.add_argument("--handle")
    ap.add_argument("--name")
    ap.add_argument("--key-file")
    ap.add_argument("--persona")
    ap.add_argument("--likes", nargs="*")
    ap.add_argument("--dislikes", nargs="*")
    ap.add_argument("--backend", default=os.environ.get("MIFGASH_LLM_BACKEND", "stub"),
                    choices=["stub", "claude", "meta"])
    ap.add_argument("--once", action="store_true", help="poll one time and stop")
    ap.add_argument("--interval", type=float, default=5.0, help="seconds between polls")
    args = ap.parse_args(argv)
    agents = build_agents(args)
    if not agents:
        ap.error("give --config or --handle")
    missing = [a.handle for a in agents if not a.api_key]
    if missing:
        ap.error(f"no key for: {', '.join(missing)}")
    while True:
        for a in agents:
            try:
                a.poll()
            except ApiError as e:
                a.log(f"error {e.status}: {e}")
            except urllib.error.URLError as e:
                a.log(f"cannot reach {a.url}: {e.reason}")
        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
