from __future__ import annotations

from pathlib import Path

from cdel.v18_0.omega_allowlists_v1 import load_allowlists
from cdel.v18_0.omega_common_v1 import canon_hash_obj
from cdel.v18_0.omega_promoter_v1 import run_promotion
from cdel.v1_7r.canon import load_canon_json, write_canon_json


def _allowlists() -> dict:
    path = Path(__file__).resolve().parents[4] / "campaigns" / "rsi_omega_daemon_v18_0" / "omega_allowlists_v1.json"
    return load_allowlists(path)[0]


def _setup_dispatch(tmp_path: Path, *, receipt_decision: str) -> tuple[dict[str, object], dict[str, object]]:
    run_root = tmp_path / "runs" / "ccap_run_001"
    state_root = run_root / "daemon" / "rsi_omega_daemon_v18_0" / "state"
    dispatch_dir = state_root / "dispatch" / "a01"
    subrun_root = state_root / "subruns" / "a01_mock_ccap_campaign"
    verifier_dir = dispatch_dir / "verifier"

    verifier_dir.mkdir(parents=True, exist_ok=True)
    (subrun_root / "ccap" / "blobs").mkdir(parents=True, exist_ok=True)

    ccap_id = "sha256:" + ("1" * 64)
    ccap_rel = "ccap/sha256_" + ("1" * 64) + ".ccap_v1.json"
    patch_rel = "ccap/blobs/sha256_" + ("2" * 64) + ".patch"

    ccap_payload = {
        "meta": {
            "ccap_version": 1,
            "base_tree_id": "sha256:" + ("3" * 64),
            "auth_hash": "sha256:" + ("4" * 64),
            "dsbx_profile_id": "sha256:" + ("5" * 64),
            "env_contract_id": "sha256:" + ("6" * 64),
            "toolchain_root_id": "sha256:" + ("7" * 64),
            "ek_id": "sha256:" + ("8" * 64),
            "op_pool_id": "sha256:" + ("9" * 64),
            "canon_version_ids": {
                "ccap_can_v": "sha256:" + ("a" * 64),
                "ir_can_v": "sha256:" + ("b" * 64),
                "op_can_v": "sha256:" + ("c" * 64),
                "obs_can_v": "sha256:" + ("d" * 64),
            },
        },
        "payload": {
            "kind": "PATCH",
            "patch_blob_id": "sha256:" + ("2" * 64),
        },
        "build": {
            "build_recipe_id": "sha256:" + ("e" * 64),
            "build_targets": [],
            "artifact_bindings": {},
        },
        "eval": {
            "stages": [{"stage_name": "REALIZE"}],
            "final_suite_id": "sha256:" + ("f" * 64),
        },
        "budgets": {
            "cpu_ms_max": 1000,
            "wall_ms_max": 1000,
            "mem_mb_max": 1000,
            "disk_mb_max": 1000,
            "fds_max": 100,
            "procs_max": 10,
            "threads_max": 10,
            "net": "forbidden",
        },
    }
    write_canon_json(subrun_root / ccap_rel, ccap_payload)
    (subrun_root / patch_rel).write_bytes(b"patch")

    bundle = {
        "schema_version": "omega_promotion_bundle_ccap_v1",
        "ccap_id": ccap_id,
        "ccap_relpath": ccap_rel,
        "patch_relpath": patch_rel,
        "touched_paths": [ccap_rel, patch_rel],
        "activation_key": "ccap_activation_key_v1",
    }
    bundle_hash = canon_hash_obj(bundle)
    bundle_path = subrun_root / f"sha256_{bundle_hash.split(':', 1)[1]}.omega_promotion_bundle_ccap_v1.json"
    write_canon_json(bundle_path, bundle)

    receipt = {
        "schema_version": "ccap_receipt_v1",
        "ccap_id": ccap_id,
        "base_tree_id": "sha256:" + ("3" * 64),
        "applied_tree_id": "sha256:" + ("e" * 64),
        "realized_out_id": "sha256:" + ("f" * 64),
        "ek_id": "sha256:" + ("8" * 64),
        "op_pool_id": "sha256:" + ("9" * 64),
        "auth_hash": "sha256:" + ("4" * 64),
        "determinism_check": "PASS",
        "eval_status": "PASS" if receipt_decision == "PROMOTE" else "FAIL",
        "decision": receipt_decision,
        "cost_vector": {
            "cpu_ms": 1,
            "wall_ms": 1,
            "mem_mb": 1,
            "disk_mb": 1,
            "fds": 1,
            "procs": 0,
            "threads": 0,
        },
        "logs_hash": "sha256:" + ("0" * 64),
    }
    receipt_hash = canon_hash_obj(receipt)
    write_canon_json(verifier_dir / f"sha256_{receipt_hash.split(':', 1)[1]}.ccap_receipt_v1.json", receipt)

    realized = {
        "schema_version": "realized_capsule_receipt_v1",
        "realized_receipt_id": "sha256:" + ("3" * 64),
        "ccap_id": ccap_id,
        "base_tree_id": "sha256:" + ("3" * 64),
        "applied_tree_id": "sha256:" + ("e" * 64),
        "realized_out_id": "sha256:" + ("f" * 64),
        "ek_id": "sha256:" + ("8" * 64),
        "op_pool_id": "sha256:" + ("9" * 64),
        "auth_hash": "sha256:" + ("4" * 64),
        "determinism_check": "PASS",
        "eval_status": "PASS",
        "cost_vector": {
            "cpu_ms": 1,
            "wall_ms": 1,
            "mem_mb": 1,
            "disk_mb": 1,
            "fds": 1,
            "procs": 0,
            "threads": 0,
        },
        "logs_hash": "sha256:" + ("0" * 64),
    }
    realized_dir = subrun_root / "ccap" / "realized"
    realized_dir.mkdir(parents=True, exist_ok=True)
    realized_hash = canon_hash_obj(realized)
    write_canon_json(realized_dir / f"sha256_{realized_hash.split(':', 1)[1]}.realized_capsule_receipt_v1.json", realized)
    write_canon_json(realized_dir / "realized_capsule_receipt_v1.json", realized)

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
    subverifier = {"result": {"status": "VALID", "reason_code": None}}
    return dispatch_ctx, subverifier


