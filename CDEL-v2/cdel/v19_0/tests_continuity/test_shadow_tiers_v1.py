from __future__ import annotations

import pytest

from cdel.v19_0.determinism_witness_v1 import evaluate_determinism_witness
from cdel.v19_0.shadow_j_eval_v1 import evaluate_j_comparison
from cdel.v19_0.shadow_runner_v1 import enforce_outbox_only_writes


def _det_profile() -> dict[str, object]:
    return {
        "schema_name": "witnessed_determinism_profile_v1",
        "schema_version": "v19_0",
        "profile_id": "sha256:" + ("a" * 64),
        "tier_a": {"n_double_runs": 50},
        "tier_b": {"n_double_runs": 1000},
    }


def _j_profile(*, per_tick_floor_enabled_b: bool) -> dict[str, object]:
    return {
        "schema_name": "j_comparison_v1",
        "schema_version": "v19_0",
        "comparison_id": "sha256:" + ("b" * 64),
        "window_rule": {
            "kind": "SUM_WINDOW_NON_WEAKENING",
            "margin_q32": 0,
        },
        "per_tick_floor_enabled_b": bool(per_tick_floor_enabled_b),
        "epsilon_tick_q32": 0,
    }


def test_determinism_counts_pinned() -> None:
    profile = _det_profile()
    rows_a = [{"run_a_hash": "sha256:" + ("1" * 64), "run_b_hash": "sha256:" + ("1" * 64)} for _ in range(50)]
    rows_b = [{"run_a_hash": "sha256:" + ("2" * 64), "run_b_hash": "sha256:" + ("2" * 64)} for _ in range(1000)]
    out_a = evaluate_determinism_witness(profile=profile, tier="TIER_A", witness_rows=rows_a)
    out_b = evaluate_determinism_witness(profile=profile, tier="TIER_B", witness_rows=rows_b)
    assert out_a["pass_b"] is True
    assert out_b["pass_b"] is True
    assert out_a["observed_n_double_runs_u64"] == 50
    assert out_b["observed_n_double_runs_u64"] == 1000


def test_j_semantics_tier_a_sum_rule_only() -> None:
    profile = _j_profile(per_tick_floor_enabled_b=False)
    out = evaluate_j_comparison(
        profile=profile,
        j19_window_q32=[0, 10, 0],
        j20_window_q32=[10, 0, 0],
    )
    assert out["window_rule_pass_b"] is True
    assert out["pass_b"] is True


def test_j_semantics_tier_b_strict_per_tick_floor() -> None:
    profile = _j_profile(per_tick_floor_enabled_b=True)
    out = evaluate_j_comparison(
        profile=profile,
        j19_window_q32=[10, 10, 10],
        j20_window_q32=[10, 9, 11],
    )
    assert out["window_rule_pass_b"] is True
    assert out["per_tick_floor_pass_b"] is False
    assert out["pass_b"] is False


def test_forbidden_cache_write_rejected() -> None:
    with pytest.raises(RuntimeError, match="SHADOW_FORBIDDEN_WRITE"):
        enforce_outbox_only_writes(
            observed_write_paths=[".omega_cache/v19/cache.bin"],
            outbox_root_rel="daemon/rsi_omega_daemon_v19_0/shadow_outbox/rsi_omega_daemon_v20_0",
            forbidden_cache_root_rel=".omega_cache",
        )

