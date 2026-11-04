"""The decision code of a friend agent: accept or decline an outing, pick the place, confirm or
counter the exact time. Standard library only, so demo/friend_agent.py (a script on any machine)
and planner/sandbox_agent.py (the quick-demo friend on the server, M7b T179) share it.

Backends: stub (rules from the persona), claude (local `claude -p`), meta (Muse Spark Open on
Baseten: BASETEN_API_KEY, BASETEN_BASE_URL, BASETEN_MODEL). A model error falls back to the stub.
"""
import json
import os
import re
import subprocess
import time
import urllib.request

# A dislike word also covers these words in a place name or tag.
SYNONYMS = {
    "bar": ["bar", "bars", "cocktail", "cocktails", "pub", "drinks", "beer", "wine"],
    "loud": ["loud", "busy", "club"],
    "cocktails": ["cocktail", "cocktails"],
    "expensive": ["expensive", "fancy"],
}


def words(text):
    return set(re.findall(r"[a-z]+", (text or "").lower()))


def option_words(proposal, option):
    return words(" ".join([option.get("name", ""), " ".join(option.get("tags") or []), proposal.get("kind", "")]))


def disliked(prefs, proposal, option):
    """The dislike that rules this option out, or None."""
    have = option_words(proposal, option)
    for d in prefs.get("dislikes") or []:
        d = d.lower()
        if have & set(SYNONYMS.get(d, [d])):
            return d
    return None


def stub_decide(prefs, proposal):
    """{answer, choice_id, note} from the persona only. Deterministic."""
    likes = [k.lower() for k in prefs.get("likes") or []]
    kind = proposal.get("kind", "")
    if likes and kind not in likes:
        return {"answer": "decline", "choice_id": None, "note": f"not into {kind} plans"}
    options = proposal.get("options") or []
    good = [o for o in options if not disliked(prefs, proposal, o)]
    if options and not good:
        why = disliked(prefs, proposal, options[0])
        return {"answer": "decline", "choice_id": None, "note": f"does not like {why}"}
    areas = [a.lower() for a in prefs.get("areas") or []]
    good.sort(key=lambda o: 0 if (o.get("area") or "").lower() in areas else 1)
    pick = good[0]["id"] if good else None
    return {"answer": "accept", "choice_id": pick, "note": ""}


DECIDE_SYSTEM = """You are a personal social agent. Your human has this persona:
{persona}
Likes: {likes}. Dislikes: {dislikes}. Favourite areas: {areas}.
A friend proposes the outing below. Decide as your human would.
Return ONLY a JSON object: {{"answer": "accept" or "decline", "choice_id": one option id or null, "note": "short reason"}}."""


