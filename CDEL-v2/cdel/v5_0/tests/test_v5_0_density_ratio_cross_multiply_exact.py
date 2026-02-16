from __future__ import annotations

from cdel.v5_0.thermo_metrics import ProbeResult, density_ratio, ratio_ge


def test_density_ratio_cross_multiply_exact() -> None:
    prev = ProbeResult(passes=50, energy_mJ=1000)
    cur = ProbeResult(passes=60, energy_mJ=1000)
    num, den = density_ratio(prev, cur)

    # ratio = (60/1000) / (50/1000) = 6/5 = 1.2 >= 1.05
    assert (num, den) == (60 * 1000, 50 * 1000)
    assert ratio_ge(num, den, 105, 100)

    # And a failing case.
    prev2 = ProbeResult(passes=100, energy_mJ=1000)
    cur2 = ProbeResult(passes=100, energy_mJ=1100)
    num2, den2 = density_ratio(prev2, cur2)
    assert not ratio_ge(num2, den2, 105, 100)

