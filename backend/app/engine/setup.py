"""Seeded group setup.

All random draws for a group derive from one integer seed. Each kind of draw
uses its own named sub-stream, so the same seed yields the same endowments,
skills, number of rounds, events and per-round audit/detection draws regardless
of condition or of what players do (matched design / common random numbers).
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .config import Config, EventSpec
from .types import CoordinatorAccount, GroupState, Policy


def substream(seed: int, name: str) -> random.Random:
    """Independent, reproducible RNG for a named purpose (str seeds hash via SHA-512)."""
    return random.Random(f"island:{seed}:{name}")


def round_rng(seed: int, round_number: int) -> random.Random:
    """RNG handed to resolve_round for the given round (audits and bribe detection)."""
    return substream(seed, f"round:{round_number}")


def draw_event(cfg: Config, u: float) -> EventSpec:
    acc = 0.0
    for e in cfg.events:
        acc += e.probability
        if u < acc:
            return e
    return cfg.events[-1]


@dataclass(frozen=True)
class GroupSetup:
    seed: int
    n_rounds: int
    wealth0: tuple[int, ...]
    skills: tuple[float, ...]
    events: tuple[str, ...]       # event names for rounds 1..n_rounds

    def event_for(self, cfg: Config, round_number: int) -> EventSpec:
        return cfg.event(self.events[round_number - 1])


def draw_group_setup(seed: int, cfg: Config) -> GroupSetup:
    n = cfg.n_players
    n_rounds = substream(seed, "rounds").randint(cfg.rounds_min, cfg.rounds_max)
    rw = substream(seed, "wealth")
    wealth0 = tuple(rw.randint(cfg.wealth_min, cfg.wealth_max) for _ in range(n))
    rs = substream(seed, "skill")
    skills = tuple(rs.uniform(cfg.skill_min, cfg.skill_max) for _ in range(n))
    # Always draw rounds_max events so the sequence prefix is identical for any T.
    re = substream(seed, "events")
    events = tuple(draw_event(cfg, re.random()).name for _ in range(cfg.rounds_max))[:n_rounds]
    return GroupSetup(seed=seed, n_rounds=n_rounds, wealth0=wealth0, skills=skills, events=events)


def initial_state(setup: GroupSetup, cfg: Config) -> GroupState:
    n = len(setup.wealth0)
    return GroupState(
        round=1,
        stock=cfg.stock_initial,
        infra=cfg.infra_initial,
        insurance_pool=0.0,
        wealth=[float(w) for w in setup.wealth0],
        capital=[0.0] * n,
        skill=list(setup.skills),
        coordinator=CoordinatorAccount(),
        last_allocation=[None] * n,
    )


def default_policy(cfg: Config) -> Policy:
    """Policy with all levers at zero/off (condition `none`, and before any coordinator action)."""
    return Policy.from_dict(cfg.default_policy)
