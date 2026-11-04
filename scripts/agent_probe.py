#!/usr/bin/env python3
"""F2b (T252): can a fresh AI agent sign up to Mifgash from the setup prompt alone?

Runs the local `claude -p` (the house subscription, no API key) in an empty folder, with ONLY the
'Set me up' prompt plus one line that names the handle to use. The model may run curl and nothing
else. Then a second, observer signup asks the friend search for the handle: found = signed up.

    python3 scripts/agent_probe.py [--base https://mifgash.sveder.com] [--model sonnet]

Prints the transcript and the result. NOT part of manage.py test. Afterwards purge the zz_probe
people on the server: manage.py purge_test_people (both handles start with zz_).
"""
import argparse
import json
import secrets
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def setup_prompt(base):
    # The same words as the /setup/ page (planner.views.SETUP_PROMPT), without Django.
    src = (ROOT / "planner" / "views.py").read_text()
    start = src.index("SETUP_PROMPT = (")
    expr = src[start + len("SETUP_PROMPT = "):src.index("\n\n", start)]
    return eval(expr, {}).format(base=base, name="Mifgash")  # noqa: S307 - our own constant


def call(base, path, body=None, key=None):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "User-Agent": "mifgash-probe"})
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://mifgash.sveder.com")
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--timeout", type=int, default=600)
    a = ap.parse_args()
    base = a.base.rstrip("/")
    tag = secrets.token_hex(2)
    handle = f"zz_probe_{tag}"
    prompt = setup_prompt(base) + f"\nYou have curl. Use the handle {handle}."
    print("PROMPT:", prompt, sep="\n", flush=True)
    with tempfile.TemporaryDirectory() as empty:
        run = subprocess.run(
            ["claude", "-p", prompt, "--model", a.model, "--output-format", "text",
             "--permission-mode", "dontAsk", "--allowedTools", "Bash(curl:*)"],
            cwd=empty, capture_output=True, text=True, timeout=a.timeout)
    print("\nTRANSCRIPT (final answer):", run.stdout.strip() or "(empty)", sep="\n")
    if run.returncode:
        print("stderr:", run.stderr.strip()[-2000:])
    obs = call(base, "/api/v1/signup/", {"name": "Probe Observer", "handle": f"zz_probe_obs_{tag}",
                                         "email": f"zz_probe_obs_{tag}@example.com"})
    hits = call(base, f"/api/v1/friends/search/?q={handle}", key=obs["api_key"])["results"]
    ok = any(h["handle"] == handle for h in hits)
    print(f"\nRESULT: {'SIGNED UP' if ok else 'NOT SIGNED UP'} as @{handle}")
    print("Purge: manage.py purge_test_people (zz_probe_" + tag + " and zz_probe_obs_" + tag + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
