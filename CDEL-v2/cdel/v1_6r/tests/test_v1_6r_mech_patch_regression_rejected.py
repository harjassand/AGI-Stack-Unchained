from __future__ import annotations

from pathlib import Path

from cdel.v1_6r.canon import write_canon_json
from cdel.v1_6r.mech_patch_eval import compute_mech_patch_eval_cert


def test_mech_patch_regression_rejected(tmp_path: Path) -> None:
    instance_pack = {
        "schema": "instance_pack_v1",
        "schema_version": 1,
        "instances": [
            {
                "env": "gridworld-v1",
                "max_steps": 10,
                "start": {"x": 0, "y": 0},
                "goal": {"x": 4, "y": 0},
                "walls": [],
            }
        ],
    }
    inst_path = tmp_path / "instances.json"
    write_canon_json(inst_path, instance_pack)

    benchmark_pack = {
        "schema": "mech_benchmark_pack_v1",
        "schema_version": 1,
        "cases": [
            {
                "case_id": "mb-001",
                "env": "gridworld-v1",
                "instance_pack_path": str(inst_path),
                "epoch_key": "sha256:" + "11" * 32,
                "budget": {"max_env_steps_total": 2000, "max_bytes_hashed_total": 5000000},
            }
        ],
    }

    base_mech = {
        "schema": "base_mech_v1",
        "schema_version": 1,
        "candidate_symbol": "policy_right",
        "baseline_symbol": "policy_right",
        "oracle_symbol": "policy_right",
        "definitions": [{"name": "policy_right", "body": {"tag": "int", "value": 3}}],
    }

    patch = {
        "schema": "mech_patch_v1",
        "schema_version": 1,
        "patch_id": "",
        "base_state_hash": "sha256:" + "0" * 64,
        "policy_program": {"name": "policy_up", "body": {"tag": "int", "value": 0}},
        "bounds": {
            "max_env_steps_per_instance": 512,
            "max_instance_bytes": 4096,
            "max_instantiation_gas": 1024,
            "max_shrink_gas": 1024,
        },
        "x-provenance": "test",
    }

    cert, _ = compute_mech_patch_eval_cert(
        epoch_id="epoch_1",
        patch=patch,
        base_mech=base_mech,
        benchmark_pack=benchmark_pack,
        base_patch_set_hash="sha256:" + "0" * 64,
        benchmark_pack_hash="sha256:" + "0" * 64,
    )

    assert cert["overall"]["pass"] is False
    assert "MECH_PATCH_REGRESSION" in cert["overall"]["reason_codes"]
