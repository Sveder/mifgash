"""What the person wants from the place (T255, F6a): food, taste words, places they like or avoid.

Plan.wants = {"food": str|None, "tastes": [..], "likes": [..], "dislikes": [..], "text": str}.
Filled from the parse of the free text and from the API fields 'preferences' (free text) and
'tastes' (list). The place step (matching.suggest_activities) ranks on it. No model call here:
the preferences line is read with plain rules, so it costs nothing and never fails."""
import re

FOODS = ("sushi", "falafel", "hummus", "pizza", "burger", "vegan", "asian", "italian", "coffee",
         "mexican", "greek", "seafood", "sandwich", "brunch", "ramen", "thai", "indian", "chinese",
         "french", "californian", "tacos", "burrito", "wine", "cocktails", "beer")
FOOD_RE = re.compile(r"\b(" + "|".join(FOODS) + r")\b")
TASTES = ("quiet", "outdoor", "indoor", "kid-friendly", "new place", "cheap", "quick", "free",
          "sea", "group", "historic", "loud", "crowded")
# a taste word -> the place tags it fits
TASTE_TAGS = {"kid-friendly": {"playground", "park", "kids"}, "new place": set()}
NEG_RE = re.compile(r"\b(?:no|not|avoid|avoids|avoiding|hate|hates|dislike|dislikes|without|never)\b\s+(.+)")
POS_RE = re.compile(r"\b(?:likes?|loves?|enjoys?|prefers?|favou?rite)\b\s+(.+)")
LIMIT = 8
# words after 'no' / 'not' that are no place word: 'not tomorrow', 'no later than 2'
STOP = {"places", "place", "spots", "the", "a", "an", "too", "very", "at", "in", "on", "for", "to", "of",
        "today", "tomorrow", "tonight", "morning", "lunch", "afternoon", "evening", "noon", "later", "than",
        "earlier", "before", "after", "more", "one", "kids", "friends", "friend", "time", "rush", "it", "me",
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "weekend", "week",
        "far", "much", "long", "problem", "worries", "matter"}


def empty():
    return {"food": None, "tastes": [], "likes": [], "dislikes": [], "text": ""}


def _clean(word):
    return " ".join(re.sub(r"[^\w\s'&-]", " ", str(word).lower()).split())[:40]


def _add(items, word):
    w = _clean(word)
    for stop in ("places", "place", "spots", "the "):
        w = w.removesuffix(" " + stop) if stop != "the " else w.removeprefix(stop)
    w = w.strip()
    if w and w not in items and len(items) < LIMIT:
        items.append(w)


def read(text):
    """Plain-rule read of a free line: 'sushi; quiet; likes Ferry Building; avoids loud bars'."""
    out = empty()
    t = (text or "").lower()
    for part in re.split(r"[;,\n]|\band\b|\bbut\b", t):
        part = part.strip()
        if not part:
            continue
        neg, pos = NEG_RE.search(part), POS_RE.search(part)
        if neg:  # 'no loud places', 'avoids loud bars' -> dislikes 'loud', 'bars' -> 'bar'
            for w in neg.group(1).split():
                w = _clean(w)
                if w in STOP or not w or w.isdigit():
                    continue
                _add(out["dislikes"], w[:-1] if w.endswith("s") and not w.endswith("ss") and len(w) > 3 else w)
            continue
        if pos:
            _add(out["likes"], pos.group(1))
            continue
        m = FOOD_RE.search(part)
        if m and not out["food"]:
            out["food"] = m.group(1)
        for w in TASTES:
            if re.search(r"\b" + re.escape(w) + r"\b", part):
                _add(out["tastes"], w)
    return out


def merge(*parts):
    """Join wants dicts in order: the first food wins, the lists are joined without repeats."""
    out = empty()
    for p in parts:
        if not p:
            continue
        if not out["food"] and p.get("food"):
            out["food"] = _clean(p["food"]) or None
        for k in ("tastes", "likes", "dislikes"):
            for w in p.get(k) or []:
                _add(out[k], w)
        if p.get("text"):
            out["text"] = (out["text"] + " " + str(p["text"])).strip()[:300]
    # a taste the person avoids is not a taste ('no loud places' must not rank loud first)
    out["tastes"] = [w for w in out["tastes"] if w not in out["dislikes"]]
    return out


def place_words(a):
    return {t.lower() for t in (a.tags or [])}, a.name.lower()


def is_disliked(a, dislikes):
    tags, name = place_words(a)
    for d in dislikes or []:
        d = d.lower()
        if d in tags or (len(d) > 3 and d in name):
            return True
    return False


def food_match(a, food):
    if not food:
        return False
    tags, name = place_words(a)
    return food in tags or food in name


def score(a, wants):
    """Higher first: a liked place 4, the food 3, each taste word 1."""
    if not wants:
        return 0
    tags, name = place_words(a)
    s = 0
    for like in wants.get("likes") or []:
        if len(like) > 3 and (like in name or name in like):
            s += 4
    if food_match(a, wants.get("food")):
        s += 3
    for w in wants.get("tastes") or []:
        if w in tags or TASTE_TAGS.get(w, set()) & tags:
            s += 1
    return s


def summary(wants):
    """One short line for the log and the API: 'sushi; quiet; likes ferry building; avoids loud'."""
    if not wants:
        return ""
    bits = ([wants["food"]] if wants.get("food") else []) + list(wants.get("tastes") or [])
    bits += [f"likes {w}" for w in wants.get("likes") or []]
    bits += [f"avoids {w}" for w in wants.get("dislikes") or []]
    return "; ".join(bits)
