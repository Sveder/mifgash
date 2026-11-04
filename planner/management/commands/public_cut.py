"""A silent rough cut of the public demo run, with captions (1/11/2026).

  python3 manage.py public_cut --url https://mifgash.sveder.com --link <one-time dashboard link>
      --plan <outing id> --calendar <calendar short link> --transcript <file.md> --out DIR

It films the PUBLIC site, not the local one: the landing page (light and dark), agents.md, the
owner's dashboard and the outing ticket (light and dark), the calendar page, plus three cards made
here: the title, the Telegram ask (a stand-in until Michael records his phone) and the WhatsApp
chat with the other agent (from the transcript file). Each segment gets a burned-in caption
(ffmpeg drawtext). The segments are joined into one H.264 mp4 with no sound.

The frames hold the viewport only, never an address bar. A page whose text holds a LAN, loopback
or tailnet address stops the cut. The dashboard link is spent by the login.
"""
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
import time

from django.core.management.base import BaseCommand, CommandError

from planner.management.commands.rough_cut import BG, FPS, H, W, Command as RoughCut, private_text
from planner.management.commands.screens import Browser, find_chrome
from planner.management.commands import cut_v2

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

CARD_CSS = """
body{margin:0;height:100vh;display:flex;align-items:center;justify-content:center;
font-family:system-ui,-apple-system,'Segoe UI',sans-serif;background:#0e1116;color:#e8eaf0}
.c{max-width:900px;padding:40px;text-align:center}
h1{font-size:64px;margin:0 0 16px;letter-spacing:-1px}
p{font-size:28px;line-height:1.4;color:#b8bfcc;margin:8px 0}
.tag{display:inline-block;margin-top:24px;padding:6px 14px;border-radius:999px;background:#2a2f3a;font-size:20px;color:#9aa3b5}
.chat{width:390px;margin:0 auto;text-align:left}
.top{background:#1f2c34;color:#e9edef;padding:14px 16px;font-size:17px;font-weight:600;border-radius:14px 14px 0 0}
.log{background:#0b141a;padding:12px 10px 24px;border-radius:0 0 14px 14px}
.b{max-width:82%;margin:6px 0;padding:8px 11px;border-radius:10px;font-size:15px;line-height:1.35;white-space:pre-wrap}
.me{background:#005c4b;color:#e9edef;margin-left:auto}
.them{background:#202c33;color:#e9edef}
.t{display:block;font-size:11px;color:#8696a0;text-align:right;margin-top:3px}
.tg .top{background:#17212b}.tg .log{background:#0e1621}.tg .me{background:#2b5278}.tg .them{background:#182533}
"""


def card(body):
    return f"<!doctype html><meta charset=utf-8><meta name=viewport content=\"width=device-width\"><style>{CARD_CSS}</style>{body}"


def chat_html(title, rows, cls=""):
    bubbles = "".join(f'<div class="b {side}">{html.escape(text)}<span class="t">{html.escape(t)}</span></div>'
                      for side, t, text in rows)
    return card(f'<div class="chat {cls}"><div class="top">{html.escape(title)}</div>'
                f'<div class="log">{bubbles}</div></div>')


def transcript_rows(path):
    """(side, time, text) from the transcript file: '**HH:MM Who:** text' blocks."""
    rows = []
    for m in re.finditer(r"\*\*(\d\d:\d\d) ([^:*]+):\*\* (.*?)(?=\n\*\*\d\d:\d\d |\Z)", open(path).read(), re.S):
        t, who, text = m.groups()
        text = text.strip()
        if text.startswith("["):
            continue  # a removed link or an ignored offer: not on screen
        side = "me" if who.startswith("Kurt") else "them"
        if side == "me":
            text = text.split("\n\nSteps:")[0] if "Steps:" in text else text
        rows.append((side, t, text[:420]))
    return rows


