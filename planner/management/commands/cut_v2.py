"""Video v2 helpers (M13b, T184, 3/11/2026): shot times from demo/narration.json, burned-in
captions from the narration, the 'Actual agent conversation' panel from a /plan/<id>/log/ JSON,
and the audio mix (narration wavs at the shot starts + the music bed). No browser and no ffmpeg
here, so the tests can run them."""
import html
import re

FPS = 24


def shot_bounds(shots, fps=FPS):
    """[(id, start, end)] on the frame grid, from the narration starts. The ends are rounded to whole
    frames from the running total, so 15 shots never drift by more than one frame."""
    out = []
    for s in shots:
        a = round(s["start"] * fps) / fps
        b = round((s["start"] + s["seconds"]) * fps) / fps
        out.append((s["id"], a, b))
    return out


def chunks(text, max_chars=64):
    """The narration cut into caption lines: whole sentences, and a long sentence cut at a comma
    or between words, each line at most max_chars."""
    out = []
    for sent in re.split(r"(?<=[.!?])\s+", text.strip()):
        while len(sent) > max_chars:
            cut = sent.rfind(", ", 0, max_chars)
            cut = cut + 1 if cut > max_chars // 3 else sent.rfind(" ", 0, max_chars)
            out.append(sent[:cut].strip())
            sent = sent[cut:].strip()
        if sent:
            out.append(sent)
    return out


def captions(shots, lead=0.4, tail=0.5):
    """[(start, end, line)] for every shot: the lines share the speech time by their length."""
    rows = []
    for s in shots:
        lines = chunks(s["text"])
        t = s["start"] + s.get("speech_start", lead)
        span = max(0.5, s["seconds"] - s.get("speech_start", lead) - tail)
        total = sum(len(x) for x in lines) or 1
        for x in lines:
            d = span * len(x) / total
            rows.append((round(t, 2), round(t + d, 2), x))
            t += d
    return rows


def audio_filter(shots, bed_index=0):
    """ffmpeg -filter_complex for [bed, wav 1..n]: each wav delayed to its shot start, then one mix
    with no level change (the bed is already at its level)."""
    parts, names = [], [f"[{bed_index}:a]"]
    for i, s in enumerate(shots, start=1):
        ms = int(round(s["start"] * 1000))
        parts.append(f"[{i}:a]aresample=24000,aformat=channel_layouts=mono,adelay={ms}:all=1[v{i}]")
        names.append(f"[v{i}]")
    parts.append(f"[{bed_index}:a]aresample=24000,aformat=channel_layouts=mono[bed]")
    names[0] = "[bed]"
    parts.append("".join(names) + f"amix=inputs={len(names)}:normalize=0:duration=first[a]")
    return ";".join(parts)


WHO = re.compile(r"^(.*?)\s*→\s*(.*)$")


def conversation(log, me="Chris"):
    """The plan log JSON (newest first) as chat rows, oldest first: (side, who, time, text, model).
    The owner's own agent is on the right."""
    rows = []
    for r in reversed(log.get("rows", [])):
        m = WHO.match(r.get("who", ""))
        src = m.group(1) if m else r.get("from", "")
        if src == "Your agent":
            src, side = f"{me}'s agent", "me"
        else:
            side = "them"
        rows.append((side, src, r.get("t", "")[:5], r.get("summary", ""), r.get("model", "")))
    return rows


PANEL_CSS = """
body{margin:0;min-height:100vh;display:flex;align-items:flex-start;justify-content:center;
font-family:system-ui,-apple-system,'Segoe UI',sans-serif;background:#0e1116;color:#e8eaf0}
.p{width:760px;margin:28px auto}
h1{font-size:30px;margin:0 0 4px}.sub{color:#9aa3b5;font-size:17px;margin:0 0 18px}
.b{max-width:78%;margin:10px 0;padding:10px 14px;border-radius:14px;font-size:18px;line-height:1.35}
.me{background:#2b5278;margin-left:auto}.them{background:#202630}
.w{display:block;font-size:13px;color:#9aa3b5;margin-bottom:3px}
.m{display:inline-block;margin-left:6px;padding:2px 9px;border-radius:999px;background:#3b2f6e;color:#d9d2ff;font-size:13px;white-space:nowrap}
"""


def panel_html(rows, title="Actual agent conversation", sub=""):
    bubbles = "".join(
        f'<div class="b {side}"><span class="w">{html.escape(who)} · {html.escape(t)}</span>{html.escape(text)}'
        + (f' <span class="m">{html.escape(model)}</span>' if model else "") + "</div>"
        for side, who, t, text, model in rows)
    return (f'<!doctype html><meta charset=utf-8><style>{PANEL_CSS}</style><div class="p"><h1>{html.escape(title)}</h1>'
            f'<p class="sub">{html.escape(sub)}</p>{bubbles}</div>')


def ics_fields(text):
    """SUMMARY, start, LOCATION and DESCRIPTION lines of the first VEVENT, unfolded and unescaped."""
    text = text.replace("\r\n ", "").replace("\n ", "")
    out = {}
    if "BEGIN:VEVENT" in text:
        text = text.split("BEGIN:VEVENT", 1)[1]
    for line in text.splitlines():
        key, _, val = line.partition(":")
        key = key.split(";")[0]
        if key in ("SUMMARY", "LOCATION", "DESCRIPTION", "DTSTART") and key not in out and val:
            out[key] = val.replace("\\,", ",").replace("\\n", "\n").replace("\\;", ";")
    return out


def calendar_html(f):
    """The calendar invite as a card: what, when, where and the description lines."""
    st = f.get("DTSTART", "")
    when = f"{st[6:8]}/{st[4:6]}/{st[:4]} {st[9:11]}:{st[11:13]}" if len(st) >= 13 else st
    try:
        import datetime as dt
        d = dt.datetime.strptime(st[:13], "%Y%m%dT%H%M")
        when = d.strftime("%a %b ") + str(d.day) + d.strftime(", %H:%M")
    except ValueError:
        pass
    desc = "".join(f"<p>{html.escape(x)}</p>" for x in f.get("DESCRIPTION", "").split("\n") if x.strip())
    return (f'<!doctype html><meta charset=utf-8><style>{PANEL_CSS}.card{{background:#1a1f27;border-radius:16px;padding:22px 26px;'
            f'font-size:20px;line-height:1.45}}.card p{{margin:6px 0;color:#c9cfdb;word-break:break-all}}</style>'
            f'<div class="p"><h1>The calendar invite</h1><p class="sub">The real .ics file of the outing. One tap adds it.</p>'
            f'<div class="card"><h1 style="font-size:26px">{html.escape(f.get("SUMMARY", ""))}</h1>'
            f'<p><b>{html.escape(when)}</b></p><p>{html.escape(f.get("LOCATION", ""))}</p>{desc}</div></div>')
