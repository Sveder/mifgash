"""'How this meetup came together' (Michael 4/11): a Sankey story of one plan, from the data the app
already keeps (offers, place options, the log). Server-side inline SVG; no JS, no CDN.

PRIVACY (the core rule: a no stays private). The graph shows COUNTS for 'not this time', 'no answer'
and 'not needed', never a name, and never the order of the asks. Only people who said yes are named.
A guest (anyone but the plan owner) does not see the ask funnel at all: decline counts before a 1:1
yes would tell the guest that she or he was not asked first.
"""
from django.utils.html import escape

from . import llm, matching, messages
from . import wants as wants_mod
from .models import Activity, AgentMessage, Friendship

# ---- layout ---------------------------------------------------------------------------------------


class Node:
    def __init__(self, key, label, value, cls="main", sub="", children=None):
        self.key, self.label, self.value, self.cls, self.sub = key, label, value, cls, sub
        self.children = [c for c in (children or []) if c.value > 0]
        self.x = self.y = self.h = 0.0
        self.depth = 0


def _heights(node, k, min_h):
    """Display height: a leaf is value*k (at least min_h); a parent is the sum of its children, so
    every band leaves the parent and enters the child at the same thickness."""
    if not node.children:
        node.h = max(min_h, node.value * k)
    else:
        node.h = sum(_heights(c, k, min_h) for c in node.children)
    return node.h


def _walk(node, depth=0):
    node.depth = depth
    yield node
    for c in node.children:
        yield from _walk(c, depth + 1)


def _label_h(n):
    return 15 * (2 if n.sub else 1)


def _bottom(n):
    """The lowest pixel a node takes: its bar, or its label lines when the bar is thinner."""
    return n.y + max(n.h, _label_h(n))


def layout(root, width=400, max_h=130, node_w=8, gap=8, min_h=4, label_w=122):
    """Tree Sankey layout. Columns = depth; nodes stack top-down in tree order, so bands never cross.
    Returns {'width', 'height', 'nodes': [Node], 'links': [{'src','dst','d','w','depth'}]}.
    The scale k is the largest that keeps the root within max_h."""
    nodes = list(_walk(root))
    depth = max(n.depth for n in nodes)
    lo, hi = 0.0, max_h / max(root.value, 1)
    for _ in range(30):  # min_h on small leaves can push the root past max_h: shrink k until it fits
        k = (lo + hi) / 2
        if _heights(root, k, min_h) <= max_h:
            lo = k
        else:
            hi = k
    _heights(root, lo, min_h)
    col_w = (width - label_w - node_w) / max(depth, 1)
    cols = {}
    for n in nodes:
        cols.setdefault(n.depth, []).append(n)
    height = 0.0
    for d, col in cols.items():
        y = 0.0
        for n in col:
            n.x, n.y = d * col_w, y
            y += max(n.h, _label_h(n)) + gap
        height = max(height, y - gap)
    # a parent sits level with the middle of its children when that is lower (keeps short bands flat)
    for n in sorted(nodes, key=lambda n: -n.depth):
        if n.children:
            mid = (n.children[0].y + n.children[-1].y + n.children[-1].h) / 2
            want = mid - n.h / 2
            col = cols[n.depth]
            i = col.index(n)
            floor = _bottom(col[i - 1]) + gap if i else 0.0
            n.y = max(want, floor, n.y)
            for j in range(i + 1, len(col)):  # push the nodes below down when the move overlaps them
                col[j].y = max(col[j].y, _bottom(col[j - 1]) + gap)
    height = max(_bottom(n) for n in nodes)
    links = []
    for n in nodes:
        y0 = n.y
        for c in n.children:
            sy, ty = y0 + c.h / 2, c.y + c.h / 2
            x0, x1 = n.x + node_w, c.x
            mx = (x0 + x1) / 2
            links.append({"src": n, "dst": c, "w": c.h, "depth": n.depth,
                          "d": f"M{x0:.1f},{sy:.1f} C{mx:.1f},{sy:.1f} {mx:.1f},{ty:.1f} {x1:.1f},{ty:.1f}"})
            y0 += c.h
    return {"width": width, "height": height, "nodes": nodes, "links": links, "node_w": node_w}


