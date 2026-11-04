"""Screenshots of every page, light and dark, phone and desktop (T123).

  python3 manage.py screens [--url https://mifgash.sveder.com] [--out DIR] [--keep]

1. Signs up a zz_ test person through the live API and adds the demo friends Maria and Jordan.
2. Makes the dashboard states in the database: an ask from Maria, one plan that waits for the owner,
   one confirmed and one final outing, one plan still looking. Dates are 8-12 days ahead, so the
   hand test (tomorrow) does not meet them.
3. Drives headless Chromium over the DevTools protocol and saves a full-page PNG of each page with a
   390x844 and a 1280x800 viewport, with prefers-color-scheme light and dark.
4. Purges the test person and everything it touched (purge_test_people), also on failure.

Needs the websocket-client package (pip install websocket-client) and a Chromium build; set
MIFGASH_CHROME to the binary, else the Playwright cache is searched. The server must use the same
database as this command.
"""
import base64
import datetime as dt
import glob
import json
import os
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from planner import llm, matching
from planner.api import log_post
from planner.management.commands.purge_test_people import delete
from planner.models import Activity, MagicLink, Offer, Person, Plan

SIZES = [("390", 390, 844, True), ("1280", 1280, 800, False)]
THEMES = ["light", "dark"]


def find_chrome():
    if os.environ.get("MIFGASH_CHROME"):
        return os.environ["MIFGASH_CHROME"]
    found = sorted(glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome")))
    for name in ("chromium", "chromium-browser", "google-chrome"):
        if shutil.which(name):
            found.append(shutil.which(name))
    if not found:
        raise CommandError("no Chromium found; set MIFGASH_CHROME")
    return found[0]


def api(base, path, body=None, key=None):
    req = urllib.request.Request(base + "/api/v1/" + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


class Browser:
    """One headless Chromium tab, driven over the DevTools protocol."""

    def __init__(self, chrome):
        import websocket  # websocket-client; imported here so manage.py test does not need it
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        self.profile = tempfile.mkdtemp(prefix="mif-screens-")
        self.proc = subprocess.Popen([chrome, "--headless=new", f"--remote-debugging-port={port}",
                                      f"--user-data-dir={self.profile}", "--no-first-run", "--hide-scrollbars",
                                      "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ws_url = None
        for _ in range(100):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=2) as r:
                    ws_url = next(t["webSocketDebuggerUrl"] for t in json.loads(r.read()) if t["type"] == "page")
                break
            except Exception:
                time.sleep(0.1)
        if not ws_url:
            self.close()
            raise CommandError("Chromium did not start")
        self.ws = websocket.create_connection(ws_url, timeout=30, suppress_origin=True)
        self.n = 0
        for m in ("Page.enable", "Network.enable", "Runtime.enable"):
            self.call(m)

    def call(self, method, **params):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.n:
                if "error" in msg:
                    raise CommandError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def wait_load(self, timeout=15):
        end = time.time() + timeout
        while time.time() < end:
            if self.eval("document.readyState") == "complete":
                return
            time.sleep(0.1)

    def eval(self, js):
        return self.call("Runtime.evaluate", expression=js, returnByValue=True).get("result", {}).get("value")

    def go(self, url):
        self.call("Page.navigate", url=url)
        time.sleep(0.3)
        self.wait_load()

    def look(self, width, height, mobile, theme):
        self.call("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=1, mobile=mobile)
        self.call("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": theme}])

    def shot(self, path):
        self.eval("document.fonts && document.fonts.ready.then(() => 1)")
        time.sleep(0.25)
        # The whole page, not only the first screen: the lower dashboard sections change too.
        w, h = self.eval("[window.innerWidth, Math.max(window.innerHeight, document.documentElement.scrollHeight)]")
        data = self.call("Page.captureScreenshot", format="png", captureBeyondViewport=True,
                         clip={"x": 0, "y": 0, "width": w, "height": min(h, 6000), "scale": 1})["data"]
        with open(path, "wb") as f:
            f.write(base64.b64decode(data))

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass
        self.proc.terminate()
        try:
            self.proc.wait(5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        shutil.rmtree(self.profile, ignore_errors=True)


def make_states(me, maria, jordan, today):
    """The dashboard states, written straight to the database. Returns the URLs to shoot."""
    day = lambda n: today + dt.timedelta(days=n)  # noqa: E731
    area = me.home_area
    lunch = list(Activity.objects.filter(kind="lunch", area=area)[:1]) or list(Activity.objects.filter(kind="lunch")[:1])
    evening = list(Activity.objects.filter(kind="evening")[:3])
    weekend = list(Activity.objects.filter(kind="weekend")[:3]) or evening
    later = timezone.now() + dt.timedelta(days=2)
    # A weekend plan sits on a Saturday or a Sunday (the US week, T395), never on a weekday (T149).
    weekend_day = next(d for d in (day(11 + i) for i in range(7)) if d.weekday() in matching.WEEKEND)

    def plan(status, date, part, kind, options, **kw):
        p = Plan.objects.create(owner=kw.pop("owner", me), raw_text=kw.pop("text", f"free {kind}"), kind=kind,
                                date=date, part=part, area=kw.pop("area", area), status=status, **kw)
        p.options.set(options)
        if p.owner_id == me.pk:  # the agent's post and the 'Read as' row, so the log is not empty
            log_post(p, p.raw_text, {"backend": "stub"})
        return p

    def offer(pl, person, status, choice=None):
        # Every sent offer carries the 'Why it fits' sentence, as the product writes it (T149).
        return Offer.objects.create(plan=pl, person=person, order=0, status=status, choice=choice,
                                    reason=llm.reason_fallback(pl), reason_backend="",
                                    sent_at=timezone.now(), expires_at=later,
                                    answered_at=timezone.now() if status != "pending" else None)

    # A friend's ask that waits for me.
    ask = plan("asking", day(8), "evening", "evening", evening, owner=maria, area=maria.home_area or area)
    offer(ask, me, "pending")
    # My plan: Jordan (no agent) said yes on the human page, I must approve.
    wait = plan("asking", day(9), "lunch", "lunch", lunch)
    wait_offer = offer(wait, jordan, "owner_wait", lunch[0] if lunch else None)
    # My plan: Jordan is asked now, on the human page.
    pending = plan("asking", day(10), "evening", "evening", evening)
    pending_offer = offer(pending, jordan, "pending")
    # Confirmed with Maria, no exact time yet.
    conf = plan("confirmed", weekend_day, "morning", "weekend", weekend, chosen=weekend[0] if weekend else None)
    offer(conf, maria, "accepted", conf.chosen)
    # Final with Jordan: time, place, calendar.
    final = plan("final", day(12), "evening", "evening", evening, chosen=evening[1] if len(evening) > 1 else None,
                 exact_time=dt.time(20, 30))
    final_offer = offer(final, jordan, "accepted", final.chosen)
    # Confirmed with Jordan, no exact time yet: Jordan picks or agrees it on the human page (T121).
    # Three lunch places, so the human page shows the place select on its own row (T202).
    lunch3 = lunch + [a for a in Activity.objects.filter(kind="lunch").exclude(pk__in=[x.pk for x in lunch])[:2]]
    agreed = plan("confirmed", day(14), "lunch", "lunch", lunch3, chosen=lunch3[0] if lunch3 else None)
    agreed_offer = offer(agreed, jordan, "accepted", agreed.chosen)
    # A plan that closed while Jordan's ask was still open.
    shut = plan("no_match", day(15), "evening", "evening", evening)
    closed_offer = offer(shut, jordan, "closed")
    # Still looking.
    plan("open", day(13), "lunch", "lunch", [])
    return {"conf": conf.uid, "final": final.uid, "h_pending": pending_offer.token, "h_wait": wait_offer.token,
            "h_set": final_offer.token, "h_agreed": agreed_offer.token, "h_closed": closed_offer.token}


class Command(BaseCommand):
    help = "Screenshots of every page at 390x844 and 1280x800, light and dark, with a zz_ test person."

    def add_arguments(self, parser):
        parser.add_argument("--url", default=os.environ.get("MIFGASH_SCREENS_URL", "https://mifgash.sveder.com"))
        parser.add_argument("--out", help="folder; default media/screens/<YYYYMMDD-HHMM> in the repo")
        parser.add_argument("--keep", action="store_true", help="do not purge the test person (to look by hand)")

    def handle(self, *args, **o):
        base = o["url"].rstrip("/")
        out = o["out"] or os.path.join("media", "screens", timezone.localtime().strftime("%Y%m%d-%H%M"))
        os.makedirs(out, exist_ok=True)
        handle = "zz_scr" + secrets.token_hex(2)
        browser = None
        try:
            r = api(base, "signup/", {"name": "Alex Screens", "handle": handle, "home_area": "SoMa"})
            key, link = r["api_key"], r["dashboard_url"]
            for friend in ("maria", "jordan"):
                try:
                    api(base, "friends/", {"handle": friend}, key=key)
                except urllib.error.HTTPError as e:
                    if e.code != 409:
                        raise
            me = Person.objects.get(handle=handle)
            maria, jordan = Person.objects.get(handle="maria"), Person.objects.get(handle="jordan")
            ids = make_states(me, maria, jordan, timezone.localdate())
            token = link.rstrip("/").rsplit("/", 1)[1]
            expired, expired_token = MagicLink.issue(me)
            expired.expires_at = timezone.now() - dt.timedelta(hours=1)
            expired.save(update_fields=["expires_at"])
            owner = Person.objects.filter(is_owner=True).first()

            browser = Browser(find_chrome())
            pages = [("landing", "/"), ("link-open", f"/d/{token}/")]  # before the login spends the link
            after = [("dashboard", "/d/"), ("outing-confirmed", f"/outing/{ids['conf']}/"),
                     ("outing-final", f"/outing/{ids['final']}/"), ("friends", "/friends/"),
                     ("human-pending", f"/h/{ids['h_pending']}/"), ("human-waiting", f"/h/{ids['h_wait']}/"),
                     ("human-set", f"/h/{ids['h_set']}/"), ("human-agreed", f"/h/{ids['h_agreed']}/"),
                     ("human-closed", f"/h/{ids['h_closed']}/"), ("link-used", f"/d/{token}/"),
                     ("link-expired", f"/d/{expired_token}/")]
            if owner:
                after.append(("open-times", f"/open/{owner.token}/"))
            saved = self.shoot(browser, base, pages, out)
            browser.go(base + f"/d/{token}/")
            browser.eval("document.querySelector('form').submit()")
            time.sleep(0.5)
            browser.wait_load()
            if not browser.eval("location.pathname").startswith("/d/"):
                raise CommandError("dashboard login failed")
            saved += self.shoot(browser, base, after, out)
        finally:
            if browser:
                browser.close()
            if not o["keep"]:
                people = list(Person.objects.filter(handle=handle))
                if people:
                    with transaction.atomic():
                        delete(people)
        light = sum(1 for f in saved if "-light-" in f)
        self.stdout.write(f"{len(saved)} PNGs ({light} light, {len(saved) - light} dark) in {os.path.abspath(out)}")
        self.stdout.write(f"test person @{handle} " + ("kept" if o["keep"] else "purged"))

    def shoot(self, browser, base, pages, out):
        saved = []
        for name, path in pages:
            for theme in THEMES:
                for label, w, h, mobile in SIZES:
                    browser.look(w, h, mobile, theme)
                    browser.go(base + path)
                    browser.eval("localStorage.removeItem('mif-theme'); document.documentElement.removeAttribute('data-theme')")
                    f = os.path.join(out, f"{name}-{theme}-{label}.png")
                    browser.shot(f)
                    saved.append(f)
        return saved
