# Mifgash demo video kit

Two cuts exist. Video v2 (3/11/2026) is the current one. Video v1 (1/11/2026) stays below for reference.
Both play on the private research page on the house server (the link is not in the repo).

## Video v2 (3/11/2026)

File: `media/mifgash-demo/mifgash-demo-v2.mp4`, 2:54 (173.6 s), 1 video stream and 1 audio stream
(narration + music bed), captions burned in. The narration text is in `demo/narration.md`
(15 shots, 402 words, voice Kokoro-82M am_michael, made offline, no paid credit). How to remake the cut: see
"How to remake the v2 cut" at the end of this file.

The story: Chris (the owner, "my agent" on Telegram) is free Thursday evening near North Beach.
Sam is free the same evening but wants to stay in the Mission, so Mifgash makes no match for Sam.
Maria is free near Chinatown, a short walk away, so Mifgash matches Chris and Maria. Maria's agent
says yes first, then Chris approves, the two agents agree on 19:30 at The Stinking Rose
(325 Columbus Ave), and both sides get the outing card and a calendar invite. Every model turn runs
on Muse Spark Open (backend `meta`). Live run: plan 55 on https://mifgash.sveder.com, 3/11/2026.

### v2 shot list

| # | Starts | Sec | On screen | Source | Narration |
|---|---|---|---|---|---|
| 1 | 0:00.00 | 6.8 | Title card with the tagline, then the main page (dark) | cut (live run) | "Meet friends on your terms, without messaging ten people for a yes. This is Mifgash." |
| 2 | 0:06.83 | 14.5 | Main page, the three intent cards | cut (live run) | "A dinner with friends usually costs a group chat, ten messages and a lot of maybes. Most of those messages are about when and where. Mifgash gives that job to your own AI agent." |
| 3 | 0:21.31 | 14.7 | Caption card 'Setup takes one line' with the mif.py one-liner | cut; phone shot P1 can replace it | "Setup takes one line. You give your agent the Mifgash page, and the agent signs you up. My agent runs on Telegram. Any agent that can read a web page and call an API can join." |
| 4 | 0:35.96 | 15.1 | Telegram stand-in: the ask, then the dashboard with the open outing | cut has a stand-in card; phone shot P2 replaces it | "I tell my agent one sentence: I am free Thursday evening for dinner near North Beach. The agent posts that free time to Mifgash. My dashboard shows the open outing: where, when and what." |
| 5 | 0:51.04 | 10.4 | Dashboard friends card: Maria and Sam | cut (live run) | "Maria and Sam are my friends on Mifgash. Each of them has an own agent, and each agent posts their free time the same way." |
| 6 | 1:01.47 | 12.2 | Sam's open outing in the Mission, no match | cut (live run) | "Sam is free on Thursday evening too, but in the Mission, and he wants to stay there. That is too far from North Beach, so Mifgash makes no match for Sam this time." |
| 7 | 1:13.71 | 15.2 | Match card with 'Why it fits' and the Muse tag | cut (live run); phone shot P3 can follow it | "Maria is free on Thursday evening near Chinatown, a short walk away. That is a match. Muse Spark Open, an open-weights Meta model, reads every free-text post and writes why the match fits." |
| 8 | 1:28.92 | 14.1 | Proposal on the human page and in the agent log | cut (live run) | "Nobody is asked in public. Mifgash asks Maria's agent first, and her agent asks Maria. If she says no, nobody sees it, and nobody sees who got the question first." |
| 9 | 1:43.04 | 13.4 | Panel 'Actual agent conversation' from the live log | cut (live run) | "Then the two agents talk. This is the actual conversation from the live site. My agent proposes seven thirty. Maria's agent agrees, and the two agents pick one place." |
| 10 | 1:56.46 | 8.7 | Outing card: The Stinking Rose, 325 Columbus Avenue | cut; phone shot P4 can follow it | "The place is The Stinking Rose on Columbus Avenue, the garlic restaurant. Both agents agree. Bring mints." |
| 11 | 2:05.14 | 10.4 | Outing card dark, then light | cut (live run) | "Maria and I get the same card: the place, the time, a map link and where to park. Nobody had to copy an address from a chat." |
| 12 | 2:15.51 | 6.0 | Calendar page with the .ics and the Google Calendar link | cut (live run) | "One tap puts the dinner in the calendar, with the address and the parking line." |
| 13 | 2:21.48 | 13.4 | The /h/ page for a person with no agent | cut (live run) | "A friend with no agent gets a clean web page. The friend can accept, decline or pick another time there. Mifgash works for people with an agent and for people without one." |
| 14 | 2:34.85 | 7.7 | Dashboard agent log | cut (live run) | "The dashboard shows every step that each agent did, so I always see what my agent said for me." |
| 15 | 2:42.55 | 11.1 | Main page (light), then the end card with the URL and 'Made by Sveder' | cut (live run) | "Three friends, two agents that agree, one dinner, and no group chat. Mifgash, built for the Meta hackathon. mifgash dot sveder dot com." |

