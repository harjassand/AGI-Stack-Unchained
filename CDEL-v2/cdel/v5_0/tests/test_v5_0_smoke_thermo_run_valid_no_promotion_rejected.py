from __future__ import annotations

import os
import subprocess
import time
import shutil
from pathlib import Path

from cdel.v1_7r.canon import write_canon_json
from cdel.v2_3.immutable_core import load_lock
from cdel.v5_0.constants import meta_identities, require_constants
from cdel.v5_0.thermo_verify_utils import compute_pack_hash
from cdel.v5_0.verify_rsi_thermo_v1 import verify


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _make_pack(*, enabled: bool, max_promos: int, sealed_cfg_rel: str) -> dict:
    repo_root = _repo_root()
    identities = meta_identities()
    constants = require_constants()
    lock = load_lock(repo_root / constants["IMMUTABLE_CORE_LOCK_REL"])

    pack = {
        "pack_version": "rsi_real_thermo_pack_v1",
        "root": {"required_icore_id": lock["core_id"], "required_meta_hash": identities["META_HASH"], "pack_hash": "sha256:" + "0" * 64},
        "suite": {"suite_id": "grand_challenge_heldout_v1", "suite_manifest_path": "@ROOT/campaigns/rsi_real_omega_v4_0/suite_manifest/grand_challenge_suite_manifest_v1.json"},
        "thermo": {
            "sealed_thermo_config_path": "@ROOT/" + sealed_cfg_rel,
            "probe": {"probe_kind": "SOLVE_WINDOW", "window_tasks": 10},
            "constraints": {"thermal_state_abort_at": "critical", "thermal_state_max_for_valid_probe": "serious", "max_probe_wall_seconds": 5},
            "metrics": {"density_ratio_threshold_num": 105, "density_ratio_threshold_den": 100, "consecutive_windows_required": 1, "min_windows_before_ignition_check": 1},
        },
        "run": {"stop_protocol": "EXTERNAL_ONLY", "checkpoint_every_epochs": 1, "checkpoint_every_windows": 1, "ledger_flush_mode": "STREAM_APPEND"},
        "self_improvement": {
            "enabled": enabled,
            "max_promotions_per_checkpoint": max_promos,
            "promotion_kind_allowlist": ["COMPILER_FLAGSET_V1"],
            "dev_gate": {"dev_suite_id": "omega_dev_v1", "min_correctness_delta_passes": 0, "min_density_ratio_num": 105, "min_density_ratio_den": 100},
        },
        "build": {"targets": [{"target_id": "noop_clang", "kind": "CLANG_TARGET", "path": "@ROOT/thermo_targets/noop.c", "baseline_flagset_id": "baseline", "flagsets": []}], "toolchain_capture": {"capture_commands": ["echo"]}},
    }
    pack["root"]["pack_hash"] = compute_pack_hash(pack)
    return pack


def test_smoke_thermo_run_valid_no_promotion_rejected() -> None:
    repo_root = _repo_root()
    run_root = repo_root / "runs" / f"_pytest_thermo_v5_0_{int(time.time()*1000)}"
    pack = _make_pack(enabled=False, max_promos=0, sealed_cfg_rel="CDEL-v2/cdel/v5_0/tests/fixtures/sealed_thermo_fixture_ok.toml")
    pack_path = run_root.with_suffix(".pack.json")
    write_canon_json(pack_path, pack)

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{repo_root / 'Extension-1/agi-orchestrator'}:{repo_root / 'CDEL-v2'}"

    proc = subprocess.Popen([env.get("PYTHON", "python3"), "-m", "orchestrator.rsi_thermo_v5_0", "--thermo_pack", str(pack_path), "--out_dir", str(run_root)], env=env)
    try:
        # Wait for at least one probe receipt then request stop.
        for _ in range(200):
            if (run_root / "thermo" / "probes").exists() and list((run_root / "thermo" / "probes").glob("*.json")):
                break
            time.sleep(0.05)
        (run_root / "thermo").mkdir(parents=True, exist_ok=True)
        (run_root / "thermo" / "STOP").write_text("stop\n", encoding="utf-8")
        proc.wait(timeout=30)
    finally:
        if proc.poll() is None:
            proc.kill()

    receipt = verify(run_root)
    assert receipt["verdict"] == "VALID"
    shutil.rmtree(run_root, ignore_errors=True)
    pack_path.unlink(missing_ok=True)
