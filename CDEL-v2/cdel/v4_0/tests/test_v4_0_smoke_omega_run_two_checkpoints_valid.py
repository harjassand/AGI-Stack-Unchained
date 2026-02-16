from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from cdel.v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json
from cdel.v2_3.immutable_core import load_lock, validate_lock
from cdel.v4_0.constants import meta_identities
from cdel.v4_0.verify_rsi_omega_v1 import verify


def _write_test_pack(tmp_path: Path, repo_root: Path) -> Path:
    lock_path = repo_root / "meta-core" / "meta_constitution" / "v4_0" / "immutable_core_lock_v1.json"
    lock = load_lock(lock_path)
    validate_lock(lock)
    meta_hash = meta_identities()["META_HASH"]

    baseline_path = repo_root / "baselines" / "pi0_grand_challenge_v1" / "baseline_report_v1.json"
    baseline = load_canon_json(baseline_path)
    baseline_hash = sha256_prefixed(canon_bytes(baseline))

    suite_manifest_path = repo_root / "campaigns" / "rsi_real_omega_v4_0" / "suite_manifest" / "grand_challenge_suite_manifest_v1.json"

    pack = {
        "schema": "rsi_real_omega_pack_v1",
        "spec_version": "v4_0",
        "pack_hash": "",
        "root": {
            "required_icore_id": lock["core_id"],
            "required_meta_hash": meta_hash,
        },
        "swarm": {
            "protocol_version": "v3_3",
            "commit_policy": "ROUND_COMMIT_V4_OMEGA",
            "authority": {"min_nodes": 1, "max_depth": 0},
            "meta": {"enabled": True, "consensus_policy": "HOLO_CONSENSUS_V1", "exchange_root_path": "@ROOT/meta_exchange"},
        },
        "omega": {
            "enabled": True,
            "unbounded_epochs": True,
            "tasks_per_epoch": 1,
            "task_sampling": {"policy": "SHUFFLE_CYCLE_V1", "seed": "sha256:" + "0" * 64, "allow_repeats": True},
            "checkpoint": {"every_epochs": 1, "write_receipt": True},
            "suite": {"suite_manifest_path": str(suite_manifest_path)},
            "baseline": {
                "baseline_id": baseline["baseline_id"],
                "baseline_report_path": str(baseline_path),
                "baseline_report_hash": baseline_hash,
            },
            "self_improvement": {
                "enabled": False,
                "proposal_systems": {
                    "autonomy_v2": False,
                    "recursive_ontology_v2_1": False,
                    "csi_v2_2": False,
                    "hardening_v2_3": False,
                },
                "promotion_policy": "PROMOTE_ONLY_IF_DEV_IMPROVES_V1",
                "dev_gate": {"sealed_config_path": str(repo_root / "CDEL-v2" / "configs" / "sealed_env_dev.toml"), "min_delta_score_num": 0, "min_delta_score_den": 1},
                "max_promotions_per_checkpoint": 0,
                "max_patch_bytes": 0,
                "max_patch_files_touched": 0,
            },
            "success_criteria": {
                "min_new_solves_over_baseline": 0,
                "rolling_window": {"window_tasks": 1, "min_windows": 1},
                "min_passrate_gain_num": 0,
                "min_passrate_gain_den": 1,
                "acceleration": {"metric": "ACCEL_INDEX_V1", "min_accel_ratio_num": 0, "min_accel_ratio_den": 1, "min_consecutive_windows": 1},
            },
            "stop_conditions": [{"kind": "MAX_CHECKPOINTS", "max_checkpoints": 2}],
        },
    }
    pack["pack_hash"] = sha256_prefixed(canon_bytes({k: v for k, v in pack.items() if k != "pack_hash"}))
    pack_path = tmp_path / "omega_pack.json"
    write_canon_json(pack_path, pack)
    return pack_path


def test_v4_0_smoke_omega_run_two_checkpoints_valid(tmp_path: Path, repo_root: Path) -> None:
    pack_path = _write_test_pack(tmp_path, repo_root)
    out_dir = tmp_path / "run"

    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(repo_root / "Extension-1" / "agi-orchestrator"), str(repo_root / "CDEL-v2")])

    subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator.rsi_omega_v4_0",
            "--omega_pack",
            str(pack_path),
            "--out_dir",
            str(out_dir),
        ],
        check=True,
        env=env,
        cwd=str(repo_root),
    )

    receipt = verify(out_dir)
    assert receipt["verdict"] == "VALID"
    assert receipt["checkpoints_written"] >= 2
