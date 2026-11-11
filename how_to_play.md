# Island Economy — guide for researchers

This page explains, without technical detail, which parts the study has, which web
address does what, and what you can do today. For setup and code, see `README.md`.

---

## The game in one paragraph

Four participants ("islanders") share one sea. Each round they split 10 effort points
between **fishing** (coins now), **building infrastructure** (better fishing for everyone
later) and **saving** (safe private coins). Over-fishing shrinks the fish stock for
everyone; below a threshold it stops growing back. In the **no-coordinator** condition the
group governs itself. In the **coordinator** condition a fifth participant sets the rules
(coming next). At the end, each participant's coins plus savings become a bonus payment.

---

## The four parts

| Part | Who uses it | What it is for |
| --- | --- | --- |
| **Participant website** | Participants | Instructions, waiting room, the game itself, final payoff |
| **Researcher dashboard** | You | Meant for managing sessions and watching groups (see below: not ready yet) |
| **Game server** | Nobody directly | Runs every game, keeps the clocks, stores all data. Also has a researcher page for creating and checking sessions |
| **Database** | Nobody directly | Where everything is stored |

When the research engineer starts the study on a laptop with Docker, these appear as four
"services":

| Docker service | Part | Address on that laptop |
| --- | --- | --- |
| `frontend-dev` | Participant website | http://localhost:3000 |
| `dashboard-dev` | Researcher dashboard | http://localhost:3001 |
| `backend` | Game server | http://localhost:8000 |
| `db` | Database | (no web page) |

On the institute's servers each part gets its own web address of the form
`https://<project>-frontend.<cluster>`, `https://<project>-dashboard.<cluster>` and
`https://<project>-backend.<cluster>`. Ask the research engineer for the exact addresses
of this project.

---

## Addresses you will use

Replace `PARTICIPANT-SITE` and `GAME-SERVER` with the addresses above.

| Address | What you see |
| --- | --- |
| `PARTICIPANT-SITE/play?session=CODE` | **The study link for participants.** Instructions, then the waiting room, then the game |
| `PARTICIPANT-SITE/instruction` | **Preview of the instructions** exactly as participants see them. Nothing is recorded |
| `GAME-SERVER/docs` | **Researcher page** for creating sessions and checking on them (log in with the dashboard username and password) |
| `GAME-SERVER/api/admin/sessions` | List of all sessions (asks for the same login) |
| `GAME-SERVER/api/admin/sessions/CODE` | One session: how many people are waiting, and each group's condition, round, phase and status |

**Example on a laptop running the study with Docker** (session code `AB12CD34`):

| What | Open this address |
| --- | --- |
| Participant link | http://localhost:3000/play?session=AB12CD34 |
| Participant link as Prolific would send it | http://localhost:3000/play?session=AB12CD34&PROLIFIC_PID=test001&STUDY_ID=pilot&SESSION_ID=s1 |
| Instructions preview | http://localhost:3000/instruction |
| Researcher page (create sessions) | http://localhost:8000/docs |
| All sessions | http://localhost:8000/api/admin/sessions |
| This session's progress | http://localhost:8000/api/admin/sessions/AB12CD34 |
| Researcher dashboard | http://localhost:3001 |

To try a whole game alone, open the participant link in four different browser windows
(for example, private windows or different browsers). Each window counts as one
participant. If you use the Prolific-style link, give each window a different
`PROLIFIC_PID` (`test001`, `test002`, …), because one Prolific ID counts as one person.

All numbers in the instructions (effort points, prices, bonus rate, …) are read from the
game's settings file, so the instructions always match the game.

---

## Running a session today

1. **Create a session.** Open `GAME-SERVER/docs`, click **Authorize** and log in. Open
   *POST /api/admin/sessions*, click **Try it out**, and fill in, for example:

   - `label`: a name you will recognise, e.g. `pilot 12 Nov`
   - `conditions`: `["none"]` (the coordinator condition is not available yet)
   - `seeds`: one number per group you plan, e.g. `[1, 2, 3]` for three groups

   Click **Execute**. The answer contains the **session code**, e.g. `AB12CD34`.

   *What is a seed?* It fixes the luck of a group: starting coins, fishing skills, the
   events at sea and the number of rounds. Using the same seed in both conditions gives
   both conditions exactly the same luck, so differences come from the condition.

2. **Put the link in Prolific:**
   `PARTICIPANT-SITE/play?session=AB12CD34`
   In Prolific, choose to record Prolific IDs **with URL parameters**. Prolific then adds
   `PROLIFIC_PID`, `STUDY_ID` and `SESSION_ID` to the link by itself.

3. **Watch.** Open `GAME-SERVER/api/admin/sessions/AB12CD34` and refresh it to see how many
   people are waiting and how far each group is.

**How participants move through the study**

1. They open the link and read the instructions (9 short pages, one with a "try it" example).
2. They wait until 4 participants are there. The first four become group 1 (first seed),
   the next four group 2, and so on. When all planned groups are full, later arrivals are
   told that the session is full.
3. They play. Each round has four steps — **Event, Talk, Decide, Results** — each with a
   timer. A step ends early when everyone is done.
4. They see their final coins and bonus.

**Good to know**

- If someone does not decide in time, their choice from the previous round is used again
  (in round 1 a default split), and this is recorded as a timeout.
- A participant who closes the tab can reopen the same link and continue where the group is.
- If the game server is restarted, games that are running at that moment end; their
  participants see a message to contact you. Do not restart the server during a session.
- Nobody — not participants, not the coordinator — is told how many rounds there are.

---

## The researcher dashboard

**Today** the dashboard is still the institute's project template: a login page and a list of
"users" from the template. It does **not** show this study's sessions or groups yet. Use the
game server's researcher page described above instead.

**Planned** (milestone 8), the dashboard will let you:

- create sessions and choose conditions and seeds,
- watch every group live (round, phase, who is connected),
- see dropouts and flagged groups,
- download all data as spreadsheets (CSV) and Parquet files.

---

## What is recorded

Every action is stored with a time stamp: when someone joins, how long they spent on the
instructions, entering the waiting room, every decision (with response time and how often
the sliders were moved), timeouts, the full outcome of every round (catch, income, savings,
stock, infrastructure), the optional fairness ratings, and the final payments. Each group
also records its condition, seed, the exact settings file and the program version used.

Prolific IDs are stored **separately** from the game data; the game data uses anonymous IDs
only.

---

## What exists and what is coming

| Available now | Coming |
| --- | --- |
| No-coordinator condition, end to end | Coordinator condition and coordinator screen (milestones 4 and 6) |
| Instructions with an interactive example | Chat, private messages and bribe offers (milestone 5); the Talk step shows a placeholder until then |
| Waiting room and automatic group forming | Consent page, comprehension quiz, practice rounds, questionnaire, Prolific completion link (milestone 7) |
| Timers, timeouts, results after each round, final payoff | Computer players replacing dropouts, dashboard, data downloads (milestone 8) |
| Complete data recording | Load test and pilot checklist (milestone 9) |
