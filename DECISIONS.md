# Design decisions

Choices made where the build spec was ambiguous or silent. Each picks the simplest
option that keeps the two conditions (`none`, `human`) comparable and the coordinator
interface clean. Parameter values live in `backend/config/default.yaml`.

## Stack (Milestone 1)

- **Stack** = this repository's template: FastAPI + python-socketio + async SQLAlchemy
  (PostgreSQL) in `backend/`, React 19 + MUI + socket.io-client in `frontend/`
  (participants) and `dashboard/` (experimenter/admin). Nothing in the spec conflicts with it.
- The game engine (`backend/app/engine/`) is pure Python (stdlib only + PyYAML for config):
  no I/O, no database, no sockets, so it can be reused unchanged by the server, the
  simulation CLI and tests.
- The duplicated top-level `app/` and `pyproject.toml` (template leftovers mirroring
  `backend/`) are left untouched; all work happens in `backend/`.

## Randomness and the matched design

- Every random draw derives from one integer seed per group, via named sub-streams
  (`random.Random("island:{seed}:{name}")`): `rounds`, `wealth`, `skill`, `events`,
  `round:{t}`. Draws of one kind never shift draws of another kind.
- Events are pre-drawn for `rounds_max` rounds and truncated to T, so the event sequence
  for a seed is identical in both conditions.
- In each round, `resolve_round` always draws one audit uniform per player and then one
  detection uniform per bribe offer, whether or not they are needed (common random numbers).

## Section 5 — payoff order and money

- **Solvency.** Money moves on a per-player running balance in the order of section 5,
  so no one goes below zero: premiums, transfers and bribes are capped at the balance at
  that step. Quota fines (step 2) and bribery fines (step 10) are *assessed* when they
  occur and *collected* at step 12, capped at the remaining balance. Unpaid fines are
  logged (`fines_unpaid`).
- **Fines are destroyed** (leave the economy), as the conservation statement in section 13 implies.
- **Audit.** Only players over the quota can be audited; an audit always detects them.
  A player is "audited" when their audit draw `u < audit_prob`.
- **Quota `0` means no quota** (per spec), so no one can be fined with quota 0.
- **Match cost.** The match is paid out of the pot at `match_cost_per_point` coins (default 1)
  per matched contribution point: cost = `match_rate · Σ e_c · match_cost_per_point`.
  If the pot is short the match is scaled down proportionally (`match_scale`).
- **Pot never carries over.** After the match the pot is fully redistributed (or, under the
  `infrastructure` rule, converted into A at `gain_per_pot_coin`, γ_pot; default 0.005 per coin after calibration).
- **Redistribution weights** use start-of-round totals (`wealth + private capital`) for the
  `need` rule ("private capital is kept as a separate balance in wealth"). If all weights
  are zero (e.g. `contribution` with no contributions, `need` with equal totals) the pot is
  split by the `equal` rule; this is logged (`redistribution_fallback_equal`).
  `double_redistribution_weight` doubles the favored player's weight under any rule.
- **Insurance.** While insurance is on, every player pays `premium` (default 2 coins) into a
  pool that carries over between rounds. On an event marked `insurance_payout` (`storm`) the
  whole pool, including this round's premiums, is paid out equally — also if the coordinator
  has since switched insurance off (players already paid for the cover). A leftover pool is
  refunded equally at the end of the game (`refund_pool_at_end`).
- **Infrastructure** in round t uses A_t for harvests; contributions, match and the
  `infrastructure` rule all add to A_{t+1}.
- **Collapse.** "If S_t < S_min, regrowth = 0" uses the stock at the *start* of the round,
  exactly as written.
- **Transfers** go to other players only (not the coordinator); outgoing amounts are capped
  at the balance before any transfer is received, so incoming money cannot fund outgoing.
- **Bribe escrow.** The server reserves the offered amount when an offer is made (so the
  player cannot transfer or re-offer it); the engine debits it only when the offer is
  accepted (step 10). Refused/expired offers simply release the reservation. Bribery
  detection does not reverse the bribe; both sides pay `F_bribe`.
