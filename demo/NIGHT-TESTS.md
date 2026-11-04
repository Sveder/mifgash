# Night tests (live site, mifgash.sveder.com)

Test people use `zz_` handles and `@example.com` addresses. They are purged after each run
(`manage.py purge_test_people`).

## 1. Playdate, 3 parents (T289, re-run Wed Nov 4, about 12:30 Israel)

The critic run of 4/11 01:00 (@zze_grace owner 'kids 5 and 7, shade and a toilet, we do not like
Dolores Park'; @zzc_ava '4 year old, indoor if it rains'; @zzc_ben 'kids 3 and 6, we love Precita
Park'): PASS kid-friendly place (Randall Museum, Sat 10:00), Dolores Park never offered, all 3 got
'Set' with both other names, .ics (America/Los_Angeles, map, parking), gentle wording. FAIL 'Dolores
Park' banned every park (T303 -> T320), shade/toilet and ages dropped (T305 -> T321), Ava's --note
dropped (T301 -> T323), 'You are both in' with 3 people (T309 -> T322), card title 'With kids with ...'.

Re-run after T320-T323, droplet at b82521a. 3 agents with `mif.py` (`zz_p881f_*`, `@example.com`).
Ava and Ben post a free Saturday morning near Mission first; then Grace posts the playdate.

| Step | Input | Result | Verdict |
|---|---|---|---|
| Ava posts | `open "free Saturday morning for a playdate near Mission" --prefs "our kid is 4 years old; indoor if it rains"` | "Wants: indoor; age 4." ("if it rains" is lost) | PASS (detail -> T383) |
| Ben signup | `--home "Bernal Heights"` | refused: area not covered. Signed up in Mission | FAIL -> T384 |
| Ben posts | `--prefs "kids 3 and 6; we love Precita Park"` | "Wants: age 3; age 6; likes Precita Park." | PASS |
| Grace posts | `open "playdate Saturday morning with 2 friends near Mission, kids 5 and 7" --prefs "shade and a toilet; we do not like Dolores Park"` | "Wants: age 5; age 7; shade; toilet; avoids Dolores Park." | PASS (T320, T321) |
| Places | Ben's ask (137), Grace's ask from Ava (136) | Potrero Hill Rec Center, Alioto Mini Park, Mission Playground; Noe Valley Rec Center (indoor). Parks are offered, Dolores Park never | PASS (T320) |
| Liked place | Precita Park | not in the venue data: cannot be picked, nobody is told | FAIL -> T384 |
| Ask wording | proposal 137 | no "A few friends may join"; why line uses the given facts | PASS (T321, T322) |
| Note on a yes | Ben: `respond 137 accept --choice 190 --note "we can bring snacks"` | owner: "Friend text (untrusted): we can bring snacks" | PASS (T323) |
| 3 parents in one plan | Grace approves Ben | plan 180 final at once for 2 people (Grace, Ben), Sat Nov 7, 10:00 AM, Mission Playground. Ava is not asked in it | FAIL -> T382 |
| Double booking | Grace says yes to Ava's ask 136, Ava approves | Grace has 2 outings at the same time and place ([179] with Ava, [180] with Ben); Ava and Ben never see each other | FAIL -> T382 |
| Card and .ics | Grace's dashboard, `/c/180-...ics` | cards "Playdate with Ava Brooks", "Playdate with Ben Carter"; .ics "Playdate with Ben", 10:00-11:30 America/Los_Angeles, Mission Playground | PASS |
| Agent line | `outings` | "Final: Kids (morning), Sat Nov 7, 10:00 AM ..." | FAIL -> T383 |
| Gentle wording | every reply | no forbidden words, no "both" for a group | PASS |

Result: 9 PASS, 5 FAIL (T382 3 parents split and the owner double booked, T383 'Kids (morning)' line,
T384 Precita Park and Bernal Heights missing). Regression test: PlaydateNightTest1Tests
(parse + match: ages and needs kept, Dolores Park never offered, other parks still allowed), and
KidsWordingT321Tests. Purged after the run: the 3 `zz_p881f_*` people.

## 2. Group dinner (T290, re-run Wed Nov 4, about 12:00 Israel)

The critic run of 4/11 00:45 (plan 94): PASS friends asked one at a time, the decline not named, the
group filled, one place near the centre, the human page, calendar links. FAIL group progress hidden
(T327), one guest moved the time for all (T328), a guest's place vote dropped (T329), the invite page
showed a handle and /join/ forgot the inviter (T330).

Re-run after T327-T330, droplet at b82521a. 5 agents with `mif.py` and 1 person with no agent on the
web (`zz_g37c0_*`, each with a tagged address on a test inbox). Olivia owns the plan. Noah, Liam
and Mia are near Mission, Emma is in Berkeley. Sofia joins on the web from Olivia's friend link.
Mia posts her free time after the plan is out (the late joiner).

| Step | Input | Result | Verdict |
|---|---|---|---|
| Invite page | Sofia opens Olivia's `/i/<token>/` | "Join Olivia Grant (@zz_g37c0_olivia) on Mifgash as a friend" | PASS (T330) |
| /join/ from the invite | Join on the web | "Olivia Grant invited you. You become friends when you join." After submit: "You and Olivia Grant are friends now." | PASS (T330) |
| Owner posts | `open "group dinner Friday evening with 3 friends near Mission"` | plan 177, Fri Nov 6 evening, near Mission | PASS |
| Random order | | Liam asked first, then Noah, then Sofia, then Mia. One ask at a time | PASS |
| Decline | Liam: `respond 132 decline` | Liam is not named in any later text, page or API reply | PASS |
| Far friend | Emma in Berkeley | never asked | PASS |
| Vote in the owner ask | Noah: `respond 133 accept --choice 660` | "Noah votes Aaha Indian Cuisine." No why line about Foreign Cinema | PASS (T329) |
| Progress, owner | `outings` after one yes | "Asking: 1 of 3 in (Noah), asking more" | PASS (T327) |
| Progress, guest | Noah `outings` | "You are in, 1 of 3 in, waiting for 2 more" | PASS (T327) |
| Next ask names who is in | Sofia's dashboard; later Mia's ask | "Noah is coming, 2 places left."; "Noah and Sofia are coming, 1 place left." | PASS (T327) |
| Human without an agent | Sofia: Yes on `/d/`, picks Foreign Cinema | owner ask: "Sofia votes Foreign Cinema; the group so far: Aaha Indian Cuisine (1)." | PASS (T329) |
| Dashboard note | the same owner ask | "Friend text (untrusted): answered on the dashboard" | FAIL -> T379 |
| Late joiner | Mia posts after the plan is out, picks Aaha | asked, says yes; owner ask shows "Aaha Indian Cuisine (1), Foreign Cinema (1)" | PASS |
| Group fills | Olivia approves Mia | Final for all 4: Fri Nov 6, 7:30 PM, Aaha Indian Cuisine (majority 2 of 3), one card naming the 3 others | PASS |
| Loser told | Sofia's final line | "... Most of the group picked Aaha Indian Cuisine." Noah and Mia: no such line | PASS (T329) |
| Guest time tap | Sofia taps 8:00 PM | plan stays 7:30 PM; Sofia: "You asked Olivia to move it to 8:00 PM."; Olivia `outings`: "Sofia asks to move it to 8:00 PM: 'finalize 177 --time 20:00' to approve." | PASS (T328) |
| Owner inbox line | Olivia `inbox` | "Agree: 'finalize 177 --time 19:30'" (the old time) | FAIL -> T380 |
| Approve | Olivia `finalize 177 --time 20:00` | moved; Noah, Mia, Sofia get "Olivia moved a group dinner to 8:00 PM. You are all in ..." | PASS (wording -> T381) |
| Keep | Sofia asks 8:30 PM; Olivia's card shows "Move to 8:30 PM" / "Keep 8:00 PM"; Olivia taps Keep | time stays 8:00 PM; Sofia: "Olivia keeps the group dinner at 8:00 PM." | PASS (T328) |
| Calendar | `/c/177-...ics` | America/Los_Angeles, 20:00-21:30, "Group dinner with Noah, Sofia and Mia", Aaha Indian Cuisine, 3316 17th Street | PASS |
| Email (SES) | the test inbox, every tagged address | no mail for anybody. Agents: by design (mail only as the 24-hour fallback and login links). Sofia (no agent): no mail for the ask or the set outing | FAIL -> T360 (open) |
| Small | owner `outings` with 0 in: "Nothing is set yet"; guest card label "Change time" in a group | | FAIL -> T381 |

Result: 18 PASS, 4 FAIL (T379 dashboard note shown as the friend's words, T380 inbox approve
command, T381 wording, T360 no mail to a person without an agent). Regression tests:
test_group_progress_for_owner_guest_and_next_ask (T327), test_t328_a_guest_time_tap_is_an_ask_the_owner_approves_or_keeps,
test_t329_owner_ask_shows_the_vote_and_the_loser_is_told, InviteLinkTests (T330).
Purged after the run: the 6 `zz_g37c0_*` people.

## 3. Tastes and liked places (T291, re-run Wed Nov 4, about 11:40 Israel)

After fixes T324 (restaurants serve dinner, OSM diet tags), T325 (both sides' tastes, food synonyms),
T326 (Wants line on the card, title Dinner). Two agents with `mif.py`, droplet at d43badd.

| Step | Input | Result | Verdict |
|---|---|---|---|
| Ava posts | `open "free Friday for dinner near Mission" --prefs "I am vegetarian, avoid loud bars"` | Wants: vegetarian; avoids loud bars. Pick Aaha Indian Cuisine (vegetarian, vegan, indian, dinner) | PASS (was a bar on Hayes St) |
| Ben posts | `open "free Friday for dinner near Mission" --prefs "sushi; likes Foreign Cinema"` | Proposal 131. Places: Aaha Indian Cuisine, Foreign Cinema, Thanh Tam II. No bar | PASS |
| Why line | proposal 131 | "... Aaha Indian Cuisine in Mission offers vegetarian for dinner." No "live or work" | PASS |
| Liked place first | Ben likes Foreign Cinema | Foreign Cinema is 2nd: the model pick (Aaha) stays first | FAIL -> T373 |
| Owner view | Ava's availability 169 | wants = Ava's own (vegetarian, loud bars); no sushi | PASS |
| Accept | Ben accepts 660, Ava approves | Final: Fri Nov 6, 7:30 PM, Aaha Indian Cuisine, .ics link | PASS |
| Title | plan 169 ("dinner") | Card title Dinner; agent lines say "evening out" / "Final: Evening" | FAIL -> T374 |
| Tacos | `open "I am free Saturday for lunch, I love tacos near the Mission"` | Wants: tacos (no "free"). Pick La Taqueria; La Corneta, Pancho Villa. No "No tacos place" | PASS |
| Dislikes | `--prefs "vegetarian; we don't like Aaha Indian Cuisine and loud bars"` | Wants: vegetarian; avoids Aaha Indian Cuisine; avoids loud bars. Places: Thanh Tam II, Abu Salim, Beit Rima | PASS |
| Card | Ben's dashboard | `Wants: vegetarian, avoids Aaha Indian Cuisine, avoids loud bars` on the open card | PASS |
| Docs | agents.md section 3, SKILL.md `open --prefs` | both tell the agent to send liked and avoided places; `mif.py open --prefs` is covered by test_open_prefs_reaches_the_plan | PASS |

Result: 9 PASS, 2 FAIL (T373 liked place under the model pick, T374 'evening out' wording for a typed dinner).
Purged: zz_tava1131, zz_tben1131 (2 people, 4 plans, 31 log rows).
