"""T236: print the landing explainer keyframes. One clock (LOOP s); each layer = (class, start, end).
Fades take FADE s. Every opacity layer starts and ends at 0 (the base scene), so the loop has no jump.
Run: python3 scripts/explainer_css.py  -> paste between the EXPLAINER markers in mifgash.css."""
LOOP, FADE = 34, 0.5
LAYERS = [  # class, visible from, visible to (seconds)
    ("x-c1", 0.3, 2.5), ("x-say", 0.5, 5.6),
    ("x-c2", 3.0, 5.1), ("x-taste", 3.2, 33.4),
    ("x-c3", 5.6, 7.7),
    ("x-c4", 8.2, 10.3), ("x-l-sam", 8.2, 10.8), ("x-sam", 8.4, 10.8),
    ("x-c5", 10.8, 12.9), ("x-l-mar", 10.8, 33.4), ("x-mar", 11.0, 33.4),
    ("x-c6", 13.4, 33.4), ("x-card", 13.6, 33.4),
]
# pulses: class, dx, dy (from the badge to the mark), start, end of travel
PULSES = [("x-pu", 112, 25, 5.8, 7.6), ("x-pm", -118, 83, 5.9, 7.7), ("x-ps", -118, -57, 6.0, 7.8)]


def p(s):
    return ("%.2f" % (100 * s / LOOP)).rstrip("0").rstrip(".") + "%"


out = []
for cls, a, b in LAYERS:
    name = "xp-" + cls[2:].replace("-", "")
    out.append("@keyframes %s{0%%{opacity:0}%s{opacity:0}%s{opacity:1}%s{opacity:1}%s{opacity:0}100%%{opacity:0}}"
               % (name, p(a), p(a + FADE), p(b), p(b + FADE)))
    out.append(".xp.play .%s{animation:%s %ds linear infinite}" % (cls, name, LOOP))
a = 13.6
out.append("@keyframes xp-rise{0%%,%s{transform:translateY(14px)}%s,100%%{transform:translateY(0)}}" % (p(a), p(a + 0.9)))
out.append(".xp.play .x-card-in{animation:xp-rise %ds ease-out infinite}" % LOOP)
for cls, dx, dy, a, b in PULSES:
    name = "xp-" + cls[2:]
    t = "translate(%dpx,%dpx)" % (dx, dy)
    out.append("@keyframes %s{0%%,%s{opacity:0;transform:translate(0,0)}%s{opacity:1;transform:translate(0,0)}"
               "%s{opacity:1;transform:%s}%s,100%%{opacity:0;transform:%s}}"
               % (name, p(a - 0.3), p(a), p(b), t, p(b + 0.3), t))
    out.append(".xp.play .%s{animation:%s %ds ease-in-out infinite}" % (cls, name, LOOP))
print("\n".join(out))
