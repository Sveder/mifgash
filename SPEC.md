# Mifgash: spec (28/10/2026, rewritten to the owner's 28/10 22:07 brief)

"Mifgash" (מפגש) is Hebrew for "meetup". It also works as a verb: "mifgash me tomorrow". Short form: "mif".
The name lives in one setting: `PRODUCT_NAME` in `mifgash_site/settings.py`.

**One line:** you tell YOUR OWN agent when you are free. Your agent talks to the Mifgash API. Mifgash finds
a friend who is free too, near you, and sets up the meetup. Nobody feels left out.

Mifgash is a general social planner. A playdate is one option. It is not the main case.

## 1. What changed from the first POC

- You do NOT chat with the site. You talk to your own agent (in the demo: OpenClaw on Telegram).
  The agent calls the Mifgash API.
- The site is a **user dashboard**. It shows what your agent did: open outings, matches, the agent log.
  The outing card stays. The card shows no raw JSON.
- A person with no agent gets one clean web page for a proposal (section 6).

## 2. User types

| Type | Has an agent | What the person does |
|---|---|---|
| Member with an agent | yes | Talks to the own agent: "I am open tomorrow for lunch". Reads the dashboard. |
| Member without an agent | no | Gets a link (email, Telegram or WhatsApp stub). Sees one calm page with the proposal. |

## 3. Main flow (the demo scenario)

a. **Sign up.** "Kurt, sign me up to Mifgash." The agent calls `POST /api/v1/signup`. The API returns an
   agent key and a dashboard magic link. The agent sends the link to its human.
b. **Friends.** Import from Facebook (OAuth is a stub for now, real later), or search users by handle or id
   and add them.
c. **Availability.** "I am open tomorrow" (told to the agent on Telegram). The agent posts an availability.
   The dashboard shows an open outing: where, when, what.
d. **No match.** Two friends do the same. One friend wants a different place that is too far. Mifgash makes
   no match for now. (Later: "Is it fine to go a bit out of your way?", maybe asked ahead of time.)
e. **Match.** The other friend matches. Mifgash picks ONE candidate at random. Mifgash shows that friend
   the match and asks "does this make sense?": through the friend's agent (webhook), or the human directly
   (email, Telegram or WhatsApp, stubs in the POC). The agent asks its human. The human approves. Then the
   match goes to the person who posted first, to approve or decline. The gentle rules (section 5) apply:
   nobody sees who declined or who was asked first.
f. **Human page.** A person with no agent sees the proposal on a web page and accepts, or picks another
   time or place.
g. **Finalize.** Mifgash fixes the exact time and place, in the first messages or with more
   agent-to-agent turns.
h. **Calendar invite.** An `.ics` file and a Google Calendar link, with the address, a map link and
   parking information.

Later polish, only after a-h work end to end: groups; activities, not only places; context-aware
acceptance; standing "free times"; meeting new people, friends of friends, mixed lunches;
conversation-topic hints.

## 4. Agent API (`/api/v1/`)

Every call carries `Authorization: Bearer <agent key>`, except signup. The server stores a hash of the
key only.

| Endpoint | Job |
|---|---|
| `POST /signup` | New member. Returns the agent key and a dashboard magic link. |
| `GET /friends/search?q=` | Find members by handle or id. |
| `POST /friends` | Add a friend. |
| `POST /friends/import/facebook` | Import friends (stub OAuth in the POC). |
| `POST /availability` | Free text ("open tomorrow lunch near SoMa") or structured fields: when, where, radius, kind, group. |
| `POST /availability/<id>/confirm/` | Group dinner: the owner takes the group as it is now (at least one yes). |
| `GET /proposals` | Proposals that wait for this member: `role` candidate (a friend's plan asks you) or owner (a friend said yes to your plan). |
| `POST /proposals/<id>/respond` | `{answer: accept|decline, choice_id?, note?}`. Candidate yes -> waits for the owner; owner yes -> confirmed; owner no -> the friend hears the neutral close line and the next friend is asked. A note stays private. |
| `GET /outings/`, `GET /outings/<id>` | Read your outings: confirmed, proposed time, final with calendar links. |
| `POST /outings/<id>/finalize` | Fix the exact time and place. |
| `GET /events/?after=<id>` | Poll your own push events with an id cursor, for an agent with no public webhook URL. |
| `PUT /webhook` | Set the URL where Mifgash pushes proposals to the agent. |

Free text from the agent goes to the LLM, which returns a structured availability. Code checks every field.

An OpenClaw skill for the owner's agent lives in `integrations/openclaw/` (`SKILL.md` and a small Python
client `mif.py`). Simulated demo friends are LLM agents with their own preferences. They call the same API,
so the demo video shows real agent-to-agent traffic.