def svg(lay, title):
    """The layout as one inline SVG. Colours are CSS classes (mifgash.css), so light and dark modes
    both work. Each band is a stroked curve with pathLength=1, so CSS can draw it in left to right."""
    pad_t, pad_b = 16, 22
    w, h, nw = lay["width"], lay["height"] + pad_t + pad_b, lay["node_w"]
    out = [f'<svg class="sk" viewBox="0 0 {w} {h:.0f}" role="img" aria-label="{escape(title)}" '
           f'preserveAspectRatio="xMinYMin meet"><g transform="translate(0,{pad_t})">']
    for ln in lay["links"]:
        out.append(f'<path class="sk-l {ln["dst"].cls}" d="{ln["d"]}" stroke-width="{max(ln["w"] - 1, 1):.1f}" '
                   f'pathLength="1" style="--d:{ln["depth"]}"/>')
    for n in lay["nodes"]:
        out.append(f'<rect class="sk-n {n.cls}" x="{n.x:.1f}" y="{n.y:.1f}" width="{nw}" height="{n.h:.1f}" '
                   f'rx="2" style="--d:{n.depth}"/>')
    for n in lay["nodes"]:
        cy = n.y + n.h / 2
        tx = n.x + nw + 5
        lines = [(n.label, "sk-t"), *([(n.sub, "sk-s")] if n.sub else [])]
        y = cy - (len(lines) - 1) * 7 + 4
        for text, cls in lines:
            out.append(f'<text class="{cls}" x="{tx:.1f}" y="{y:.1f}" style="--d:{n.depth}">{escape(text)}</text>')
            y += 14
    out.append("</g></svg>")
    return "".join(out)


# ---- data -----------------------------------------------------------------------------------------

YES = ("accepted", "owner_wait")


def who_tree(plan):
    """The ask funnel, for the OWNER only: friends -> free nearby -> asked -> answers. Counts only for
    every answer that is not a yes; the yes people are named (the site names them already)."""
    offers = list(plan.offers.select_related("person"))
    if not offers:
        return None
    st = {}
    for o in offers:
        st[o.status] = st.get(o.status, 0) + 1
    n_friends = max(Friendship.friends_of(plan.owner_id).count(), len(offers))
    yes_names = [messages.first_name(o.person) for o in offers if o.status in YES]
    asked = len(offers) - st.get("queued", 0) - st.get("not_sent", 0)
    later = "Not asked yet" if plan.status in ("asking", "open") else "Not needed"
    answers = [
        Node("yes", f"Yes: {len(yes_names)}", len(yes_names), "yes", ", ".join(yes_names)[:22]),
        Node("closed", f"Yes, closed: {st.get('closed', 0)}", st.get("closed", 0), "quiet"),
        Node("no", f"Not this time: {st.get('declined', 0)}", st.get("declined", 0), "quiet"),
        Node("none", f"No answer: {st.get('expired', 0)}", st.get("expired", 0), "quiet"),
        Node("wait", f"Waiting: {st.get('pending', 0)}", st.get("pending", 0), "wait"),
    ]
    free = Node("free", f"Free: {len(offers)}", len(offers), children=[
        Node("asked", f"Asked: {asked}", asked, "main", "", answers),
        Node("later", f"{later}: {len(offers) - asked}", len(offers) - asked, "quiet"),
    ])
    return Node("friends", f"Friends: {n_friends}", n_friends, children=[
        free, Node("busy", f"Busy or far: {n_friends - len(offers)}", n_friends - len(offers), "quiet")])


def short_name(name, n=17):
    return name if len(name) <= n else name[:n - 1].rstrip() + "\u2026"


DROP_WORDS = {"loud": "Too loud", "crowded": "Too crowded"}


def _drop_reason(a, avoid_tags, dislikes):
    hit = set(a.tags or []) & avoid_tags
    for t in sorted(hit):
        if t in DROP_WORDS:
            return DROP_WORDS[t]
    if hit or wants_mod.is_disliked(a, dislikes):
        return next((DROP_WORDS[d] for d in (dislikes or []) if d in DROP_WORDS), "Avoided")
    return ""


def pick_reason(plan):
    """Why the chosen place won, in 2-3 words. No names but the yes people."""
    if not plan.chosen_id:
        return ""
    types = set(AgentMessage.objects.filter(plan=plan).values_list("type", flat=True))
    if "group_vote" in types:
        return "group vote"
    if "group_place" in types:
        return "middle of the group"
    if wants_mod.is_liked(plan.chosen, plan.wants):
        return "liked place"
    pick = (plan.wants or {}).get("pick") or {}
    if pick.get("id") == plan.chosen_id and pick.get("backend"):
        return f"{'Muse' if pick['backend'] == 'meta' else llm.model_label(pick['backend']) or 'model'} pick"
    o = plan.offers.filter(status="accepted", choice_id=plan.chosen_id).select_related("person").first()
    if o and AgentMessage.objects.filter(plan=plan, type="accept", payload__offer_id=o.pk, payload__picked=True).exists():
        return f"{messages.first_name(o.person)}'s pick"
    return "best fit"


