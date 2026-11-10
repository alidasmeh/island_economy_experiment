"""Plot welfare and stock over rounds for each strategy mix (from rounds.csv)."""

from __future__ import annotations

import csv
import statistics
from collections import defaultdict
from pathlib import Path

# Reference categorical palette (fixed order, light mode); text stays in ink colors.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"


def _load(path: Path) -> dict[str, dict[int, dict[str, list[float]]]]:
    data: dict[str, dict[int, dict[str, list[float]]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    with path.open() as f:
        for r in csv.DictReader(f):
            key = r["strategy_mix"] if r["condition"] == "none" else f'{r["strategy_mix"]} [{r["condition"]}]'
            cell = data[key][int(r["round"])]
            cell["earnings_cum"].append(float(r["earnings_cum"]))
            cell["stock_after"].append(float(r["stock_after"]))
    return data


def _label(mix: str) -> str:
    parts = mix.split(" [")
    seats = parts[0].split(",")
    base = f"all {seats[0]}" if len(set(seats)) == 1 else " + ".join(
        f"{seats.count(s)} {s}" for s in dict.fromkeys(seats))
    return base + (f" [{parts[1]}" if len(parts) > 1 else "")


def _place_end_labels(ax, ends: list[list]) -> None:
    """Direct labels at line ends, nudged apart vertically so they never overlap."""
    ax.figure.canvas.draw()
    lo, hi = ax.get_ylim()
    gap = (hi - lo) * 0.045
    ends.sort(key=lambda e: e[0])
    ys = [e[0] for e in ends]
    for k in range(1, len(ys)):
        ys[k] = max(ys[k], ys[k - 1] + gap)
    for (y0, x, label), y in zip(ends, ys):
        ax.annotate(label, (x, y0), xytext=(x + 0.3, y), textcoords="data", va="center", fontsize=8,
                    color=INK_2, annotation_clip=False)


def plot_rounds(rounds_csv: Path, out_dir: Path, stock_min: float | None = None) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker  # noqa: F401

    data = _load(rounds_csv)
    mixes = list(data)
    if len(mixes) > len(SERIES):
        raise ValueError(f"at most {len(SERIES)} strategy mixes per plot (got {len(mixes)}); facet the runs")
    out_dir.mkdir(parents=True, exist_ok=True)
    panels = [("earnings_cum", "Group earnings since start (coins)", "welfare_by_round.png"),
              ("stock_after", "Fish stock at end of round", "stock_by_round.png")]
    written = []
    for metric, title, fname in panels:
        fig, ax = plt.subplots(figsize=(8, 4.8), dpi=150)
        fig.patch.set_facecolor(SURFACE)
        ax.set_facecolor(SURFACE)
        ends = []
        for idx, mix in enumerate(mixes):
            color = SERIES[idx]
            rounds = sorted(data[mix])
            means, lo, hi = [], [], []
            for t in rounds:
                xs = data[mix][t][metric]
                m = statistics.mean(xs)
                se = statistics.stdev(xs) / len(xs) ** 0.5 if len(xs) > 1 else 0.0
                means.append(m)
                lo.append(m - 1.96 * se)
                hi.append(m + 1.96 * se)
            n_groups = len(data[mix][rounds[0]][metric])
            ax.fill_between(rounds, lo, hi, color=color, alpha=0.15, linewidth=0)
            ax.plot(rounds, means, color=color, linewidth=2, label=f"{_label(mix)} (n={n_groups})",
                    solid_capstyle="round")
            ends.append([means[-1], rounds[-1], _label(mix)])
        _place_end_labels(ax, ends)
        if metric == "stock_after" and stock_min is not None:
            ax.axhline(stock_min, color=INK_2, linewidth=1, linestyle=(0, (4, 3)))
            ax.annotate("collapse threshold", (1, stock_min), xytext=(0, 4), textcoords="offset points",
                        fontsize=8, color=INK_2)
        ax.set_title(title, loc="left", fontsize=11, color=INK)
        ax.set_xlabel("Round (mean, 95% CI band; groups drop out as their game ends)", fontsize=8, color=INK_2)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.tick_params(colors=INK_2, labelsize=8, length=0)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(GRID)
        ax.legend(frameon=False, fontsize=8, labelcolor=INK_2, loc="upper left", bbox_to_anchor=(0, -0.14), ncol=2)
        ax.set_xlim(left=1, right=max(max(data[m]) for m in mixes) + 3.5)
        ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
        fig.tight_layout()
        path = out_dir / fname
        fig.savefig(path, facecolor=SURFACE)
        plt.close(fig)
        written.append(path)
    return written
