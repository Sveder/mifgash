# Mifgash hand test from Telegram

A 10-step walkthrough. You talk to your own agent (Kurt, OpenClaw) on Telegram. Kurt talks to the
Mifgash API through `integrations/openclaw/mif.py`. You watch the result on the dashboard on your phone.

Before you start:

- The one live site answers 200: `curl -s -o /dev/null -w "%{http_code}" https://mifgash.sveder.com/`. There is no home copy any more.
- Your phone is on the home Wi-Fi. The links in the replies use the server's public address
  (`MIFGASH_PUBLIC_URL` in the unit file). Off the home network they do not open yet (task T16).
- Kurt has no Mifgash skill installed. Step 1 tells Kurt to read the SKILL.md from the repo. No install.
- "Tomorrow" in this file is the day after the test. The demo friend Maria has a weekly free time on
  Friday morning, so a test on a Thursday gives a match with Maria. On another day, see step 4.

Each step: what you say, what Kurt should answer, what the dashboard shows, and what to do when it fails.

## 1. Sign up

- You say: `Kurt, read integrations/openclaw/SKILL.md (in your Mifgash checkout) and sign me up to Mifgash, home area SoMa`
- Kurt runs: `python3 <repo>/integrations/openclaw/mif.py signup "<your name>" <handle> --email <your email> --home SoMa`
- Kurt answers: `Signed up as @<handle>. Dashboard (one-time link): https://mifgash.sveder.com/d/<token>/`
- Dashboard: nothing yet. You get the link only.
- When it fails: "409: handle taken" means another handle. "Not signed up yet. Ask your human: which
  area?" means Kurt must ask you for the area. A link that starts with `http://localhost` is a bug:
  the unit has no `MIFGASH_PUBLIC_URL`.

## 2. Open the dashboard

- You do: tap the link on your phone, then tap "Open my Mifgash dashboard".
- Dashboard: "Hi, <your name>", "Open outings: No open outings. Tell your agent when you are free.",
  and the agent log with the signup.
- When it fails: a "used or expired" page means the link was spent. Say `Kurt, send me my Mifgash link`.
  Kurt runs `link` and sends a new one.

## 3. Add a friend

- You say: `Kurt, add maria on Mifgash`
- Kurt runs: `friends search maria`, then `friends add maria`.
- Kurt answers: `Added @maria (Maria) as a friend.` (Maria is a demo friend and adds you back at once.)
- Kurt can also add `jordan` (a demo friend with no agent).
- The search returns @maria only.
- When it fails: search shows more than one Maria. Take `@maria` exactly, and tell the factory.

## 4. Say you are free

- You say: `Kurt, I'm open tomorrow`
- Kurt runs: `open "I'm open tomorrow"`
- Kurt answers (Thursday test): `Posted: you are free Fri Oct 30 morning (id N). A friend is
  free for morning that day, so I took morning. ... Near your home area, SoMa. ...
  Finding friends now.`
- Dashboard: the agent log has your post, a "Read as" row (tagged Claude) and a "find" row.
- When it fails: "No match yet" means no demo friend is free that day. On another weekday, say a time
  that fits a demo friend, or check that no test person holds Maria (`manage.py purge_test_people --dry-run`).

## 5. Hear the proposal

- You say: `Kurt, any plans?` (or wait: Kurt runs `inbox` when he has a polling job)
- Kurt runs: `proposals`
- Kurt answers: `Maria is free for a weekend outing on Fri Oct 30 morning and wants to meet at Embarcadero
  waterfront walk. Does it work for you? ... Places: [24] Embarcadero waterfront walk; [21] ... Ask your human.
  Yes: 'respond <proposal id> accept --choice 24' (or another place id). No: 'respond <proposal id>
  decline'.` The `inbox` line for the same proposal ends with the same places and commands.
- Dashboard: an ask card for Maria with the same places.
- When it fails: "No proposals wait for you." Run step 4 again with `open-list`, and check the state.

## 6. Say yes

