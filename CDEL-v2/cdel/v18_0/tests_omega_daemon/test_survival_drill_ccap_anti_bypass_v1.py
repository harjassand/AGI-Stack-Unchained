from __future__ import annotations

from pathlib import Path

from cdel.v18_0.ccap_runtime_v1 import ccap_payload_id
from cdel.v18_0.omega_common_v1 import canon_hash_obj, load_canon_dict
from cdel.v18_0.omega_promoter_v1 import run_subverifier
from cdel.v1_7r.canon import write_canon_json


def _ccap_payload(*, patch_blob_hex: str) -> dict:
    return {
        "meta": {
            "ccap_version": 1,
            "base_tree_id": "sha256:" + ("2" * 64),
            "auth_hash": "sha256:" + ("3" * 64),
            "dsbx_profile_id": "sha256:" + ("4" * 64),
            "env_contract_id": "sha256:" + ("5" * 64),
            "toolchain_root_id": "sha256:" + ("6" * 64),
            "ek_id": "sha256:" + ("7" * 64),
            "op_pool_id": "sha256:" + ("8" * 64),
            "canon_version_ids": {
                "ccap_can_v": "sha256:" + ("9" * 64),
                "ir_can_v": "sha256:" + ("a" * 64),
                "op_can_v": "sha256:" + ("b" * 64),
                "obs_can_v": "sha256:" + ("c" * 64),
            },
        },
        "payload": {"kind": "PATCH", "patch_blob_id": f"sha256:{patch_blob_hex}"},
        "build": {"build_recipe_id": "sha256:" + ("e" * 64), "build_targets": [], "artifact_bindings": {}},
        "eval": {"stages": [{"stage_name": "REALIZE"}], "final_suite_id": "sha256:" + ("f" * 64)},
        "budgets": {
            "cpu_ms_max": 1,
            "wall_ms_max": 1,
            "mem_mb_max": 1,
            "disk_mb_max": 1,
            "fds_max": 1,
            "procs_max": 1,
            "threads_max": 1,
            "net": "forbidden",
        },
    }