def meta_budget(where):
    """Same call cap as planner/llm.py meta_budget: MIFGASH_META_CALL_LOG + MIFGASH_META_CALL_CAP."""
    path = os.environ.get("MIFGASH_META_CALL_LOG")
    if not path:
        return lambda **row: None
    cap = int(os.environ.get("MIFGASH_META_CALL_CAP") or 0)
    used = sum(1 for _ in open(path)) if os.path.exists(path) else 0
    if cap and used >= cap:
        raise RuntimeError(f"meta call cap {cap} reached")
    start = time.monotonic()

    def done(**row):
        row = {"where": where, "seconds": round(time.monotonic() - start, 2), **row}
        with open(path, "a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return done


def llm_decide(backend, prefs, proposal):
    system = DECIDE_SYSTEM.format(persona=prefs.get("persona") or "a friendly person",
                                  likes=", ".join(prefs.get("likes") or []) or "anything",
                                  dislikes=", ".join(prefs.get("dislikes") or []) or "nothing",
                                  areas=", ".join(prefs.get("areas") or []) or "any")
    user = json.dumps({"text": proposal.get("text"), "kind": proposal.get("kind"), "date": proposal.get("date"),
                       "part": proposal.get("part"), "options": proposal.get("options")}, ensure_ascii=False)
    text = call_model(backend, system, user, "decide")
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON in model output")
    d = json.loads(m.group(0))
    ids = {o["id"] for o in proposal.get("options") or []}
    answer = "accept" if d.get("answer") == "accept" else "decline"
    choice = d.get("choice_id") if d.get("choice_id") in ids else None
    return {"answer": answer, "choice_id": choice, "note": str(d.get("note") or "")[:200]}


def keep_idea(prefs, proposal, d):
    """T405: a yes keeps the place in the offer 'Idea:' line (the first option, the model's pick).
    The friend names another place only when the persona dislikes the Idea place. The yes names the
    Idea place on purpose, so a group dinner's vote (engine.group_vote) also keeps it and does not
    fall back to the 'middle of everybody' place nobody was asked about."""
    options = proposal.get("options") or []
    if d.get("answer") != "accept" or not options:
        return d
    if not disliked(prefs, proposal, options[0]):
        return {**d, "choice_id": options[0]["id"]}
    return d


def decide(backend, prefs, proposal):
    """Returns (decision, backend used)."""
    if backend != "stub":
        try:
            return keep_idea(prefs, proposal, llm_decide(backend, prefs, proposal)), backend
        except Exception as e:  # the demo must never stop on a model error
            print(f"[{prefs.get('handle', '?')}] {backend} failed ({e.__class__.__name__}), stub decides", flush=True)
    return keep_idea(prefs, proposal, stub_decide(prefs, proposal)), "stub"


COUNTER_MIN = 30  # minutes away from the preferred time before the agent counters

TIME_SYSTEM = """You are a personal social agent. Your human has this persona:
{persona}
A friend proposes an exact time for an outing you already agreed to. Your human prefers {preferred}.
Confirm the time, or counter once with the time your human prefers.
Return ONLY a JSON object: {{"decision": "confirm" or "counter", "time": "HH:MM"}}."""


def minutes(hhmm):
    h, m = str(hhmm).split(":")
    return int(h) * 60 + int(m)


def preferred_time(prefs, outing):
    """The persona's preferred time for the outing's part, or None."""
    t = (prefs.get("preferred_times") or {}).get(outing.get("part") or "")
    try:
        minutes(t)
    except (ValueError, AttributeError):
        return None
    return t


def stub_time(prefs, outing):
    """{decision, time}: counter with the preferred time when the proposal is 30 min or more away."""
    want = preferred_time(prefs, outing)
    got = outing.get("proposed_time")
    if want and got and abs(minutes(want) - minutes(got)) >= COUNTER_MIN:
        return {"decision": "counter", "time": want}
    return {"decision": "confirm", "time": got}


# The Baseten settings. None = read the environment (demo/friend_agent.py); the server side
# (planner/sandbox_agent.py) sets a dict from the Django settings, with the same keys.
META = None


def meta_config():
    return {"key": os.environ.get("BASETEN_API_KEY", ""), "model": os.environ.get("BASETEN_MODEL", ""),
            "base_url": os.environ.get("BASETEN_BASE_URL", ""), "timeout": 90,
            "max_tokens": int(os.environ.get("MIFGASH_META_MAX_TOKENS", "4000"))}


def call_model(backend, system, user, where):
    """The raw text answer of the model ('claude' or 'meta')."""
    if backend == "claude":
        cmd = [os.environ.get("MIFGASH_CLAUDE_CLI", "claude"), "-p", "--output-format", "json",
               "--model", os.environ.get("MIFGASH_CLAUDE_MODEL", "claude-sonnet-5-5"),
               "--tools", "", "--no-session-persistence", "--system-prompt", system]
        res = subprocess.run(cmd, input=user, capture_output=True, text=True, timeout=90)
        if res.returncode != 0:
            raise RuntimeError(res.stderr.strip()[:200] or f"exit {res.returncode}")
        return json.loads(res.stdout).get("result", "")
    if backend == "meta":
        cfg = META or meta_config()
        if not cfg["key"]:
            raise RuntimeError("BASETEN_API_KEY is not set")
        body = json.dumps({"model": cfg["model"],
                           # the model reasons first; 800 tokens cut the JSON answer (T59)
                           "max_tokens": cfg["max_tokens"],
                           "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
        req = urllib.request.Request(cfg["base_url"].rstrip("/") + "/chat/completions",
                                     data=body.encode(), headers={"Authorization": f"Api-Key {cfg['key']}",
                                                                  "Content-Type": "application/json"})
        done = meta_budget(where)
        try:
            with urllib.request.urlopen(req, timeout=cfg["timeout"]) as r:
                data = json.load(r)
            msg = data["choices"][0]["message"]
        except Exception as e:
            done(error=f"{e.__class__.__name__}: {e}"[:200])
            raise
        done(content=(msg.get("content") or "")[:400], finish=data["choices"][0].get("finish_reason"),
             tokens=(data.get("usage") or {}).get("completion_tokens"))
        return msg.get("content") or msg.get("reasoning_content") or msg.get("reasoning") or ""
    raise ValueError(f"unknown backend {backend}")


def llm_time(backend, prefs, outing):
    want = preferred_time(prefs, outing)
    if not want:
        return stub_time(prefs, outing)
    system = TIME_SYSTEM.format(persona=prefs.get("persona") or "a friendly person",
                                preferred=f"{want} for {outing.get('part')}")
    user = json.dumps({"kind": outing.get("kind"), "date": outing.get("date"), "part": outing.get("part"),
                       "proposed_time": outing.get("proposed_time"), "proposed_by": outing.get("proposed_by"),
                       "place": (outing.get("proposed_place") or {}).get("name")}, ensure_ascii=False)
    m = re.search(r"\{.*\}", call_model(backend, system, user, "time"), re.S)
    if not m:
        raise ValueError("no JSON in model output")
    d = json.loads(m.group(0))
    if d.get("decision") == "counter":
        t = str(d.get("time") or want)
        minutes(t)  # a bad time raises, so the stub decides
        if t != outing.get("proposed_time"):
            return {"decision": "counter", "time": t}
    return {"decision": "confirm", "time": outing.get("proposed_time")}


def decide_time(backend, prefs, outing):
    """Returns ({decision, time}, backend used). A model error falls back to the stub rule."""
    if backend != "stub" and preferred_time(prefs, outing):
        try:
            return llm_time(backend, prefs, outing), backend
        except Exception as e:  # the demo must never stop on a model error
            print(f"[{prefs.get('handle', '?')}] {backend} failed ({e.__class__.__name__}), stub decides the time", flush=True)
    return stub_time(prefs, outing), "stub"
