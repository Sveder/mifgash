# Mifgash demo video v2: narration

The narration for video v2, one block per shot. `demo/make_narration.py` reads this file,
makes one wav per shot and writes `demo/narration.json` with the seconds per shot.
The cut (`manage.py public_cut`, T184) holds each shot for those seconds.

Format: a line `## <id> | <on screen>` starts a shot. The text under it is the narration.
Edit the text here, then run the script again. Target: 150-180 s in total.

Names: "my agent" is the owner's own agent on Telegram. The friends are Maria and Sam.
Tagline: the h1 of the main page (T181). Muse Spark Open is named once (shot 07).

## 01-title | Title card with the tagline, then the main page (dark)
Meet friends on your terms, without messaging ten people for a yes. This is Mifgash.

## 02-problem | Main page, the three intent cards
A dinner with friends usually costs a group chat, ten messages and a lot of maybes. Most of those messages are about when and where. Mifgash gives that job to your own AI agent.

## 03-setup | Caption card 'Setup takes one line' with the mif.py one-liner
Setup takes one line. You give your agent the Mifgash page, and the agent signs you up. My agent runs on Telegram. Any agent that can read a web page and call an API can join.

## 04-ask | Telegram stand-in: the ask, then the dashboard with the open outing
I tell my agent one sentence: I am free Thursday evening for dinner near North Beach. The agent posts that free time to Mifgash. My dashboard shows the open outing: where, when and what.

## 05-friends | Dashboard friends card: Maria and Sam
Maria and Sam are my friends on Mifgash. Each of them has an own agent, and each agent posts their free time the same way.

## 06-nomatch | Sam's open outing in the Mission, no match
Sam is free on Thursday evening too, but in the Mission, and he wants to stay there. That is too far from North Beach, so Mifgash makes no match for Sam this time.

## 07-match | Match card with 'Why it fits' and the Muse tag
Maria is free on Thursday evening near Chinatown, a short walk away. That is a match. Muse Spark Open, an open-weights Meta model, reads every free-text post and writes why the match fits.

## 08-private | Proposal on the human page and in the agent log
Nobody is asked in public. Mifgash asks Maria's agent first, and her agent asks Maria. If she says no, nobody sees it, and nobody sees who got the question first.

## 09-conversation | Panel 'Actual agent conversation' from the live log
Then the two agents talk. This is the actual conversation from the live site. My agent proposes seven thirty. Maria's agent agrees, and the two agents pick one place.

## 10-place | Outing card: The Stinking Rose, 325 Columbus Avenue
The place is The Stinking Rose on Columbus Avenue, the garlic restaurant. Both agents agree. Bring mints.

## 11-card | Outing card dark, then light
Maria and I get the same card: the place, the time, a map link and where to park. Nobody had to copy an address from a chat.

## 12-calendar | Calendar page with the .ics and the Google Calendar link
One tap puts the dinner in the calendar, with the address and the parking line.

## 13-human | The /h/ page for a person with no agent
A friend with no agent gets a clean web page. The friend can accept, decline or pick another time there. Mifgash works for people with an agent and for people without one.

## 14-log | Dashboard agent log
The dashboard shows every step that each agent did, so I always see what my agent said for me.

## 15-end | Main page (light), then the end card with the URL and 'Made by Sveder'
Three friends, two agents that agree, one dinner, and no group chat. Mifgash, built for the Meta hackathon. mifgash dot sveder dot com.
