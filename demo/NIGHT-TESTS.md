# Night tests (live site, mifgash.sveder.com)

Test people use `zz_` handles and `@example.com` addresses. They are purged after each run
(`manage.py purge_test_people`).

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
