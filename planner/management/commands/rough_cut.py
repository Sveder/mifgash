"""A silent rough cut of the web shots in demo/VIDEO.md (T146).

  python3 manage.py rough_cut [--url https://mifgash.sveder.com] [--out media/rough-cut] [--copy-to DIR] [--keep]

Uses the same set-up as manage.py screens: a zz_scr test person, Maria and Jordan, and the dashboard
states (an ask, an open plan, a confirmed and a final outing). Then it drives headless Chromium in
dark mode and grabs viewport frames for each segment: the landing page at 1280x800, the dashboard,
the human page before and after "Yes, I am in" and the outing ticket at 390x844. ffmpeg puts the
frames on one 1280x844 canvas, joins the segments with a crossfade and writes an H.264 mp4 with no
sound. The test person is purged at the end, also on failure.

The frames hold the viewport only, never a browser address bar. A segment fails when its page text
holds a LAN address, a loopback address or a tailnet name.
"""
import base64
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import time
import urllib.error

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from planner.management.commands.purge_test_people import delete
from planner.management.commands.screens import Browser, api, find_chrome, make_states
from planner.models import Person

W, H = 1280, 844  # the canvas: the landing at 1280x800 and a 390x844 phone both fit
FPS = 8
FADE = 1.5
BG = "0x0e1116"  # close to the dark-mode page background
PRIVATE = re.compile(r"\b(?:10|127|192\.168|172\.(?:1[6-9]|2\d|3[01]))(?:\.\d{1,3}){2,3}\b|ts\.net")


def private_text(text):
    """The first LAN, loopback or tailnet address in a page text, or None."""
    m = PRIVATE.search(text or "")
    return m.group(0) if m else None


def segment_filter():
    """Scale a frame to the canvas height when it is taller, and centre it on the dark canvas."""
    return (f"scale=-2:'min({H},ih)',pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color={BG},"
            f"fps=25,format=yuv420p,setsar=1")


def xfade_graph(durations):
    """The filter graph that joins N segments with a FADE-second crossfade. Returns (graph, total)."""
    if len(durations) == 1:
        return "[0:v]null[v]", durations[0]
    parts, prev, offset = [], "[0:v]", 0.0
    for i in range(1, len(durations)):
        offset += durations[i - 1] - FADE
        out = "[v]" if i == len(durations) - 1 else f"[x{i}]"
        parts.append(f"{prev}[{i}:v]xfade=transition=fade:duration={FADE}:offset={offset:.3f}{out}")
        prev = out
    return ";".join(parts), offset + durations[-1]


