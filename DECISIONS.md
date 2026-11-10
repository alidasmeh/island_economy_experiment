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
