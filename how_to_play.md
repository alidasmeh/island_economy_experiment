# Island Economy — guide for researchers

This page explains, without technical detail, which parts the study has, which web
address does what, and what you can do today. For setup and code, see `README.md`.

---

## The game in one paragraph

Four participants ("islanders") share one sea. Each round they split 10 effort points
between **fishing** (coins now), **building infrastructure** (better fishing for everyone
later) and **saving** (safe private coins). Over-fishing shrinks the fish stock for
everyone; below a threshold it stops growing back. In the **no-coordinator** condition the
group governs itself. In the **coordinator** condition a fifth participant, chosen by lottery, sets the
rules each round (quota, tax, insurance and more). At the end, each islander's coins plus savings become a bonus
payment; the coordinator earns a share of the islanders' total.

---

## The four parts

| Part | Who uses it | What it is for |
| --- | --- | --- |
| **Participant website** | Participants | Instructions, waiting room, the game itself, final payoff |
| **Researcher dashboard** | You | Create sessions, get the study links, watch each group's progress |
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

Replace `PARTICIPANT-SITE`, `DASHBOARD` and `GAME-SERVER` with the addresses above.

| Address | What you see |
| --- | --- |
| `PARTICIPANT-SITE/play?session=CODE` | **The study link for participants.** Instructions, then the waiting room, then the game |
| `PARTICIPANT-SITE/instruction` | **Preview of the instructions** exactly as participants see them, with buttons to switch between the three versions (no coordinator, islander with coordinator, coordinator). Nothing is recorded |
| `DASHBOARD` | **Researcher dashboard.** Create sessions and watch them (log in with the dashboard username and password) |
| `GAME-SERVER/docs` | Technical researcher page; can also create sessions (same login). Not needed if you use the dashboard |
| `GAME-SERVER/api/admin/sessions` | List of all sessions (asks for the same login) |
| `GAME-SERVER/api/admin/sessions/CODE` | One session: how many people are waiting, and each group's condition, round, phase and status |

**Example on a laptop running the study with Docker** (session code `AB12CD34`):

| What | Open this address |
| --- | --- |
| Participant link | http://localhost:3000/play?session=AB12CD34 |
| Participant link as Prolific would send it | http://localhost:3000/play?session=AB12CD34&PROLIFIC_PID=test001&STUDY_ID=pilot&SESSION_ID=s1 |
| Instructions preview | http://localhost:3000/instruction |
| All sessions | http://localhost:8000/api/admin/sessions |
| This session's progress | http://localhost:8000/api/admin/sessions/AB12CD34 |
| Researcher dashboard (create and watch sessions) | http://localhost:3001 |
| Technical researcher page | http://localhost:8000/docs |

To try a whole game alone, open the participant link in four different browser windows
(for example, private windows or different browsers). Each window counts as one
participant. If you use the Prolific-style link, give each window a different
`PROLIFIC_PID` (`test001`, `test002`, …), because one Prolific ID counts as one person.

All numbers in the instructions (effort points, prices, bonus rate, …) are read from the
game's settings file, so the instructions always match the game.

---

## Running a session today

