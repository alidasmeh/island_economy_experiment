"""Configuration loading for the Island Economy engine.

All numeric parameters come from a YAML file (default: ``backend/config/default.yaml``).
The loader converts the YAML into frozen dataclasses, validates it, and records a
SHA-256 hash of the raw file so every group can store the exact parameters it ran with.
"""

from __future__ import annotations

import hashlib
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "default.yaml"


class ConfigError(ValueError):
    """Raised when a config file is missing values or contains invalid ones."""


@dataclass(frozen=True)
class EventSpec:
    name: str
    probability: float
    harvest_mult: float = 1.0
    regrowth_mult: float = 1.0
    price_mult: float = 1.0
    insurance_payout: bool = False


@dataclass(frozen=True)
class Range:
    min: float
    max: float
    step: float | None = None

    def contains(self, value: float) -> bool:
        if value < self.min - 1e-9 or value > self.max + 1e-9:
            return False
        if self.step:
            k = (value - self.min) / self.step
            return abs(k - round(k)) < 1e-6
        return True


@dataclass(frozen=True)
class Config:
    # group
    n_players: int
    rounds_min: int
    rounds_max: int
    effort_points: int
    # endowments
    wealth_min: int
    wealth_max: int
    skill_min: float
    skill_max: float
    # resource
    carrying_capacity: float
    initial_stock_fraction: float
    regrowth_rate: float
    collapse_fraction: float
    catchability: float
    price: float
    # infrastructure
    infra_initial: float
    infra_gain_per_point: float
    infra_depreciation: float
    infra_gain_per_pot_coin: float
    match_cost_per_point: float
    # saving
    saving_return_per_point: float
    interest_rate: float
    # insurance
    insurance_premium: float
    insurance_refund_pool_at_end: bool
    # events
    events: tuple[EventSpec, ...]
    # levers
    lever_quota: Range
    lever_tax_rate: Range
    lever_match_rate: Range
    lever_fine: Range
    lever_audit_prob: Range
    redistribution_options: tuple[str, ...]
    info_policy_options: tuple[str, ...]
    announcement_max_chars: int
    default_policy: dict[str, Any]
    # bribery
    bribe_detection_prob: float
    bribe_fine: float
    # coordinator pay
    welfare_bonus_rate: float
    bribe_income_rate: float
    bribe_income_cap: float
    # phases (seconds already multiplied by time_scale)
    phase_seconds: dict[str, float]
    phase_end_when_all_ready: dict[str, bool]
    phase_grace_seconds: float
    time_scale: float
    # decision
    timeout_default_allocation: dict[str, int]
    # bots
    bot_allocations: dict[str, dict[str, int]]
    bot_random_transfer_prob: float
    bot_stub_policy: dict[str, Any]
    # payment
    coins_per_currency_unit: float
    currency: str
    show_up_fee: float
    # provenance
    source_path: str = ""
    sha256: str = ""
    raw: dict[str, Any] | None = None

    @property
    def stock_initial(self) -> float:
        return self.initial_stock_fraction * self.carrying_capacity

    @property
    def stock_min(self) -> float:
        return self.collapse_fraction * self.carrying_capacity

    def event(self, name: str) -> EventSpec:
        for e in self.events:
            if e.name == name:
                return e
        raise KeyError(name)


PHASES = ("event", "policy", "communication", "decision", "resolution")


def _time_scale(raw: dict) -> float:
    env = os.getenv("ISLAND_TIME_SCALE")
    return float(env) if env else float(_get(raw, "phases.time_scale"))


def _get(d: dict, path: str) -> Any:
    cur: Any = d
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            raise ConfigError(f"missing config value: {path}")
        cur = cur[key]
    return cur


def _range(d: dict, path: str) -> Range:
    r = _get(d, path)
    return Range(min=float(r["min"]), max=float(r["max"]), step=r.get("step"))


