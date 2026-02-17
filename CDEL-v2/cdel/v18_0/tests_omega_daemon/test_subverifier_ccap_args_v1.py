from __future__ import annotations

from pathlib import Path

from cdel.v18_0.omega_promoter_v1 import run_subverifier
from cdel.v1_7r.canon import write_canon_json


def test_ccap_subverifier_receives_ccap_specific_args(tmp_path: Path, monkeypatch) -> None:
    state_root = tmp_path / "state"
    dispatch_dir = state_root / "dispatch" / "a01"
    subrun_root = state_root / "subruns" / "a01_ccap"
    subrun_state = subrun_root / "daemon" / "mock" / "state"
    ccap_dir = subrun_root / "ccap"

    dispatch_dir.mkdir(parents=True, exist_ok=True)
    subrun_state.mkdir(parents=True, exist_ok=True)
    ccap_dir.mkdir(parents=True, exist_ok=True)

    ccap_path = ccap_dir / ("sha256_" + ("1" * 64) + ".ccap_v1.json")
    write_canon_json(
        ccap_path,
        {
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
            "payload": {"kind": "PATCH", "patch_blob_id": "sha256:" + ("d" * 64)},
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
        },
    )

    captured: dict[str, object] = {}

    def _fake_run_module(*, py_module: str, argv: list[str], cwd: Path, output_dir: Path, extra_env=None):
        captured["py_module"] = py_module
        captured["argv"] = list(argv)
        output_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = output_dir / "stdout.log"
        stderr_path = output_dir / "stderr.log"
        stdout_path.write_text("VALID\n", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
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
    assert receipt["result"]["status"] == "VALID"
    assert captured["py_module"] == "cdel.v18_0.verify_ccap_v1"
    argv = captured["argv"]
    assert "--subrun_root" in argv
    assert "--receipt_out_dir" in argv
    assert "--ccap_relpath" in argv
    assert "--enable_ccap" in argv
    assert argv[argv.index("--enable_ccap") + 1] == "1"


def test_ccap_subverifier_defaults_enable_ccap_to_zero(tmp_path: Path, monkeypatch) -> None:
    state_root = tmp_path / "state"
    dispatch_dir = state_root / "dispatch" / "a01"
    subrun_root = state_root / "subruns" / "a01_ccap"
    subrun_state = subrun_root / "daemon" / "mock" / "state"
    ccap_dir = subrun_root / "ccap"

    dispatch_dir.mkdir(parents=True, exist_ok=True)
    subrun_state.mkdir(parents=True, exist_ok=True)
    ccap_dir.mkdir(parents=True, exist_ok=True)

    ccap_path = ccap_dir / ("sha256_" + ("1" * 64) + ".ccap_v1.json")
    write_canon_json(
        ccap_path,
        {
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
            "payload": {"kind": "PATCH", "patch_blob_id": "sha256:" + ("d" * 64)},
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
        },
    )

    captured: dict[str, object] = {}

    def _fake_run_module(*, py_module: str, argv: list[str], cwd: Path, output_dir: Path, extra_env=None):
        captured["py_module"] = py_module
        captured["argv"] = list(argv)
        output_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = output_dir / "stdout.log"
        stderr_path = output_dir / "stderr.log"
        stdout_path.write_text("VALID\n", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
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
        },
        "invocation_env_overrides": {},
        "pythonpath": "",
    }

    receipt, _ = run_subverifier(tick_u64=1, dispatch_ctx=dispatch_ctx)

    assert receipt is not None
    assert receipt["result"]["status"] == "VALID"
    assert captured["py_module"] == "cdel.v18_0.verify_ccap_v1"
    argv = captured["argv"]
    assert "--enable_ccap" in argv
    assert argv[argv.index("--enable_ccap") + 1] == "0"


def test_ccap_subverifier_uses_promotion_bundle_ccap_relpath_when_multiple_candidates(
    tmp_path: Path, monkeypatch
) -> None:
    state_root = tmp_path / "state"
    dispatch_dir = state_root / "dispatch" / "a01"
    subrun_root = state_root / "subruns" / "a01_ccap"
    subrun_state = subrun_root / "daemon" / "mock" / "state"
    ccap_dir = subrun_root / "ccap"
    promo_dir = subrun_root / "promotion"

    dispatch_dir.mkdir(parents=True, exist_ok=True)
    subrun_state.mkdir(parents=True, exist_ok=True)
    ccap_dir.mkdir(parents=True, exist_ok=True)
    promo_dir.mkdir(parents=True, exist_ok=True)

    def _ccap_payload(*, base_tree_id: str) -> dict:
        return {
            "meta": {
                "ccap_version": 1,
                "base_tree_id": base_tree_id,
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
            "payload": {"kind": "PATCH", "patch_blob_id": "sha256:" + ("d" * 64)},
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

    # Lexicographically-first CCAP candidate (should be ignored when a promotion
    # bundle declares a different CCAP relpath).
    ccap_first = ccap_dir / ("sha256_" + ("1" * 64) + ".ccap_v1.json")
    write_canon_json(ccap_first, _ccap_payload(base_tree_id="sha256:" + ("2" * 64)))

    # Promotion bundle should steer subverifier toward this candidate instead.
    ccap_bundle = ccap_dir / ("sha256_" + ("a" * 64) + ".ccap_v1.json")
    write_canon_json(ccap_bundle, _ccap_payload(base_tree_id="sha256:" + ("0" * 64)))

    promo_bundle = promo_dir / ("sha256_" + ("0" * 64) + ".omega_promotion_bundle_ccap_v1.json")
    write_canon_json(
        promo_bundle,
        {
            "schema_version": "omega_promotion_bundle_ccap_v1",
            "ccap_relpath": ccap_bundle.relative_to(subrun_root).as_posix(),
        },
    )

    captured: dict[str, object] = {}

    def _fake_run_module(*, py_module: str, argv: list[str], cwd: Path, output_dir: Path, extra_env=None):
        captured["py_module"] = py_module
        captured["argv"] = list(argv)
        output_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = output_dir / "stdout.log"
        stderr_path = output_dir / "stderr.log"
        stdout_path.write_text("VALID\n", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
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
        "subrun_root_abs": subrun_root,
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
    assert captured["py_module"] == "cdel.v18_0.verify_ccap_v1"
    argv = captured["argv"]
    assert "--ccap_relpath" in argv
    assert argv[argv.index("--ccap_relpath") + 1] == ccap_bundle.relative_to(subrun_root).as_posix()
