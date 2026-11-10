"""Simulation CLI.

    python -m app.sim simulate --condition none --strategy-mix cooperative --strategy-mix selfish \
        --seeds 1..1000 --params config/default.yaml --out sim_output/
    python -m app.sim dilemma --seeds 1..500 --params config/default.yaml
    python -m app.sim plot --in sim_output/ --params config/default.yaml

Strategy mixes: 'selfish' (all seats), 'selfish:2,cooperative:2', or 'selfish,random,conditional,cooperative'.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.bots import parse_strategy_mix
from app.coordinator import ScriptedCoordinator
from app.engine import load_config

from .dilemma import run_dilemma_check
from .runner import code_version, simulate_group


def parse_seeds(spec: str) -> list[int]:
    """'1..1000' (inclusive), '1,2,7', or a mix: '1..10,50'."""
    seeds: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if ".." in part:
            a, b = part.split("..")
            seeds += range(int(a), int(b) + 1)
        elif part:
            seeds.append(int(part))
    if not seeds:
        raise ValueError("no seeds given")
    return seeds


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def cmd_simulate(args: argparse.Namespace) -> int:
    cfg = load_config(args.params)
    seeds = parse_seeds(args.seeds)
    mixes = [parse_strategy_mix(m, cfg.n_players) for m in (args.strategy_mix or ["cooperative"])]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    groups, rounds, players = [], [], []
    for mix in mixes:
        for seed in seeds:
            coord = None
            if args.condition == "coordinator_stub":
                coord = (ScriptedCoordinator.from_yaml(args.policy, cfg) if args.policy
                         else ScriptedCoordinator.from_config(cfg))
            res = simulate_group(seed, cfg, mix, coordinator=coord, condition=args.condition, n_rounds=args.rounds)
            groups.append(res.group)
            rounds += res.rounds
            players += res.players
    _write_csv(out / "groups.csv", groups)
    _write_csv(out / "rounds.csv", rounds)
    _write_csv(out / "players.csv", players)
    meta = {
        "created_at": datetime.now(timezone.utc).isoformat(), "code_version": code_version(),
        "params_path": cfg.source_path, "params_sha256": cfg.sha256, "condition": args.condition,
        "strategy_mixes": [",".join(m) for m in mixes], "seeds": args.seeds, "n_groups": len(groups),
        "policy_file": args.policy, "rounds_override": args.rounds,
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"wrote {len(groups)} groups, {len(rounds)} rounds to {out}/ (groups.csv, rounds.csv, players.csv, meta.json)")
    for mix in mixes:
        key = ",".join(mix)
        gs = [g for g in groups if g["strategy_mix"] == key]
        mean = lambda k: sum(g[k] for g in gs) / len(gs)  # noqa: E731
        collapsed = sum(g["collapse_round"] is not None for g in gs)
        print(f"  {key:45s} earnings {mean('earnings'):8.1f}  final stock {mean('final_stock'):6.1f}  "
              f"collapsed {collapsed}/{len(gs)}")
    if args.plot:
        from .plots import plot_rounds
        for p in plot_rounds(out / "rounds.csv", out, stock_min=cfg.stock_min):
            print(f"  plot: {p}")
    return 0


def cmd_dilemma(args: argparse.Namespace) -> int:
    cfg = load_config(args.params)
    report = run_dilemma_check(cfg, parse_seeds(args.seeds))
    print(report.text(cfg))
    if args.json:
        Path(args.json).write_text(json.dumps({"params_sha256": cfg.sha256, "params_path": cfg.source_path,
                                               "code_version": code_version(), **report.as_dict()}, indent=2))
    return 0 if (report.check_a and report.check_b and report.check_c) else 1


def cmd_plot(args: argparse.Namespace) -> int:
    from .plots import plot_rounds

    stock_min = load_config(args.params).stock_min if args.params else None
    for p in plot_rounds(Path(args.inp) / "rounds.csv", Path(args.out or args.inp), stock_min=stock_min):
        print(f"plot: {p}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m app.sim", description="Island Economy headless simulation")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("simulate", help="run complete bot groups and write CSVs")
    s.add_argument("--condition", choices=["none", "coordinator_stub"], default="none")
    s.add_argument("--strategy-mix", action="append",
                   help="seat strategies; repeat for several mixes (default: cooperative)")
    s.add_argument("--seeds", default="1..100", help="e.g. 1..1000 or 1,5,9")
    s.add_argument("--params", default=None, help="config YAML (default config/default.yaml)")
    s.add_argument("--policy", default=None, help="coordinator_stub policy/script YAML (default: bots.stub_policy)")
    s.add_argument("--rounds", type=int, default=None, help="override the seeded number of rounds T")
    s.add_argument("--out", default="sim_output")
    s.add_argument("--plot", action="store_true", help="also write welfare/stock plots")
    s.set_defaults(func=cmd_simulate)

    d = sub.add_parser("dilemma", help="run the section-13 dilemma check")
    d.add_argument("--seeds", default="1..500")
    d.add_argument("--params", default=None)
    d.add_argument("--json", default=None, help="also write the report as JSON")
    d.set_defaults(func=cmd_dilemma)

    p = sub.add_parser("plot", help="plot welfare and stock by round from a simulate output dir")
    p.add_argument("--in", dest="inp", required=True)
    p.add_argument("--out", default=None)
    p.add_argument("--params", default=None, help="config YAML (to draw the collapse threshold)")
    p.set_defaults(func=cmd_plot)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
