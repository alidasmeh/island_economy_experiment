"""Server-side validation of player decisions and coordinator policies.

The game server calls these before accepting any input. resolve_round assumes
validated inputs but still clamps money movements defensively.
"""

from __future__ import annotations

import math
from typing import Any

from .config import Config
from .types import Allocation, Decision, Favors, Policy


class ValidationError(ValueError):
    pass


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def validate_decision(d: Decision, cfg: Config, *, seat: int, n_players: int,
                      available_wealth: float) -> Decision:
    """Check an effort split + transfer. `available_wealth` = wealth minus bribe escrow."""
    parts = (d.harvest, d.contribute, d.save)
    if not all(_is_int(p) for p in parts):
        raise ValidationError("effort points must be integers")
    if any(p < 0 for p in parts):
        raise ValidationError("effort points must be >= 0")
    if sum(parts) != cfg.effort_points:
        raise ValidationError(f"effort points must sum to {cfg.effort_points}")
    amt = float(d.transfer_amount or 0.0)
    if not math.isfinite(amt) or amt < 0:
        raise ValidationError("transfer amount must be a non-negative number")
    if amt > 0:
        if d.transfer_to is None or not _is_int(d.transfer_to):
            raise ValidationError("transfer needs a recipient")
        if not (0 <= d.transfer_to < n_players) or d.transfer_to == seat:
            raise ValidationError("invalid transfer recipient")
        if amt > available_wealth + 1e-9:
            raise ValidationError("transfer exceeds available wealth")
    return d


def timeout_decision(last: Allocation | None, cfg: Config) -> Decision:
    """Decision used when a player does not submit: repeat last allocation (round 1: config default)."""
    if last is None:
        a = cfg.timeout_default_allocation
        return Decision(a["harvest"], a["contribute"], a["save"], timeout=True)
    return Decision(last.harvest, last.contribute, last.save, timeout=True)


def validate_policy(p: Policy, cfg: Config, *, n_players: int) -> Policy:
    def chk(name: str, value: float, rng) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValidationError(f"{name} must be a number")
        if not rng.contains(float(value)):
            raise ValidationError(f"{name}={value} outside allowed range [{rng.min}, {rng.max}]"
                                  + (f" step {rng.step}" if rng.step else ""))

    if not _is_int(p.quota):
        raise ValidationError("quota must be an integer")
    chk("quota", p.quota, cfg.lever_quota)
    chk("tax_rate", p.tax_rate, cfg.lever_tax_rate)
    chk("match_rate", p.match_rate, cfg.lever_match_rate)
    chk("fine", p.fine, cfg.lever_fine)
    chk("audit_prob", p.audit_prob, cfg.lever_audit_prob)
    if p.redistribution not in cfg.redistribution_options:
        raise ValidationError("unknown redistribution rule")
    if p.info_policy not in cfg.info_policy_options:
        raise ValidationError("unknown info_policy")
    if not isinstance(p.insurance, bool):
        raise ValidationError("insurance must be on/off")
    if not isinstance(p.announcement, str) or len(p.announcement) > cfg.announcement_max_chars:
        raise ValidationError(f"announcement must be at most {cfg.announcement_max_chars} characters")
    for seat, f in p.favors.items():
        if not _is_int(seat) or not (0 <= seat < n_players):
            raise ValidationError("favor for unknown player")
        if not isinstance(f, Favors):
            raise ValidationError("invalid favors")
    return p