- **Bribe cap** is on the coordinator's bribe *income* (`rate × amount`) per game. The engine
  rejects any accepted offer that would exceed it (`rejected_reason = "cap_reached"`) as a
  second line of defence behind server-side validation.
- **Coordinator payoff** = welfare bonus (`rate × total final player payoff`) + bribe income
  − bribery fines, floored at 0. The money that players pay in bribes beyond the coordinator's
  income share leaves the economy.
- **Gini and welfare** are computed over each player's wealth + private capital.
- Coins are floats internally; rounding happens only for display and at payment.

## Defaults

- `default_policy.info_policy = show_individual` (the spec says "all levers at zero/off" but
  `info_policy` is an enum with no "off"); it applies to the `none` condition too.
- Lever steps: `match_rate` and `audit_prob` use 0.05 steps, like `tax_rate` (the spec gives
  only ranges); quota and fine are integers.

## Bots, coordinator interface and simulation (Milestone 2)

- **Bot allocations live in config** (`bots:`): cooperative 2/6/2, selfish 10/0/0, conditional
  starts at 4/3/3. `random` draws uniformly over all integer splits of E.
- **Bots see exactly what a human in that seat would see.** They decide from
  `player_observation()`, the same function that will feed the player UI, so a bot that
  replaces a dropout gets no extra information.
- **`conditional` mirrors the whole group's average** effort split from last round (group
  totals are visible under both info policies), rounded to integers summing to E by largest
  remainder.
