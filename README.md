# Island Economy experiment (human-only)

Real-time multiplayer common-pool economy for a behavioral study at the Max Planck
Institute for Human Development (Center for Humans and Machines).

Groups of 4 islanders split 10 effort points per round between **harvesting** a shared
fish stock, **contributing** to infrastructure and **saving** privately. Two conditions
are compared:

- `none` — players self-govern (default policy: all levers zero/off);
- `human` — a 5th participant acts as coordinator and sets policy (quota, tax,
  redistribution, match, fines, audits, insurance, information, secret favors) and can
  accept or refuse bribes.

There is no AI anywhere in the game. The coordinator logic sits behind an
observation-in / action-out interface so an AI backend could be added later.

Design choices made where the spec was ambiguous are recorded in [DECISIONS.md](DECISIONS.md).

## Repository layout

| Path | What |
| --- | --- |
| `backend/` | FastAPI + python-socketio + async SQLAlchemy (PostgreSQL) |
| `backend/app/engine/` | Pure game engine: config, seeded setup, `resolve_round`, validation, metrics |
| `backend/app/bots/` | Bot strategies (Milestone 2) |
| `backend/app/sim/` | Headless simulation CLI (Milestone 2) |
| `backend/config/default.yaml` | **All** game parameters (nothing numeric is hard-coded) |
| `backend/tests/` | Unit tests (`pytest`) |
| `frontend/` | Participant UI (React 19 + MUI + socket.io-client) |
| `dashboard/` | Experimenter/admin UI (React 19 + MUI) |

## Milestones

- [x] 1. Game engine: config loading, `resolve_round`, state dynamics, unit tests
- [ ] 2. Simulation CLI with bots, welfare/stock plots, dilemma check
- [ ] 3. Multiplayer flow: rooms, phases, timers, player UI, `none` condition end to end
- [ ] 4. Human coordinator dashboard and policy pipeline
- [ ] 5. Communication and bribery: chat, DMs, escrow, favors, detection
- [ ] 6. Coordinator decision support: policy preview, lever-change logging, coordinator dropout
- [ ] 7. Onboarding and exit: consent, instructions, quiz, practice, questionnaire, payment, Prolific
- [ ] 8. Admin panel, exports, dropout handling
- [ ] 9. Pilot readiness: load test, run/deploy/config docs

## Game engine

Pure, deterministic Python (stdlib + PyYAML); no I/O, so the game server, the
simulation CLI and the tests all use the same code.

```python
from app.engine import (load_config, draw_group_setup, initial_state, default_policy,
                        resolve_round, round_rng, settle_game, Decision)

cfg = load_config()                       # backend/config/default.yaml (+ SHA-256 hash)
setup = draw_group_setup(seed=1, cfg=cfg) # T, endowments, skills, events — all from the seed
state = initial_state(setup, cfg)
for t in range(1, setup.n_rounds + 1):
    decisions = [Decision(harvest=4, contribute=3, save=3)] * cfg.n_players
    state, ledger = resolve_round(state, decisions, default_policy(cfg),
                                  setup.event_for(cfg, t), round_rng(1, t), cfg=cfg)
final = settle_game(state, cfg, has_coordinator=False)
```

- `resolve_round` applies the 12 steps of spec section 5 in fixed order and returns the
  new state plus a ledger with every payoff component per player, group-level stock /
  infrastructure / pot / insurance figures, and each bribe's outcome.
- Every round reconciles coins: in = out + fines destroyed (+ pot converted to
  infrastructure + bribes paid); the residual is stored as `ledger.group.conservation_error`.
- Same seed + same decisions → identical outcomes. Each kind of random draw uses its own
  seeded sub-stream, so both conditions share endowments, skills, T, events and audit draws.
- `validate_decision` / `validate_policy` are the server-side checks for all inputs.

### Running the tests

```bash
cd backend
poetry install
poetry run pytest tests -q
```

### Changing parameters

Edit `backend/config/default.yaml` or copy it and pass the path to `load_config(path)`.
The loader validates ranges (e.g. event probabilities must sum to 1) and records the
file's SHA-256 so every group stores the exact parameters it ran with.

---

# Deployment (CHM project template)


When you made a copy of this repo, update the name of the project in the list of places below: 
- frontend/public/manifest.json => name, short_name
- frontend/package.json => name
- backend/pyproject.toml => name
- backend/.gitlab-ci.yml => APP_NAME, DATABASE_NAME, NAMESPACE 
- frontend/.gitlab-ci.yml => APP_NAME, BACKEND_URL, REACT_APP_BACKEND_URL, NAMESPACE
- frontend/.gitlab-ci.yml => build-stage-react.before_script -> REACT_APP_BACKEND_URL, REACT_APP_BACKEND_SOCKET_URL


Create a `.env` file in the same directory as `docker-compose.yml` file. Add following variables inside.
```
DATABASE_URL = 
REACT_APP_BACKEND_URL = 
REACT_APP_BACKEND_SOCKET_URL = 
```

# Create GitLab CI/CD variables
All the following variables should be added to GitLab CI/CD variables.

- APP_NAME_PREFIX
- DASHBOARD_USERNAME
- DASHBOARD_PASSWORD
- DATABASE_URL
- REACT_APP_BACKEND_SOCKET_URL
- REACT_APP_BACKEND_URL


# Create namespace
To create a new repository for a project you should make a namespace at Portainer based on [this document](https://mpib.atlassian.net/wiki/spaces/CP/pages/1545535494/Create+a+Portainer+namespace).

You should replace all `project-template-` in `.gitlab-ci.yaml` files with the namespace (do not for get `-` at the end of the namespace.)

# Create PostgreSQL DB
To create a new PostgreSQL DB for your project/experiment follow this: [Create a Postgres database](https://mpib.atlassian.net/wiki/spaces/CP/pages/1506770989/Create+a+Postgres+database)
After getting DB credentials from GWDG update `DATABASE_URL` in gitlab>Settings>CI/CD>Variables (If you cannot access it, ask IT support or research engineers.). 