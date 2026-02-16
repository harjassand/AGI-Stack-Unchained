from __future__ import annotations

from cdel.v1_6r.eval_runner import eval_instance
from cdel.v1_6r.family_dsl.runtime import compute_family_id, compute_signature


def _editworld_family() -> dict:
    suite_row = {
        "env": "editworld-v1",
        "max_steps": 8,
        "vocab_id": "editworld_ascii32_v1",
        "goal_text": "ab",
        "start_text": "a",
        "start_cursor": 0,
        "slip_ppm": 250000,
        "obs_window": 4,
    }
    family = {
        "schema": "family_dsl_v1",
        "schema_version": 1,
        "dsl_version": 1,
        "params_schema": [],
        "resource_bounds": {
            "max_env_steps_per_instance": 8,
            "max_instance_bytes": 4096,
            "max_instantiation_gas": 10000,
            "max_shrink_gas": 10000,
        },
        "instantiator": {"op": "CONST", "value": {"suite_row": suite_row}},
        "x-salt": "core-edit-det",
    }
    family["signature"] = compute_signature(family)
    family["family_id"] = compute_family_id(family)
    return family


def test_editworld_determinism() -> None:
    family = _editworld_family()
    epoch_key = bytes.fromhex("11" * 32)
    epoch_commit = {
        "commitment": "sha256:" + epoch_key.hex(),
        "frontier_hash": "sha256:" + "0" * 64,
    }
    base_mech = {
        "schema": "base_mech_v1",
        "schema_version": 1,
        "candidate_symbol": "policy_right_0",
        "baseline_symbol": "policy_right_0",
        "oracle_symbol": "policy_right_0",
        "definitions": [
            {"name": "policy_right_0", "body": {"tag": "int", "value": 3}}
        ],
    }

    out_a = eval_instance(
        epoch_id="epoch_1",
        family=family,
        theta={},
        epoch_commit=epoch_commit,
        base_mech=base_mech,
        receipt_hash="sha256:" + "0" * 64,
        epoch_key=epoch_key,
    )
    out_b = eval_instance(
        epoch_id="epoch_1",
        family=family,
        theta={},
        epoch_commit=epoch_commit,
        base_mech=base_mech,
        receipt_hash="sha256:" + "0" * 64,
        epoch_key=epoch_key,
    )

    assert out_a[0] == out_b[0]
    assert out_a[1] == out_b[1]
