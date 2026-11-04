# Mifgash: submission text

Text for the Cerebral Valley submit form (Meta Global AI Developer Hackathon, 26/10 - 4/11/2026).

## Project name

Mifgash

## Team

Sveder (solo).

## Tagline

Your agent plans. You say yes.

## Description (150 words or fewer)

Making plans with friends takes ten WhatsApp messages and a fear of "no". Mifgash moves that work
to your own AI agent. You tell your agent "I'm free tomorrow for lunch". The agent posts the free
time to the Mifgash API. Mifgash finds friends who are free near you and asks them one at a time,
in a random order, through their own agents. Nobody sees who said no or who was asked first. A
friend with no agent gets a simple web page. When both sides say yes, the agents
agree on the exact time and place, and each person gets a calendar invite with the address, a map
link and parking. Your dashboard shows every step your agent took. Each agent turn runs on Muse
Spark Open (`meta-models/muse-spark-open-1026`) on Baseten: the model reads free text into a
structured plan and plays the friend agents.

## Why it matters and how it works

Mifgash is an open protocol, not only an app: a meeting layer between personal agents (OpenClaw,
Meta Muse, Instinct and others). Any agent that can read one page (`/agents.md`) or install a skill
can join. A no stays private, and a person with no agent answers on a web page. Inside, a Django
API and a Python matching engine do the matching and the order; Muse Spark Open on Baseten reads
free text, picks the place and writes the "why" line, with a rule-based fallback for every call.
User and agent text goes to the model as data, marked "not instructions"; keys are stored hashed.
Detail, an architecture diagram and the test count: README sections "Why this matters" and
"How it works inside".

## Meta models used

- **Muse Spark Open**, open weights, model id `meta-models/muse-spark-open-1026`, served on Baseten
  (backend `meta`, setting `MIFGASH_LLM_BACKEND=meta`). Used for:
  - reading the owner's free text ("free saturday morning near North Beach") into a structured
    free time: day, part of day, area, radius, kind of outing (`planner/llm.py`, `parse_intent`);
  - the demo friend agents: each one has its own preferences and decides with the model
    (`demo/friend_agent.py`);
  - picking the place with real tool calls: Muse gets two tools, `find_places(area, kind, food)`
    (the top candidates from Mifgash's venue list) and `check_hours(place_id, date, part)`
    (open, closed or unknown from the OpenStreetMap opening hours). Baseten's OpenAI-compatible
    endpoint answers with native `tool_calls`; Python runs each tool and the loop stops after
    3 model calls. Each call is one row on the plan log, for example
    `Muse asked: check_hours(Danny Coyle's, Thu 7:30 PM) -> open` (`planner/llm.py`, `pick_place`);
  - every agent row on the dashboard log carries the model tag, so a viewer sees which model acted.
- Places in any city: a free time in a city Mifgash does not cover yet starts a live
  OpenStreetMap import (Nominatim finds the city, Overpass loads the venues within 3 km,
  `planner/places_live.py`). A place that is surely closed at the plan's day and time is never offered.
- The model reasons before it answers, so the adapter allows 4000 output tokens.
- If a model call fails, a deterministic parser fills in, so a person never sees an error.

## New-work statement

All code in this repository is new work, written during the hackathon (26/10 - 4/11/2026).
The public repo is one squashed commit. The dated private history (over 170 commits,
28/10 - 4/11/2026) is kept and is available to the judges on request.
The first proof of concept (28/10/2026) was built during the event too: it was a chat on the
site, and the agent-first product replaced it the same day.
The demo people are invented. The activity catalog holds real public places, typed in by hand
during the event (`source='hackathon'`). No older code or data is used. The README section
"Built during the hackathon" holds the same table.

## Track

**Build for Your World**: a real problem in the author's own life. Making plans with friends
costs time and the fear of a visible "no", so people meet less than they want to.

## Bonus categories

- **Best Agentic**: your agent talks to Mifgash and to friends' agents; the people only say yes.
- **Best on open weights**: every model call goes to Muse Spark Open, an open-weights model.
- **Most Viral on X**: the demo video is posted on X.
- **Community vote**: entered.

Not entered: Best Creative (no Muse Image or Muse Wonder in the product).

## Links

- Repository (public, MIT, one squashed commit): https://github.com/Sveder/mifgash
- Demo video: https://youtu.be/6XZoucxRXuY (YouTube), 2 minutes 40 seconds (under the 3-minute limit), 1920x1080. Shot list in `demo/VIDEO.md`.
- Live site: https://mifgash.sveder.com
