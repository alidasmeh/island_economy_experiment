"""Computer players (section 9).

Bots are never presented as participants. They are used for dropout replacement,
clearly labeled practice rounds, and headless simulation. A bot decides from the
same ``PlayerObservation`` a human in that seat would see.
"""

from __future__ import annotations

import random
from typing import Protocol

from app.engine.config import Config
from app.engine.observation import PlayerObservation
from app.engine.types import Decision


class Bot(Protocol):
    name: str

    def decide(self, obs: PlayerObservation, rng: random.Random) -> Decision: ...


def round_to_effort(shares: tuple[float, float, float], total: int) -> tuple[int, int, int]:
    """Round non-negative shares to integers summing to `total` (largest remainder)."""
    s = sum(shares)
    if s <= 0:
        base = [total // 3] * 3
        base[0] += total - sum(base)
        return tuple(base)  # type: ignore[return-value]
    exact = [x / s * total for x in shares]
    floors = [int(x) for x in exact]
    rest = total - sum(floors)
    order = sorted(range(3), key=lambda k: (-(exact[k] - floors[k]), k))
    for k in order[:rest]:
        floors[k] += 1
    return tuple(floors)  # type: ignore[return-value]


class FixedBot:
    """Plays one fixed allocation every round (cooperative, selfish)."""

    def __init__(self, name: str, harvest: int, contribute: int, save: int):
        self.name = name
        self.alloc = (harvest, contribute, save)

    def decide(self, obs: PlayerObservation, rng: random.Random) -> Decision:
        return Decision(*self.alloc)


class ConditionalBot:
    """Mirrors last round's group-average effort split (visible under any info policy)."""

    name = "conditional"

    def __init__(self, first_round: dict[str, int]):
        self.first = (first_round["harvest"], first_round["contribute"], first_round["save"])

    def decide(self, obs: PlayerObservation, rng: random.Random) -> Decision:
        g = obs.last_round_group
        if not g:
            return Decision(*self.first)
        shares = (g["avg_harvest_effort"], g["avg_contribute_effort"], g["avg_save_effort"])
        return Decision(*round_to_effort(shares, obs.effort_points))


class RandomBot:
    """Uniformly random effort split (uniform over all integer compositions)."""

    name = "random"

    def __init__(self, transfer_prob: float = 0.0):
        self.transfer_prob = transfer_prob

    def decide(self, obs: PlayerObservation, rng: random.Random) -> Decision:
        e = obs.effort_points
        a, b = sorted(rng.sample(range(e + 2), 2))
        h, c, s = a, b - a - 1, e + 1 - b
        if self.transfer_prob and rng.random() < self.transfer_prob and obs.wealth > 0:
            others = [j for j in range(obs.n_players) if j != obs.seat]
            return Decision(h, c, s, transfer_to=rng.choice(others), transfer_amount=round(rng.uniform(0, obs.wealth) * 0.1, 2))
        return Decision(h, c, s)


STRATEGIES = ("cooperative", "selfish", "conditional", "random")


def make_bot(name: str, cfg: Config) -> Bot:
    if name == "cooperative":
        return FixedBot("cooperative", **cfg.bot_allocations["cooperative"])
    if name == "selfish":
        return FixedBot("selfish", **cfg.bot_allocations["selfish"])
    if name == "conditional":
        return ConditionalBot(cfg.bot_allocations["conditional_first_round"])
    if name == "random":
        return RandomBot(cfg.bot_random_transfer_prob)
    raise ValueError(f"unknown bot strategy {name!r}; choose from {', '.join(STRATEGIES)}")


def parse_strategy_mix(spec: str, n_players: int) -> list[str]:
    """Parse 'selfish:2,cooperative:2' or 'selfish,selfish,random,conditional' or 'cooperative' (all)."""
    seats: list[str] = []
    for part in [p.strip() for p in spec.split(",") if p.strip()]:
        name, _, count = part.partition(":")
        if name not in STRATEGIES:
            raise ValueError(f"unknown bot strategy {name!r}; choose from {', '.join(STRATEGIES)}")
        seats += [name] * (int(count) if count else 1)
    if len(seats) == 1:
        seats *= n_players
    if len(seats) != n_players:
        raise ValueError(f"strategy mix {spec!r} has {len(seats)} seats, group needs {n_players}")
    return seats
