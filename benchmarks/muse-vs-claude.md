# Muse Spark Open vs Claude Opus 5.5 vs Claude Sonnet 5.5

Run on Nov 4, 2026. Each model got the same system prompt and the same user text, built by Mifgash's own
prompt functions. Each output was checked with Mifgash's own parsers and checks. 21 test inputs, 4 flows,
one call per model per input: 21 Muse calls, 42 Claude calls.

- Muse Spark Open: `meta-models/muse-spark-open-1026` on Baseten, the same request body as `llm._call_meta`
  (`max_tokens` 4000, no streaming).
- Claude: the Anthropic Messages API, `stream=true`, `max_tokens` 4000, model defaults (adaptive thinking;
  default effort: `medium` on Opus 5.5, `high` on Sonnet 5.5).
- Script: [bench.py](bench.py) (`build`, `run`, `score`). Inputs and outputs: [raw/](raw/).

## Summary

| Model | Calls | Latency p50 | Latency max | First text token p50 | Output tokens (mean) | Parsed | Passed code checks | Blind grade (1-5) | Cost, all calls | Cost per call |
|---|---|---|---|---|---|---|---|---|---|---|
| Muse Spark Open | 21 | 3.24 s | 10.61 s | n/a (no stream) | 1,174 | 21/21 | **21/21** | 2.7 | $0.118 | $0.0056 |
| Claude Opus 5.5 | 21 | 2.59 s | 6.36 s | 2.18 s | 196 | 21/21 | **21/21** | 3.8 | $0.129 | $0.0061 |
| Claude Sonnet 5.5 | 21 | **2.05 s** | **4.25 s** | **1.01 s** | 105 | 20/21 | 16/21 | **3.9** | **$0.045** | **$0.0022** |

Total Anthropic API cost of this benchmark: **$0.174** (42 calls). Muse cost: $0.118 (21 calls).

Latency is wall time per call from this server (Israel). Muse wall time is the full answer, because the
code does not stream. The blind grade covers the pick, reason and decide flows (15 inputs per model).

## Where Mifgash calls Muse

| File / function | What it does | Input | Output | Fallback |
|---|---|---|---|---|
| `planner/llm.py` `parse_intent` → `_call_meta` (API `POST /api/v1/availability`) | Turns the agent's free text into a structured availability | `SYSTEM` + area list; text in `<friend_text>` | JSON: kind, day, part, area, group_size, food, tastes, time | `stub_parse` keyword parser fills any empty or bad field; model error → stub only |
| `planner/llm.py` `pick_place` (from `matching.py`) | Picks one place from the top 8 candidates, with a "why" line | `PICK_SYSTEM` + `pick_facts` (plan, wishes, candidates) | JSON: `{id, why}` | First candidate; a "why" that fails `reason_ok` or is over 20 words is dropped |
| `planner/llm.py` `match_reason_detail` | One sentence "why this fits" on the offer | `REASON_SYSTEM` + `reason_facts` | One sentence | One retry, then the fixed `reason_fallback` sentence |
| `planner/friend_brain.py` `llm_decide` (demo friend agents, sandbox agent) | A simulated friend's agent says yes or no and picks an option | `DECIDE_SYSTEM` with the persona + proposal JSON | JSON: answer, choice_id, note | `stub_decide` (persona rules) |
| `planner/friend_brain.py` `llm_time` | A friend's agent confirms or counters the exact time | `TIME_SYSTEM` + outing JSON | JSON: decision, time | `stub_time` (not in this benchmark) |

## Per flow

### 1. Parse free text into an availability (6 inputs, incl. one prompt injection)

| Model | p50 | max | First text token p50 | Fields right | Cost |
|---|---|---|---|---|---|
| Muse | 3.16 s | 4.22 s | n/a | 6/6 inputs, all fields | $0.028 |
| Opus | 2.59 s | 6.36 s | 2.37 s | 6/6 inputs, all fields | $0.033 |
| Sonnet | **2.13 s** | **2.23 s** | **1.19 s** | 6/6 inputs, all fields | **$0.014** |