- You say: `Yes, the Embarcadero walk`
- Kurt runs: `respond <proposal id> accept --choice 24`
- Kurt answers: `You said yes. You are both in: Fri Oct 30 morning, Embarcadero waterfront walk, with Maria.
  Mifgash set 10:00. Add to calendar: https://mifgash.sveder.com/c/<code> .ics: ... To move it: 'finalize N --time HH:MM'.`
- Dashboard: under Matches, a card that says "It is set" with 10:00, the calendar buttons and
  "Change time" chips (09:30, 10:30, 11:00) plus an Other select. Nobody runs `finalize`.
- When it fails: Kurt must never answer before you say yes. If he does, write it down: that is a
  SKILL.md bug.

## 7. Check the state

- You say: `Kurt, what is set on Mifgash?`
- Kurt runs: `outings`
- Kurt answers: `1 outing: [N] Final: Weekend (morning), Fri Oct 30, 10:00 AM, Embarcadero
  waterfront walk, Embarcadero at Market St, San Francisco. With Maria.`

## 8. Move the time (optional)

Mifgash already set the time in step 6. Only move it when you want another time.

- You say: `Make it 10:30`
- Kurt runs: `finalize N --time 10:30`
- Kurt answers: `Moved to 10:30 at Embarcadero waterfront walk, Embarcadero at Market St, San Francisco. The
  others hear the new time. Add to calendar: https://mifgash.sveder.com/c/<code> .ics: ...`
- Dashboard: the card says "It is set", "Fri Oct 30, 10:30 AM". The log has "Michael moved a weekend outing to 10:30."
- You can also press a "Change time" chip on the dashboard card instead of the chat.

## 9. Add it to the calendar

- You do: tap the Google Calendar link from Kurt's reply.
- Result: Google Calendar opens a new event "Weekend outing with Maria", Fri Oct 30 10:00, with the
  address in the location and the map link and parking in the details.
- The .ics link downloads an invite for any other calendar app.

## 10. Read the log

- Dashboard: scroll to "Agent log". Every step above has one row, newest first: who sent it
  (your agent, Maria's agent or Mifgash), and the plain line. Nobody's "no" is named anywhere.

## After the test

- Tell the factory what broke: one line per step, with the step number.
- Your signup stays. Test people (handles that start with `zz_` or `crit_`) are removed by
  `manage.py purge_test_people`.

## For the critic and the developer runs

Sign up with a `zz_` handle prefix (for example `zz_crit1029`), and run mif.py with your own
`--key-file` so you never touch `~/.mifgash/key`. Critic and develop runs sign up with a `zz_` or
`crit_` prefix and run `manage.py purge_test_people` after the run (`--dry-run` first), so no test
person holds a demo friend's free time before Michael's test.

## Screenshots, light and dark (UI regression check)

One command takes a full-page PNG of every page with a 390x844 and a 1280x800 viewport, in light and
dark (`prefers-color-scheme`), and writes them to `media/screens/<YYYYMMDD-HHMM>/` (gitignored):

    .venv/bin/pip install -r requirements-dev.txt   # once: websocket-client
    .venv/bin/python manage.py screens --url https://mifgash.sveder.com

- It signs up a `zz_scr<4 hex>` person through the API, adds Maria and Jordan, and makes these states
  8-13 days ahead (never tomorrow, the hand-test day): an ask from Maria, a plan where Jordan said yes
  and waits for you, a plan that asks Jordan now, a confirmed and a final outing, a lunch Jordan agreed and
  must time on the human page, a plan that closed while Jordan was asked, and a plan still looking.
- Pages: landing, link open, dashboard, outing (confirmed and final), friends, human page (pending,
  waiting, agreed, set, closed), link used, link expired, open times. 14 pages x 2 sizes x 2 themes = 56 PNGs.
- It purges its own test person at the end, also when it fails. `--keep` leaves the person for a look by hand.
- Chromium: `MIFGASH_CHROME`, else the first Chromium build in `~/.cache/ms-playwright/`.
- Every UI task links the folder of a run in its review note.
