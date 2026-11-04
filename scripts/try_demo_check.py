#!/usr/bin/env python3
"""M7c (T180): time the quick demo on a live site, the way a visitor clicks it. No key needed.

    python3 scripts/try_demo_check.py [https://mifgash.sveder.com] [--limit 60]

Steps: POST /try/, send the pre-filled line, wait for Maria's yes (the match), approve, wait for her
time, agree, wait for 'It is set', read the outing card. Prints the seconds per step. Exit 1 when the
whole run takes more than --limit seconds or a step does not arrive.
"""
import argparse
import html
import re
import sys
import time

import requests

STEP_WAIT = 90  # seconds one step may wait before the run fails
POLL = 1.0


def csrf(page):
    m = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page)
    if not m:
        raise SystemExit("no CSRF token on the page")
    return m.group(1)


class Run:
    def __init__(self, base):
        self.base = base.rstrip("/")
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "mifgash-try-demo-check/1"
        self.t0 = time.monotonic()
        self.last = self.t0
        self.rows = []

    def url(self, path):
        return self.base + path

    def post(self, path, data, page):
        data = dict(data, csrfmiddlewaretoken=csrf(page))
        r = self.s.post(self.url(path), data=data, headers={"Referer": self.url(path)}, timeout=60)
        r.raise_for_status()
        return r.text

    def dash(self):
        r = self.s.get(self.url("/d/"), timeout=30)
        r.raise_for_status()
        return r.text

    def wait(self, pattern, what):
        end = time.monotonic() + STEP_WAIT
        while True:
            page = self.dash()
            m = re.search(pattern, page, re.S)
            if m:
                return page, m
            if time.monotonic() > end:
                raise SystemExit(f"FAIL: {what} did not arrive in {STEP_WAIT} s")
            time.sleep(POLL)

    def mark(self, step):
        now = time.monotonic()
        self.rows.append((step, now - self.last, now - self.t0))
        print(f"{step:<34} {now - self.last:6.1f} s   total {now - self.t0:6.1f} s", flush=True)
        self.last = now


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base", nargs="?", default="https://mifgash.sveder.com")
    ap.add_argument("--limit", type=float, default=60)
    a = ap.parse_args()
    r = Run(a.base)

    page = r.s.get(r.url("/"), timeout=30).text  # the landing hero form, as a visitor clicks it
    page = r.post("/try/", {}, page)
    if "sandbox-form" not in page:
        raise SystemExit("FAIL: POST /try/ did not open a demo dashboard (rate limit or busy?)")
    r.mark("Try it now (POST /try/)")

    text = html.unescape(re.search(r'id="sandbox-text"[^>]*value="([^"]*)"', page).group(1))
    page = r.post("/d/free/", {"text": text}, page)
    if 'class="err"' in page:
        raise SystemExit("FAIL: the free time was not posted: " + re.search(r'class="err">([^<]*)', page).group(1))
    r.mark("send the pre-filled line")

    page, m = r.wait(r'action="(/d/answer/\d+/)"', "Maria's yes")
    r.mark("Maria's agent says yes (match)")

    page = r.post(m.group(1), {"answer": "accept"}, page)
    r.mark("approve the match")

    page, m = r.wait(r'<form method="post" action="(/d/finalize/\d+/)" class="agree">.*?name="time" value="([^"]+)">'
                     r'<input type="hidden" name="activity_id" value="(\d+)">', "Maria's time")
    r.mark(f"Maria's agent proposes {m.group(2)}")

    page = r.post(m.group(1), {"time": m.group(2), "activity_id": m.group(3)}, page)
    page, _ = r.wait(r'class="status set">It is set', "the final outing")
    r.mark("agree, outing is set")

    card = re.search(r'<article class="card ticket"[^>]*>(.*?)</article>', page, re.S).group(1)
    words = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", card)).split())
    words = re.sub(r"\s+(Add to calendar|Google Calendar|Map|Outing page)", "", words)
    print("outing card:", words[:200])
    total = time.monotonic() - r.t0
    ok = total <= a.limit and "ics" in card
    print(f"{'OK' if ok else 'FAIL'}: {total:.1f} s (limit {a.limit:.0f} s)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