- **Information access** is defined in one place (`engine/observation.py`). Players see:
  public levers + announcement (never favors), their *own* favors (otherwise a favor could
  not change the favored player's behavior), group totals, and other players' effort splits
  and harvests only under `show_individual`. Players never see others' wealth or capital.
  The coordinator sees everyone's last-round behavior and wealth, the history, and the
  current policy including favors — never T.
- **Coordinator interface**: `CoordinatorBackend.act(CoordinatorObservation) -> CoordinatorAction`
  (`app/coordinator/`). `ScriptedCoordinator` (the `coordinator_stub`) applies a fixed
  policy or a per-round script from YAML and refuses all bribes unless told otherwise.
  Default stub policy: `bots.stub_policy` in config.
- **CLI** is `python -m app.sim simulate ...` (plus `dilemma` and `plot` subcommands) rather
  than an installed `simulate` script: the backend is installed with `--no-root`, so console
  scripts would not be available in the Docker image.
- **Outputs**: `groups.csv`, `rounds.csv`, `players.csv` and `meta.json` (config hash,
  git SHA, arguments).
- `--rounds` overrides the seeded T (used for the spec's "full 20-round game" test). Events
  for rounds beyond the seeded T come from a separate sub-stream.

### Dilemma check definitions

- **(a)** compares group *earnings* (final payoff − initial endowment). Endowments are the
  same in both conditions and larger than 20 rounds of earnings, so including them would hide
  any difference. The ratio including endowments is reported too.
- **(b)** is a counterfactual: same state, same other players' decisions, same random draws;
  the focal player plays selfish vs cooperative. It is judged on rounds where the stock is
  still alive (S_t ≥ S_min), because after collapse there is nothing to harvest and no
  parameter set can make harvesting pay. The share over all rounds is reported too.
  Contexts come from all-cooperative, all-selfish, all-conditional and all-random games.
- **(c)** passes when ≥ 90% of all-selfish groups collapse (S < S_min) and the median
  collapse round is between 5 and 8 ("about 6–8").
- Results: `docs/simulation/README.md`.

### Calibration (adopted after review)

- Under the original spec values all three checks failed. After review, the calibrated values
  were adopted as defaults: q 0.01 → 0.017, ρ 1.0 → 0.3, γ 0.02 → 0.005, γ_pot 0.02 → 0.005,
  d 0.02 → 0.05. The original values are kept in `config/spec_original.yaml`.
- Engine unit tests use a fixed parameter file (`backend/tests/fixtures/test_config.yaml`,
  the original spec values) so hand-computed expectations don't change with calibration.
  A separate test checks that the shipped defaults pass dilemma checks (a) and (c).

## Multiplayer flow (Milestone 3)

- **Architecture.** One `GroupRuntime` per group runs as an asyncio task in the backend
  process. It owns the round timeline and timers, accepts submissions, calls
  `resolve_round`, and pushes per-participant `state` snapshots. It talks to the outside only
  through an `EventStore` (logging) and a `Transport` (Socket.IO), so it is unit-tested
  without a server or database.
- **Single replica.** Live state is in memory; deploy the backend with one replica. A restart
  ends running games; reconnecting participants see a "no longer available" message. The
  event log has everything needed to rebuild games later if that becomes necessary.
- **Event-sourced logging.** All game data goes into one append-only table, `ie_event_log`
  (`ts, session_id, group_id, round, participant_id, kind, payload`). The analysis tables of
  section 11 (decisions, state, ledger, ratings, ...) will be derived from it at export time
  (Milestone 8). Kinds logged so far: `session_created`, `joined`, `connected`,
  `disconnected`, `waiting_room_entered/left`, `session_full`, `group_started` (condition,
  seed, T, params hash, code version, seats, endowments, skills, events), `phase_started`,
  `phase_ended` (`all_ready` / `timeout`), `ready`, `decision` (split, transfer, timeout flag,
  server response time, client response time, slider changes), `action_rejected`,
  `round_resolved` (policy + full ledger), `state`, `fairness_rating`, `game_finished`
  (settlement), `runtime_error`, `group_aborted`.
- **Identities.** Participants get a random pseudonymous ID (`p_…`). Prolific IDs are stored
  only in `ie_external_ids`, never in game data or the event log. Access tokens are random,
  stored hashed in `ie_participant_tokens`. Re-joining with the same Prolific ID returns the
  same participant with an additional token (earlier tokens stay valid, so two tabs do not
  lock each other out). Knowing a session code and someone's Prolific ID is enough to resume
  as them; Prolific IDs are not public, so this is accepted.
- **Matching.** Arrival order. A session has a planned list of groups
  (`assignments`: condition + seed). With several conditions, each seed is played once per
  condition, interleaved (`none, human, none, human, …` for seeds 1, 1, 2, 2, …) to keep the
  matched design balanced over time. When the plan is exhausted, later arrivals are told the
  session is full (exit/payment handling comes in Milestone 7). Waiting-room timeouts come
  with Milestone 7/8.
- **Timers.** Server-side, from config (`phases:`), multiplied by `time_scale` (env
  `ISLAND_TIME_SCALE` overrides, for development only). Each phase ends early when every
  participant is done (`end_when_all_ready`). Decisions arriving up to `grace_seconds` after
  the deadline are still accepted (network delay); the client shows the deadline without the
  grace. The snapshot carries the server time, so the client corrects for clock skew.
- **Phases in `none`.** Event → Talk → Decide → Results; the policy phase is skipped. The
  Talk phase is kept (with a "chat not available yet" notice) so timing matches the later
  milestones.
- **One submission per round.** A decision is final once submitted; later attempts are
  rejected and logged. Fairness ratings may be changed during the results phase; every
  rating is logged and the last one counts.
- **Fairness rating in `none`.** Also asked in the no-coordinator condition ("How fair are
  the current rules?") so the two conditions stay comparable.
- **Transfers** name the recipient by seat ("Islander A–D"). Labels are by seat and do not
  change during a game.
- **Income preview** is computed in the browser from public parameters sent in the snapshot
  (`preview`) plus the player's own skill, and is labeled as an estimate.
- **Admin API.** HTTP Basic with `DASHBOARD_USERNAME`/`DASHBOARD_PASSWORD` (constant-time
  comparison). The dashboard UI comes in Milestone 8. The `human` condition is rejected at
  session creation until Milestone 4.
- **Template code.** The template's demo chat page (`frontend/src/pages/GamePage.jsx`) and
  its Socket.IO handlers were replaced. Consent, instruction, quiz, survey and terminate
  pages are left for Milestone 7. The template's `users_4` table and routes are untouched.
- **Dependencies.** `greenlet` is declared explicitly (SQLAlchemy's async engine needs it, and
  it is not installed automatically on every platform); `aiosqlite` for the SQLite fallback.
