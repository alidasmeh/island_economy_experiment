"""Dilemma check (spec section 13) under a given config, with the default (no-coordinator) policy.

(a) all-cooperative groups end with higher total welfare than all-selfish groups (target >= 2x).
    Welfare is measured as group *earnings* (final payoff − initial endowment), because the
    endowments (~500 coins per group) are identical across conditions and would otherwise
    swamp the comparison. The ratio of total final payoffs is reported too.
(b) in any single round, a selfish player earns more than a cooperative player facing the
    same others: counterfactual — same state, same others' decisions, same random draws,
    focal player plays selfish vs cooperative; compare that player's round earnings.
    Judged on rounds where the stock is alive (S_t >= S_min): once collapsed there is
    nothing left to harvest and no parameter set can make harvesting pay. The share over
    all rounds is reported too.
(c) all-selfish groups collapse the stock (S < S_min) within about 6–8 rounds.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any

from app.bots import STRATEGIES
from app.engine import Config, Decision, default_policy, draw_group_setup, initial_state, resolve_round, round_rng

from .runner import simulate_group

COLLAPSE_WINDOW = (6, 8)
WELFARE_RATIO_TARGET = 2.0


@dataclass
class DilemmaReport:
    n_seeds: int
    coop_earnings_mean: float
    selfish_earnings_mean: float
    earnings_ratio: float
    coop_final_welfare_mean: float
    selfish_final_welfare_mean: float
    final_welfare_ratio: float
    check_a: bool
    rounds_compared: int
    live_rounds_compared: int
    selfish_beats_coop_share_live: float
    selfish_beats_coop_share: float
    selfish_minus_coop_min: float
    selfish_minus_coop_mean: float
    stock_where_coop_wins_max: float | None
    saver_beats_selfish_share: float
    check_b: bool
    collapse_rounds: list[int | None]
    collapse_share: float
    collapse_in_window_share: float
    collapse_median: float | None
    selfish_final_stock_mean: float
    check_c: bool

    def as_dict(self) -> dict[str, Any]:
        d = dict(self.__dict__)
        d.pop("collapse_rounds")
        return d

    def text(self, cfg: Config) -> str:
        ok = lambda b: "PASS" if b else "FAIL"  # noqa: E731
        lo, hi = COLLAPSE_WINDOW
        lines = [
            f"Dilemma check — config {cfg.source_path or '(in-memory)'} sha256={cfg.sha256[:12]}, {self.n_seeds} seeds, "
            "condition none (default policy)",
            "",
            f"(a) welfare cooperative vs selfish: {ok(self.check_a)}",
            f"    group earnings  coop {self.coop_earnings_mean:8.1f}   selfish {self.selfish_earnings_mean:8.1f}   "
            f"ratio {self.earnings_ratio:.2f}x (target >= {WELFARE_RATIO_TARGET:.0f}x)",
            f"    final welfare   coop {self.coop_final_welfare_mean:8.1f}   selfish {self.selfish_final_welfare_mean:8.1f}   "
            f"ratio {self.final_welfare_ratio:.2f}x (incl. endowments)",
            f"(b) selfish beats cooperative in every round while the stock is alive (S >= S_min): {ok(self.check_b)}",
            f"    {self.live_rounds_compared} live round contexts; selfish earns more in "
            f"{100 * self.selfish_beats_coop_share_live:.1f}%",
            f"    incl. collapsed rounds ({self.rounds_compared} contexts): {100 * self.selfish_beats_coop_share:.1f}%",
            f"    selfish − coop round earnings: min {self.selfish_minus_coop_min:+.2f}, mean {self.selfish_minus_coop_mean:+.2f}",
            ("    cooperative wins only when stock <= "
             f"{self.stock_where_coop_wins_max:.1f}" if self.stock_where_coop_wins_max is not None else
             "    cooperative never wins"),
            f"    note: pure saving (0/0/{cfg.effort_points}) beats selfish in {100 * self.saver_beats_selfish_share:.1f}% of contexts",
            f"(c) all-selfish collapse within ~{lo}-{hi} rounds: {ok(self.check_c)}",
            f"    collapsed at all: {100 * self.collapse_share:.1f}%   in rounds {lo}-{hi}: "
            f"{100 * self.collapse_in_window_share:.1f}%   median collapse round: "
            f"{self.collapse_median if self.collapse_median is not None else 'never'}",
            f"    mean final stock (all-selfish): {self.selfish_final_stock_mean:.1f} (S_min = {cfg.stock_min:.1f})",
        ]
        return "\n".join(lines)


def _alloc(cfg: Config, name: str) -> Decision:
    return Decision(**cfg.bot_allocations[name])


def counterfactual_rounds(cfg: Config, seeds: list[int], mixes: list[list[str]]) -> list[dict[str, float]]:
    """For each round of each trajectory, compare focal seat 0 playing selfish / cooperative / saver."""
    selfish, coop = _alloc(cfg, "selfish"), _alloc(cfg, "cooperative")
    saver = Decision(0, 0, cfg.effort_points)
    policy = default_policy(cfg)
    out = []
    for seed in seeds:
        setup = draw_group_setup(seed, cfg)
        for mix in mixes:
            res = simulate_group(seed, cfg, mix)
            state = initial_state(setup, cfg)
            for t, led in enumerate(res.ledgers, start=1):
                actual = [Decision(p.harvest_effort, p.contribute_effort, p.save_effort) for p in led.players]
                event = cfg.event(led.group.event)
                earn = {}
                for label, focal in (("selfish", selfish), ("coop", coop), ("saver", saver)):
                    ds = [focal] + actual[1:]
                    new, _ = resolve_round(state, ds, policy, event, round_rng(seed, t), cfg=cfg)
                    earn[label] = new.total(0) - state.total(0)
                out.append({"seed": seed, "round": t, "stock": state.stock, "mix": ",".join(mix), **earn})
                state, _ = resolve_round(state, actual, policy, event, round_rng(seed, t), cfg=cfg)
    return out


def run_dilemma_check(cfg: Config, seeds: list[int], counterfactual_seeds: int = 100) -> DilemmaReport:
    n = cfg.n_players
    coop = [simulate_group(s, cfg, ["cooperative"] * n).group for s in seeds]
    selfish_runs = [simulate_group(s, cfg, ["selfish"] * n) for s in seeds]
    selfish = [r.group for r in selfish_runs]

    ce, se = statistics.mean(g["earnings"] for g in coop), statistics.mean(g["earnings"] for g in selfish)
    cw, sw = statistics.mean(g["final_welfare"] for g in coop), statistics.mean(g["final_welfare"] for g in selfish)
    ratio = ce / se if se > 0 else float("inf")

    mixes = [[s] * n for s in STRATEGIES]
    rows = counterfactual_rounds(cfg, seeds[:counterfactual_seeds], mixes)
    diffs = [r["selfish"] - r["coop"] for r in rows]
    live = [r["selfish"] - r["coop"] for r in rows if r["stock"] >= cfg.stock_min]
    coop_wins = [r["stock"] for r in rows if r["selfish"] <= r["coop"]]

    collapse = [g["collapse_round"] for g in selfish]
    lo, hi = COLLAPSE_WINDOW
    collapsed = [c for c in collapse if c is not None]
    in_window = [c for c in collapsed if lo <= c <= hi]
    return DilemmaReport(
        n_seeds=len(seeds),
        coop_earnings_mean=ce, selfish_earnings_mean=se, earnings_ratio=ratio,
        coop_final_welfare_mean=cw, selfish_final_welfare_mean=sw, final_welfare_ratio=cw / sw,
        check_a=ratio >= WELFARE_RATIO_TARGET,
        rounds_compared=len(rows),
        live_rounds_compared=len(live),
        selfish_beats_coop_share_live=sum(d > 0 for d in live) / len(live) if live else 0.0,
        selfish_beats_coop_share=sum(d > 0 for d in diffs) / len(diffs),
        selfish_minus_coop_min=min(diffs), selfish_minus_coop_mean=statistics.mean(diffs),
        stock_where_coop_wins_max=max(coop_wins) if coop_wins else None,
        saver_beats_selfish_share=sum(r["saver"] > r["selfish"] for r in rows) / len(rows),
        check_b=bool(live) and all(d > 0 for d in live),
        collapse_rounds=collapse,
        collapse_share=len(collapsed) / len(collapse),
        collapse_in_window_share=len(in_window) / len(collapse),
        collapse_median=statistics.median(collapsed) if collapsed else None,
        selfish_final_stock_mean=statistics.mean(g["final_stock"] for g in selfish),
        # "within about 6–8 rounds": most groups collapse, and by round 8 at the latest.
        check_c=len(collapsed) / len(collapse) >= 0.9 and bool(collapsed) and statistics.median(collapsed) <= hi
        and statistics.median(collapsed) >= lo - 1,
    )
