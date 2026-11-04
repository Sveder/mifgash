#!/usr/bin/env python3
"""T403 step 1: does the Baseten chat/completions endpoint for Muse Spark Open take OpenAI tools?

Makes ONE live call with tools=[find_places, check_hours] and tool_choice 'auto' and prints whether
the answer carries tool_calls. The key comes from the env (BASETEN_API_KEY, or the env file named
by MIFGASH_META_ENV) and is never printed. NOT part of manage.py test.

    MIFGASH_META_ENV=/path/to/.baseten.env python3 scripts/muse_tools_probe.py
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from planner.pick_tools import TOOLS  # noqa: E402


def load_env(path):
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main():
    if os.environ.get("MIFGASH_META_ENV"):
        load_env(os.environ["MIFGASH_META_ENV"])
    key = os.environ.get("BASETEN_API_KEY")
    if not key:
        sys.exit("BASETEN_API_KEY is not set")
    base = os.environ.get("BASETEN_BASE_URL", "https://inference.baseten.co/v1").rstrip("/")
    model = os.environ.get("BASETEN_MODEL", "meta-models/muse-spark-open-1026")
    body = {"model": model, "max_tokens": 4000, "tool_choice": "auto", "tools": TOOLS, "messages": [
        {"role": "system", "content": "You pick a place for a lunch. Before you pick, check that the "
                                      "place is open: call check_hours. Then answer {\"id\": N}."},
        {"role": "user", "content": "Plan: lunch on Thu Nov 5 2026 (2026-11-05), near Mission.\n"
                                    "Candidates:\n  id 101: La Taqueria; mexican\n  id 102: Tartine; bakery"}]}
    req = urllib.request.Request(base + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Api-Key {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode(errors='replace')[:300]}")
        print("tool_calls supported: no (HTTP error)")
        return 1
    choice = data["choices"][0]
    msg = choice["message"]
    calls = msg.get("tool_calls") or []
    print("finish_reason:", choice.get("finish_reason"))
    print("content:", (msg.get("content") or "")[:300])
    for c in calls:
        print("tool_call:", c.get("function", {}).get("name"), c.get("function", {}).get("arguments"))
    print("tool_calls supported:", "yes" if calls else "no (plain text answer)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
