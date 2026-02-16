from __future__ import annotations

from pathlib import Path

from cdel.v1_5r.canon import hash_json, load_canon_json, write_canon_json
from cdel.v1_5r.constants import meta_identities
from cdel.v1_5r.family_dsl.runtime import compute_family_id, compute_signature
from cdel.v1_5r.run_rsi_campaign import run_campaign


def _make_core_family() -> dict:
    fam = {
        "schema": "family_dsl_v1",
        "schema_version": 1,
        "dsl_version": 1,
        "params_schema": [],
        "resource_bounds": {
            "max_env_steps_per_instance": 10,
            "max_instance_bytes": 4096,
            "max_instantiation_gas": 10000,
            "max_shrink_gas": 10000,
        },
        "instantiator": {
            "op": "CONST",
            "value": {
                "suite_row": {
                    "env": "gridworld-v1",
                    "max_steps": 10,
                    "start": {"x": 0, "y": 0},
                    "goal": {"x": 6, "y": 0},
                    "walls": [{"x": 2, "y": 1}],
                }
            },
        },
        "x-salt": "core-002",
    }
    fam["signature"] = compute_signature(fam)
    fam["family_id"] = compute_family_id(fam)
    return fam


def _make_bad_signature_family() -> dict:
    fam = {
        "schema": "family_dsl_v1",
        "schema_version": 1,
        "dsl_version": 1,
        "params_schema": [],
        "resource_bounds": {
            "max_env_steps_per_instance": 10,
            "max_instance_bytes": 4096,
            "max_instantiation_gas": 10000,
            "max_shrink_gas": 10000,
        },
        "instantiator": {
            "op": "LINEWORLD_BUILD_V1",
            "length": {"op": "CONST", "value": 12},
            "start": {"op": "CONST", "value": 0},
            "goal": {"op": "KEYED_RAND_INT_V1", "min": 3, "max": 5, "tag": "goal"},
            "walls_k": {"op": "KEYED_RAND_INT_V1", "min": 1, "max": 2, "tag": "walls"},
            "max_steps": {"op": "CONST", "value": 10},
            "slip_ppm": {"op": "CONST", "value": 0},
        },
        "x-salt": "bad-sig-001",
    }
    good_sig = compute_signature(fam)
    bad_sig = {**good_sig, "fields": dict(good_sig.get("fields", {}))}
    bad_sig["fields"]["obs_class"] = (int(bad_sig["fields"].get("obs_class", 0)) + 1) % 16
    fam["signature"] = bad_sig
    fam["family_id"] = compute_family_id(fam)
    return fam


def test_v1_5r_signature_mismatch_rejected(tmp_path: Path) -> None:
    meta = meta_identities()
    camp_dir = tmp_path / "campaign"
    fam_dir = camp_dir / "families"
    fam_dir.mkdir(parents=True, exist_ok=True)

    core_family = _make_core_family()
    core_hash = hash_json(core_family)
    write_canon_json(fam_dir / f"{core_hash.split(':',1)[1]}.json", core_family)

    bad_family = _make_bad_signature_family()
    bad_hash = hash_json(bad_family)
    write_canon_json(fam_dir / f"{bad_hash.split(':',1)[1]}.json", bad_family)

    manifest = {
        "schema": "family_manifest_v1",
        "schema_version": 1,
        "core_families": [
            {
                "family_id": core_family["family_id"],
                "family_hash": core_hash,
                "path": f"families/{core_hash.split(':',1)[1]}.json",
                "role": "core",
            }
        ],
        "sacrificial_families": [],
        "insertion_families": [],
    }
    write_canon_json(camp_dir / "family_manifest_v1.json", manifest)

    pack = {
        "schema": "rsi_real_campaign_pack_v1",
        "schema_version": 1,
        "N_epochs": 1,
        "insertion_epochs": [],
        "macro_proposal_epochs": [],
        "family_proposals_by_epoch": {"1": [f"families/{bad_hash.split(':',1)[1]}.json"]},
        "macro_proposals_by_epoch": {},
        "mech_patch_proposals_by_epoch": {},
        "expected_frontier_events": {},
        "x-family_manifest": "family_manifest_v1.json",
        "x-meta": meta,
    }
    pack_path = camp_dir / "rsi_real_campaign_pack_v1.json"
    write_canon_json(pack_path, pack)

    out_dir = tmp_path / "run"
    run_campaign(
        out_dir,
        {},
        strict_rsi=False,
        strict_integrity=False,
        strict_portfolio=False,
        mode="real",
        campaign_pack=load_canon_json(pack_path),
        pack_path=pack_path,
    )

    report = load_canon_json(out_dir / "epochs" / "epoch_1" / "diagnostics" / "family_semantics_report_v1.json")
    checks = report.get("checks", {})
    sig_check = checks.get("signature_matches_recomputed", {})
    assert sig_check.get("ok") is False
    reasons = sig_check.get("reason_codes", [])
    assert "FAMILY_SIGNATURE_MISMATCH" in reasons
