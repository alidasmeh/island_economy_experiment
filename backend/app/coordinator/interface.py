"""Coordinator interface: observation in, action out.

The game only ever talks to a coordinator through ``CoordinatorBackend.act``.
In Study 1 the backends are:
  * the human coordinator (the server turns dashboard input into a CoordinatorAction), and
  * ``ScriptedCoordinator`` — a fixed or per-round scripted policy for tests and simulation.
An AI backend could later implement the same protocol without changing the game.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import yaml

from app.engine.config import Config
from app.engine.observation import CoordinatorObservation
from app.engine.types import Policy


@dataclass(frozen=True)
class BribeResponse:
    accept: bool
    reply: str = ""


@dataclass(frozen=True)
class CoordinatorAction:
    policy: Policy                                       # levers, favors, announcement
    bribe_responses: dict[str, BribeResponse] = field(default_factory=dict)  # offer_id -> response


class CoordinatorBackend(Protocol):
    def act(self, obs: CoordinatorObservation) -> CoordinatorAction: ...


class ScriptedCoordinator:
    """Applies a fixed policy, or a per-round script (testing/simulation only).

    ``script`` maps round number -> partial policy dict; rounds not listed keep the
    previous round's policy. Bribes are always refused unless ``accept_bribes``.
    """

    def __init__(self, base: dict[str, Any], script: dict[int, dict[str, Any]] | None = None,
                 accept_bribes: bool = False):
        self.base = dict(base)
        self.script = {int(k): dict(v) for k, v in (script or {}).items()}
        self.accept_bribes = accept_bribes
        self._current = dict(self.base)

    def act(self, obs: CoordinatorObservation) -> CoordinatorAction:
        if obs.round in self.script:
            self._current = {**self._current, **self.script[obs.round]}
        policy = Policy.from_dict(self._current)
        responses = {m["offer_id"]: BribeResponse(self.accept_bribes)
                     for m in obs.inbox if m.get("type") == "bribe" and m.get("status", "pending") == "pending"}
        return CoordinatorAction(policy=policy, bribe_responses=responses)

    @classmethod
    def from_config(cls, cfg: Config) -> "ScriptedCoordinator":
        return cls(cfg.bot_stub_policy)

    @classmethod
    def from_yaml(cls, path: str | Path, cfg: Config) -> "ScriptedCoordinator":
        """YAML: either a flat policy, or {base: {...}, rounds: {3: {...}}, accept_bribes: bool}."""
        raw = yaml.safe_load(Path(path).read_text()) or {}
        if "base" in raw or "rounds" in raw:
            base = {**cfg.default_policy, **(raw.get("base") or {})}
            return cls(base, raw.get("rounds"), bool(raw.get("accept_bribes", False)))
        return cls({**cfg.default_policy, **raw})