1. **Create a session.** Open the dashboard (on a laptop: http://localhost:3001) and log in.
   The home page has a **Create a new session** form:

   - **Name**: something you will recognise, e.g. `pilot 12 Nov` (only you see it).
   - **Conditions**: *No coordinator*, *Human coordinator*, or both. A coordinator group
     needs 5 participants (4 islanders + 1 coordinator).
   - **Groups and seeds**: either let the dashboard pick random seeds (type how many groups
     you plan), or type your own seeds, e.g. `1, 2, 3`. The form tells you how many groups
     and participants this plans.

   Click **Create session**. You get a **session code** (e.g. `AB12CD34`) and two links with
   **Copy** buttons.

   *What is a seed?* It fixes the luck of a group: starting coins, fishing skills, the
   events at sea and the number of rounds. Each seed is played once in every chosen
   condition, so both conditions get exactly the same luck and differences come from the
   condition.

2. **Put the link in Prolific.** Copy the **Study URL for Prolific** and paste it into
   Prolific, with Prolific IDs recorded **with URL parameters**. Prolific fills in each
   participant's ID itself. The other link (**Participant link**) is for trying the game
   yourself.

3. **Watch.** Click the session in the list. Its page shows how many people are in the
   waiting room, how many groups have started, and each group's round, step and status. It
   updates by itself every few seconds.

**How participants move through the study**

1. They open the link. The study places them right away into the next planned group that
   still needs people, and gives them a role: **islander**, or in a coordinator group, by
   lottery, **coordinator** (each newcomer has a 1 in 5 chance while all seats are open).
2. They read the instructions for their condition and role (9 short pages, one with a "try
   it" example). Coordinators read about their rules and their pay instead of the fishing
   decision.
3. They wait until their group is complete (4 islanders, plus the coordinator). Groups start
   as soon as they are complete, so a no-coordinator group may start before a coordinator
   group that is still missing its coordinator. When all planned groups have started, later
   arrivals are told that the session is full.
4. They play. Each round has four steps — **Event, Talk, Decide, Results** — and in
   coordinator groups a **Policy** step after the Event, in which the coordinator sets the
   rules. Each step has a timer and ends early when everyone is done.
5. They see their final coins and bonus.

**The coordinator's screen** shows the round's event, a form for the rules (fishing quota
with audit chance and fine, tax, matching of infrastructure work, what happens to the tax
pot, storm insurance, what islanders see about each other, and an announcement), charts of
the group's wealth, inequality and fish stock, and a table of what each islander did in the
last round. Coordinators never fish. Islanders are told truthfully that the coordinator is
another participant.

**Good to know**

- If someone does not decide in time, their choice from the previous round is used again
  (in round 1 a default split), and this is recorded as a timeout. If the coordinator does
  not confirm rules in time, the previous rules stay in force (also recorded).
- A participant who closes the tab can reopen the same link and continue where the group is.
- If the game server is restarted, games that are running at that moment end; their
  participants see a message to contact you. Do not restart the server during a session.
- Nobody — not participants, not the coordinator — is told how many rounds there are.

---

## The researcher dashboard

**Today** the dashboard lets you:

- log in with the dashboard username and password (you stay logged in until you close the tab),
- create sessions (name, conditions, seeds),
- see all sessions, newest first,
- open a session to copy its links and watch the waiting room and every group (condition,
  seed, round, step, running / finished).

The number of rounds is shown to you on the dashboard only; participants never see it.

**Planned** (milestone 8), the dashboard will also:

- show who in each group is connected, and dropouts,
- show flagged groups,
- download all data as spreadsheets (CSV) and Parquet files.

---

## What is recorded

Every action is stored with a time stamp: when someone joins, which condition and role they
were given, how long they spent on the instructions, entering the waiting room, every set of
rules the coordinator confirmed (with response time and which rules changed), every decision (with response time and how often
the sliders were moved), timeouts, the full outcome of every round (catch, income, savings,
stock, infrastructure), the optional fairness ratings, and the final payments. Each group
also records its condition, seed, the exact settings file and the program version used.

Prolific IDs are stored **separately** from the game data; the game data uses anonymous IDs
only.

---

## What exists and what is coming

| Available now | Coming |
| --- | --- |
| No-coordinator and human-coordinator conditions, end to end | Rule preview for the coordinator, coordinator dropout handling (milestone 6) |
| Instructions for each condition and role, with an interactive example | Chat, private messages, bribe offers and favours (milestone 5); the Talk step shows a placeholder until then |
| Waiting room and automatic group forming | Consent page, comprehension quiz, practice rounds, questionnaire, Prolific completion link (milestone 7) |
| Timers, timeouts, results after each round, final payoff | Computer players replacing dropouts, dropout monitoring, data downloads (milestone 8) |
| Dashboard: create sessions, study links, group progress | |
| Complete data recording | Load test and pilot checklist (milestone 9) |