Total: 173.6 seconds, 15 shots.

### Phone shots the owner records (v2)

The cut runs without these shots. Each phone shot replaces a stand-in card or follows a shot,
for a real screen. Record them in dark mode, with the demo persona "Chris Demo", on the public site.

Before you record:

- [ ] Kurt needs the Mifgash skill (`integrations/openclaw/SKILL.md` and `mif.py`). It is NOT
      installed in Kurt's live skills. The owner installs it before the recording.
- [ ] Use demo personas only: Chris Demo (you), Maria Demo and Sam Demo (friend agents,
      `demo/video_run.py` plays them). No real names, phone numbers or email addresses on screen.
- [ ] Record before Thursday 5/11, so "Thursday" means Thu Nov 5.
- [ ] Never show an API key or a one-time dashboard link in full. Crop the address bar.
- [ ] After the recording: `manage.py purge_test_people` on the server.

The shots, with the exact words you type:

1. **P1, Telegram, the signup (shot 3):** you type to Kurt:
   `Kurt, sign me up to Mifgash. My name is Chris Demo, handle zz_chris.`
   Kurt answers with the signup line and the dashboard link. Crop the link.
2. **P2, Telegram, the ask (shot 4, replaces the stand-in card):** you type:
   `I am free Thursday evening for dinner near North Beach.`
   Kurt answers: he posted the free time for Thursday evening near North Beach, and nobody is
   open near there yet.
3. **P3, Telegram, the proposal (after shot 7):** Kurt says
   "Maria is free for an evening out on Thursday and wants to meet at The Stinking Rose. Does it
   work for you? Yes, or not this time." You type: `Yes. 19:30 works for me.`
4. **P4, Telegram, the final line (after shot 10):** Kurt says
   "Final: evening out with Maria, Thu Nov 5 19:30, The Stinking Rose, 325 Columbus Ave, San Francisco."
   with the calendar link. You type nothing. (The date form follows T208; before T208 it reads "Thu 5/11".)
5. **P5, the calendar (after shot 12, optional):** tap the calendar link in Kurt's message and show
   the event with the address and the parking line.

No WhatsApp shot in v2. The Instinct test (v1) is not in the v2 cut. If M12 (T172) keeps a
second outside agent, the owner picks the variant there.

---

## Video v1 (1/11/2026)

The shot list and the narration for the hackathon video. It is built on the real public run of
1/11/2026 on https://mifgash.sveder.com: the owner asks his own agent (Kurt, OpenClaw on Telegram),
Kurt signs up, a DIFFERENT agent (Instinct, a cloud AI assistant on WhatsApp) reads `/agents.md`
and signs up alone, Mifgash matches the two, the owner approves, and both sides get the outing card
and a calendar invite.

Every model turn on the public host runs on **Muse Spark Open** (`meta-models/muse-spark-open-1026`,
on Baseten, backend `meta`). The dashboard shows the tag "Muse Spark Open (Baseten)" on the
"Why it fits" line. Show that tag on screen at least once.

### Rough cut (exists)

`media/mifgash-demo/mifgash-demo-rough-*.mp4` (about 75 s, no sound, captions burned in) was made by

    .venv/bin/python manage.py public_cut --link <one-time dashboard link> --plan <outing id> \
        --calendar <calendar short link> --transcript <whatsapp transcript .md> --out <dir>

It holds: the title card, a stand-in card for the Telegram ask, the landing page (dark and light),
`/agents.md`, the WhatsApp chat with Instinct (as a chat card from the real transcript), the
owner's dashboard, the outing card (dark and light), the calendar page and the end card.
Use it as the skeleton. Replace the two stand-in cards with real phone recordings.

### Before you record

- [ ] Record on the PUBLIC host, https://mifgash.sveder.com. It runs on Muse; it has no demo mode.
- [ ] Use demo personas only (for example "Chris Demo" and "Alex Demo"). No real names, no real
      phone numbers, no real email addresses on screen.
- [ ] Phone in dark mode. Hide or crop the address bar where it shows a one-time link.
- [ ] Never show an API key. `mif.py` keeps the key in its key file and never prints it.
- [ ] After the recording: delete the test people (`manage.py purge_test_people` on the server
      removes `zz_` handles; a demo persona with another handle needs a manual delete).

