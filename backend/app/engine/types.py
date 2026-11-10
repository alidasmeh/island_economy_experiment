"""Plain data types for the Island Economy engine.

Players are referred to by their seat index 0..N-1 inside a group. The server
layer maps seats to (pseudonymized) participant IDs; the engine never sees them.
"""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Allocation:
    harvest: int
    contribute: int
    save: int

    def as_dict(self) -> dict[str, int]:
        return {"harvest": self.harvest, "contribute": self.contribute, "save": self.save}


@dataclass(frozen=True)
class Decision:
    """One player's private decision for a round (section 4, phase 4)."""

    harvest: int
    contribute: int
    save: int
    transfer_to: int | None = None      # seat index of another player, or None
    transfer_amount: float = 0.0
    timeout: bool = False

    @property
    def allocation(self) -> Allocation:
        return Allocation(self.harvest, self.contribute, self.save)


@dataclass(frozen=True)
class Favors:
    """Secret per-player favors a coordinator can grant (never shown to other players)."""

    quota_exempt: bool = False
    audit_immune: bool = False
    double_redistribution_weight: bool = False

    def any(self) -> bool:
        return self.quota_exempt or self.audit_immune or self.double_redistribution_weight


@dataclass(frozen=True)
class Policy:
    """The set of coordinator levers in force during a round (section 6)."""

    quota: int = 0                      # fish per player; 0 = no quota
    tax_rate: float = 0.0
    redistribution: str = "equal"       # equal | need | contribution | infrastructure
    match_rate: float = 0.0
    fine: float = 0.0                   # coins per unit over quota
    audit_prob: float = 0.0
    insurance: bool = False
    info_policy: str = "show_individual"
    announcement: str = ""
    favors: dict[int, Favors] = field(default_factory=dict)

    def favors_for(self, seat: int) -> Favors:
        return self.favors.get(seat, Favors())

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Policy":
        d = dict(d)
        favors = {int(k): (v if isinstance(v, Favors) else Favors(**v)) for k, v in (d.pop("favors", None) or {}).items()}
        return cls(favors=favors, **d)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["favors"] = {str(k): asdict(v) for k, v in self.favors.items()}
        return d


@dataclass(frozen=True)
class BribeOffer:
    """A bribe offer and the coordinator's response, as handed to resolve_round.

    The amount was held in escrow by the server since the offer was made, so it
    is guaranteed to be <= the sender's wealth at the start of resolution.
    """

    offer_id: str
    sender: int
    amount: float
    accepted: bool


@dataclass
class CoordinatorAccount:
    bribe_gross: float = 0.0     # total accepted bribe amount (coins paid by players)
    bribe_income: float = 0.0    # coordinator's bribe income = rate * gross (capped)
    fines: float = 0.0           # bribery fines assessed on the coordinator


@dataclass
class GroupState:
    """Complete state of a group between rounds."""

    round: int                    # number of the NEXT round to be played (1-based)
    stock: float                  # S_t
    infra: float                  # A_t
    insurance_pool: float
    wealth: list[float]           # w_i
    capital: list[float]          # k_i (private capital, a separate balance)
    skill: list[float]            # theta_i
    coordinator: CoordinatorAccount = field(default_factory=CoordinatorAccount)
    last_allocation: list[Allocation | None] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.wealth)

    def total(self, seat: int) -> float:
        return self.wealth[seat] + self.capital[seat]

    def copy(self) -> "GroupState":
        return copy.deepcopy(self)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["last_allocation"] = [a.as_dict() if a else None for a in self.last_allocation]
        return d


@dataclass
class PlayerLedger:
    """Every payoff component for one player in one round (section 5)."""

    seat: int
    harvest_effort: int = 0
    contribute_effort: int = 0
    save_effort: int = 0
    timeout: bool = False
    # 1. harvest
    harvest_raw: float = 0.0
    harvest: float = 0.0
    # 2. quota and audit
    over_quota: float = 0.0
    audited: bool = False
    caught: bool = False
    quota_fine_assessed: float = 0.0
    # 3–4. income and tax
    harvest_income: float = 0.0
    tax: float = 0.0
    # 6. redistribution
    redistribution_weight: float = 0.0
    redistribution: float = 0.0
    # 7. insurance
    premium: float = 0.0
    insurance_payout: float = 0.0
    # 8. saving
    capital_before: float = 0.0
    interest: float = 0.0
    saving_added: float = 0.0
    capital_after: float = 0.0
    # 9. transfers
    transfer_to: int | None = None
    transfer_requested: float = 0.0
    transfer_out: float = 0.0
    transfer_in: float = 0.0
    # 10. bribes
    bribes_paid: float = 0.0
    bribe_fine_assessed: float = 0.0
    # 12. wealth
    fines_assessed: float = 0.0
    fines_paid: float = 0.0
    wealth_before: float = 0.0
    wealth_after: float = 0.0


@dataclass
class BribeLedger:
    offer_id: str
    sender: int
    amount: float
    accepted: bool               # coordinator's response
    executed: bool = False       # actually paid (False if refused or cap reached)
    rejected_reason: str = ""    # "" | "refused" | "cap_reached"
    paid: float = 0.0
    coordinator_income: float = 0.0
    detected: bool = False


@dataclass
class GroupLedger:
    round: int
    event: str
    # stock
    stock_before: float = 0.0
    regrowth: float = 0.0
    total_harvest_raw: float = 0.0
    harvest_scale: float = 1.0
    total_harvest: float = 0.0
    stock_after: float = 0.0
    collapsed: bool = False       # stock below S_min at start of round (no regrowth)
    # infrastructure
    infra_before: float = 0.0
    total_contribution: float = 0.0
    match_points_requested: float = 0.0
    match_scale: float = 1.0
    match_cost: float = 0.0
    infra_from_pot: float = 0.0
    infra_after: float = 0.0
    # pot
    pot_collected: float = 0.0
    pot_after_match: float = 0.0
    pot_redistributed: float = 0.0
    pot_to_infrastructure: float = 0.0
    redistribution_rule: str = "equal"
    redistribution_fallback_equal: bool = False
    # insurance
    pool_before: float = 0.0
    premiums: float = 0.0
    pool_payout: float = 0.0
    pool_after: float = 0.0
    # aggregates
    price: float = 0.0
    fines_paid: float = 0.0
    fines_unpaid: float = 0.0
    bribes_paid: float = 0.0
    coordinator_bribe_income: float = 0.0
    coordinator_fines: float = 0.0
    welfare: float = 0.0          # sum of wealth + capital after the round
    gini: float = 0.0
    conservation_error: float = 0.0


@dataclass
class RoundLedger:
    group: GroupLedger
    players: list[PlayerLedger]
    bribes: list[BribeLedger]

    def to_dict(self) -> dict[str, Any]:
        return {
            "group": asdict(self.group),
            "players": [asdict(p) for p in self.players],
            "bribes": [asdict(b) for b in self.bribes],
        }
