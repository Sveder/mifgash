# /agents.md fresh-model test (29/10/2026)

Goal: an agent that knows nothing about Mifgash, and has no SKILL.md and no mif.py, reads only
the text of `/agents.md` and does the job with curl.

Setup: a fresh `claude -p --model sonnet` call in an empty folder, tools limited to `Bash(curl:*)`.
The prompt held the guide text and one line from the human:
"Sign me up to Mifgash, handle zz_t99, home area SoMa. Then tell Mifgash I am free tomorrow for lunch."

Result: pass. 2 calls, no wrong call, no retry. The key and the link token are cut below;
`<host>` stands for the server address.

## Call 1
    curl -s -X POST http://<host>/api/v1/signup/ -H 'Content-Type: application/json' \
      -d '{"name":"Zz Tester","handle":"zz_t99","home_area":"SoMa"}'
    -> {"person_id": 157, "handle": "zz_t99", "name": "Zz Tester", "has_agent": true,
        "home_area": "SoMa", "work_area": null, "webhook": false,
        "api_key": "mif_<cut>", "dashboard_url": "http://<host>/d/<cut>/"}

## Call 2
    curl -s -X POST http://<host>/api/v1/availability/ -H 'Content-Type: application/json' \
      -H 'Authorization: Bearer mif_<cut>' -d '{"text":"free tomorrow for lunch near SoMa"}'
    -> {"availability_id": 148, "status": "open", "date": "2026-10-30", "part": "lunch", "kind": "lunch",
        "area": "SoMa", "radius_km": 3.0, ...,
        "note": "Nobody is open near there yet. Your time stays open, ..."}

## What the agent told its human
> You're signed up to Mifgash as zz_t99, with SoMa as your home area.
> Here is your dashboard link. It works once, so open it yourself: http://<host>/d/<cut>/
> I also posted that you're free for lunch tomorrow, Friday 2026-10-30, near SoMa. The search radius
> is 3 km. Nobody is open near there yet, so your time stays open.
> I haven't accepted anything for you. If a friend proposal comes in, I'll ask you before I answer.
> I also haven't set up a scheduled check of the inbox, so I won't see new proposals until I'm asked to look.

It kept the key out of the reply and promised to ask before an answer. It made no polling job:
the test prompt allowed curl only. A later change makes the guide ask for that job more firmly.
The test user zz_t99 was deleted after the run.