class Command(BaseCommand):
    help = "Silent rough cut with captions of the public demo run."

    def add_arguments(self, parser):
        parser.add_argument("--url", default="https://mifgash.sveder.com")
        parser.add_argument("--link", help="one-time dashboard link of the owner")
        parser.add_argument("--plan", help="the final outing uid (the uuid in /outing/<uid>/)")
        parser.add_argument("--calendar", help="calendar short link of the outing")
        parser.add_argument("--transcript")
        parser.add_argument("--out", required=True)
        # v2 (T184): python3 manage.py public_cut --v2 --run demo/video-run.json --links <file, chmod 600>
        #   --out media/mifgash-demo/mifgash-demo-v2.mp4
        parser.add_argument("--v2", action="store_true", help="the narrated v2 cut from demo/narration.json")
        parser.add_argument("--run", help="v2: demo/video_run.py output (plan id, calendar link)")
        parser.add_argument("--links", help="v2: JSON file with one-time dashboard tokens and /h/ tokens")
        parser.add_argument("--narration", default="demo/narration.json")
        parser.add_argument("--log-out", default="demo/video-run-log.json", help="v2: where the plan log JSON goes")

    def handle(self, *args, **o):
        if not shutil.which("ffmpeg"):
            raise CommandError("ffmpeg is missing")
        if o["v2"]:
            return V2(self, o).make()
        if not all(o.get(k) for k in ("link", "plan", "calendar", "transcript")):
            raise CommandError("v1 needs --link, --plan, --calendar and --transcript")
        base = o["url"].rstrip("/")
        work = tempfile.mkdtemp(prefix="mif-pubcut-")
        os.makedirs(o["out"], exist_ok=True)
        browser = Browser(find_chrome())
        rec = RoughCut()
        clips = []
        try:
            def look(w, h, mobile, theme):
                browser.call("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1, mobile=mobile)
                browser.call("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": theme}])

            def seg(name, caption, secs, url=None, page=None, size=(1280, 800, False), theme="dark", scroll=0.0, top=0):
                look(*size, theme)
                if page is not None:
                    path = os.path.join(work, f"{name}.html")
                    with open(path, "w") as f:
                        f.write(page)
                    browser.go("file://" + path)
                elif url:
                    browser.go(url)
                leak = private_text(browser.eval("document.body.innerText"))
                if leak:
                    raise CommandError(f"{name}: the page shows {leak}")
                lst, _ = rec.record(browser, os.path.join(work, name), secs, scroll, top)
                clips.append(self.clip(lst, caption, os.path.join(work, f"{name}.mp4"), theme))
                self.stdout.write(f"  {name}: {secs} s")

            seg("title", "Mifgash: your AI agent finds a friend who is free when you are.", 5,
                page=card('<div class="c"><h1>Mifgash</h1><p>Tell your own AI agent when you are free.</p>'
                          '<p>It finds a friend who is free too, and books the outing.</p>'
                          '<span class="tag">Muse Spark Open on Baseten</span></div>'))
            seg("ask", "1. The owner asks his own agent (Kurt, on Telegram). Stand-in card.", 6,
                page=chat_html("Kurt (Telegram)", [
                    ("me", "01:24", "Kurt, sign me up to Mifgash. I am free Tuesday evening near Noe Valley."),
                    ("them", "01:25", "Done. You are @chris_demo. Posted: free Tue 3/11 evening, near Noe Valley. No match yet. Mifgash keeps looking.")],
                    "tg"), size=(390, 844, True))
            seg("landing", "2. No chat on the site. Your agent uses the API; you see the result.", 8,
                url=base + "/", scroll=0.7)
            seg("landing-light", "Light mode too.", 4, url=base + "/", theme="light")
            seg("agents-md", "3. Any agent can join: one plain page, /agents.md, explains the API.", 6,
                url=base + "/agents.md", size=(560, 844, False), scroll=0.5)
            rows = transcript_rows(o["transcript"])
            seg("whatsapp", "4. Another agent, Instinct on WhatsApp, read agents.md and signed up alone.", 14,
                page=chat_html("Instinct (WhatsApp)", rows), size=(390, 844, True), scroll=1.0)
            browser.go(o["link"])
            browser.eval("document.querySelector('form').submit()")
            time.sleep(0.6)
            browser.wait_load()
            if not browser.eval("location.pathname").startswith("/d/"):
                raise CommandError("dashboard login failed")
            seg("dashboard", "5. The dashboard: the match, the approval and the agent log.", 10,
                size=(390, 844, True), scroll=1.0)
            seg("outing", "6. The outing card: place, time, map and parking.", 8,
                url=f"{base}/outing/{o['plan']}/", size=(390, 844, True), scroll=1.0)
            seg("outing-light", "Light mode.", 4, url=f"{base}/outing/{o['plan']}/", size=(390, 844, True), theme="light")
            seg("calendar", "7. One tap adds it to the calendar (.ics or Google Calendar).", 5,
                url=o["calendar"], size=(390, 844, True))
            seg("end", "mifgash.sveder.com - Made by Sveder", 5,
                page=card('<div class="c"><h1>Mifgash</h1><p>Two agents. One outing. No group chat.</p>'
                          '<p>mifgash.sveder.com</p><span class="tag">Made by Sveder</span></div>'))
        finally:
            browser.close()
        stamp = time.strftime("%Y%m%d-%H%M")
        mp4 = os.path.abspath(os.path.join(o["out"], f"mifgash-demo-rough-{stamp}.mp4"))
        lst = os.path.join(work, "clips.txt")
        with open(lst, "w") as f:
            f.writelines(f"file '{c}'\n" for c in clips)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                        "-c", "copy", "-movflags", "+faststart", mp4], check=True)
        shutil.rmtree(work, ignore_errors=True)
        dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", mp4],
                             capture_output=True, text=True).stdout.strip()
        self.stdout.write(f"{mp4}: {float(dur):.1f} s, {os.path.getsize(mp4) / 1e6:.1f} MB")

    def clip(self, frames_list, caption, out, theme):
        """One segment: the frames on a 1280x844 canvas, a caption bar at the bottom."""
        txt = out + ".txt"
        with open(txt, "w") as f:
            f.write(caption)
        bg = BG if theme == "dark" else "0xf4f5f7"
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color={bg},"
              f"fps={FPS * 3},format=yuv420p,"
              f"drawbox=x=0:y={H - 78}:w={W}:h=78:color=black@0.72:t=fill,"
              f"drawtext=fontfile={FONT}:textfile={txt}:fontcolor=white:fontsize=22:"
              f"x=(w-text_w)/2:y={H - 52}")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", frames_list,
                        "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-r", str(FPS * 3),
                        "-an", out], check=True)
        return out


