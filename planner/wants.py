"""What the person wants from the place (T255, F6a): food, taste words, places they like or avoid.

Plan.wants = {"food": str|None, "tastes": [..], "likes": [..], "dislikes": [..], "text": str}.
Filled from the parse of the free text and from the API fields 'preferences' (free text) and
'tastes' (list). The place step (matching.suggest_activities) ranks on it. No model call here:
the preferences line is read with plain rules, so it costs nothing and never fails."""
import re

FOODS = ("sushi", "falafel", "hummus", "pizza", "burger", "vegan", "asian", "italian", "coffee",
         "mexican", "greek", "seafood", "sandwich", "brunch", "ramen", "thai", "indian", "chinese",
         "french", "californian", "tacos", "burrito", "wine", "cocktails", "beer")
KIND_GROUP_RE = re.compile(r"\bgroup\s+(?:dinner|lunch|meal|outing|of)\b")
FOOD_RE = re.compile(r"\b(" + "|".join(FOODS) + r")\b")
TASTES = ("quiet", "outdoor", "indoor", "kid-friendly", "new place", "cheap", "quick",
          "sea", "group", "historic", "loud", "crowded")
# a taste word -> the place tags it fits
TASTE_TAGS = {"kid-friendly": {"playground", "park", "kids"}, "new place": set()}
# T320: 'don't like', 'can't stand' as well. A dislike is the whole phrase after the word, never
# single words: 'do not like Mission Playground' -> 'mission playground', not like/mission/playground.
NEG_RE = re.compile(r"\b(?:no|not|avoid|avoids|avoiding|hate|hates|dislike|dislikes|without|never|"
                    r"don't|dont|doesn't|doesnt|can't stand|cannot stand)\b\s*(.*)")
POS_RE = re.compile(r"\b(?:likes?|loves?|enjoys?|prefers?|favou?rite)\b\s+(.+)")
LIMIT = 8
# words after 'no' / 'not' that are no place word: 'not tomorrow', 'no later than 2'
STOP = {"places", "place", "spots", "the", "a", "an", "too", "very", "at", "in", "on", "for", "to", "of",
        "today", "tomorrow", "tonight", "morning", "lunch", "afternoon", "evening", "noon", "later", "than",
        "earlier", "before", "after", "more", "one", "kids", "friends", "friend", "time", "rush", "it", "me",
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "weekend", "week",
        "far", "much", "long", "problem", "worries", "matter", "please", "really", "any", "so",
        "free", "open", "available", "busy"}
# T320: words at the start of a dislike phrase that are no part of the place: 'not LIKE x', 'can't STAND x'
LEAD = {"like", "likes", "want", "wanna", "go", "going", "into", "care", "fan", "big", "stand", "eat",
        "eating", "love", "enjoy", "do", "does", "really", "much", "we", "i", "no", "not", "never"}
# T299: availability words are no want ('I am free Friday' -> no taste 'free')
NOT_WANTS = {"free", "open", "available", "busy"}
# T320: generic place words. A dislike phrase made only of these ('loud bars', 'coffee places') rules
# out every place with one of the words as a tag; any other phrase ('Dolores Park') is a place name.
CATEGORY = {"bar", "pub", "cafe", "coffee", "park", "playground", "restaurant", "club", "museum", "diner",
            "bistro", "brewery", "lounge", "market", "mall", "beach", "kids", "chain", "food", "spot",
            "shop", "tiki bar", "coffee shop", "fast food", "noise", "crowd", "music"}
GENERIC = set(TASTES) | set(FOODS) | CATEGORY
# T321: a parent's facts are kept as taste words, so the place step and the card can use them:
# 'my 4 year old' / 'kids 3 and 6' / 'ages 5 and 7' -> 'age 4'; 'shade and a toilet' -> 'shade', 'toilet'.
AGE_RE = re.compile(r"\b(\d{1,2})[\s-]*(?:years?|yrs?|yo)[\s-]*olds?\b|\b(\d{1,2})[\s-]*yo\b")
AGE_LIST_RE = re.compile(r"\b(?:kids?|children|child|boys?|girls?|sons?|daughters?|ages?|aged)\s+"
                         r"(?:are\s+|of\s+)?(\d{1,2}(?:\s*(?:,|and|&)\s*\d{1,2})*)\b")
NEEDS = {"shade": r"shade|shady", "toilet": r"toilets?|restrooms?|bathrooms?|wc",
         "stroller": r"strollers?|buggy|pram", "changing table": r"changing tables?",
         "fenced": r"fenced"}


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


def _one(w):
    return w[:-1] if w.endswith("s") and not w.endswith("ss") and len(w) > 3 else w


def phrase_words(phrase):
    return [_one(w) for w in phrase.split()]


def is_generic(phrase):
    return bool(phrase) and (phrase in GENERIC or _one(phrase) in GENERIC
                             or all(w in GENERIC for w in phrase_words(phrase)))


