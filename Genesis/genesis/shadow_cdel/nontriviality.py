from __future__ import annotations

import math
from typing import Iterable, Tuple

MIN_ACTION_DIVERSITY = 0.25
MIN_ACTION_ENTROPY = 0.05
MIN_OUTPUT_VARIANCE = 0.01


def is_finite(value: float) -> bool:
    return math.isfinite(value)


def output_variance(values: Iterable[float]) -> float:
    items = list(values)
    if not items:
        return 0.0
    mean = sum(items) / len(items)
    return sum((val - mean) ** 2 for val in items) / len(items)


def action_stats(actions: Iterable[int]) -> Tuple[float, float, int, int]:
    counts = {}
    for action in actions:
        counts[action] = counts.get(action, 0) + 1
    total = sum(counts.values())
    unique = len(counts)
    diversity = (unique / total) if total else 0.0
    if unique > 1 and total:
        entropy = 0.0
        for count in counts.values():
            p = count / total
            entropy -= p * math.log(p)
        entropy = entropy / math.log(unique)
    else:
        entropy = 0.0
    return diversity, entropy, unique, total


def margin_bucket(margin: float | None) -> str:
    if margin is None:
        return "base_unknown"
    if margin < 0.0:
        return "base_neg"
    if margin < 0.05:
        return "base_low"
    if margin < 0.2:
        return "base_mid"
    return "base_high"
