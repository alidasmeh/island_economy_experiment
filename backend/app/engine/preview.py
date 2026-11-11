"""Policy preview for the coordinator (section 7): an *estimate* of next round's effects.

Assumes every islander repeats last round's effort split (round 1: the configured
default split) and makes no transfers or offers. It runs the real ``resolve_round``
on a copy of the state, with no audit or detection draws, and adds the *expected*
quota fine (audit chance × fine × fish over the quota) separately, so the
numbers follow exactly the same rules as the game itself. Pure, no I/O.
"""

from __future__ import annotations

import random
from typing import Any

from .config import Config, EventSpec
from .resolve import resolve_round
from .types import Decision, GroupState, Policy


class _NoDraws(random.Random):
    """An RNG under which no audit or detection ever happens (every draw = 1.0)."""

    def random(self) -> float:  # noqa: D401
        return 1.0


def policy_preview(state: GroupState, policy: Policy, event: EventSpec, cfg: Config) -> dict[str, Any]:
    default = cfg.timeout_default_allocation
    allocs = [a for a in state.last_allocation] if state.last_allocation else [None] * state.n
    based_on = "last_round" if any(a is not None for a in allocs) else "default_split"
    decisions = [Decision(a.harvest, a.contribute, a.save) if a is not None
                 else Decision(default["harvest"], default["contribute"], default["save"]) for a in allocs]
    _new, led = resolve_round(state, decisions, policy, event, _NoDraws(), cfg=cfg)
    players = []
    for i, p in enumerate(led.players):
        fav = policy.favors_for(i)
        expected_fine = 0.0
        if policy.quota > 0 and p.over_quota > 0 and not fav.quota_exempt and not fav.audit_immune:
            expected_fine = policy.audit_prob * policy.fine * p.over_quota
        coins = p.harvest_income - p.tax + p.redistribution - p.premium + p.insurance_payout - expected_fine
        players.append({
            "seat": i,
            "harvest_effort": p.harvest_effort, "contribute_effort": p.contribute_effort, "save_effort": p.save_effort,
            "harvest": p.harvest, "over_quota": p.over_quota, "harvest_income": p.harvest_income, "tax": p.tax,
            "redistribution": p.redistribution, "premium": p.premium, "insurance_payout": p.insurance_payout,
            "expected_fine": expected_fine, "coins_change": coins,
        })
    g = led.group
    return {
        "estimate": True,
        "based_on": based_on,
        "event": event.name,
        "players": players,
        "total_harvest": g.total_harvest,
        "pot_collected": g.pot_collected,
        "match_cost": g.match_cost,
        "pot_redistributed": g.pot_redistributed,
        "pot_to_infrastructure": g.pot_to_infrastructure,
        "expected_fines": sum(p["expected_fine"] for p in players),
        "stock_after": g.stock_after,
        "infra_after": g.infra_after,
    }
