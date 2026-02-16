from __future__ import annotations

import hashlib
from pathlib import Path

from cdel.v18_0.omega_allowlists_v1 import load_allowlists
from cdel.v18_0.omega_common_v1 import canon_hash_obj
from cdel.v18_0.omega_promoter_v1 import run_promotion
from cdel.v1_7r.canon import load_canon_json, write_canon_json


def _make_dispatch_ctx(tmp_path: Path) -> dict[str, object]:
    run_root = tmp_path / "runs" / "rsi_omega_daemon_v18_0_tick_0001"
    state_root = run_root / "daemon" / "rsi_omega_daemon_v18_0" / "state"
    dispatch_dir = state_root / "dispatch" / "a01"
    subrun_root = state_root / "subruns" / "a01_rsi_sas_code_v12_0"
    bundle_path = (
        subrun_root
        / "daemon"
        / "rsi_sas_code_v12_0"
        / "state"
        / "promotion"
        / "sha256_c001d00d.sas_code_promotion_bundle_v1.json"
    )
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    dispatch_dir.mkdir(parents=True, exist_ok=True)

    write_canon_json(
        bundle_path,
        {
            "schema_version": "sas_code_promotion_bundle_v1",
            "candidate_algo_id": "sha256:" + ("2" * 64),
            "touched_paths": ["CDEL-v2/cdel/v12_0/verify_rsi_sas_code_v1.py"],
        },
    )

    return {
        "dispatch_dir": dispatch_dir,
        "state_root": state_root,
        "subrun_root_abs": subrun_root,
        "campaign_entry": {
            "campaign_id": "rsi_sas_code_v12_0",
            "capability_id": "RSI_SAS_CODE",
            "promotion_bundle_rel": "daemon/rsi_sas_code_v12_0/state/promotion/*.sas_code_promotion_bundle_v1.json",
        },
    }


def test_activation_bundle_contains_binding_blob(tmp_path, monkeypatch) -> None:
    allowlists, _ = load_allowlists(
        Path(__file__).resolve().parents[4]
        / "campaigns"
        / "rsi_omega_daemon_v18_0"
        / "omega_allowlists_v1.json"
    )

    def _fake_run_verify(*, out_dir: Path, bundle_dir: Path) -> tuple[dict[str, object], bool]:
        return (
            {
                "schema_version": "meta_core_promo_verify_receipt_v1",
                "return_code": 0,
                "stdout_hash": "sha256:" + ("0" * 64),
                "stderr_hash": "sha256:" + ("0" * 64),
                "verifier_out_hash": "sha256:" + ("0" * 64),
                "pass": True,
            },
            True,
        )

    monkeypatch.setattr("cdel.v18_0.omega_promoter_v1._run_meta_core_promo_verify", _fake_run_verify)

    dispatch_ctx = _make_dispatch_ctx(tmp_path)
    subverifier_receipt = {"result": {"status": "VALID", "reason_code": None}}

    receipt, _ = run_promotion(
        tick_u64=1,
        dispatch_ctx=dispatch_ctx,
        subverifier_receipt=subverifier_receipt,
        allowlists=allowlists,
    )
    assert receipt is not None
    assert receipt["result"]["status"] == "PROMOTED"

    tick_binding_path = Path(dispatch_ctx["dispatch_dir"]) / "promotion" / "omega_activation_binding_v1.json"
    bundle_dir = Path(str(dispatch_ctx["meta_core_activation_bundle_dir"]))
    bundle_binding_path = bundle_dir / "omega" / "omega_activation_binding_v1.json"

    assert tick_binding_path.exists()
    assert bundle_binding_path.exists()

    tick_binding = load_canon_json(tick_binding_path)
    bundle_binding = load_canon_json(bundle_binding_path)
    assert canon_hash_obj(bundle_binding) == canon_hash_obj(tick_binding)

    bundle_raw = bundle_binding_path.read_bytes()
    bundle_sha = hashlib.sha256(bundle_raw).hexdigest()

    manifest = load_canon_json(bundle_dir / "constitution.manifest.json")
    blobs = manifest.get("blobs")
    assert isinstance(blobs, list)
    binding_rows = [row for row in blobs if isinstance(row, dict) and row.get("path") == "omega/omega_activation_binding_v1.json"]
    assert len(binding_rows) == 1
    assert binding_rows[0]["sha256"] == bundle_sha
    assert int(binding_rows[0]["bytes"]) == len(bundle_raw)
