from __future__ import annotations

import json
from pathlib import Path

from cdel.v18_0.omega_allowlists_v1 import load_allowlists
from cdel.v18_0.omega_common_v1 import canon_hash_obj
from cdel.v18_0.omega_promoter_v1 import run_promotion
from cdel.v1_7r.canon import write_canon_json


def test_forbidden_path_patch_reject(tmp_path) -> None:
    state_root = tmp_path / "state"
    dispatch_dir = state_root / "dispatch" / "a0"
    subrun_root = state_root / "subruns" / "a0_campaign"
    dispatch_dir.mkdir(parents=True)
    subrun_root.mkdir(parents=True)

    bundle = {
        "schema_version": "omega_mock_bundle_v1",
        "touched_paths": ["meta-core/kernel/forbidden.py"],
    }
    bundle_hash = canon_hash_obj(bundle)
    bundle_path = subrun_root / f"sha256_{bundle_hash.split(':', 1)[1]}.omega_mock_bundle_v1.json"
    write_canon_json(bundle_path, bundle)

    allowlists, _ = load_allowlists(
        Path(__file__).resolve().parents[4]
        / "campaigns"
        / "rsi_omega_daemon_v18_0"
        / "omega_allowlists_v1.json"
    )

    dispatch_ctx = {
        "dispatch_dir": dispatch_dir,
        "subrun_root_abs": subrun_root,
        "campaign_entry": {
            "campaign_id": "mock_campaign",
            "promotion_bundle_rel": "sha256_*.omega_mock_bundle_v1.json",
        },
    }
    subverifier_receipt = {"result": {"status": "VALID", "reason_code": None}}

    receipt, _ = run_promotion(
        tick_u64=1,
        dispatch_ctx=dispatch_ctx,
        subverifier_receipt=subverifier_receipt,
        allowlists=allowlists,
    )

    assert receipt is not None
    assert receipt["result"]["status"] == "REJECTED"
    assert receipt["result"]["reason_code"] == "FORBIDDEN_PATH"