def _patch_meta_core(monkeypatch, tmp_path: Path) -> None:
    def _fake_build_promo(*, out_dir: Path, campaign_id: str, source_bundle_hash: str) -> Path:
        path = tmp_path / "meta_core_promo_bundle"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _fake_verify(*, out_dir: Path, bundle_dir: Path):
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

    def _fake_build_activation(*, out_dir: Path, binding_payload: dict, binding_hash_hex8: str):
        path = tmp_path / "meta_core_activation_bundle"
        path.mkdir(parents=True, exist_ok=True)
        return path, "sha256:" + ("a" * 64)

    monkeypatch.setattr("cdel.v18_0.omega_promoter_v1._build_meta_core_promotion_bundle", _fake_build_promo)
    monkeypatch.setattr("cdel.v18_0.omega_promoter_v1._run_meta_core_promo_verify", _fake_verify)
    monkeypatch.setattr("cdel.v18_0.omega_promoter_v1._build_meta_core_activation_bundle", _fake_build_activation)
    monkeypatch.setattr("cdel.v18_0.omega_promoter_v1._read_active_binding", lambda _root: None)


def test_ccap_promotion_rejects_when_receipt_not_promote(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OMEGA_BLACKBOX", raising=False)
    dispatch_ctx, subverifier = _setup_dispatch(tmp_path, receipt_decision="REJECT")
    _patch_meta_core(monkeypatch, tmp_path)
    monkeypatch.setattr("cdel.v18_0.omega_promoter_v1._verify_ccap_apply_matches_receipt", lambda **_: True)

    receipt, _ = run_promotion(
        tick_u64=1,
        dispatch_ctx=dispatch_ctx,
        subverifier_receipt=subverifier,
        allowlists=_allowlists(),
    )
    assert receipt is not None
    assert receipt["execution_mode"] == "STRICT"
    assert receipt["result"]["status"] == "REJECTED"
    assert receipt["result"]["reason_code"] == "CCAP_RECEIPT_REJECTED"


def test_ccap_promotion_rejects_when_apply_hash_mismatch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OMEGA_BLACKBOX", raising=False)
    dispatch_ctx, subverifier = _setup_dispatch(tmp_path, receipt_decision="PROMOTE")
    _patch_meta_core(monkeypatch, tmp_path)
    monkeypatch.setattr("cdel.v18_0.omega_promoter_v1._verify_ccap_apply_matches_receipt", lambda **_: False)

    receipt, _ = run_promotion(
        tick_u64=1,
        dispatch_ctx=dispatch_ctx,
        subverifier_receipt=subverifier,
        allowlists=_allowlists(),
    )
    assert receipt is not None
    assert receipt["execution_mode"] == "STRICT"
    assert receipt["result"]["status"] == "REJECTED"
    assert receipt["result"]["reason_code"] == "CCAP_APPLY_MISMATCH"


def test_ccap_promotion_promotes_when_receipt_and_replay_match(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OMEGA_BLACKBOX", raising=False)
    dispatch_ctx, subverifier = _setup_dispatch(tmp_path, receipt_decision="PROMOTE")
    _patch_meta_core(monkeypatch, tmp_path)
    monkeypatch.setattr("cdel.v18_0.omega_promoter_v1._verify_ccap_apply_matches_receipt", lambda **_: True)

    receipt, _ = run_promotion(
        tick_u64=1,
        dispatch_ctx=dispatch_ctx,
        subverifier_receipt=subverifier,
        allowlists=_allowlists(),
    )
    assert receipt is not None
    assert receipt["execution_mode"] == "STRICT"
    assert receipt["result"]["status"] == "PROMOTED"
    assert receipt["result"]["reason_code"] is None


def test_ccap_promotion_rejects_when_realized_receipt_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OMEGA_BLACKBOX", raising=False)
    dispatch_ctx, subverifier = _setup_dispatch(tmp_path, receipt_decision="PROMOTE")
    realized_dir = Path(dispatch_ctx["subrun_root_abs"]) / "ccap" / "realized"
    if realized_dir.exists():
        for path in realized_dir.glob("*"):
            path.unlink()
    _patch_meta_core(monkeypatch, tmp_path)
    monkeypatch.setattr("cdel.v18_0.omega_promoter_v1._verify_ccap_apply_matches_receipt", lambda **_: True)

    receipt, _ = run_promotion(
        tick_u64=1,
        dispatch_ctx=dispatch_ctx,
        subverifier_receipt=subverifier,
        allowlists=_allowlists(),
    )
    assert receipt is not None
    assert receipt["execution_mode"] == "STRICT"
    assert receipt["result"]["status"] == "REJECTED"
    assert receipt["result"]["reason_code"] == "CCAP_RECEIPT_MISSING_OR_MISMATCH"


def test_ccap_promotion_blackbox_ignores_verdict_fields(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMEGA_BLACKBOX", "1")
    dispatch_ctx, subverifier = _setup_dispatch(tmp_path, receipt_decision="REJECT")
    _patch_meta_core(monkeypatch, tmp_path)
    monkeypatch.setattr("cdel.v18_0.omega_promoter_v1._verify_ccap_apply_matches_receipt", lambda **_: True)

    receipt, _ = run_promotion(
        tick_u64=1,
        dispatch_ctx=dispatch_ctx,
        subverifier_receipt=subverifier,
        allowlists=_allowlists(),
    )
    assert receipt is not None
    assert receipt["execution_mode"] == "BLACKBOX"
    assert receipt["result"]["status"] == "PROMOTED"
    assert receipt["result"]["reason_code"] is None


def test_ccap_promotion_blackbox_still_rejects_apply_mismatch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMEGA_BLACKBOX", "true")
    dispatch_ctx, subverifier = _setup_dispatch(tmp_path, receipt_decision="REJECT")
    _patch_meta_core(monkeypatch, tmp_path)
    monkeypatch.setattr("cdel.v18_0.omega_promoter_v1._verify_ccap_apply_matches_receipt", lambda **_: False)

    receipt, _ = run_promotion(
        tick_u64=1,
        dispatch_ctx=dispatch_ctx,
        subverifier_receipt=subverifier,
        allowlists=_allowlists(),
    )
    assert receipt is not None
    assert receipt["execution_mode"] == "BLACKBOX"
    assert receipt["result"]["status"] == "REJECTED"
    assert receipt["result"]["reason_code"] == "CCAP_APPLY_MISMATCH"


def test_ccap_promotion_blackbox_still_requires_valid_subverifier(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMEGA_BLACKBOX", "1")
    dispatch_ctx, _ = _setup_dispatch(tmp_path, receipt_decision="REJECT")
    subverifier = {"result": {"status": "INVALID", "reason_code": "VERIFY_ERROR"}}
    _patch_meta_core(monkeypatch, tmp_path)
    monkeypatch.setattr("cdel.v18_0.omega_promoter_v1._verify_ccap_apply_matches_receipt", lambda **_: True)

    receipt, _ = run_promotion(
        tick_u64=1,
        dispatch_ctx=dispatch_ctx,
        subverifier_receipt=subverifier,
        allowlists=_allowlists(),
    )
    assert receipt is not None
    assert receipt["execution_mode"] == "BLACKBOX"
    assert receipt["result"]["status"] == "REJECTED"
    assert receipt["result"]["reason_code"] == "SUBVERIFIER_INVALID"


def test_ccap_promotion_blackbox_accepts_refuted_receipt_without_realized(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMEGA_BLACKBOX", "1")
    dispatch_ctx, subverifier = _setup_dispatch(tmp_path, receipt_decision="REJECT")
    verifier_dir = Path(dispatch_ctx["dispatch_dir"]) / "verifier"
    ccap_receipt_path = next(verifier_dir.glob("sha256_*.ccap_receipt_v1.json"))
    ccap_receipt = load_canon_json(ccap_receipt_path)
    ccap_receipt["applied_tree_id"] = "sha256:" + ("0" * 64)
    ccap_receipt["realized_out_id"] = ""
    ccap_receipt["determinism_check"] = "REFUTED"
    ccap_receipt["eval_status"] = "REFUTED"
    write_canon_json(ccap_receipt_path, ccap_receipt)
    write_canon_json(verifier_dir / "ccap_receipt_v1.json", ccap_receipt)
    realized_dir = Path(dispatch_ctx["subrun_root_abs"]) / "ccap" / "realized"
    if realized_dir.exists():
        for path in realized_dir.glob("*"):
            path.unlink()
    _patch_meta_core(monkeypatch, tmp_path)
    monkeypatch.setattr("cdel.v18_0.omega_promoter_v1._verify_ccap_apply_matches_receipt", lambda **_: True)

    receipt, _ = run_promotion(
        tick_u64=1,
        dispatch_ctx=dispatch_ctx,
        subverifier_receipt=subverifier,
        allowlists=_allowlists(),
    )
    assert receipt is not None
    assert receipt["execution_mode"] == "BLACKBOX"
    assert receipt["result"]["status"] == "PROMOTED"
    assert receipt["result"]["reason_code"] is None
