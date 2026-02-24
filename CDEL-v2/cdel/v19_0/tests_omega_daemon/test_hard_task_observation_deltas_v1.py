from __future__ import annotations

import json
from pathlib import Path

from cdel.v18_0.omega_common_v1 import canon_hash_obj
from cdel.v19_0 import omega_promoter_v1 as promoter


def _write_canon(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _write_observation(obs_dir: Path, payload: dict[str, object]) -> str:
    digest = canon_hash_obj(payload)
    hex_part = digest.split(":", 1)[1]
    _write_canon(obs_dir / f"sha256_{hex_part}.omega_observation_report_v1.json", payload)
    return digest


def _write_hashed(path_dir: Path, suffix: str, payload: dict[str, object]) -> str:
    digest = canon_hash_obj(payload)
    hex_part = digest.split(":", 1)[1]
    _write_canon(path_dir / f"sha256_{hex_part}.{suffix}", payload)
    return digest


def _observation_payload(
    *,
    tick_u64: int,
    code_q32: int,
    perf_q32: int,
    reasoning_q32: int,
    suite_q32: int,
) -> dict[str, object]:
    return {
        "schema_version": "omega_observation_report_v1",
        "report_id": "sha256:" + ("0" * 64),
        "tick_u64": int(tick_u64),
        "active_manifest_hash": "sha256:" + ("1" * 64),
        "metrics": {
            "hard_task_code_correctness_q32": {"q": int(code_q32)},
            "hard_task_performance_q32": {"q": int(perf_q32)},
            "hard_task_reasoning_q32": {"q": int(reasoning_q32)},
            "hard_task_suite_score_q32": {"q": int(suite_q32)},
        },
        "sources": [],
        "inputs_hashes": {
            "policy_hash": "sha256:" + ("2" * 64),
            "registry_hash": "sha256:" + ("3" * 64),
            "objectives_hash": "sha256:" + ("4" * 64),
        },
    }


def _benchmark_receipt(*, tick_u64: int, code_q32: int, perf_q32: int, reasoning_q32: int, suite_q32: int) -> dict[str, object]:
    return {
        "schema_version": "ccap_receipt_v1",
        "benchmark_run_receipt_v2": {
            "schema_version": "benchmark_run_receipt_v2",
            "receipt_id": "sha256:" + (f"{tick_u64:064x}"),
            "ek_id": "sha256:" + ("a" * 64),
            "anchor_suite_set_id": "sha256:" + ("b" * 64),
            "extensions_ledger_id": "sha256:" + ("c" * 64),
            "suite_runner_id": "sha256:" + ("d" * 64),
            "executed_suites": [
                {
                    "suite_id": "sha256:" + ("e" * 64),
                    "suite_name": "hard_task_probe",
                    "suite_set_id": "sha256:" + ("f" * 64),
                    "suite_source": "ANCHOR",
                    "ledger_ordinal_u64": 0,
                    "suite_outcome": "PASS",
                    "metrics": {
                        "hard_task_code_correctness_q32": {"q": int(code_q32)},
                        "hard_task_performance_q32": {"q": int(perf_q32)},
                        "hard_task_reasoning_q32": {"q": int(reasoning_q32)},
                        "hard_task_suite_score_q32": {"q": int(suite_q32)},
                        "hard_task_score_q32": {"q": int(suite_q32)},
                    },
                    "gate_results": [{"gate_id": "ALL_SUITES_PASS", "passed_b": True}],
                    "budget_outcome": {
                        "within_budget_b": True,
                        "cpu_ms_u64": 1,
                        "wall_ms_u64": 1,
                        "disk_mb_u64": 0,
                    },
                }
            ],
            "effective_suite_ids": ["sha256:" + ("e" * 64)],
            "aggregate_metrics": {
                "hard_task_code_correctness_q32": {"q": int(code_q32)},
                "hard_task_performance_q32": {"q": int(perf_q32)},
                "hard_task_reasoning_q32": {"q": int(reasoning_q32)},
                "hard_task_suite_score_q32": {"q": int(suite_q32)},
                "hard_task_score_q32": {"q": int(suite_q32)},
            },
            "gate_results": [{"gate_id": "ALL_SUITES_PASS", "passed_b": True}],
            "budget_outcome": {
                "within_budget_b": True,
                "cpu_ms_u64": 1,
                "wall_ms_u64": 1,
                "disk_mb_u64": 0,
            },
        },
    }


def test_hard_task_observation_deltas_counts_positive_metric_gains(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    obs_dir = state_root / "observations"
    _write_observation(
        obs_dir,
        _observation_payload(
            tick_u64=9,
            code_q32=100,
            perf_q32=200,
            reasoning_q32=300,
            suite_q32=200,
        ),
    )
    latest_hash = _write_observation(
        obs_dir,
        _observation_payload(
            tick_u64=10,
            code_q32=120,
            perf_q32=180,
            reasoning_q32=340,
            suite_q32=220,
        ),
    )

    deltas = promoter._hard_task_observation_deltas({"state_root": str(state_root)})
    assert deltas["observation_hash"] == latest_hash
    assert int(deltas["gain_count_u64"]) == 3
    delta_by_metric = deltas["delta_by_metric"]
    assert isinstance(delta_by_metric, dict)
    assert int(delta_by_metric["hard_task_code_correctness_q32"]) == 20
    assert int(delta_by_metric["hard_task_performance_q32"]) == -20
    assert int(delta_by_metric["hard_task_reasoning_q32"]) == 40
    assert int(delta_by_metric["hard_task_suite_score_q32"]) == 20


def test_hard_task_observation_deltas_falls_back_to_v2_receipt_metrics(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    obs_dir = state_root / "observations"
    _write_observation(
        obs_dir,
        {
            "schema_version": "omega_observation_report_v1",
            "report_id": "sha256:" + ("0" * 64),
            "tick_u64": 9,
            "active_manifest_hash": "sha256:" + ("1" * 64),
            "metrics": {"hard_task_baseline_init_u64": 0},
            "sources": [],
            "inputs_hashes": {
                "policy_hash": "sha256:" + ("2" * 64),
                "registry_hash": "sha256:" + ("3" * 64),
                "objectives_hash": "sha256:" + ("4" * 64),
            },
        },
    )
    _write_observation(
        obs_dir,
        {
            "schema_version": "omega_observation_report_v1",
            "report_id": "sha256:" + ("0" * 64),
            "tick_u64": 10,
            "active_manifest_hash": "sha256:" + ("1" * 64),
            "metrics": {"hard_task_baseline_init_u64": 0},
            "sources": [],
            "inputs_hashes": {
                "policy_hash": "sha256:" + ("2" * 64),
                "registry_hash": "sha256:" + ("3" * 64),
                "objectives_hash": "sha256:" + ("4" * 64),
            },
        },
    )

    dispatch_9 = state_root / "dispatch" / "d09"
    dispatch_10 = state_root / "dispatch" / "d10"
    _write_canon(
        dispatch_9 / "dispatch.omega_dispatch_receipt_v1.json",
        {"schema_version": "omega_dispatch_receipt_v1", "tick_u64": 9},
    )
    _write_canon(
        dispatch_10 / "dispatch.omega_dispatch_receipt_v1.json",
        {"schema_version": "omega_dispatch_receipt_v1", "tick_u64": 10},
    )
    _write_hashed(
        dispatch_9 / "verifier",
        "ccap_receipt_v1.json",
        _benchmark_receipt(
            tick_u64=9,
            code_q32=100,
            perf_q32=200,
            reasoning_q32=300,
            suite_q32=200,
        ),
    )
    _write_hashed(
        dispatch_10 / "verifier",
        "ccap_receipt_v1.json",
        _benchmark_receipt(
            tick_u64=10,
            code_q32=120,
            perf_q32=180,
            reasoning_q32=340,
            suite_q32=220,
        ),
    )

    deltas = promoter._hard_task_observation_deltas({"state_root": str(state_root)})
    assert bool(deltas["required_metrics_present_b"]) is True
    assert deltas["missing_required_metric_ids_v1"] == []
    delta_by_metric = deltas["delta_by_metric"]
    assert isinstance(delta_by_metric, dict)
    assert int(delta_by_metric["hard_task_code_correctness_q32"]) == 20
    assert int(delta_by_metric["hard_task_performance_q32"]) == -20
    assert int(delta_by_metric["hard_task_reasoning_q32"]) == 40
    assert int(delta_by_metric["hard_task_suite_score_q32"]) == 20


def test_hard_task_observation_deltas_marks_missing_required_v2_metric(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    obs_dir = state_root / "observations"
    _write_observation(
        obs_dir,
        {
            "schema_version": "omega_observation_report_v1",
            "report_id": "sha256:" + ("0" * 64),
            "tick_u64": 9,
            "active_manifest_hash": "sha256:" + ("1" * 64),
            "metrics": {"hard_task_baseline_init_u64": 0},
            "sources": [],
            "inputs_hashes": {
                "policy_hash": "sha256:" + ("2" * 64),
                "registry_hash": "sha256:" + ("3" * 64),
                "objectives_hash": "sha256:" + ("4" * 64),
            },
        },
    )
    _write_observation(
        obs_dir,
        {
            "schema_version": "omega_observation_report_v1",
            "report_id": "sha256:" + ("0" * 64),
            "tick_u64": 10,
            "active_manifest_hash": "sha256:" + ("1" * 64),
            "metrics": {"hard_task_baseline_init_u64": 0},
            "sources": [],
            "inputs_hashes": {
                "policy_hash": "sha256:" + ("2" * 64),
                "registry_hash": "sha256:" + ("3" * 64),
                "objectives_hash": "sha256:" + ("4" * 64),
            },
        },
    )

    dispatch_9 = state_root / "dispatch" / "d09"
    dispatch_10 = state_root / "dispatch" / "d10"
    _write_canon(
        dispatch_9 / "dispatch.omega_dispatch_receipt_v1.json",
        {"schema_version": "omega_dispatch_receipt_v1", "tick_u64": 9},
    )
    _write_canon(
        dispatch_10 / "dispatch.omega_dispatch_receipt_v1.json",
        {"schema_version": "omega_dispatch_receipt_v1", "tick_u64": 10},
    )
    receipt_9 = _benchmark_receipt(
        tick_u64=9,
        code_q32=100,
        perf_q32=200,
        reasoning_q32=300,
        suite_q32=200,
    )
    receipt_10 = _benchmark_receipt(
        tick_u64=10,
        code_q32=120,
        perf_q32=220,
        reasoning_q32=340,
        suite_q32=240,
    )
    executed_9 = receipt_9["benchmark_run_receipt_v2"]["executed_suites"][0]["metrics"]
    executed_10 = receipt_10["benchmark_run_receipt_v2"]["executed_suites"][0]["metrics"]
    aggregate_9 = receipt_9["benchmark_run_receipt_v2"]["aggregate_metrics"]
    aggregate_10 = receipt_10["benchmark_run_receipt_v2"]["aggregate_metrics"]
    del executed_9["hard_task_reasoning_q32"]
    del executed_10["hard_task_reasoning_q32"]
    del aggregate_9["hard_task_reasoning_q32"]
    del aggregate_10["hard_task_reasoning_q32"]

    _write_hashed(
        dispatch_9 / "verifier",
        "ccap_receipt_v1.json",
        receipt_9,
    )
    _write_hashed(
        dispatch_10 / "verifier",
        "ccap_receipt_v1.json",
        receipt_10,
    )

    deltas = promoter._hard_task_observation_deltas({"state_root": str(state_root)})
    assert bool(deltas["required_metrics_present_b"]) is False
    missing = deltas["missing_required_metric_ids_v1"]
    assert isinstance(missing, list)
    assert "hard_task_reasoning_q32" in missing
