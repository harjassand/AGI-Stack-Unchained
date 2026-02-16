from __future__ import annotations

import hashlib
from pathlib import Path

from cdel.v1_6r.canon import canon_bytes, hash_json, sha256_prefixed, write_canon_json
from cdel.v1_6r.family_dsl.runtime import instantiate_family
from cdel.v1_6r.witness_constants import WITNESS_REPLAY_KEY_DOMAIN_V1
from cdel.v1_6r.witness_family_generalizer_v2 import propose_witness_family_v2


def test_witness_family_replay_property(tmp_path: Path) -> None:
    diag_dir = tmp_path / "epoch_1" / "diagnostics"
    witness_dir = diag_dir / "instance_witnesses_v1"
    witness_dir.mkdir(parents=True)

    suite_row = {
        "env": "gridworld-v1",
        "max_steps": 6,
        "start": {"x": 0, "y": 0},
        "goal": {"x": 4, "y": 0},
        "walls": [],
    }
    witness_payload = {
        "schema": "instance_witness_v1",
        "schema_version": 1,
        "epoch_id": "epoch_1",
        "env_kind": "gridworld-v1",
        "instance_kind": "anchor",
        "suite_row": suite_row,
        "suite_row_hash": sha256_prefixed(canon_bytes(suite_row)),
        "inst_hash": "sha256:" + "0" * 64,
        "failure_mode": "TIMEOUT_MAX_STEPS",
        "trace_hash": "sha256:" + "0" * 64,
        "trace_excerpt": [],
        "workvec": {"env_steps_total": 0, "bytes_hashed_total": 0, "verifier_gas_total": 0},
    }
    witness_hash = hash_json(witness_payload)
    write_canon_json(witness_dir / f"{witness_hash.split(':', 1)[1]}.json", witness_payload)

    index_payload = {
        "schema": "instance_witness_index_v1",
        "schema_version": 1,
        "epoch_id": "epoch_1",
        "witnesses_by_env_kind": {
            "gridworld-v1": {"anchor": [witness_hash], "pressure": [], "gate": []}
        },
    }
    index_path = diag_dir / "instance_witness_index_v1.json"
    write_canon_json(index_path, index_payload)

    out_dir = tmp_path / "out"
    family = propose_witness_family_v2(
        epoch_id="epoch_2",
        epoch_key=bytes.fromhex("22" * 32),
        witness_index_path=index_path,
        frontier_hash="sha256:" + "0" * 64,
        macro_active_set_hash=None,
        out_dir=out_dir,
    )
    assert family is not None

    replay_key = hashlib.sha256(
        WITNESS_REPLAY_KEY_DOMAIN_V1.encode("utf-8") + bytes.fromhex(witness_hash.split(":", 1)[1])
    ).digest()
    inst = instantiate_family(
        family,
        {},
        {"commitment": "sha256:" + replay_key.hex()},
        epoch_key=replay_key,
    )
    suite_row_out = inst.get("payload", {}).get("suite_row")
    assert isinstance(suite_row_out, dict)
    suite_hash = sha256_prefixed(canon_bytes(suite_row_out))
    assert suite_hash == witness_payload["suite_row_hash"]
