"""RSI ignition computation for v1.5r (turnover-tolerant rho).

RSI-L5 introduces deliberate stress + deactivation; strict rho monotonicity is too strong.
We enforce a pinned bounded-drop + recovery rule instead.

Rule (pinned defaults):
- Allow rho dips up to MAX_DROP_FRAC from the running peak.
- Require recovery to >= previous peak within K_RECOVER epochs.
- Otherwise fail rho_non_decreasing.
"""

from __future__ import annotations

from typing import Any


def _has_increase(xs: list[int]) -> bool:
    return any(xs[i] < xs[i + 1] for i in range(len(xs) - 1))


def _rho_turnover_ok(xs: list[int], *, max_drop_frac: float = 0.50, k_recover: int = 2) -> bool:
    if not xs:
        return False
    peak = xs[0]
    i = 1
    while i < len(xs):
        v = xs[i]
        if v >= peak:
            peak = v
            i += 1
            continue

        # dip detected: bound the dip
        min_allowed = int(peak * (1.0 - max_drop_frac))
        if v < min_allowed:
            return False

        # require recovery within k_recover
        recovered = False
        for j in range(i + 1, min(len(xs), i + 1 + k_recover)):
            if xs[j] >= peak:
                recovered = True
                i = j  # jump to recovery point
                peak = xs[j]
                break
        if not recovered:
            return False

        i += 1

    return True


def compute_ignition(rsi_records: list[dict[str, Any]]) -> dict[str, Any]:
    barrier_values = [int(r.get("barrier_scalar_value", 0)) for r in rsi_records]

    novelty_ok = all(bool(r.get("novelty_pass", False)) for r in rsi_records) if rsi_records else False
    recovered_ok = all(bool(r.get("recovered", False)) for r in rsi_records) if rsi_records else False

    # admitted-only rho series
    rho_values_admitted = [int(r.get("rho_num_admitted", 0)) for r in rsi_records]
    rho_increases = _has_increase(rho_values_admitted)

    # Turnover-tolerant monotonicity predicate (pinned parameters)
    rho_non_decreasing = _rho_turnover_ok(rho_values_admitted, max_drop_frac=0.50, k_recover=2)

    # Macro subset invariant (fail-closed): if any epoch violates subset, ignition is forced false.
    macro_subset_ok = all(bool(r.get("macro_subset_ok", False)) for r in rsi_records) if rsi_records else False
    if not macro_subset_ok:
        return {
            "schema": "rsi_ignition_report_v1",
            "schema_version": 1,
            "barrier_values": barrier_values,
            "eligible": False,
            "ignition": False,
            "novelty_ok": novelty_ok,
            "recovered_ok": recovered_ok,
            "rho_increases": rho_increases,
            "rho_non_decreasing": rho_non_decreasing,
            "rho_values_admitted": rho_values_admitted,
        }

    eligible = bool(rsi_records) and novelty_ok and recovered_ok
    ignition = eligible and rho_non_decreasing and rho_increases

    return {
        "schema": "rsi_ignition_report_v1",
        "schema_version": 1,
        "barrier_values": barrier_values,
        "eligible": eligible,
        "ignition": ignition,
        "novelty_ok": novelty_ok,
        "recovered_ok": recovered_ok,
        "rho_increases": rho_increases,
        "rho_non_decreasing": rho_non_decreasing,
        "rho_values_admitted": rho_values_admitted,
    }