## 5. Gentle matching rules

These rules are code, with tests (`planner/tests.py`). The wording lives in `planner/messages.py` only.

1. **Random order, no ranking.** No "closest first", no "best friend first". A ranking means "they preferred someone else".
2. **Sequential offers.** One open offer per plan. A friend never sees that someone was asked before.
3. **No visible rejections.** The owner never sees who said no, who did not answer, or how many friends were asked.
4. **A "no" reason stays local.** The friend's agent sends a bare `decline`. The reason never leaves the friend's side.
5. **Unasked friends hear nothing.** When the plan fills, the rest of the queue is marked `not_sent`.
6. **Neutral wording.** "This time it did not work out. That is normal: free times often do not line up. Here are other options." No names, no reason.
7. **Always a next step.** "Did not work out" always comes with buttons: other times in the next 7 days when at least one friend is open, or "post it as an open slot".
8. **Invite expiry.** An offer expires after `OFFER_TTL_MINUTES` (default 180), or 2 hours before the plan, whichever is first. An expiry is silent: the agent moves to the next friend. A late link shows "This plan is already closed. No problem." and the owner's open times.
9. **Banned words** in any human text: declined, rejected, refused, said no, instead of, first/second choice, preferred, nobody wanted. A test checks every template.

## 6. Member without an agent (web page)

- One link per proposal: `/h/<token>/`. The link is the key. No login.
- The page shows the proposal in one sentence, up to 3 place ideas, and two buttons: "Yes, I will join" and
  "Not this time". The page says that "Not this time" is private.
- Under the proposal: the other person's open times for the next 7 days, each with one activity idea.
- "I can join" on an open time confirms at once, because the other person said that time is open.
- The same list is the member's public open-times page: `/open/<token>/` (Calendly-like).

## 7. Activity catalog

`Activity`: name, kind, area, price (0 free ... 3 high), tags, note. The demo world has 32 real public places in San Francisco, Sausalito, Oakland, Berkeley and Daly City, typed in during the hackathon.

Suggestion logic (`matching.suggest_activities`): same kind, inside radius + 1 km, nearest first, then cheapest. A friend's agent skips places with a tag the friend dislikes (for example "crowded", "loud", "paid"). A food type from the owner's words moves matching places to the top.

Later: import the 128 kids activities collected for school holidays (older data, must be marked "reused"), add a flyer photo to the catalog with a vision model, live events by web search.

## 8. Data model

- `Area`: neighbourhood centre point (no home addresses), aliases for parsing.
- `Person`: is_owner, has_agent, home_area, work_area, likes (kinds), dislikes (tags), max_km, one_on_one_only, kids_ages, token;
  email, phone, telegram, webhook_url, webhook_secret (encrypted), email_digest (HMAC, for lookup by email).
- `AgentKey`: person, prefix, key_hash (HMAC only, the plain key is shown once), label, last_used, revoked_at.
- `Slot`: weekly open time (weekday, part of day, area at that time).
- `Activity`: see section 6.
- Group dinner (kind `group_dinner`, G1): "dinner Friday with 3 friends" asks for 2-6 friends. Offers go out
  one friend at a time in random order; each yes joins. The plan confirms at N yeses, or at `fill_by`
  (15:00 on the day) with 2 or more; the owner can confirm a smaller group earlier. One yes at the
  deadline ends with the neutral "did not come together" line. Nobody sees who said no or the order.