def where_tree(plan):
    """Places of this kind -> dropped (avoided, too loud, too far) -> near enough -> short list -> chosen."""
    opts = list(plan.options.all())
    if plan.chosen_id and plan.chosen_id not in {a.pk for a in opts}:
        opts.append(plan.chosen)
    if not opts:
        return None
    keep = {a.pk for a in opts}
    sides = [plan.owner] + plan.guests()
    avoid_tags = set().union(*[set(p.dislikes or []) for p in sides])
    dislikes = list((plan.wants or {}).get("dislikes") or [])
    drops, near = {}, 0
    for a in Activity.objects.filter(kind=matching.base_kind(plan.kind)).select_related("area"):
        if a.pk in keep:
            near += 1
            continue
        why = _drop_reason(a, avoid_tags, dislikes)
        if not why and matching.km(a.area, plan.area) > plan.radius_km + 1.0:
            why = "Too far"
        if why:
            drops[why] = drops.get(why, 0) + 1
        else:
            near += 1
    total = near + sum(drops.values())
    s = len(opts)
    short_kids = []
    if plan.chosen_id:
        short_kids = [Node("chosen", short_name(plan.chosen.name), 1, "yes", pick_reason(plan)),
                      Node("other", f"Other picks: {s - 1}", s - 1, "quiet")]
    short = Node("short", f"Short list: {s}", s, "main", children=short_kids)
    reach = Node("near", f"Near: {near}", near, "main", children=[
        short, Node("notpicked", f"Not picked: {near - s}", near - s, "quiet")])
    word = "for dinner" if plan.kind == "group_dinner" or plan.is_dinner else {
        "kids": "for kids", "lunch": "for lunch"}.get(plan.kind, "")
    kids = [reach] + [Node("drop-" + k, f"{k}: {v}", v, "quiet") for k, v in sorted(drops.items(), key=lambda kv: -kv[1])]
    return Node("places", f"Places: {total}", total, "main", word, children=kids)


def when_steps(plan):
    """The time story as short steps: posted, matched, time set, moves, final, calendar invite."""
    steps = [("Free time posted", messages.fmt_day(plan.date))]
    rows = list(AgentMessage.objects.filter(plan=plan, type__in=[
        "confirm", "auto_time", "finalize_set", "time_change", "final"]).order_by("created", "pk"))
    if any(r.type == "confirm" for r in rows) or plan.status in ("confirmed", "final"):
        steps.append(("Match", "everyone said yes" if plan.group_size > 1 else "a friend said yes"))
    seen = set()
    for r in rows:
        t = (r.payload or {}).get("time")
        if not t:
            continue
        if r.type in ("auto_time", "finalize_set") and ("set", t) not in seen:
            steps.append(("Time set", messages.clock(t)))
            seen.add(("set", t))
        elif r.type == "time_change":
            steps.append(("Moved", messages.clock(t)))
    if plan.status == "final" and plan.exact_time:
        at = messages.clock(plan.exact_time)
        steps.append(("Agreed", "by all" if steps[-1][1] == at else at))
        steps.append(("Calendar invite", "sent to all"))
    elif plan.status in ("asking", "open"):
        steps.append(("Now", "asking friends" if plan.status == "asking" else "waiting for a match"))
    return steps


def build(plan, viewer):
    """The story for one viewer. viewer = the dashboard person, or None for the demo operator page
    (which is treated as a guest: no ask funnel)."""
    is_owner = viewer is not None and viewer.pk == plan.owner_id
    out = {"who": "", "where": "", "when": when_steps(plan), "going": ""}
    if is_owner:
        t = who_tree(plan)
        if t:
            out["who"] = svg(layout(t), "Who: your friends, who was free, and the answers (counts only)")
    else:
        names = [messages.first_name(p) for p in [plan.owner] + plan.guests() if viewer is None or p.pk != viewer.pk]
        out["going"] = ", ".join(names + (["you"] if viewer is not None else []))
    t = where_tree(plan)
    if t:
        out["where"] = svg(layout(t), "Where: the places considered, why some were dropped, and the pick")
    out["any"] = bool(out["who"] or out["where"])
    return out
