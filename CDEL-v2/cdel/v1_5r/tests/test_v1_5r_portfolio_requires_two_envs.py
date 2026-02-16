from __future__ import annotations

from pathlib import Path

from cdel.v1_5r.canon import hash_json, load_canon_json, write_canon_json
from cdel.v1_5r.constants import meta_identities
from cdel.v1_5r.family_dsl.runtime import compute_family_id, compute_signature
from cdel.v1_5r.run_rsi_campaign import run_campaign
from cdel.v1_5r.verify_rsi_portfolio import verify as verify_portfolio


def _make_grid_family() -> dict:
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
                    "walls": [{"x": 1, "y": 1}],
                }
            },
        },
        "x-salt": "grid-only-001",
    }
    fam["signature"] = compute_signature(fam)
    fam["family_id"] = compute_family_id(fam)
    return fam


def test_v1_5r_portfolio_requires_two_envs(tmp_path: Path) -> None:
    meta = meta_identities()
    camp_dir = tmp_path / "campaign"
    fam_dir = camp_dir / "families"
    fam_dir.mkdir(parents=True, exist_ok=True)

    core_family = _make_grid_family()
    core_hash = hash_json(core_family)
    write_canon_json(fam_dir / f"{core_hash.split(':',1)[1]}.json", core_family)

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
        "family_proposals_by_epoch": {},
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

    ok, reason = verify_portfolio(out_dir)
    assert not ok
    assert "PORTFOLIO_ENV_COUNT_FAIL" in reason
