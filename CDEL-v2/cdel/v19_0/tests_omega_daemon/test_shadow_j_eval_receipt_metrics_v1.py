from __future__ import annotations

import json
from pathlib import Path

import pytest

from cdel.v19_0.shadow_j_eval_v1 import (
    build_ccap_receipt_metric_index_for_state_root,
    extract_metric_q32_from_ccap_receipt,
)
from cdel.v19_0.common_v1 import canon_hash_obj


def _write_canon(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _write_hashed(path_dir: Path, suffix: str, payload: dict[str, object]) -> Path:
    digest = canon_hash_obj(payload)
    path = path_dir / f"sha256_{digest.split(':', 1)[1]}.{suffix}"
    _write_canon(path, payload)
    return path


def _benchmark_receipt(
    *,
    metric_id: str,
    q_rows: list[int],
    ek_id: str = "sha256:" + ("a" * 64),
) -> dict[str, object]:
    suites = []
    for idx, q in enumerate(q_rows):
        suites.append(
            {
                "suite_id": f"sha256:{idx:064x}",
                "suite_name": f"suite_{idx}",
                "suite_set_id": "sha256:" + ("b" * 64),
                "suite_source": "ANCHOR" if idx == 0 else "EXTENSION",
                "ledger_ordinal_u64": idx,
                "suite_outcome": "PASS",
                "metrics": {
                    metric_id: {"q": int(q)},
                },
                "gate_results": [{"gate_id": "ALL_SUITES_PASS", "passed_b": True}],
                "budget_outcome": {
                    "within_budget_b": True,
                    "cpu_ms_u64": 1,
                    "wall_ms_u64": 1,
                    "disk_mb_u64": 0,
                },
            }
        )
    payload = {
        "schema_version": "benchmark_run_receipt_v2",
        "receipt_id": "sha256:" + ("0" * 64),
        "ek_id": ek_id,
        "anchor_suite_set_id": "sha256:" + ("c" * 64),
        "extensions_ledger_id": "sha256:" + ("d" * 64),
        "suite_runner_id": "sha256:" + ("e" * 64),
        "executed_suites": suites,
        "effective_suite_ids": [str(row["suite_id"]) for row in suites],
        "aggregate_metrics": {metric_id: {"q": int(sum(q_rows) // max(1, len(q_rows)))}},
        "gate_results": [{"gate_id": "ALL_SUITES_PASS", "passed_b": True}],
        "budget_outcome": {
            "within_budget_b": True,
            "cpu_ms_u64": 1,
            "wall_ms_u64": 1,
            "disk_mb_u64": 0,
        },
    }
    payload_no_id = dict(payload)
    payload_no_id.pop("receipt_id", None)
    payload["receipt_id"] = canon_hash_obj(payload_no_id)
    return payload


def test_extract_metric_q32_from_v2_executed_suites_mean() -> None:
    receipt = {
        "schema_version": "ccap_receipt_v1",
        "benchmark_run_receipt_v2": _benchmark_receipt(
            metric_id="hard_task_suite_score_q32",
            q_rows=[100, 200, 300],
        ),
    }
    metric_q32, source = extract_metric_q32_from_ccap_receipt(
        ccap_receipt=receipt,
        metric_id="hard_task_suite_score_q32",
        require_consistent_mirror_b=True,
    )
    assert metric_q32 == 200
    assert source == "V2_EXECUTED_SUITES_MEAN"


def test_extract_metric_q32_from_legacy_flat_fallback() -> None:
    receipt = {
        "schema_version": "ccap_receipt_v1",
        "score_cand_summary": {
            "median_stps_non_noop_q32": 123,
            "non_noop_ticks_per_min_f64": 1.5,
            "promotions_u64": 2,
            "activation_success_u64": 1,
        },
    }
    metric_q32, source = extract_metric_q32_from_ccap_receipt(
        ccap_receipt=receipt,
        metric_id="median_stps_non_noop_q32",
        require_consistent_mirror_b=True,
    )
    assert metric_q32 == 123
    assert source == "LEGACY_FLAT"


def test_extract_metric_q32_prefers_v2_and_rejects_mirror_mismatch() -> None:
    receipt = {
        "schema_version": "ccap_receipt_v1",
        "benchmark_run_receipt_v2": _benchmark_receipt(
            metric_id="median_stps_non_noop_q32",
            q_rows=[50],
        ),
        "score_cand_summary": {
            "median_stps_non_noop_q32": 999,
            "non_noop_ticks_per_min_f64": 0,
            "promotions_u64": 0,
            "activation_success_u64": 0,
        },
    }
    with pytest.raises(RuntimeError, match="NONDETERMINISM"):
        extract_metric_q32_from_ccap_receipt(
            ccap_receipt=receipt,
            metric_id="median_stps_non_noop_q32",
            require_consistent_mirror_b=True,
        )


def test_build_ccap_metric_index_from_state_root_uses_tick_bound_dispatch_receipts(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    dispatch_root = state_root / "dispatch"

    for tick_u64, score_q32 in ((10, 400), (11, 460)):
        dispatch_dir = dispatch_root / f"d{tick_u64}"
        _write_canon(
            dispatch_dir / f"dispatch_{tick_u64}.omega_dispatch_receipt_v1.json",
            {
                "schema_version": "omega_dispatch_receipt_v1",
                "tick_u64": int(tick_u64),
            },
        )
        ccap_receipt = {
            "schema_version": "ccap_receipt_v1",
            "benchmark_run_receipt_v2": _benchmark_receipt(
                metric_id="hard_task_suite_score_q32",
                q_rows=[int(score_q32)],
            ),
        }
        _write_hashed(dispatch_dir / "verifier", "ccap_receipt_v1.json", ccap_receipt)

    index = build_ccap_receipt_metric_index_for_state_root(
        state_root=state_root,
        required_metric_ids=["hard_task_suite_score_q32"],
        require_consistent_mirror_b=True,
    )
    assert index[10]["hard_task_suite_score_q32"] == 400
    assert index[11]["hard_task_suite_score_q32"] == 460
