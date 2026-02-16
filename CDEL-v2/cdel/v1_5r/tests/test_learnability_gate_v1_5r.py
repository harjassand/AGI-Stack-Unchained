from __future__ import annotations

import hashlib
from pathlib import Path

from cdel.v1_5r.canon import canon_bytes, sha256_prefixed
from cdel.v1_5r.family_dsl.runtime import compute_family_id, compute_signature
from cdel.v1_5r.pi0_gate_eval import evaluate_pi0_gate


def _family_with_suite_row(suite_row: dict) -> dict:
    family = {
        "schema": "family_dsl_v1",
        "schema_version": 1,
        "dsl_version": 1,
        "params_schema": [],
        "resource_bounds": {
            "max_env_steps_per_instance": 8,
            "max_instance_bytes": 2048,
            "max_instantiation_gas": 1000,
            "max_shrink_gas": 1000,
        },
        "instantiator": {"op": "CONST", "value": {"suite_row": suite_row}},
        "signature": {},
        "family_id": "",
    }
    family["signature"] = compute_signature(family)
    family["family_id"] = compute_family_id(family)
    return family


def _epoch_commit() -> dict:
    return {"commitment": sha256_prefixed(b"epoch_commit")}


def test_learnability_gate_passes_without_inst_hash_filter(tmp_path: Path) -> None:
    suite_row = {
        "env": "gridworld-v1",
        "start": {"x": 0, "y": 0},
        "goal": {"x": 0, "y": 1},
        "walls": [],
        "max_steps": 1,
    }
    family = _family_with_suite_row(suite_row)
    gate_seed = hashlib.sha256(b"seed" + family["family_id"].encode("utf-8")).digest()
    learnable, report, gate_eval = evaluate_pi0_gate(
        family=family,
        epoch_id="epoch_test",
        epoch_commit=_epoch_commit(),
        gate_seed=gate_seed,
        diagnostics_dir=tmp_path,
    )
    assert learnable is True
    assert report["learnable"] is True
    assert gate_eval["results"]


def test_learnability_gate_all_fail(tmp_path: Path) -> None:
    suite_row = {
        "env": "gridworld-v1",
        "start": {"x": 0, "y": 0},
        "goal": {"x": 0, "y": 1},
        "walls": [{"x": 0, "y": 1}],
        "max_steps": 1,
    }
    family = _family_with_suite_row(suite_row)
    gate_seed = hashlib.sha256(b"seed" + family["family_id"].encode("utf-8")).digest()
    learnable, report, _gate_eval = evaluate_pi0_gate(
        family=family,
        epoch_id="epoch_test",
        epoch_commit=_epoch_commit(),
        gate_seed=gate_seed,
        diagnostics_dir=tmp_path,
    )
    assert learnable is False
    assert report["learnable"] is False
    assert "PI0_ALL_FAIL" in report["failure_reason_codes"]


def test_learnability_gate_deterministic(tmp_path: Path) -> None:
    suite_row = {
        "env": "gridworld-v1",
        "start": {"x": 0, "y": 0},
        "goal": {"x": 0, "y": 1},
        "walls": [],
        "max_steps": 1,
    }
    family = _family_with_suite_row(suite_row)
    gate_seed = hashlib.sha256(b"seed" + family["family_id"].encode("utf-8")).digest()
    epoch_commit = _epoch_commit()

    learnable_a, report_a, gate_eval_a = evaluate_pi0_gate(
        family=family,
        epoch_id="epoch_test",
        epoch_commit=epoch_commit,
        gate_seed=gate_seed,
        diagnostics_dir=tmp_path,
    )
    learnable_b, report_b, gate_eval_b = evaluate_pi0_gate(
        family=family,
        epoch_id="epoch_test",
        epoch_commit=epoch_commit,
        gate_seed=gate_seed,
        diagnostics_dir=tmp_path,
    )

    assert learnable_a == learnable_b
    assert canon_bytes(report_a) == canon_bytes(report_b)
    assert canon_bytes(gate_eval_a) == canon_bytes(gate_eval_b)