def _ccap_receipt_payload(ccap_id: str) -> dict:
    return {
        "schema_version": "ccap_receipt_v1",
        "ccap_id": ccap_id,
        "base_tree_id": "sha256:" + ("2" * 64),
        "applied_tree_id": "sha256:" + ("1" * 64),
        "realized_out_id": "sha256:" + ("0" * 64),
        "ek_id": "sha256:" + ("7" * 64),
        "op_pool_id": "sha256:" + ("8" * 64),
        "auth_hash": "sha256:" + ("3" * 64),
        "determinism_check": "PASS",
        "eval_status": "PASS",
        "decision": "PROMOTE",
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


def test_subverifier_ccap_selects_ccap_from_promotion_bundle(tmp_path: Path, monkeypatch) -> None:
    state_root = tmp_path / "state"
    dispatch_dir = state_root / "dispatch" / "a01"
    subrun_root = state_root / "subruns" / "a01_ccap"
    subrun_state = subrun_root / "daemon" / "mock" / "state"
    ccap_dir = subrun_root / "ccap"
    promo_dir = subrun_root / "promotion"
    patch_dir = subrun_root / "ccap" / "blobs"

    dispatch_dir.mkdir(parents=True, exist_ok=True)
    subrun_state.mkdir(parents=True, exist_ok=True)
    ccap_dir.mkdir(parents=True, exist_ok=True)
    promo_dir.mkdir(parents=True, exist_ok=True)
    patch_dir.mkdir(parents=True, exist_ok=True)

    # Two CCAP candidates, lexicographically-first is the "wrong" one for the selected promotion bundle.
    ccap_a = ccap_dir / ("sha256_" + ("1" * 64) + ".ccap_v1.json")
    ccap_b = ccap_dir / ("sha256_" + ("2" * 64) + ".ccap_v1.json")
    write_canon_json(ccap_a, _ccap_payload(patch_blob_hex=("a" * 64)))
    write_canon_json(ccap_b, _ccap_payload(patch_blob_hex=("b" * 64)))

    patch_rel = "ccap/blobs/sha256_" + ("b" * 64) + ".patch"
    (subrun_root / patch_rel).write_bytes(b"patch")

    ccap_rel_b = ccap_b.relative_to(subrun_root).as_posix()
    ccap_id_b = ccap_payload_id(_ccap_payload(patch_blob_hex=("b" * 64)))
    bundle = {
        "schema_version": "omega_promotion_bundle_ccap_v1",
        "ccap_id": ccap_id_b,
        "ccap_relpath": ccap_rel_b,
        "patch_relpath": patch_rel,
        "touched_paths": [ccap_rel_b, patch_rel],
        "activation_key": "ccap_activation_key_v1",
    }
    bundle_hash = canon_hash_obj(bundle)
    bundle_path = promo_dir / f"sha256_{bundle_hash.split(':', 1)[1]}.omega_promotion_bundle_ccap_v1.json"
    write_canon_json(bundle_path, bundle)

    captured: dict[str, object] = {}

    def _fake_run_module(*, py_module: str, argv: list[str], cwd: Path, output_dir: Path, extra_env=None):
        captured["argv"] = list(argv)
        output_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = output_dir / "stdout.log"
        stderr_path = output_dir / "stderr.log"
        stdout_path.write_text("VALID\n", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")

        # Write a receipt matching whichever CCAP the subverifier selected.
        rel = argv[argv.index("--ccap_relpath") + 1]
        ccap_path = (subrun_root / rel).resolve()
        payload = load_canon_dict(ccap_path)
        ccap_id = ccap_payload_id(payload)
        write_canon_json(output_dir / "ccap_receipt_v1.json", _ccap_receipt_payload(ccap_id))

        return {
            "return_code": 0,
            "stdout_path": stdout_path,
            "stderr_path": stderr_path,
            "stdout_hash": "sha256:" + ("1" * 64),
            "stderr_hash": "sha256:" + ("0" * 64),
            "env_fingerprint_hash": "sha256:" + ("2" * 64),
        }

    monkeypatch.setattr("cdel.v18_0.omega_promoter_v1.run_module", _fake_run_module)

    dispatch_ctx = {
        "dispatch_dir": dispatch_dir,
        "state_root": state_root,
        "subrun_state_rel_state": "subruns/a01_ccap/daemon/mock/state",
        "subrun_root_rel_state": "subruns/a01_ccap",
        "campaign_entry": {
            "campaign_id": "mock_ccap_campaign",
            "verifier_module": "cdel.v18_0.verify_ccap_v1",
            "enable_ccap": 1,
            "promotion_bundle_rel": "promotion/sha256_*.omega_promotion_bundle_ccap_v1.json",
        },
        "invocation_env_overrides": {},
        "pythonpath": "",
    }

    receipt, _ = run_subverifier(tick_u64=1, dispatch_ctx=dispatch_ctx)
    assert receipt is not None
    assert receipt["result"]["status"] == "VALID"

    argv = captured["argv"]
    assert argv[argv.index("--ccap_relpath") + 1] == ccap_rel_b


def test_subverifier_ccap_missing_receipt_is_invalid(tmp_path: Path, monkeypatch) -> None:
    state_root = tmp_path / "state"
    dispatch_dir = state_root / "dispatch" / "a01"
    subrun_root = state_root / "subruns" / "a01_ccap"
    subrun_state = subrun_root / "daemon" / "mock" / "state"
    ccap_dir = subrun_root / "ccap"

    dispatch_dir.mkdir(parents=True, exist_ok=True)
    subrun_state.mkdir(parents=True, exist_ok=True)
    ccap_dir.mkdir(parents=True, exist_ok=True)

    ccap_path = ccap_dir / ("sha256_" + ("1" * 64) + ".ccap_v1.json")
    write_canon_json(ccap_path, _ccap_payload(patch_blob_hex=("a" * 64)))

    def _fake_run_module(*, py_module: str, argv: list[str], cwd: Path, output_dir: Path, extra_env=None):
        output_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = output_dir / "stdout.log"
        stderr_path = output_dir / "stderr.log"
        stdout_path.write_text("VALID\n", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        # Intentionally do not write a receipt.
        return {
            "return_code": 0,
            "stdout_path": stdout_path,
            "stderr_path": stderr_path,
            "stdout_hash": "sha256:" + ("1" * 64),
            "stderr_hash": "sha256:" + ("0" * 64),
            "env_fingerprint_hash": "sha256:" + ("2" * 64),
        }

    monkeypatch.setattr("cdel.v18_0.omega_promoter_v1.run_module", _fake_run_module)
    monkeypatch.setattr("cdel.v18_0.verify_ccap_v1.verify", lambda **_: None)

    dispatch_ctx = {
        "dispatch_dir": dispatch_dir,
        "state_root": state_root,
        "subrun_state_rel_state": "subruns/a01_ccap/daemon/mock/state",
        "subrun_root_rel_state": "subruns/a01_ccap",
        "campaign_entry": {
            "campaign_id": "mock_ccap_campaign",
            "verifier_module": "cdel.v18_0.verify_ccap_v1",
            "enable_ccap": 1,
        },
        "invocation_env_overrides": {},
        "pythonpath": "",
    }

    receipt, _ = run_subverifier(tick_u64=1, dispatch_ctx=dispatch_ctx)
    assert receipt is not None
    assert receipt["result"]["status"] == "INVALID"


def test_subverifier_ccap_corrupt_receipt_is_invalid(tmp_path: Path, monkeypatch) -> None:
    state_root = tmp_path / "state"
    dispatch_dir = state_root / "dispatch" / "a01"
    subrun_root = state_root / "subruns" / "a01_ccap"
    subrun_state = subrun_root / "daemon" / "mock" / "state"
    ccap_dir = subrun_root / "ccap"

    dispatch_dir.mkdir(parents=True, exist_ok=True)
    subrun_state.mkdir(parents=True, exist_ok=True)
    ccap_dir.mkdir(parents=True, exist_ok=True)

    ccap_path = ccap_dir / ("sha256_" + ("1" * 64) + ".ccap_v1.json")
    write_canon_json(ccap_path, _ccap_payload(patch_blob_hex=("a" * 64)))

    def _fake_run_module(*, py_module: str, argv: list[str], cwd: Path, output_dir: Path, extra_env=None):
        output_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = output_dir / "stdout.log"
        stderr_path = output_dir / "stderr.log"
        stdout_path.write_text("VALID\n", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        (output_dir / "ccap_receipt_v1.json").write_text("{", encoding="utf-8")
        return {
            "return_code": 0,
            "stdout_path": stdout_path,
            "stderr_path": stderr_path,
            "stdout_hash": "sha256:" + ("1" * 64),
            "stderr_hash": "sha256:" + ("0" * 64),
            "env_fingerprint_hash": "sha256:" + ("2" * 64),
        }

    monkeypatch.setattr("cdel.v18_0.omega_promoter_v1.run_module", _fake_run_module)

    dispatch_ctx = {
        "dispatch_dir": dispatch_dir,
        "state_root": state_root,
        "subrun_state_rel_state": "subruns/a01_ccap/daemon/mock/state",
        "subrun_root_rel_state": "subruns/a01_ccap",
        "campaign_entry": {
            "campaign_id": "mock_ccap_campaign",
            "verifier_module": "cdel.v18_0.verify_ccap_v1",
            "enable_ccap": 1,
        },
        "invocation_env_overrides": {},
        "pythonpath": "",
    }

    receipt, _ = run_subverifier(tick_u64=1, dispatch_ctx=dispatch_ctx)
    assert receipt is not None
    assert receipt["result"]["status"] == "INVALID"
