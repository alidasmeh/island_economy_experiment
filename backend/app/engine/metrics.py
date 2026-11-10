"""Group-level outcome metrics."""

from __future__ import annotations

from collections.abc import Sequence


def gini(values: Sequence[float]) -> float:
    """Gini coefficient of non-negative values (0 = perfect equality)."""
    xs = sorted(max(0.0, float(v)) for v in values)
    n = len(xs)
    total = sum(xs)
    if n == 0 or total <= 0:
        return 0.0
    cum = sum((i + 1) * x for i, x in enumerate(xs))
    return (2.0 * cum) / (n * total) - (n + 1.0) / n


def welfare(wealth: Sequence[float], capital: Sequence[float]) -> float:
    return float(sum(wealth) + sum(capital))
