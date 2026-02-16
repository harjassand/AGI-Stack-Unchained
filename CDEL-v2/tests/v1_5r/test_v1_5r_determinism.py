import base64
import hashlib
from pathlib import Path

from cdel.v1_5r.canon import hash_json, write_canon_json
from cdel.v1_5r.epoch import run_epoch
from cdel.v1_5r.family_dsl.runtime import compute_family_id, compute_signature


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_state(tmp_path: Path) -> tuple[Path, Path, Path]:
    state_dir = tmp_path / "state"
    current = state_dir / "current"
    current.mkdir(parents=True)

    base_ontology = current / "base_ontology.json"
    base_mech = current / "base_mech.json"
    write_canon_json(base_ontology, {"schema": "base_ontology_v1", "schema_version": 1})
    write_canon_json(base_mech, {"schema": "base_mech_v1", "schema_version": 1})

    family = {
        "schema": "family_dsl_v1",
        "schema_version": 1,
        "dsl_version": 1,
        "params_schema": [],
        "resource_bounds": {
            "max_env_steps_per_instance": 1,
            "max_instance_bytes": 64,
            "max_instantiation_gas": 32,
            "max_shrink_gas": 32,
        },
        "instantiator": {"op": "CONST", "value": {"payload": "ok"}},
    }
    family["signature"] = compute_signature(family)
    family["family_id"] = compute_family_id(family)
    family_hash = hash_json(family)
    fam_dir = current / "families"
    fam_dir.mkdir(parents=True)
    write_canon_json(fam_dir / f"{family_hash.split(':', 1)[1]}.json", family)

    frontier = {
        "schema": "frontier_v1",
        "schema_version": 1,
        "frontier_id": "sha256:" + "0" * 64,
        "families": [{"family_id": family["family_id"], "family_hash": family_hash}],
        "M_FRONTIER": 16,
        "signature_version": 1,
        "compression_proof_hash": "sha256:" + "0" * 64,
    }
    write_canon_json(current / "frontier_v1.json", frontier)

    write_canon_json(
        current / "macro_active_set_v1.json",
        {"schema": "macro_active_set_v1", "schema_version": 1, "active_macro_ids": [], "ledger_head_hash": "sha256:" + "0" * 64},
    )
    (current / "macro_ledger_v1.jsonl").write_text("", encoding="utf-8")
    write_canon_json(
        current / "pressure_schedule_v1.json",
        {"schema": "pressure_schedule_v1", "schema_version": 1, "p_t": 0, "history": []},
    )
    write_canon_json(
        current / "meta_patch_set_v1.json",
        {"schema": "meta_patch_set_v1", "schema_version": 1, "active_patch_ids": []},
    )

    return state_dir, base_ontology, base_mech


def test_epoch_outputs_deterministic(tmp_path: Path) -> None:
    state_dir, base_ontology, base_mech = _write_state(tmp_path)
    key = base64.b64encode(b"\x01" * 32).decode("utf-8")

    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"

    run_epoch(
        epoch_id="epoch_test",
        base_ontology=base_ontology,
        base_mech=base_mech,
        state_dir=state_dir,
        out_dir=out_a,
        master_key_b64=key,
        created_unix_ms=0,
    )
    run_epoch(
        epoch_id="epoch_test",
        base_ontology=base_ontology,
        base_mech=base_mech,
        state_dir=state_dir,
        out_dir=out_b,
        master_key_b64=key,
        created_unix_ms=0,
    )

    files = [
        "epoch_commit_v1.json",
        "work_meter_v1.json",
        "success_matrix.json",
        "selection.json",
        "candidate_decisions.json",
        "epoch_summary.json",
        "diagnostics/failure_witness_v1.json",
        "diagnostics/macro_admission_report_v1.json",
        "diagnostics/frontier_update_report_v1.json",
        "traces/trace_dev_v1.jsonl",
        "traces/trace_heldout_v1.jsonl",
    ]
    for rel in files:
        assert _sha256(out_a / rel) == _sha256(out_b / rel)
