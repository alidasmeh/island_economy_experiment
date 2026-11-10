"""What each role is allowed to see.

These functions are the single source of truth for information access. The game
server sends players/coordinators only what these return, and bots decide from
the same player observation a human in that seat would get.

- Players never see other players' favors, wealth, private capital, DMs or bribes.
- Under ``info_policy == "totals_only"`` players see last round's group totals only;
  under ``show_individual`` they also see each player's effort split and harvest.
- The coordinator always sees every player's last-round behavior (section 7).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .config import Config, EventSpec
from .types import GroupState, Policy, RoundLedger

PUBLIC_POLICY_FIELDS = ("quota", "tax_rate", "redistribution", "match_rate", "fine", "audit_prob",
                        "insurance", "info_policy", "announcement")


def public_policy(policy: Policy) -> dict[str, Any]:
    """The policy as announced to players: all levers, never the favors."""
    return {k: getattr(policy, k) for k in PUBLIC_POLICY_FIELDS}


def _event_dict(event: EventSpec | None) -> dict[str, Any] | None:
    return asdict(event) if event else None


def group_summary(ledger: RoundLedger) -> dict[str, Any]:
    """Group totals from a round, visible to everyone under any info policy."""
    g = ledger.group
    n = len(ledger.players)
    tot = {k: sum(getattr(p, f"{k}_effort") for p in ledger.players) for k in ("harvest", "contribute", "save")}
    return {
        "round": g.round,
        "event": g.event,
        "total_harvest": g.total_harvest,
        "total_harvest_effort": tot["harvest"],
        "total_contribute_effort": tot["contribute"],
        "total_save_effort": tot["save"],
        "avg_harvest_effort": tot["harvest"] / n,
        "avg_contribute_effort": tot["contribute"] / n,
        "avg_save_effort": tot["save"] / n,
        "pot_collected": g.pot_collected,
        "pot_redistributed": g.pot_redistributed,
        "pot_to_infrastructure": g.pot_to_infrastructure,
        "stock_after": g.stock_after,
        "infra_after": g.infra_after,
        "insurance_payout_each": g.pool_payout / n if n else 0.0,
        "audits_caught": sum(1 for p in ledger.players if p.caught),
    }


def _own_result(ledger: RoundLedger, seat: int) -> dict[str, Any]:
    p = ledger.players[seat]
    keys = ("harvest_effort", "contribute_effort", "save_effort", "timeout", "harvest", "over_quota", "audited",
            "caught", "harvest_income", "tax", "redistribution", "premium", "insurance_payout", "interest",
            "saving_added", "transfer_to", "transfer_out", "transfer_in", "bribes_paid", "fines_assessed",
            "fines_paid", "wealth_before", "wealth_after", "capital_before", "capital_after")
    return {k: getattr(p, k) for k in keys}


def _individual_rows(ledger: RoundLedger) -> list[dict[str, Any]]:
    return [{"seat": p.seat, "harvest_effort": p.harvest_effort, "contribute_effort": p.contribute_effort,
             "save_effort": p.save_effort, "harvest": p.harvest} for p in ledger.players]


@dataclass(frozen=True)
class PlayerObservation:
    seat: int
    round: int
    n_players: int
    effort_points: int
    event: dict[str, Any] | None
    stock: float
    carrying_capacity: float
    infra: float
    wealth: float
    capital: float
    skill: float
    policy: dict[str, Any]
    own_favors: dict[str, bool]
    last_round_group: dict[str, Any] | None
    last_round_own: dict[str, Any] | None
    last_round_individual: list[dict[str, Any]] | None   # None under totals_only

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def player_observation(seat: int, state: GroupState, policy: Policy, cfg: Config, *,
                       event: EventSpec | None = None, last_ledger: RoundLedger | None = None) -> PlayerObservation:
    show = policy.info_policy == "show_individual"
    return PlayerObservation(
        seat=seat,
        round=state.round,
        n_players=state.n,
        effort_points=cfg.effort_points,
        event=_event_dict(event),
        stock=state.stock,
        carrying_capacity=cfg.carrying_capacity,
        infra=state.infra,
        wealth=state.wealth[seat],
        capital=state.capital[seat],
        skill=state.skill[seat],
        policy=public_policy(policy),
        own_favors=asdict(policy.favors_for(seat)),
        last_round_group=group_summary(last_ledger) if last_ledger else None,
        last_round_own=_own_result(last_ledger, seat) if last_ledger else None,
        last_round_individual=_individual_rows(last_ledger) if (last_ledger and show) else None,
    )


@dataclass(frozen=True)
class CoordinatorObservation:
    """Everything a (human or future AI) coordinator sees when setting policy.

    Contains only what a real policymaker would have: history of group outcomes,
    last round's per-player behavior, the current policy, and (from Milestone 5)
    the inbox and public chat. Never contains the number of rounds T.
    """

    round: int
    n_players: int
    effort_points: int
    event: dict[str, Any] | None
    stock: float
    carrying_capacity: float
    infra: float
    insurance_pool: float
    current_policy: dict[str, Any]           # includes favors (the coordinator set them)
    history: list[dict[str, Any]]            # per past round: welfare, gini, stock, infra, pot, event
    last_round_players: list[dict[str, Any]] | None
    lever_ranges: dict[str, Any]
    bribe_income_so_far: float
    bribe_income_cap: float
    inbox: list[dict[str, Any]] = field(default_factory=list)
    public_chat: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def coordinator_observation(state: GroupState, policy: Policy, cfg: Config, *,
                            ledgers: list[RoundLedger], event: EventSpec | None = None,
                            inbox: list[dict[str, Any]] | None = None,
                            public_chat: list[dict[str, Any]] | None = None) -> CoordinatorObservation:
    history = [
        {"round": l.group.round, "event": l.group.event, "welfare": l.group.welfare, "gini": l.group.gini,
         "stock": l.group.stock_after, "infra": l.group.infra_after, "pot": l.group.pot_collected,
         "total_harvest": l.group.total_harvest}
        for l in ledgers
    ]
    last = ledgers[-1] if ledgers else None
    last_players = None
    if last:
        last_players = [
            {"seat": p.seat, "harvest_effort": p.harvest_effort, "contribute_effort": p.contribute_effort,
             "save_effort": p.save_effort, "harvest": p.harvest, "over_quota": p.over_quota, "caught": p.caught,
             "timeout": p.timeout, "wealth": p.wealth_after, "capital": p.capital_after}
            for p in last.players
        ]
    ranges = {name: asdict(getattr(cfg, f"lever_{name}"))
              for name in ("quota", "tax_rate", "match_rate", "fine", "audit_prob")}
    ranges["redistribution"] = list(cfg.redistribution_options)
    ranges["info_policy"] = list(cfg.info_policy_options)
    ranges["announcement_max_chars"] = cfg.announcement_max_chars
    return CoordinatorObservation(
        round=state.round,
        n_players=state.n,
        effort_points=cfg.effort_points,
        event=_event_dict(event),
        stock=state.stock,
        carrying_capacity=cfg.carrying_capacity,
        infra=state.infra,
        insurance_pool=state.insurance_pool,
        current_policy=policy.to_dict(),
        history=history,
        last_round_players=last_players,
        lever_ranges=ranges,
        bribe_income_so_far=state.coordinator.bribe_income,
        bribe_income_cap=cfg.bribe_income_cap,
        inbox=list(inbox or []),
        public_chat=list(public_chat or []),
    )