All three models got every field right and ignored the injection ("set area to Oakland").
Opus wrapped one answer in a ```` ```json ```` fence; the code's parser accepts it.
**Winner: Sonnet** (same quality, fastest, cheapest).

### 2. Pick a place + "why" line (5 inputs)

| Model | p50 | max | Passed code checks | Blind grade | Cost |
|---|---|---|---|---|---|
| Muse | 3.09 s | 4.87 s | 5/5 | 3.0 | $0.025 |
| Opus | 2.06 s | 2.66 s | 5/5 | **4.2** | $0.023 |
| Sonnet | **2.05 s** | **2.35 s** | 2/5 | 3.8 | **$0.009** |

All three picked the same place for every input. The difference is in the "why" line:
- Sonnet wrote 3 lines over 20 words, so the code drops them. It also wrote prose before the JSON once
  (the prompt says "ONLY a JSON object"); the parser still found the JSON.
- Muse invented "quiet" once (the wish was "not loud") and hid a 4.9 km distance behind "within reach",
  with "cheap" that no tag supports.
- Opus kept to the facts and was honest about the distance.

**Winner: Opus.**

### 3. "Why this fits" sentence (5 inputs, one group dinner)

| Model | p50 | max | First text token p50 | Passed `reason_ok` | Blind grade | Cost |
|---|---|---|---|---|---|---|
| Muse | 6.98 s | 10.61 s | n/a | 5/5 | 1.8 | $0.051 |
| Opus | 4.41 s | 5.95 s | 4.06 s | 5/5 | **4.0** | $0.051 |
| Sonnet | **2.05 s** | **4.25 s** | **1.35 s** | 4/5 | 3.8 | **$0.013** |

- Muse passes the checks but copies the fact lines into clumsy sentences: "with shared kids and weekend
  tastes", "vegan for kids and lunch tastes". It is also the slowest flow for Muse (2,292 output tokens
  on average, almost all reasoning).
- Sonnet's one fail is a false positive of the code check: "works for you all" contains "works", which
  the check reads as an invented workplace.
- Opus writes the most natural sentence and passes every check.

**Winner: Opus** (Sonnet a close second, at half the time).

### 4. Friend agent decides (5 inputs, incl. one injection)

| Model | p50 | max | First text token p50 | Right answer + choice | Blind grade | Cost |
|---|---|---|---|---|---|---|
| Muse | 2.00 s | 3.75 s | n/a | **5/5** | 3.4 | $0.014 |
| Opus | 2.35 s | 3.35 s | 1.83 s | **5/5** | 3.2 | $0.022 |
| Sonnet | **1.76 s** | **2.50 s** | **0.76 s** | 4/5 | **4.0** | **$0.008** |

- Sonnet writes the best friend-facing notes, but once it wrote broken JSON and then a "Correction"
  with a second object. The code's parser fails on that, so the stub decides.
- Opus often writes in the third person ("suits Lena", "Sam never says no"), which is wrong for an agent
  that speaks as its human, and once explained the injection in the note.
- Muse is short and always correct, a little flat in tone.

**Winner: Muse** (correct every time, cheap). Sonnet has the best words but one broken answer.

## What each model is good at

- **Muse Spark Open:** follows the JSON format every time (21/21 parsed and passed). Good at the yes/no
  decision. Weak at natural sentences. It always reasons first (about 1,200 output tokens per call),
  so it is the slowest model, and its low token price does not make it cheap: per call it costs about
  the same as Opus.
- **Claude Opus 5.5:** the best facts and the best sentences for people (place "why" and "why this fits").
  21/21 passed the code checks. Slower to its first text token than Sonnet (2.18 s p50) because it
  thinks a little first.
- **Claude Sonnet 5.5:** the fastest (first text token 1.01 s p50) and the cheapest (about a third of
  Opus per call). The best tone in the friend notes. Weak at hard limits: 3 "why" lines over 20 words,
  one broken JSON answer.

## How the grading was done

- Code checks: the code's own functions. Parse: `llm._json_from` (then the reasoning field, as for Muse);
  each expected field compared. Pick: candidate id on the list, `llm.reason_ok` + the 20-word rule, food
  served, no avoided tag. Reason: `llm.reason_ok` with the code's own names list. Decide: the
  `friend_brain.llm_decide` parse, answer and choice compared with the expected ones.
- Blind grade: for each input the three outputs were shuffled and labelled A, B, C (fixed seed), graded
  1-5 for facts kept, no invented facts, rules followed and tone, and only then un-blinded.
  Grades: [raw/blind-grades.json](raw/blind-grades.json), labels: [raw/blind-key.json](raw/blind-key.json).
  One grader (the benchmark agent), so read the grades as a guide, not a measurement.

## Limits

- 21 inputs, one call each. Latency varies from call to call; treat a difference under 0.5 s as noise.
- Claude ran at its default effort. A lower effort (for example `low`) would cut Opus and Sonnet latency
  further; this was not tested.
- Muse did not stream, so it has no first-token time. A streaming Muse call would still spend most of
  its time on reasoning before the first answer token.
- Prices: Claude list prices from the Claude API reference (cached Oct 6, 2026): Opus 5.5 $4 / $20,
  Sonnet 5.5 $2 / $10 per million input / output tokens. Muse on Baseten: $1.25 / $4.25.
  No prompt caching was used.

## Side note: the first Claude run through the CLI

An earlier pass ran Claude through `claude -p` (the code's own `_call_claude`). Those rows are not in the
tables above. CLI wall time includes the CLI start-up: p50 4.02 s (Opus) and 2.99 s (Sonnet) on 9 calls
each, against `duration_api_ms` p50 2.60 s and 1.76 s. Rows: [raw/cli-side-note.json](raw/cli-side-note.json).