- Group dinner, one place and one time (G2): at the confirm, Mifgash picks a dinner place with big tables
  (tag `group`) nearest the centre of every member's area, fewest dislikes first. The exact time is final
  only when EVERY member sent the same time and place (`Plan.agreed`); a new time or place resets the yeses.
  The outing card, `/h/`, the API (`group_size`, `waiting_for`, `you_agreed`) and mif.py show the group;
  every .ics names everybody.
- `Plan`: owner, kind, date, part, area, radius_km, group_size, min_guests, fill_by, options, chosen, status (draft / asking / confirmed / no_match), seed, llm_backend.
- `Offer`: plan, person, order, status (queued / pending / accepted / declined / expired / not_sent / closed), choice, sent_at, expires_at, token.
- `AgentMessage`: the protocol log.
- `ChatTurn`: the first POC's on-site chat. It goes away with the dashboard.

Storage: PostgreSQL 16 on localhost only, with its own role. Contact handles, phone numbers, emails,
webhook URLs and secrets are encrypted at rest with Fernet keys from `.env` (`planner/crypto.py`, values start
with `enc1:`). An encrypted field accepts no `exact` filter; look up by the HMAC digest column instead.
Agent API keys are stored as an HMAC only. Not encrypted yet: the link tokens `Person.token` and
`Offer.token`; the dashboard magic links in the agent API will be stored hashed.

## 9. Agent-to-agent protocol (mifgash/0.1, JSON)

Every message has `protocol`, `type`, `plan_id`.

```json
{"protocol": "mifgash/0.1", "type": "offer", "plan_id": 12, "offer_id": 31,
 "intent": {"kind": "lunch", "date": "2026-11-01", "part": "lunch",
            "area": {"name": "SoMa", "lat": 37.7785, "lon": -122.4056},
            "radius_km": 3.0, "group_size": 1},
 "options": [{"activity_id": 1, "name": "Ferry Building Marketplace", "area": "SoMa", "price": 2, "tags": ["food hall"]}],
 "expires_at": "2026-10-28T13:00:00+02:00",
 "visibility": {"others_asked": false, "order_shown": false},
 "text": "Michael is free for lunch on Sun 1/11 at 12:30 PM ..."}
```

| type | from -> to | key fields |
|---|---|---|
| `find` | owner agent -> directory | intent, candidates (count), order_seed |
| `offer` | owner agent -> friend | offer_id, intent, options, expires_at, visibility, link (humans only) |
| `accept` | friend -> owner agent | offer_id, choice |
| `decline` | friend -> owner agent | offer_id, `reason_shared: false` |
| `expired` | clock -> owner agent | offer_id |
| `confirm` | owner agent -> each guest | when, where, who |
| `close` | owner agent -> guests of a group that did not come together | outcome, neutral text |
| `join` | human -> owner agent | slot picked on the open-times page |

What one agent may see about another owner: open or not for the asked time, the plan kind, the area centre. Never calendar text, home address or reasons.

## 10. Models: who does what

The LLM reads words. Code decides who is asked, in which order, and what each person sees. That split keeps the gentle rules testable ("verifiable agents").

| Job | Model now (POC) | Hackathon target |
|---|---|---|
| Owner words -> intent JSON | Claude Sonnet 5.5 through `claude -p` (setting `LLM_BACKEND=claude`) | Muse Spark (Meta Model API) or Muse Spark Open on Baseten (`LLM_BACKEND=meta`) |
| Clarifying question wording | fixed templates | Muse Spark, checked by the banned-words test |
| Friend agent decision when rules do not cover the case | rules only (`matching.friend_decision`) | Muse Spark Open (open weights: the friend's data stays with the friend's agent) |
| Voice note -> text | not in POC | Muse Voice Transcribe |
| Invite card picture | not in POC | Muse Image |
| Flyer photo -> new activity | not in POC | Muse Spark vision |
| Order, matching, expiry, wording rules | Python + tests | Python + tests |

The adapter keeps three backends: `claude` (now), `meta` (Muse, replaces Claude later with one setting) and
`stub` (tests). ⚠ Hackathon stage 1 is pass/fail on "uses Meta models". Switch `LLM_BACKEND=meta` before the demo.

## 11. Not in the POC yet

Real Facebook OAuth, real WhatsApp delivery, friend-of-friend discovery, groups, rhythms ("lunch twice a week"), voice.