### Shots the owner records on a phone

These shots need a real phone screen. The rough cut has stand-ins or nothing for them.

1. **Telegram, ask (shot 2):** you type to Kurt: "Kurt, sign me up to Mifgash. I am free Tuesday
   evening near Noe Valley." Then Kurt's reply with the signup line and the dashboard link.
2. **Telegram, the proposal (shot 6):** Kurt says "Alex is free for an evening out on Tuesday and
   wants to meet at Firefly. Does it work for you?" You answer "Yes".
3. **Telegram, the final line (shot 8):** Kurt says "Final: 20:00 at Firefly" with
   the calendar links.
4. **WhatsApp (shot 4):** the chat with Instinct, scrolled slowly from the brief to "Final status:
   confirmed". The transcript of the real run is in `whatsapp-instinct-transcript.md`.
5. **Dashboard on the phone (shot 7):** tap the dashboard link, then scroll to the match card and
   the agent log. Hold 2 s on the "Why it fits ... (Muse Spark Open (Baseten))" line.
6. **Calendar (shot 9):** tap "Add to calendar", show the event with the address and the parking line.

### Shot list

| # | Sec | On screen | Source | Narration |
|---|---|---|---|---|
| 1 | 12 | Title card, then the landing page `/` (dark) | rough cut | "Making plans with friends takes ten WhatsApp messages. Mifgash gives the job to your AI agent." |
| 2 | 16 | Telegram: the ask to Kurt and Kurt's reply | the owner's phone | "I tell my own agent when I am free. It signs me up to Mifgash and posts my free time." |
| 3 | 14 | `/agents.md` scrolling | rough cut | "Mifgash has no chat window. It is an API for agents. Any agent can read this one page and join." |
| 4 | 30 | WhatsApp chat with Instinct | the owner's phone (rough cut has a card) | "To test that, I asked a different AI, Instinct on WhatsApp, to play my friend Alex. It read the page, signed Alex up, added me as a friend and posted her free time. I gave it no code." |
| 5 | 12 | Dashboard: the match card with "Why it fits" and the Muse tag | rough cut + phone | "Mifgash sees that we are both free on Tuesday evening near Noe Valley. Muse Spark Open, an open-weights Meta model, reads every free-text post and writes why the match fits." |
| 6 | 16 | Telegram: Kurt asks "Does it work for you?", you say yes | the owner's phone | "Nobody is asked in public. Alex's agent says yes first, then my agent asks me. A no stays private." |
| 7 | 14 | Dashboard agent log | rough cut + phone | "The dashboard shows what each agent did, step by step." |
| 8 | 22 | Outing card dark, then light; Telegram final line | rough cut + phone | "The two agents agree on 20:00. Both of us get the same card: the place, the time, a map and the parking." |
| 9 | 14 | Calendar event | the owner's phone | "One tap puts it in the calendar." |
| 10 | 20 | Landing page (light), then the end card | rough cut | "Two agents, one outing, no group chat. Mifgash, built in one week for the Meta hackathon on Muse Spark Open. mifgash.sveder.com" |

Total: 170 seconds, 10 shots.

### What the real run showed (1/11/2026)

- Instinct used `/agents.md` alone: signup, friend request, free time, accept with a place, the
  time proposal and the final check. Every call answered 200 or 201, except one 403 when it tried
  to propose a time before the owner approved (the guide now says to wait for "confirmed").
- Instinct cannot poll by itself. It said "I'm keeping an eye out" and then did nothing until it
  got a message. Kurt sent 3 short nudges. The guide now tells such an agent to say so to its human.
- Instinct posted its free time before the friendship existed. The one-minute clock matched the two
  plans after the friend accept, with no extra call.

---

## How to remake the v2 cut (T184, 3/11)

1. `python3 demo/video_run.py --out demo/video-run.json` (with `.baseten.env` loaded: the friend agents run on Muse). Four zz_ personas on the live site; ends final at The Stinking Rose, 19:30.
2. On the server, write one-time dashboard tokens for zz_chris and zz_sam (`MagicLink.issue`) and the /h/ tokens of Maria's and Lena's offers into a JSON file (chmod 600, never in the repo): keys `zz_chris`, `zz_sam`, `maria_h`, `lena_h`.
3. `python3 manage.py public_cut --v2 --run demo/video-run.json --links <file> --out media/mifgash-demo/mifgash-demo-v2.mp4` (about 4 minutes). It saves the plan log JSON to demo/video-run-log.json and prints the shot-start table.
4. On the server: `manage.py purge_test_people`.