def config_from_dict(raw: dict[str, Any], *, source_path: str = "", sha256: str = "") -> Config:
    g = lambda p: _get(raw, p)  # noqa: E731
    events = tuple(
        EventSpec(
            name=str(e["name"]),
            probability=float(e["probability"]),
            harvest_mult=float(e.get("harvest_mult", 1.0)),
            regrowth_mult=float(e.get("regrowth_mult", 1.0)),
            price_mult=float(e.get("price_mult", 1.0)),
            insurance_payout=bool(e.get("insurance_payout", False)),
        )
        for e in g("events")
    )
    cfg = Config(
        n_players=int(g("group.n_players")),
        rounds_min=int(g("group.rounds_min")),
        rounds_max=int(g("group.rounds_max")),
        effort_points=int(g("group.effort_points")),
        wealth_min=int(g("endowments.wealth_min")),
        wealth_max=int(g("endowments.wealth_max")),
        skill_min=float(g("endowments.skill_min")),
        skill_max=float(g("endowments.skill_max")),
        carrying_capacity=float(g("resource.carrying_capacity")),
        initial_stock_fraction=float(g("resource.initial_stock_fraction")),
        regrowth_rate=float(g("resource.regrowth_rate")),
        collapse_fraction=float(g("resource.collapse_fraction")),
        catchability=float(g("resource.catchability")),
        price=float(g("resource.price")),
        infra_initial=float(g("infrastructure.initial")),
        infra_gain_per_point=float(g("infrastructure.gain_per_point")),
        infra_depreciation=float(g("infrastructure.depreciation")),
        infra_gain_per_pot_coin=float(g("infrastructure.gain_per_pot_coin")),
        match_cost_per_point=float(g("infrastructure.match_cost_per_point")),
        saving_return_per_point=float(g("saving.return_per_point")),
        interest_rate=float(g("saving.interest_rate")),
        insurance_premium=float(g("insurance.premium")),
        insurance_refund_pool_at_end=bool(g("insurance.refund_pool_at_end")),
        events=events,
        lever_quota=_range(raw, "levers.quota"),
        lever_tax_rate=_range(raw, "levers.tax_rate"),
        lever_match_rate=_range(raw, "levers.match_rate"),
        lever_fine=_range(raw, "levers.fine"),
        lever_audit_prob=_range(raw, "levers.audit_prob"),
        redistribution_options=tuple(g("levers.redistribution_options")),
        info_policy_options=tuple(g("levers.info_policy_options")),
        announcement_max_chars=int(g("levers.announcement_max_chars")),
        default_policy=dict(g("default_policy")),
        bribe_detection_prob=float(g("bribery.detection_prob")),
        bribe_fine=float(g("bribery.fine")),
        welfare_bonus_rate=float(g("coordinator_pay.welfare_bonus_rate")),
        bribe_income_rate=float(g("coordinator_pay.bribe_income_rate")),
        bribe_income_cap=float(g("coordinator_pay.bribe_income_cap")),
        phase_seconds={name: float(g(f"phases.{name}.seconds")) * _time_scale(raw) for name in PHASES},
        phase_end_when_all_ready={name: bool(g(f"phases.{name}.end_when_all_ready")) for name in PHASES},
        phase_grace_seconds=float(g("phases.grace_seconds")) * _time_scale(raw),
        time_scale=_time_scale(raw),
        timeout_default_allocation={k: int(v) for k, v in g("decision.timeout_default_allocation").items()},
        bot_allocations={
            name: {k: int(v) for k, v in g(f"bots.{name}").items()}
            for name in ("cooperative", "selfish", "conditional_first_round")
        },
        bot_random_transfer_prob=float(g("bots.random_transfer_prob")),
        bot_stub_policy=dict(g("bots.stub_policy")),
        coins_per_currency_unit=float(g("payment.coins_per_currency_unit")),
        currency=str(g("payment.currency")),
        show_up_fee=float(g("payment.show_up_fee")),
        source_path=source_path,
        sha256=sha256,
        raw=raw,
    )
    _validate(cfg)
    return cfg


def _validate(cfg: Config) -> None:
    errs: list[str] = []
    if cfg.n_players < 2:
        errs.append("n_players must be >= 2")
    if not (1 <= cfg.rounds_min <= cfg.rounds_max):
        errs.append("need 1 <= rounds_min <= rounds_max")
    if cfg.effort_points < 1:
        errs.append("effort_points must be >= 1")
    if not (0 <= cfg.wealth_min <= cfg.wealth_max):
        errs.append("need 0 <= wealth_min <= wealth_max")
    if not (0 < cfg.skill_min <= cfg.skill_max):
        errs.append("need 0 < skill_min <= skill_max")
    if cfg.carrying_capacity <= 0:
        errs.append("carrying_capacity must be > 0")
    for name in ("initial_stock_fraction", "collapse_fraction", "infra_depreciation",
                 "bribe_detection_prob"):
        v = getattr(cfg, name)
        if not (0 <= v <= 1):
            errs.append(f"{name} must be in [0, 1]")
    if not cfg.events:
        errs.append("at least one event is required")
    total_p = sum(e.probability for e in cfg.events)
    if not math.isclose(total_p, 1.0, abs_tol=1e-9):
        errs.append(f"event probabilities must sum to 1 (got {total_p})")
    if len({e.name for e in cfg.events}) != len(cfg.events):
        errs.append("event names must be unique")
    alloc = cfg.timeout_default_allocation
    if set(alloc) != {"harvest", "contribute", "save"} or sum(alloc.values()) != cfg.effort_points:
        errs.append("timeout_default_allocation must have harvest/contribute/save summing to effort_points")
    for name, a in cfg.bot_allocations.items():
        if set(a) != {"harvest", "contribute", "save"} or sum(a.values()) != cfg.effort_points or min(a.values()) < 0:
            errs.append(f"bots.{name} must have non-negative harvest/contribute/save summing to effort_points")
    if not (0 <= cfg.bot_random_transfer_prob <= 1):
        errs.append("bots.random_transfer_prob must be in [0, 1]")
    if cfg.default_policy.get("redistribution") not in cfg.redistribution_options:
        errs.append("default_policy.redistribution not in redistribution_options")
    if cfg.default_policy.get("info_policy") not in cfg.info_policy_options:
        errs.append("default_policy.info_policy not in info_policy_options")
    if cfg.time_scale <= 0 or any(v <= 0 for v in cfg.phase_seconds.values()):
        errs.append("phase seconds and time_scale must be > 0")
    if cfg.coins_per_currency_unit <= 0:
        errs.append("coins_per_currency_unit must be > 0")
    if errs:
        raise ConfigError("; ".join(errs))


def load_config(path: str | Path | None = None) -> Config:
    """Load and validate a YAML config file. Records its SHA-256 for provenance."""
    p = Path(path) if path else DEFAULT_CONFIG_PATH
    data = p.read_bytes()
    raw = yaml.safe_load(data)
    if not isinstance(raw, dict):
        raise ConfigError(f"{p} is not a YAML mapping")
    return config_from_dict(raw, source_path=str(p), sha256=hashlib.sha256(data).hexdigest())