TITLE_V2 = ('<div class="c"><h1>Mifgash</h1><p style="font-size:34px;color:#e8eaf0">Meet friends on your terms,<br>'
            'without messaging ten people for a yes.</p><span class="tag">Muse Spark Open on Baseten</span></div>')
SETUP_V2 = ('<div class="c"><h1 style="font-size:52px">Setup takes one line</h1>'
            '<p>You say to your own agent:</p><p style="font-size:30px;color:#e8eaf0">'
            '"Read mifgash.sveder.com/agents.md and sign me up."</p><p>The agent runs:</p>'
            '<p><code style="font-size:26px;background:#2a2f3a;padding:8px 16px;border-radius:10px;color:#e8eaf0">'
            'python3 mif.py signup Chris zz_chris</code></p><span class="tag">Any agent that reads a page and calls an API</span></div>')
END_V2 = ('<div class="c"><h1>Mifgash</h1><p>Three friends. Two agents. One dinner. No group chat.</p>'
          '<p style="font-size:34px;color:#e8eaf0">mifgash.sveder.com</p><span class="tag">Made by Sveder</span></div>')
PHONE, DESK = (390, 844, True), (1280, 800, False)


class V2:
    """The narrated v2 cut. Every shot lasts exactly its narration (demo/narration.json), on the
    frame grid. The shots film the public site after a demo/video_run.py run."""

    def __init__(self, cmd, o):
        self.cmd, self.o = cmd, o
        self.base = o["url"].rstrip("/")
        self.nar = json.load(open(o["narration"]))
        self.run = json.load(open(o["run"]))
        self.links = json.load(open(o["links"]))
        self.bounds = {i: (a, b) for i, a, b in cut_v2.shot_bounds(self.nar["shots"])}
        self.work = tempfile.mkdtemp(prefix="mif-v2-")
        self.clips = {}
        self.rec = RoughCut()

    def say(self, s):
        self.cmd.stdout.write(s)

    def page(self, name, body):
        path = os.path.join(self.work, f"{name}.html")
        with open(path, "w") as f:
            f.write(body)
        return "file://" + path

    def login(self, token):
        self.b.go(f"{self.base}/d/{token}/")
        self.b.eval("document.querySelector('form').submit()")
        time.sleep(0.8)
        self.b.wait_load()
        if not self.b.eval("location.pathname").startswith("/d/"):
            raise CommandError("dashboard login failed")

    def shot(self, sid, parts):
        """parts: [(share, url, size, theme, scroll, focus)]; focus = text of the element to show at the top."""
        a, b = self.bounds[sid]
        secs_total, done, files = b - a, 0.0, []
        for k, (share, url, size, theme, scroll, focus) in enumerate(parts):
            secs = secs_total - done if k == len(parts) - 1 else round(secs_total * share * cut_v2.FPS) / cut_v2.FPS
            done += secs
            self.b.look(*size, theme)
            if url:
                self.b.go(url)
            leak = private_text(self.b.eval("document.body.innerText"))
            if leak:
                raise CommandError(f"{sid}: the page shows {leak}")
            top = 0
            if focus:
                top = self.b.eval("(()=>{const t=" + json.dumps(focus) + ";const e=[...document.querySelectorAll("
                                  "'h2,h3,li,p,div,article')].reverse().find(x=>x.innerText&&x.innerText.includes(t));"
                                  "return e?Math.max(0,e.getBoundingClientRect().top+scrollY-90):0})()") or 0
            lst, _ = self.rec.record(self.b, os.path.join(self.work, f"{sid}-{k}"), secs, scroll, top)
            files.append(self.clip(lst, secs, os.path.join(self.work, f"{sid}-{k}.mp4"), theme))
        self.clips[sid] = files
        self.say(f"  {sid}: {secs_total:.2f} s in {len(parts)} part(s)")

    def clip(self, lst, secs, out, theme):
        bg = BG if theme == "dark" else "0xf4f5f7"
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color={bg},"
              f"fps={cut_v2.FPS},format=yuv420p,tpad=stop_mode=clone:stop_duration=2")  # exact length with -t
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-vf", vf,
                        "-t", f"{secs:.4f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                        "-r", str(cut_v2.FPS), "-an", out], check=True)
        return out

    def make(self):
        base, run, L = self.base, self.run, self.links
        plan = run["plan_id"]
        puid = run["plan_uid"]  # F8a (T260): /plan/ and /outing/ URLs take the uuid; the integer is a 404
        self.b = Browser(find_chrome())
        try:
            self.login(L["zz_chris"])
            self.b.go(f"{base}/plan/{puid}/log/?format=json")
            log = json.loads(self.b.eval("document.body.innerText"))
            with open(self.o["log_out"], "w") as f:
                json.dump(log, f, indent=1)
            rows = cut_v2.conversation(log)
            panel = self.page("panel", cut_v2.panel_html(rows, sub=f"From the live log of outing {plan} on mifgash.sveder.com"))
            ask = run["lines"]
            chat = chat_html("Chris's agent (Telegram)", [
                ("me", "15:22", "I am free Thursday evening for dinner near North Beach."),
                ("them", "15:22", "Posted to Mifgash: Thu Nov 5, evening, near North Beach. Nobody is free near there yet. I keep looking.")], "tg")
            friends = chat_html("Chris's agent (Telegram)", [
                ("me", "15:21", "Who are my friends on Mifgash?"),
                ("them", "15:21", "Maria (@zz_maria), Sam (@zz_sam) and Lena (@zz_lena). Each of them has an own agent.")], "tg")
            sam_reply = next((x for x in ask if x.startswith("[") and "Sam:" in x), "")
            self.shot("01-title", [(0.55, self.page("title", card(TITLE_V2)), DESK, "dark", 0, None),
                                   (0.45, base + "/", DESK, "dark", 0, None)])
            self.shot("02-problem", [(1, base + "/", DESK, "dark", 0.8, None)])
            self.shot("03-setup", [(1, self.page("setup", card(SETUP_V2)), DESK, "dark", 0, None)])
            self.shot("04-ask", [(0.5, self.page("ask", chat), PHONE, "dark", 0, None),
                                 (0.5, base + "/d/", PHONE, "dark", 0, None)])
            self.shot("05-friends", [(1, self.page("friends", friends), PHONE, "dark", 0, None)])
            match = [r for r in rows if r[3].startswith(("Yes, picks", "yes, picks", "Maria said yes", "looking for friends open evening"))]
            match_page = self.page("match", cut_v2.panel_html(match, title="The match",
                                                              sub="Chris and Maria, Thu Nov 5, evening, near North Beach"))
            self.shot("07-match", [(0.4, base + "/d/", PHONE, "dark", 0, None),
                                   (0.6, match_page, (1280, 844, False), "dark", 0, None)])
            self.shot("08-private", [(1, f"{base}/h/{L['maria_h']}/", PHONE, "dark", 0, None)])
            self.shot("09-conversation", [(1, panel, (1280, 844, False), "dark", 1.0, None)])
            self.shot("10-place", [(1, f"{base}/outing/{puid}/", PHONE, "dark", 0, None)])
            self.shot("11-card", [(0.5, f"{base}/h/{L['maria_h']}/", PHONE, "dark", 0, "Evening out with Chris"),
                                  (0.5, f"{base}/outing/{puid}/", PHONE, "light", 0, None)])
            import urllib.request
            with urllib.request.urlopen(run["ics_url"], timeout=30) as r:
                ics = cut_v2.ics_fields(r.read().decode("utf-8", "replace"))
            self.shot("12-calendar", [(1, self.page("calendar", cut_v2.calendar_html(ics)), (1280, 844, False), "dark", 0, None)])
            self.shot("13-human", [(1, f"{base}/h/{L['lena_h']}/", PHONE, "dark", 0.6, None)])
            self.shot("14-log", [(1, base + "/d/", PHONE, "dark", 0.7, "Agent log")])
            self.shot("15-end", [(0.4, base + "/", DESK, "light", 0, None),
                                 (0.6, self.page("end", card(END_V2)), DESK, "dark", 0, None)])
            self.login(L["zz_sam"])  # last: this ends the owner's session
            self.shot("06-nomatch", [(1, base + "/d/", PHONE, "dark", 0, None)])
            self.say(f"  Sam's post: {sam_reply}")
        finally:
            self.b.close()
        return self.join()

    def join(self):
        order = [s["id"] for s in self.nar["shots"]]
        lst = os.path.join(self.work, "clips.txt")
        with open(lst, "w") as f:
            for sid in order:
                f.writelines(f"file '{c}'\n" for c in self.clips[sid])
        silent = os.path.join(self.work, "silent.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", silent], check=True)
        self.report(order)
        # captions + audio in one pass
        caps = cut_v2.captions(self.nar["shots"])
        draws = [f"drawbox=x=0:y={H - 92}:w={W}:h=92:color=black@0.72:t=fill"]
        for i, (a, b, line) in enumerate(caps):
            txt = os.path.join(self.work, f"cap{i:03d}.txt")
            with open(txt, "w") as f:
                f.write(line)
            draws.append(f"drawtext=fontfile={FONT}:textfile={txt}:fontcolor=white:fontsize=30:"
                         f"x=(w-text_w)/2:y={H - 62}:enable='between(t,{a},{b})'")
        vf_path = os.path.join(self.work, "vf.txt")
        afilter = cut_v2.audio_filter(self.nar["shots"])
        # inputs: 0 = silent video, 1 = bed, 2.. = wavs; shift the audio indexes by one
        a_parts = re.sub(r"\[(\d+):a\]", lambda m: f"[{int(m.group(1)) + 1}:a]", afilter)
        with open(vf_path, "w") as f:
            f.write("[0:v]" + ",".join(draws) + "[v];" + a_parts)
        out = os.path.abspath(self.o["out"])
        os.makedirs(os.path.dirname(out), exist_ok=True)
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", silent, "-i", self.nar["bed"]]
        for s in self.nar["shots"]:
            cmd += ["-i", s["wav"]]
        cmd += ["-filter_complex_script", vf_path, "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium",
                "-crf", "24", "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-shortest", "-movflags", "+faststart", out]
        subprocess.run(cmd, check=True)
        shutil.rmtree(self.work, ignore_errors=True)
        dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", out],
                             capture_output=True, text=True).stdout.strip()
        self.say(f"{out}: {float(dur):.1f} s, {os.path.getsize(out) / 1e6:.1f} MB")

    def report(self, order):
        """The table for the acceptance line: narration start vs the real clip start."""
        t = 0.0
        self.say("shot             narration  video   diff")
        for s in self.nar["shots"]:
            self.say(f"{s['id']:<16} {s['start']:8.2f} {t:7.2f} {t - s['start']:+6.2f}")
            for c in self.clips[s["id"]]:
                t += float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                           "csv=p=0", c], capture_output=True, text=True).stdout.strip())
