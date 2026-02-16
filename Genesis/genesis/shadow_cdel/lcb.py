from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class LcbResult:
    bound: float
    radius: float


def hoeffding_lcb(value: float, n: int, delta: float) -> LcbResult:
    if n <= 0 or delta <= 0:
        return LcbResult(bound=float("-inf"), radius=float("inf"))
    radius = math.sqrt(math.log(1.0 / delta) / (2.0 * n))
    return LcbResult(bound=value - radius, radius=radius)


def hoeffding_ucb(value: float, n: int, delta: float) -> LcbResult:
    if n <= 0 or delta <= 0:
        return LcbResult(bound=float("inf"), radius=float("inf"))
    radius = math.sqrt(math.log(1.0 / delta) / (2.0 * n))
    return LcbResult(bound=value + radius, radius=radius)
