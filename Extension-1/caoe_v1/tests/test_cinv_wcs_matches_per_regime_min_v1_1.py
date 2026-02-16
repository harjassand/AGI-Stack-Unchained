from __future__ import annotations

from cli.caoe_proposer_cli_v1 import _avg_success, _min_success


def test_cinv_wcs_matches_per_regime_min_v1_1() -> None:
    values = {"r0": 1, "r1": 0, "r2": 0, "r3": 0, "r4": 1, "r5": 0, "r6": 0, "r7": 1}
    assert _avg_success(values) == 0.375
    assert _min_success(values) == 0.0
