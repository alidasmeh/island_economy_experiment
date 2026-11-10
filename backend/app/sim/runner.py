"""Headless simulation of complete groups (no UI, no database).

Bots decide from the same player observations humans get; a coordinator backend
(if any) decides from the coordinator observation. Everything is seeded, so a
(seed, strategies, coordinator, config) tuple always reproduces the same run.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.bots import make_bot
from app.coordinator import CoordinatorBackend
from app.engine import (
    Config,
    RoundLedger,
    default_policy,
    draw_group_setup,
    initial_state,
    resolve_round,
    round_rng,
    settle_game,
    validate_decision,
    validate_policy,
)
from app.engine.observation import coordinator_observation, player_observation
from app.engine.setup import substream


@dataclass
class GroupResult:
    group: dict[str, Any]
    rounds: list[dict[str, Any]] = field(default_factory=list)
    players: list[dict[str, Any]] = field(default_factory=list)
    ledgers: list[RoundLedger] = field(default_factory=list)


def simulate_group(seed: int, cfg: Config, strategies: list[str], *,
                   coordinator: CoordinatorBackend | None = None, condition: str = "none",
                   n_rounds: int | None = None) -> GroupResult:
    """Play one group to the end. `n_rounds` overrides the seeded T (e.g. full 20-round tests)."""
    if len(strategies) != cfg.n_players:
        raise ValueError(f"need {cfg.n_players} strategies, got {len(strategies)}")
    setup = draw_group_setup(seed, cfg)
    T = n_rounds or setup.n_rounds
    events = [setup.event_for(cfg, t) if t <= setup.n_rounds else cfg.event(_extra_event(seed, t, cfg))
              for t in range(1, T + 1)]
    state = initial_state(setup, cfg)
    bots = [make_bot(s, cfg) for s in strategies]
    bot_rngs = [substream(seed, f"bot:{i}") for i in range(cfg.n_players)]
    policy = default_policy(cfg)
    mix = ",".join(strategies)
    initial_total = sum(state.wealth) + sum(state.capital)
    res = GroupResult(group={})

    for t, event in enumerate(events, start=1):
        if coordinator is not None:
            obs = coordinator_observation(state, policy, cfg, ledgers=res.ledgers, event=event)
            policy = validate_policy(coordinator.act(obs).policy, cfg, n_players=state.n)
        last = res.ledgers[-1] if res.ledgers else None
        decisions = []
        for i, bot in enumerate(bots):
            pobs = player_observation(i, state, policy, cfg, event=event, last_ledger=last)
            d = bot.decide(pobs, bot_rngs[i])
            decisions.append(validate_decision(d, cfg, seat=i, n_players=state.n, available_wealth=state.wealth[i]))
        before = state
        state, led = resolve_round(state, decisions, policy, event, round_rng(seed, t), cfg=cfg)
        res.ledgers.append(led)
        g = led.group
        res.rounds.append({
            "seed": seed, "condition": condition, "strategy_mix": mix, "round": t, "event": g.event,
            "stock_before": g.stock_before, "regrowth": g.regrowth, "total_harvest": g.total_harvest,
            "stock_after": g.stock_after, "collapsed": g.collapsed, "infra_after": g.infra_after,
            "pot_collected": g.pot_collected, "match_cost": g.match_cost, "pot_redistributed": g.pot_redistributed,
            "pool_after": g.pool_after, "fines_paid": g.fines_paid, "welfare": g.welfare,
            "earnings_cum": g.welfare - initial_total, "gini": g.gini, "conservation_error": g.conservation_error,
        })
        for p in led.players:
            res.players.append({
                "seed": seed, "condition": condition, "strategy_mix": mix, "round": t, "seat": p.seat,
                "strategy": strategies[p.seat], "harvest_effort": p.harvest_effort,
                "contribute_effort": p.contribute_effort, "save_effort": p.save_effort, "harvest": p.harvest,
                "harvest_income": p.harvest_income, "tax": p.tax, "redistribution": p.redistribution,
                "fines_paid": p.fines_paid, "saving_added": p.saving_added, "interest": p.interest,
                "round_earnings": (p.wealth_after + p.capital_after) - (before.wealth[p.seat] + before.capital[p.seat]),
                "wealth_after": p.wealth_after, "capital_after": p.capital_after,
            })

    settle = settle_game(state, cfg, has_coordinator=coordinator is not None)
    collapse_round = next((r["round"] for r in res.rounds if r["stock_after"] < cfg.stock_min), None)
    final_total = sum(settle.payoff_coins)
    res.group = {
        "seed": seed, "condition": condition, "strategy_mix": mix, "n_rounds": T,
        "initial_welfare": initial_total, "final_welfare": final_total, "earnings": final_total - initial_total,
        "final_stock": state.stock, "min_stock": min(r["stock_after"] for r in res.rounds),
        "collapse_round": collapse_round, "final_infra": state.infra,
        "final_gini": res.rounds[-1]["gini"], "mean_gini": sum(r["gini"] for r in res.rounds) / T,
        "coordinator_payoff_coins": settle.coordinator_payoff_coins,
        "max_conservation_error": max(r["conservation_error"] for r in res.rounds),
        **{f"strategy_{i}": s for i, s in enumerate(strategies)},
        **{f"earnings_{i}": settle.payoff_coins[i] - setup.wealth0[i] for i in range(cfg.n_players)},
    }
    return res


def _extra_event(seed: int, t: int, cfg: Config) -> str:
    """Event for rounds beyond the seeded T (only when n_rounds is overridden)."""
    from app.engine.setup import draw_event
    return draw_event(cfg, substream(seed, f"extra_event:{t}").random()).name


def code_version() -> str:
    """Git SHA of the running code (with '-dirty' if there are uncommitted changes)."""
    root = Path(__file__).resolve().parents[3]
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True,
                             check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True).stdout
        return sha + ("-dirty" if dirty.strip() else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
