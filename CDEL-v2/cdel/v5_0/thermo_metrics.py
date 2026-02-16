"""Deterministic thermo metrics (v5.0)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cmp_to_key


@dataclass(frozen=True)
class ProbeResult:
    passes: int
    energy_mJ: int


def density_ratio(
    prev: ProbeResult,
    cur: ProbeResult,
) -> tuple[int, int]:
    """Return density ratio as a rational (num, den).

    density = passes / max(energy_mJ, 1)
    ratio = density_cur / density_prev = (passes1*energy0) / (passes0*energy1)
    with denominator protection when passes0==0 (ratio = 0/1).
    """

    passes0 = int(prev.passes)
    energy0 = max(int(prev.energy_mJ), 1)
    passes1 = int(cur.passes)
    energy1 = max(int(cur.energy_mJ), 1)
    if passes0 == 0:
        return (0, 1)
    return (passes1 * energy0, passes0 * energy1)


def ratio_ge(num: int, den: int, thresh_num: int, thresh_den: int) -> bool:
    return int(num) * int(thresh_den) >= int(thresh_num) * int(den)


def ratio_ge_threshold(prev: ProbeResult, cur: ProbeResult, thresh_num: int, thresh_den: int) -> bool:
    num, den = density_ratio(prev, cur)
    return ratio_ge(num, den, thresh_num, thresh_den)


def _compare_ratio(a: tuple[int, int], b: tuple[int, int]) -> int:
    left = a[0] * b[1]
    right = b[0] * a[1]
    if left < right:
        return -1
    if left > right:
        return 1
    return 0


def _median_ratio(ratios: list[tuple[int, int]]) -> tuple[int, int]:
    if not ratios:
        return (0, 1)
    ordered = sorted(ratios, key=cmp_to_key(_compare_ratio))
    return ordered[len(ordered) // 2]


def trailing_consecutive_meeting_threshold(
    probes: list[ProbeResult],
    *,
    thresh_num: int,
    thresh_den: int,
    consecutive_required: int,
) -> tuple[int, tuple[int, int]]:
    """Return (consecutive_count, median_ratio_last_k)."""

    if consecutive_required <= 0:
        return (0, (0, 1))

    ratios: list[tuple[int, int]] = []
    for idx in range(len(probes) - 1):
        ratios.append(density_ratio(probes[idx], probes[idx + 1]))

    # Median of last K ratios (if present).
    if len(ratios) >= consecutive_required:
        last_k = ratios[-consecutive_required:]
        median = _median_ratio(last_k)
    else:
        median = (0, 1)

    consecutive = 0
    for num, den in reversed(ratios):
        if ratio_ge(num, den, thresh_num, thresh_den):
            consecutive += 1
            if consecutive >= consecutive_required:
                consecutive = consecutive_required
                break
            continue
        break

    return (int(consecutive), (int(median[0]), int(median[1])))


__all__ = [
    "ProbeResult",
    "density_ratio",
    "ratio_ge",
    "ratio_ge_threshold",
    "trailing_consecutive_meeting_threshold",
]

