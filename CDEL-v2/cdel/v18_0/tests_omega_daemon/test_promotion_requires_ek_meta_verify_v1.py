from __future__ import annotations

from pathlib import Path

from cdel.v18_0.omega_allowlists_v1 import load_allowlists
from cdel.v18_0.omega_promoter_v1 import run_promotion
from cdel.v1_7r.canon import write_canon_json


def _allowlists() -> dict:
    path = Path(__file__).resolve().parents[4] / "campaigns" / "rsi_omega_daemon_v18_0" / "omega_allowlists_v1.json"
    return load_allowlists(path)[0]


def test_promotion_rejects_ek_authority_touch_without_meta_verify_receipt(tmp_path: Path) -> None:
    run_root = tmp_path / "runs" / "ek_gate_001"
    state_root = run_root / "daemon" / "rsi_omega_daemon_v18_0" / "state"
    dispatch_dir = state_root / "dispatch" / "a01"
    subrun_root = state_root / "subruns" / "a01_mock_campaign"
    dispatch_dir.mkdir(parents=True, exist_ok=True)
    subrun_root.mkdir(parents=True, exist_ok=True)

    bundle = {
        "schema_version": "omega_promotion_bundle_ccap_v1",
        "ccap_id": "sha256:" + ("1" * 64),
        "ccap_relpath": "ccap/sha256_" + ("1" * 64) + ".ccap_v1.json",
        "patch_relpath": "ccap/blobs/sha256_" + ("2" * 64) + ".patch",
        "touched_paths": [
            "ccap/sha256_" + ("1" * 64) + ".ccap_v1.json",
            "ccap/blobs/sha256_" + ("2" * 64) + ".patch",
            "authority/evaluation_kernels/ek_omega_v18_0_v1.json",
        ],
        "activation_key": "ek-touch-v1",
    }
    bundle_path = subrun_root / f"sha256_{'3' * 64}.omega_promotion_bundle_ccap_v1.json"
    write_canon_json(bundle_path, bundle)

    dispatch_ctx = {
        "dispatch_dir": dispatch_dir,
        "state_root": state_root,
        "subrun_root_abs": subrun_root,
        "campaign_entry": {
            "campaign_id": "mock_ccap_campaign",
            "capability_id": "MOCK_CCAP",
            "promotion_bundle_rel": "sha256_*.omega_promotion_bundle_ccap_v1.json",
        },
    }
    subverifier_receipt = {
        "result": {
            "status": "VALID",
            "reason_code": None,
        }
    }

    receipt, _ = run_promotion(
        tick_u64=1,
        dispatch_ctx=dispatch_ctx,
        subverifier_receipt=subverifier_receipt,
        allowlists=_allowlists(),
    )

    assert receipt is not None
    assert receipt["result"]["status"] == "REJECTED"
    assert receipt["result"]["reason_code"] == "EK_META_VERIFY_MISSING_OR_FAIL"
