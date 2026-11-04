"""What the words imply, before anything is asked (used by the availability API).

The old chat with the site (chat turns, clarifying questions, /dev/chat/) is removed (T71, 1/11).
"""
from . import matching


def infer(owner, draft):
    """Fill what the words imply, before asking anything."""
    kind, part, date = draft.get("kind"), draft.get("part"), draft.get("date")
    if kind and not part:
        part = matching.DEFAULT_PART[kind]
        if kind == "kids" and date and date.weekday() in (4, 5):
            part = "morning"
    if part and not kind:
        kind = matching.KIND_FOR_PART.get(part)
        if part == "morning" and date and date.weekday() not in (4, 5):
            kind = None
    draft["kind"], draft["part"] = kind, part
    if kind == "kids" and not draft.get("group_size"):
        draft["group_size"] = 2  # kids outings work with 1-2 families
    return draft
