from __future__ import annotations

import shutil
from pathlib import Path

from cdel.v18_0.omega_allowlists_v1 import load_allowlists
from cdel.v18_0.omega_promoter_v1 import run_promotion
from cdel.v1_7r.canon import write_canon_json


def _make_meta_core_stub(tmp_path: Path) -> tuple[Path, str]:
    meta_core_root = tmp_path / "meta-core"
    active_hex = "a" * 64
    (meta_core_root / "active").mkdir(parents=True, exist_ok=True)
    (meta_core_root / "active" / "ACTIVE_BUNDLE").write_text(active_hex + "\n", encoding="utf-8")
    (meta_core_root / "store" / "bundles" / active_hex / "omega").mkdir(parents=True, exist_ok=True)
    return meta_core_root, active_hex


def _make_dispatch_ctx(tmp_path: Path, *, tick: int) -> dict[str, object]:
    run_root = tmp_path / "runs" / f"rsi_omega_daemon_v18_0_tick_{tick:04d}"
    state_root = run_root / "daemon" / "rsi_omega_daemon_v18_0" / "state"
    dispatch_dir = state_root / "dispatch" / f"a{tick:02d}"
    subrun_root = state_root / "subruns" / f"a{tick:02d}_rsi_sas_code_v12_0"
    bundle_path = (
        subrun_root
        / "daemon"
        / "rsi_sas_code_v12_0"
        / "state"
        / "promotion"
        / "sha256_feedface.sas_code_promotion_bundle_v1.json"
    )
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    dispatch_dir.mkdir(parents=True, exist_ok=True)

    write_canon_json(
        bundle_path,
        {
            "schema_version": "sas_code_promotion_bundle_v1",
            "candidate_algo_id": "sha256:" + ("1" * 64),
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


def test_promotion_skips_if_already_active(tmp_path, monkeypatch) -> None:
    meta_core_root, active_hex = _make_meta_core_stub(tmp_path)
    monkeypatch.setenv("OMEGA_META_CORE_ROOT", str(meta_core_root))

    allowlists, _ = load_allowlists(
        Path(__file__).resolve().parents[4]
        / "campaigns"
        / "rsi_omega_daemon_v18_0"
        / "omega_allowlists_v1.json"
    )

    def _fake_build_promo_bundle(*, out_dir: Path, campaign_id: str, source_bundle_hash: str) -> Path:
        bundle_dir = out_dir / "meta_core_promotion_bundle_v1"
        bundle_dir.mkdir(parents=True, exist_ok=True)
        return bundle_dir

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

    def _fake_build_activation_bundle(
        *,
        out_dir: Path,
        binding_payload: dict[str, object],
        binding_hash_hex8: str,
    ) -> tuple[Path, str]:
        bundle_dir = out_dir / "meta_core_activation_bundle_v1"
        (bundle_dir / "omega").mkdir(parents=True, exist_ok=True)
        write_canon_json(bundle_dir / "omega" / "omega_activation_binding_v1.json", binding_payload)
        return bundle_dir, "sha256:" + ("b" * 64)

    monkeypatch.setattr("cdel.v18_0.omega_promoter_v1._build_meta_core_promotion_bundle", _fake_build_promo_bundle)
    monkeypatch.setattr("cdel.v18_0.omega_promoter_v1._run_meta_core_promo_verify", _fake_run_verify)
    monkeypatch.setattr("cdel.v18_0.omega_promoter_v1._build_meta_core_activation_bundle", _fake_build_activation_bundle)

    subverifier_receipt = {"result": {"status": "VALID", "reason_code": None}}

    dispatch_ctx_1 = _make_dispatch_ctx(tmp_path, tick=1)
    receipt_1, _ = run_promotion(
        tick_u64=1,
        dispatch_ctx=dispatch_ctx_1,
        subverifier_receipt=subverifier_receipt,
        allowlists=allowlists,
    )
    assert receipt_1 is not None
    assert receipt_1["result"]["status"] == "PROMOTED"

    tick1_binding = Path(dispatch_ctx_1["dispatch_dir"]) / "promotion" / "omega_activation_binding_v1.json"
    assert tick1_binding.exists()
    active_binding_path = meta_core_root / "store" / "bundles" / active_hex / "omega" / "omega_activation_binding_v1.json"
    active_binding_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(tick1_binding, active_binding_path)

    dispatch_ctx_2 = _make_dispatch_ctx(tmp_path, tick=2)
    receipt_2, _ = run_promotion(
        tick_u64=2,
        dispatch_ctx=dispatch_ctx_2,
        subverifier_receipt=subverifier_receipt,
        allowlists=allowlists,
    )
    assert receipt_2 is not None
    assert receipt_2["result"]["status"] == "SKIPPED"
    assert receipt_2["result"]["reason_code"] == "ALREADY_ACTIVE"
    assert "meta_core_activation_bundle_dir" not in dispatch_ctx_2
    assert not (Path(dispatch_ctx_2["dispatch_dir"]) / "promotion" / "meta_core_promo_verify_receipt_v1.json").exists()
