from __future__ import annotations

import hashlib
from pathlib import Path

from cdel.v1_6r.family_dsl.runtime import instantiate_family
from cdel.v1_7r.canon import hash_json
from cdel.v1_7r.science.witness_family_generalizer_science_v1 import (
    SCI_WITNESS_REPLAY_KEY_DOMAIN_V1,
    propose_witness_family_science_v1,
)
from cdel.v1_7r.science.witness_v1 import emit_science_witness_index, emit_science_witness_on_fail


def test_v1_7r_science_witness_replay_property(tmp_path: Path) -> None:
    diag_dir = tmp_path / "epochs" / "epoch_1" / "diagnostics"

    suite_row = {
        "env": "wmworld-v1",
        "max_steps": 32,
        "generator": {
            "kind": "wm_linear_sep_int_v1",
            "n": 16,
            "d": 1,
            "x_min": -2,
            "x_max": 2,
            "w_true_min": -1,
            "w_true_max": 1,
            "b_true_min": -1,
            "b_true_max": 1,
            "noise_ppm": 0,
        },
        "params": [
            {"param_id": "w0", "values_int": [-2, -1, 0, 1, 2]},
            {"param_id": "b", "values_int": [-2, -1, 0, 1, 2]},
        ],
        "start": {"p_idx": 0, "param_value_idxs": [2, 2]},
        "objective": {"metric_name": "accuracy", "min_accuracy": "0/1"},
    }

    epoch_id_parent = "epoch_1"
    epoch_id_child = "epoch_2"
    inst_hash = bytes.fromhex("33" * 32)

    witness_hash = emit_science_witness_on_fail(
        diagnostics_dir=diag_dir,
        epoch_id=epoch_id_parent,
        env_kind="wmworld-v1",
        instance_kind="anchor",
        suite_row=suite_row,
        inst_hash=inst_hash,
        failure_mode="TIMEOUT_MAX_STEPS",
        trace=[],
        final_last_eval={
            "has_value": False,
            "pass": False,
            "metric_name": "accuracy",
            "metric_value": "",
            "threshold": "0/1",
            "reason_codes": ["TIMEOUT_MAX_STEPS"],
        },
        workvec={"env_steps_total": 0, "bytes_hashed_total": 0, "verifier_gas_total": 0},
        x_meta={},
    )
    emit_science_witness_index(diagnostics_dir=diag_dir, epoch_id=epoch_id_parent)

    index_path = diag_dir / "science_instance_witness_index_v1.json"
    assert index_path.exists()

    family = propose_witness_family_science_v1(
        epoch_id=epoch_id_child,
        epoch_key=bytes.fromhex("44" * 32),
        witness_index_path=index_path,
        frontier_hash="sha256:" + "0" * 64,
        out_dir=tmp_path / "out",
    )
    assert family is not None

    replay_key = hashlib.sha256(
        SCI_WITNESS_REPLAY_KEY_DOMAIN_V1.encode("utf-8") + bytes.fromhex(witness_hash.split(":", 1)[1])
    ).digest()

    inst = instantiate_family(
        family,
        {},
        {"commitment": "sha256:" + replay_key.hex()},
        epoch_key=replay_key,
    )
    suite_row_out = inst.get("payload", {}).get("suite_row")
    assert isinstance(suite_row_out, dict)
    assert hash_json(suite_row_out) == hash_json(suite_row)