def _dislike(items, text):
    """The whole phrase after the 'no' word, without the lead and tail words around it."""
    text = re.split(r"\b(?:near|around|in|at|on|for|with|when|if)\b", text)[0]
    words = _clean(text).split()
    while words and (words[0] in LEAD or words[0] in STOP or words[0].isdigit()):
        words.pop(0)
    while words and (words[-1] in STOP or words[-1].isdigit()):
        words.pop()
    if words:
        _add(items, " ".join(words))


def _plain(out, part):
    pos = POS_RE.search(part)
    if pos:  # 'I love tacos near the Mission' -> likes 'tacos', not 'tacos near the mission'
        like = re.split(r"\b(?:near|around|in|at|on|for|with)\b", pos.group(1))[0]
        _add(out["likes"], like)
        if FOOD_RE.search(like) and not out["food"]:
            out["food"] = FOOD_RE.search(like).group(1)
        return
    m = FOOD_RE.search(part)
    if m and not out["food"]:
        out["food"] = m.group(1)
    for w in TASTES:
        if re.search(r"\b" + re.escape(w) + r"\b", part):
            if w == "group" and KIND_GROUP_RE.search(part):
                continue  # T354: 'group dinner' names the kind, not a taste ('Wants: group')
            _add(out["tastes"], w)


def read(text):
    """Plain-rule read of a free line: 'sushi; quiet; likes Ferry Building; avoids loud bars'.
    T320: a 'no' word carries over 'and' / 'or' ('I hate Tartine and loud bars' -> two dislikes),
    a comma, ';', a full stop or 'but' ends it."""
    out = empty()
    t = (text or "").lower().replace("\u2019", "'")
    for clause in re.split(r"[;\n!?]|\.(?:\s|$)|\bbut\b", t):
        neg = False
        for piece in re.split(r"(,|\band\b|\bor\b)", clause):
            if piece == ",":
                neg = False
                continue
            piece = piece.strip()
            if not piece or piece in ("and", "or"):
                continue
            m = NEG_RE.search(piece)
            if m:
                if piece[:m.start()].strip():
                    _plain(out, piece[:m.start()])
                _dislike(out["dislikes"], m.group(1))
                neg = True
            elif neg and not POS_RE.search(piece):
                _dislike(out["dislikes"], piece)
            else:
                neg = False
                _plain(out, piece)
    _kid_facts(out, t)
    return out


def _kid_facts(out, t):
    """T321: ages ('age 4') and needs ('shade', 'toilet') as taste words, never as a dislike."""
    ages = [a or b for a, b in AGE_RE.findall(t)]
    for m in AGE_LIST_RE.finditer(t):
        ages += re.findall(r"\d{1,2}", m.group(1))
    for a in ages:
        if 0 < int(a) < 18:
            _add(out["tastes"], f"age {int(a)}")
    for word, pattern in NEEDS.items():
        if re.search(r"\b(?:" + pattern + r")\b", t) and not any(word in d for d in out["dislikes"]):
            _add(out["tastes"], word)


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
    # a taste the person avoids is not a taste ('no loud places' must not rank loud first); T320: a
    # word of a dislike phrase counts too ('hate loud bars' -> no taste 'loud'); T299: no 'free'
    avoided = set(out["dislikes"]) | {w for d in out["dislikes"] for w in phrase_words(d)}
    out["tastes"] = [w for w in out["tastes"] if w not in avoided and _one(w) not in avoided
                     and w not in NOT_WANTS]
    if out["food"] in NOT_WANTS:
        out["food"] = None
    return out


def place_words(a):
    return {t.lower() for t in (a.tags or [])}, a.name.lower()


def is_disliked(a, dislikes):
    tags, name = place_words(a)
    for d in dislikes or []:
        d = _clean(d)
        if not d:
            continue
        if " " not in d:
            if d in tags or _one(d) in tags or (len(d) > 3 and d in name):
                return True
        elif d in name or d in tags:  # a place name ('mission playground') or a tag ('coffee shop')
            return True
        elif is_generic(d) and set(phrase_words(d)) & tags:  # 'loud bars' -> every loud place and bar
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


def shown(phrase):
    """A place name in title case ('Mission Playground'), a generic phrase as it is ('loud bars')."""
    p = str(phrase)
    return p if is_generic(p.lower()) or p != p.lower() else " ".join(w[:1].upper() + w[1:] for w in p.split())


def summary(wants):
    """One short line for the log and the API: 'sushi; quiet; likes ferry building; avoids loud'."""
    if not wants:
        return ""
    bits = ([wants["food"]] if wants.get("food") else []) + list(wants.get("tastes") or [])
    bits += [f"likes {shown(w)}" for w in wants.get("likes") or []]
    bits += [f"avoids {shown(w)}" for w in wants.get("dislikes") or []]
    return "; ".join(bits)
