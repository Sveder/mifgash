"""T402: is a place open at a plan's date and part of the day? No network, no model call.

open_at(hours_text, date, part) reads a subset of the OpenStreetMap opening_hours rules:
  '24/7', 'Mo-Su 11:00-22:00', 'Mo-Fr 09:00-17:00; Sa 10:00-14:00', day lists 'Mo,We,Fr',
  ranges that wrap ('Th-Tu', 'Su-Mo'), 'off' / 'closed', two ranges in a day ('11:30-14:30,17:30-22:30'),
  late ends ('17:00-02:00', '14:00-26:00', '17:00-22:00+', '16:00+'). 'PH ...' rules (public holidays) are ignored.
It answers True (open in the part window), False (surely closed) or None (no hours, or a text this
parser does not read, such as 'sunrise-22:00'). An unknown answer keeps the place.
"""
import re

DAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
# The part windows (the PARTS keys in models.py), in minutes from midnight.
WINDOWS = {"morning": (9 * 60, 12 * 60), "lunch": (12 * 60, 14 * 60),
           "afternoon": (14 * 60, 17 * 60), "evening": (19 * 60, 21 * 60)}
TOKEN = re.compile(r"Mo|Tu|We|Th|Fr|Sa|Su|PH|SH|\d{1,2}:\d{2}|off|closed|[-,+]|\S+")


def _minutes(t):
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def _day_range(a, b):
    i, j = DAYS.index(a), DAYS.index(b)
    return [DAYS[(i + k) % 7] for k in range(((j - i) % 7) + 1)]


def _rule(text):
    """One ';' rule -> list of (days or None, ranges) groups, or None when unreadable.
    A rule may hold more than one group: 'Mo-Th 16:00-02:00, Fr,Sa 15:00-02:00'."""
    toks = TOKEN.findall(text)
    groups, days, ranges, seen_time, i = [], None, [], False, 0
    def flush():
        groups.append((days, ranges))
    while i < len(toks):
        t = toks[i]
        if t in DAYS or t in ("PH", "SH"):
            if seen_time:  # a new day group starts after times: 'Mo-Th 16:00-02:00, Fr,Sa ...'
                flush()
                days, ranges, seen_time = None, [], False
            days = days if days is not None else []
            if i + 2 < len(toks) and toks[i + 1] == "-" and toks[i + 2] in DAYS and t in DAYS:
                days += _day_range(t, toks[i + 2])
                i += 3
                continue
            days.append(t)  # PH / SH stay as a marker here and are dropped below
            i += 1
        elif t == ",":
            i += 1
        elif t in ("off", "closed"):
            ranges, seen_time = "off", True
            i += 1
        elif re.fullmatch(r"\d{1,2}:\d{2}", t):
            if ranges == "off":
                return None
            if i + 1 < len(toks) and toks[i + 1] == "+":  # '16:00+': open from 16:00, no end given
                ranges.append((_minutes(t), 24 * 60))
                seen_time = True
                i += 2
                continue
            if not (i + 2 < len(toks) and toks[i + 1] == "-" and re.fullmatch(r"\d{1,2}:\d{2}", toks[i + 2])):
                return None
            start, end = _minutes(t), _minutes(toks[i + 2])
            if end <= start:
                end += 24 * 60  # '17:00-02:00' ends after midnight
            i += 3
            if i < len(toks) and toks[i] == "+":
                end = max(end, 24 * 60)  # '22:00+': open end
                i += 1
            ranges.append((start, end))
            seen_time = True
        else:
            return None
    if days is not None or ranges:
        if not seen_time:
            return None
        flush()
    out = []
    for d, r in groups:
        if d is not None:
            real = [x for x in d if x in DAYS]
            if not real:
                continue  # 'PH off', 'SH closed': holidays only, ignored
            d = real
        out.append((d, r))
    return out


def parse(text):
    """hours text -> {day: [(start, end), ...]} for every day, or None when unreadable.
    Days no rule names are closed, as in OpenStreetMap, but only when some rule gives open times."""
    text = (text or "").strip()
    if not text:
        return None
    if text == "24/7":
        return {d: [(0, 24 * 60)] for d in DAYS}
    sched = {}
    any_open = False
    for part in text.split(";"):
        part = part.strip()
        if not part:
            continue
        groups = _rule(part)
        if groups is None:
            return None
        for days, ranges in groups:
            value = [] if ranges == "off" else list(ranges)
            any_open = any_open or bool(value)
            for d in (days or DAYS):  # later rules replace earlier ones for the days they name
                sched[d] = value
    if not sched:
        return None
    if not any_open:
        return {d: sched.get(d) for d in DAYS}  # only 'off' rules: other days unknown (None)
    return {d: sched.get(d, []) for d in DAYS}


def open_at(hours_text, date, part):
    """True / False / None for the part window on that date (see the module text)."""
    win = WINDOWS.get(part)
    sched = parse(hours_text)
    if win is None or sched is None or date is None:
        return None
    day = DAYS[date.weekday()]
    prev = DAYS[(date.weekday() - 1) % 7]
    today, before = sched.get(day), sched.get(prev) or []
    if today is None:
        return None
    ranges = list(today) + [(s - 24 * 60, e - 24 * 60) for s, e in before if e > 24 * 60]
    lo, hi = win
    return any(s < hi and e > lo for s, e in ranges)


def hours_from_note(note):
    """The raw opening_hours text kept in an imported note 'Hours: ...', or ''. A note cut at
    160 characters may have lost rules, so a full-length note gives '' (unknown), not a wrong 'closed'."""
    note = note or ""
    if not note.startswith("Hours: ") or len(note) >= 160:
        return ""
    text = note[len("Hours: "):].strip()
    return text if len(text) <= 120 else ""
