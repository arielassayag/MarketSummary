"""Estatística sem dependências extras: IC de Wilson, bootstrap pareado por
caso, kappa de Cohen, Spearman e MAE."""

from __future__ import annotations

import math
import random
from collections.abc import Sequence


def wilson_ci(successes: int, n: int, z: float = 1.959963985) -> tuple[float, float]:
    """Intervalo de confiança de Wilson para proporções."""
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def bootstrap_paired_delta_by_case(
    per_case_a: dict[str, float],
    per_case_b: dict[str, float],
    *,
    n_boot: int = 2000,
    seed: int = 42,
) -> tuple[float, float, float]:
    """Delta médio pareado (B - A) com IC por bootstrap REAMPLICANDO CASOS.

    Ambos os dicionários devem ter as mesmas chaves (casos pareados). Para cada
    caso com múltiplos outputs, agregue antes (ex.: média por caso).
    """
    cases = sorted(set(per_case_a) & set(per_case_b))
    if not cases:
        return (0.0, 0.0, 0.0)
    deltas = [per_case_b[c] - per_case_a[c] for c in cases]
    mean_delta = sum(deltas) / len(deltas)
    rng = random.Random(seed)
    boot: list[float] = []
    for _ in range(n_boot):
        sample = [deltas[rng.randrange(len(deltas))] for _ in range(len(deltas))]
        boot.append(sum(sample) / len(sample))
    boot.sort()
    lo = boot[int(0.025 * (n_boot - 1))]
    hi = boot[int(0.975 * (n_boot - 1))]
    return (mean_delta, lo, hi)


def _ranks(values: Sequence[float]) -> list[float]:
    indexed = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and values[indexed[j + 1]] == values[indexed[i]]:
            j += 1
        avg_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[indexed[k]] = avg_rank
        i = j + 1
    return ranks


def _pearson(x: Sequence[float], y: Sequence[float]) -> float | None:
    n = len(x)
    if n < 2:
        return None
    mx, my = sum(x) / n, sum(y) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y, strict=False))
    sxx = math.sqrt(sum((a - mx) ** 2 for a in x))
    syy = math.sqrt(sum((b - my) ** 2 for b in y))
    if sxx == 0 or syy == 0:
        return None
    return sxy / (sxx * syy)


def spearman(x: Sequence[float], y: Sequence[float]) -> float | None:
    if len(x) != len(y) or not x:
        return None
    return _pearson(_ranks(list(x)), _ranks(list(y)))


def cohens_kappa(a: Sequence[bool], b: Sequence[bool]) -> float | None:
    if len(a) != len(b) or not a:
        return None
    n = len(a)
    po = sum(1 for x, y in zip(a, b, strict=False) if x == y) / n
    pa = sum(a) / n
    pb = sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    if pe == 1:
        return 1.0 if po == 1 else 0.0
    return (po - pe) / (1 - pe)


def mae(a: Sequence[float], b: Sequence[float]) -> float | None:
    if len(a) != len(b) or not a:
        return None
    return sum(abs(x - y) for x, y in zip(a, b, strict=False)) / len(a)


def percentile(sorted_values: Sequence[float], q: float) -> float:
    """q em [0,1]; valores devem estar ordenados."""
    if not sorted_values:
        return 0.0
    idx = q * (len(sorted_values) - 1)
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return float(sorted_values[lo])
    frac = idx - lo
    return float(sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac)


def summarize(values: Sequence[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "median": 0.0, "p10": 0.0, "std": 0.0}
    s = sorted(values)
    mean = sum(s) / len(s)
    var = sum((v - mean) ** 2 for v in s) / (len(s) - 1) if len(s) > 1 else 0.0
    return {
        "mean": mean,
        "median": percentile(s, 0.5),
        "p10": percentile(s, 0.1),
        "std": math.sqrt(var),
    }


__all__ = [
    "bootstrap_paired_delta_by_case",
    "cohens_kappa",
    "mae",
    "percentile",
    "summarize",
    "spearman",
    "wilson_ci",
]