class Command(BaseCommand):
    help = "Silent rough cut (mp4) of the landing, the dashboard, the human page and the outing ticket."

    def add_arguments(self, parser):
        parser.add_argument("--url", default=os.environ.get("MIFGASH_SCREENS_URL", "https://mifgash.sveder.com"))
        parser.add_argument("--out", default=os.path.join("media", "rough-cut"))
        parser.add_argument("--copy-to", help="also copy the mp4 into this folder as <stamp>-T146-rough-cut.mp4")
        parser.add_argument("--keep", action="store_true", help="do not purge the test person")

    def handle(self, *args, **o):
        if not shutil.which("ffmpeg"):
            raise CommandError("ffmpeg is missing")
        base = o["url"].rstrip("/")
        stamp = timezone.localtime().strftime("%Y%m%d-%H%M")
        os.makedirs(o["out"], exist_ok=True)
        work = tempfile.mkdtemp(prefix="mif-cut-")
        handle = "zz_scr" + secrets.token_hex(2)
        browser = None
        try:
            r = api(base, "signup/", {"name": "Alex", "handle": handle, "home_area": "SoMa"})
            key, link = r["api_key"], r["dashboard_url"]
            for friend in ("maria", "jordan"):
                try:
                    api(base, "friends/", {"handle": friend}, key=key)
                except urllib.error.HTTPError as e:
                    if e.code != 409:
                        raise
            me = Person.objects.get(handle=handle)
            ids = make_states(me, Person.objects.get(handle="maria"), Person.objects.get(handle="jordan"),
                              timezone.localdate())
            token = link.rstrip("/").rsplit("/", 1)[1]

            browser = Browser(find_chrome())
            browser.call("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "dark"}])
            segs = []

            def seg(name, path, secs, size=(390, 844, True), scroll=0.0, top=0):
                browser.call("Emulation.setDeviceMetricsOverride", width=size[0], height=size[1],
                             deviceScaleFactor=1, mobile=size[2])
                if path:
                    browser.go(base + path)
                leak = private_text(browser.eval("document.body.innerText"))
                if leak:
                    raise CommandError(f"{name}: the page shows {leak}")
                segs.append(self.record(browser, os.path.join(work, name), secs, scroll, top))
                self.stdout.write(f"  {name}: {segs[-1][1]:.1f} s")

            seg("landing", "/", 7, size=(1280, 800, False), scroll=0.6)  # VIDEO.md shots 1, 2 and 14
            browser.go(base + f"/d/{token}/")
            browser.eval("document.querySelector('form').submit()")
            time.sleep(0.5)
            browser.wait_load()
            if not browser.eval("location.pathname").startswith("/d/"):
                raise CommandError("dashboard login failed")
            seg("dashboard", None, 6)  # shot 4/7: the dashboard and the open plan
            # Shot 8: scroll down to the match card and the agent log.
            seg("matches", None, 8, scroll=1.0, top=browser.eval("window.innerHeight") * 0.6)
            seg("human-ask", f"/h/{ids['h_pending']}/", 7, scroll=0.5)  # shot 11, before the yes
            browser.eval("document.querySelector('button[value=yes]').click()")
            time.sleep(0.6)
            browser.wait_load()
            seg("human-yes", None, 5)  # shot 11, after the yes
            seg("outing", f"/outing/{ids['final']}/", 8, scroll=1.0)  # shots 9 and 10: the final ticket

            mp4 = os.path.abspath(os.path.join(o["out"], f"{stamp}.mp4"))
            total = self.join(segs, mp4)
        finally:
            if browser:
                browser.close()
            if not o["keep"]:
                people = list(Person.objects.filter(handle=handle))
                if people:
                    with transaction.atomic():
                        delete(people)
            shutil.rmtree(work, ignore_errors=True)
        size = os.path.getsize(mp4)
        self.stdout.write(f"{mp4}: {total:.1f} s, {size / 1e6:.1f} MB")
        if o["copy_to"]:
            os.makedirs(o["copy_to"], exist_ok=True)
            dest = os.path.join(o["copy_to"], f"{stamp}-T146-rough-cut.mp4")
            shutil.copy(mp4, dest)
            self.stdout.write(f"copied to {dest}")
        self.stdout.write(f"test person @{handle} " + ("kept" if o["keep"] else "purged"))

    def record(self, browser, folder, secs, scroll, top):
        """Grab viewport frames for secs seconds. With scroll > 0 the page scrolls down by that share
        of its free height in the middle of the segment (from top, in px). Returns (concat file, secs)."""
        os.makedirs(folder)
        browser.eval("document.fonts && document.fonts.ready.then(() => 1)")
        room = browser.eval("Math.max(0, document.documentElement.scrollHeight - window.innerHeight)") or 0
        start_y = min(top, room)
        end_y = start_y + (room - start_y) * scroll
        browser.eval(f"window.scrollTo(0, {start_y})")
        frames, t0 = [], time.time()
        while True:
            t = time.time() - t0
            if t >= secs:
                break
            if scroll:  # still for the first and last 20 %, then a steady scroll
                k = min(1.0, max(0.0, (t / secs - 0.2) / 0.6))
                browser.eval(f"window.scrollTo(0, {start_y + (end_y - start_y) * k:.0f})")
            data = browser.call("Page.captureScreenshot", format="jpeg", quality=90)["data"]
            path = os.path.join(folder, f"{len(frames):05d}.jpg")
            with open(path, "wb") as f:
                f.write(base64.b64decode(data))
            frames.append((path, time.time() - t0))
            time.sleep(max(0.0, 1 / FPS - (time.time() - t0 - frames[-1][1])))
        lst = os.path.join(folder, "frames.txt")
        with open(lst, "w") as f:
            for i, (path, at) in enumerate(frames):
                end = frames[i + 1][1] if i + 1 < len(frames) else secs
                f.write(f"file '{path}'\nduration {max(end - at, 0.04):.3f}\n")
            f.write(f"file '{frames[-1][0]}'\n")  # the concat demuxer drops the last duration otherwise
        return lst, secs

    def join(self, segs, mp4):
        clips, durations = [], []
        for i, (lst, secs) in enumerate(segs):
            clip = os.path.join(os.path.dirname(lst), "clip.mp4")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                            "-vf", segment_filter(), "-t", f"{secs}", "-an", "-c:v", "libx264",
                            "-preset", "medium", "-crf", "23", clip], check=True)
            clips.append(clip)
            durations.append(secs)
        graph, total = xfade_graph(durations)
        cmd = ["ffmpeg", "-v", "error", "-y"]
        for c in clips:
            cmd += ["-i", c]
        cmd += ["-filter_complex", graph, "-map", "[v]", "-an", "-c:v", "libx264", "-preset", "medium",
                "-crf", "26", "-pix_fmt", "yuv420p", "-movflags", "+faststart", mp4]
        subprocess.run(cmd, check=True)
        return total
