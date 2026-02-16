from __future__ import annotations

from pathlib import Path

from cdel.v1_6r.canon import hash_json, load_canon_json, write_canon_json
from cdel.v1_6r.constants import meta_identities
from cdel.v1_6r.family_dsl.runtime import compute_family_id, compute_signature
from cdel.v1_6r.run_rsi_campaign import run_campaign


def _write_family(path: Path, suite_row: dict, salt: str) -> dict:
    family = {
        "schema": "family_dsl_v1",
        "schema_version": 1,
        "dsl_version": 1,
        "params_schema": [],
        "resource_bounds": {
            "max_env_steps_per_instance": int(suite_row.get("max_steps", 4)),
            "max_instance_bytes": 4096,
            "max_instantiation_gas": 10000,
            "max_shrink_gas": 10000,
        },
        "instantiator": {"op": "CONST", "value": {"suite_row": suite_row}},
        "x-salt": salt,
    }
    family["signature"] = compute_signature(family)
    family["family_id"] = compute_family_id(family)
    write_canon_json(path, family)
    return family


def test_editworld_invalid_token_witness(tmp_path: Path) -> None:
    base_dir = tmp_path / "campaign"
    fam_dir = base_dir / "families"
    fam_dir.mkdir(parents=True)

    suite_row = {
        "env": "editworld-v1",
        "max_steps": 8,
        "vocab_id": "editworld_ascii32_v1",
        "goal_text": "ab~",
        "start_text": "ab",
        "start_cursor": 0,
        "slip_ppm": 0,
        "obs_window": 4,
    }
    fam_path = fam_dir / "invalid_token.json"
    family = _write_family(fam_path, suite_row, "core-invalid-token")
    fam_hash = hash_json(family)

    manifest = {
        "schema": "family_manifest_v1",
        "schema_version": 1,
        "core_families": [
            {
                "family_id": family["family_id"],
                "family_hash": fam_hash,
                "path": "families/invalid_token.json",
                "corridor_len": 4,
                "role": "core",
            }
        ],
        "insertion_families": [],
        "sacrificial_families": [],
    }
    write_canon_json(base_dir / "family_manifest_v1.json", manifest)

    meta = meta_identities()
    campaign_pack = {
        "schema": "rsi_real_campaign_pack_v2",
        "schema_version": 2,
        "N_epochs": 1,
        "insertion_epochs": [],
        "macro_proposal_epochs": [],
        "policy_synthesizer_epochs": [],
        "family_proposals_by_epoch": {},
        "macro_proposals_by_epoch": {},
        "expected_frontier_events": {},
        "enable_witness_emission": True,
        "enable_witness_family_generalizer_v2": False,
        "enable_mech_patch_searcher": False,
        "transfer_expected": {"must_emit_transfer_receipt": False},
        "x-family_manifest": "family_manifest_v1.json",
        "x-meta": meta,
    }
    pack_path = base_dir / "rsi_real_campaign_pack_v2.json"
    write_canon_json(pack_path, campaign_pack)

    out_dir = tmp_path / "run"
    run_campaign(
        out_dir,
        {},
        strict_rsi=False,
        strict_integrity=False,
        strict_portfolio=False,
        strict_transfer=False,
        mode="real",
        campaign_pack=campaign_pack,
        pack_path=pack_path,
    )

    witness_dir = out_dir / "epochs" / "epoch_1" / "diagnostics" / "instance_witnesses_v1"
    witnesses = [load_canon_json(path) for path in witness_dir.glob("*.json")]
    assert any(w.get("failure_mode") == "VOCAB_TOKEN_INVALID" for w in witnesses)
