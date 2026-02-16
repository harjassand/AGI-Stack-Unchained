from __future__ import annotations

import base64
from pathlib import Path

from cdel.v1_6r.canon import hash_json, load_canon_json, write_canon_json
from cdel.v1_6r.constants import require_constants
from cdel.v1_6r.epoch import run_epoch
from cdel.v1_6r.family_dsl.runtime import compute_family_id, compute_signature
from cdel.v1_6r.proposals.inbox import INBOX_FAMILY_DIR
from cdel.v1_6r.run_rsi_campaign import _write_base_state


def _grid_family() -> dict:
    suite_row = {
        "env": "gridworld-v1",
        "max_steps": 6,
        "start": {"x": 0, "y": 0},
        "goal": {"x": 6, "y": 0},
        "walls": [],
    }
    family = {
        "schema": "family_dsl_v1",
        "schema_version": 1,
        "dsl_version": 1,
        "params_schema": [],
        "resource_bounds": {
            "max_env_steps_per_instance": 6,
            "max_instance_bytes": 4096,
            "max_instantiation_gas": 10000,
            "max_shrink_gas": 10000,
        },
        "instantiator": {"op": "CONST", "value": {"suite_row": suite_row}},
        "x-salt": "core-grid-test",
    }
    family["signature"] = compute_signature(family)
    family["family_id"] = compute_family_id(family)
    return family


def test_witness_family_requires_keyed_ops(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    constants = require_constants()
    base_family = _grid_family()
    base_ontology, base_mech, _ = _write_base_state(
        state_dir,
        constants,
        families=[base_family],
        anchor_families=[base_family],
        policy_action=0,
    )

    master_key_b64 = base64.b64encode(b"\x01" * 32).decode("utf-8")

    epoch1_dir = state_dir / "epochs" / "epoch_1"
    run_epoch(
        epoch_id="epoch_1",
        base_ontology=base_ontology,
        base_mech=base_mech,
        state_dir=state_dir,
        out_dir=epoch1_dir,
        master_key_b64=master_key_b64,
        created_unix_ms=0,
        strict_rsi=False,
        strict_integrity=False,
        strict_portfolio=False,
        strict_transfer=False,
    )

    witness_dir = epoch1_dir / "diagnostics" / "instance_witnesses_v1"
    witness_files = sorted(witness_dir.glob("*.json"))
    assert witness_files
    parent_hash = "sha256:" + witness_files[0].stem

    candidate = {
        "schema": "family_dsl_v1",
        "schema_version": 1,
        "dsl_version": 1,
        "params_schema": [],
        "resource_bounds": {
            "max_env_steps_per_instance": 6,
            "max_instance_bytes": 4096,
            "max_instantiation_gas": 10000,
            "max_shrink_gas": 10000,
        },
        "instantiator": {"op": "CONST", "value": {"suite_row": base_family["instantiator"]["value"]["suite_row"]}},
        "x-provenance": "witness_family_generalizer_v2",
        "x-parent_witness_hash": parent_hash,
        "x-salt": "wit-const",
    }
    candidate["signature"] = compute_signature(candidate)
    candidate["family_id"] = compute_family_id(candidate)

    inbox_dir = state_dir / INBOX_FAMILY_DIR
    inbox_dir.mkdir(parents=True, exist_ok=True)
    cand_hash = hash_json(candidate).split(":", 1)[1]
    write_canon_json(inbox_dir / f"{cand_hash}.json", candidate)

    epoch2_dir = state_dir / "epochs" / "epoch_2"
    run_epoch(
        epoch_id="epoch_2",
        base_ontology=base_ontology,
        base_mech=base_mech,
        state_dir=state_dir,
        out_dir=epoch2_dir,
        master_key_b64=master_key_b64,
        created_unix_ms=0,
        strict_rsi=False,
        strict_integrity=False,
        strict_portfolio=False,
        strict_transfer=False,
    )

    sem_report = load_canon_json(epoch2_dir / "diagnostics" / "family_semantics_report_v1.json")
    witness_checks = sem_report.get("x-witness_checks")
    assert isinstance(witness_checks, dict)
    keyed_check = witness_checks.get("witness_keyed_op")
    assert isinstance(keyed_check, dict)
    assert keyed_check.get("ok") is False
    assert "FAMILY_NOT_KEYED" in keyed_check.get("reason_codes", [])
