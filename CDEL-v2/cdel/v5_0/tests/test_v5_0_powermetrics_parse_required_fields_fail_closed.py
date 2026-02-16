from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest

from cdel.v1_7r.canon import canon_bytes, sha256_prefixed, write_canon_json, write_jsonl_line
from cdel.v2_3.immutable_core import load_lock
from cdel.v5_0.constants import meta_identities, require_constants
from cdel.v5_0.thermo_verify_utils import compute_pack_hash, compute_receipt_hash, sha256_file_prefixed
from cdel.v5_0.verify_rsi_thermo_v1 import verify


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def test_powermetrics_parse_required_fields_fail_closed() -> None:
    repo_root = _repo_root()
    run_root = repo_root / "runs" / f"_pytest_thermo_v5_0_parsefail_{int(time.time()*1000)}"
    try:
        (run_root / "thermo" / "env").mkdir(parents=True, exist_ok=True)
        (run_root / "thermo" / "probes" / "raw").mkdir(parents=True, exist_ok=True)

        identities = meta_identities()
        constants = require_constants()
        lock = load_lock(repo_root / constants["IMMUTABLE_CORE_LOCK_REL"])

        pack = {
            "pack_version": "rsi_real_thermo_pack_v1",
            "root": {"required_icore_id": lock["core_id"], "required_meta_hash": identities["META_HASH"], "pack_hash": "sha256:" + "0" * 64},
            "suite": {"suite_id": "x", "suite_manifest_path": "@ROOT/x.json"},
            "thermo": {"sealed_thermo_config_path": "@ROOT/x.toml", "probe": {"probe_kind": "SOLVE_WINDOW", "window_tasks": 1}, "constraints": {"thermal_state_abort_at": "critical", "thermal_state_max_for_valid_probe": "serious", "max_probe_wall_seconds": 1}, "metrics": {"density_ratio_threshold_num": 105, "density_ratio_threshold_den": 100, "consecutive_windows_required": 1, "min_windows_before_ignition_check": 1}},
            "run": {"stop_protocol": "EXTERNAL_ONLY", "checkpoint_every_epochs": 1, "checkpoint_every_windows": 1, "ledger_flush_mode": "STREAM_APPEND"},
            "self_improvement": {"enabled": False, "max_promotions_per_checkpoint": 0, "promotion_kind_allowlist": ["COMPILER_FLAGSET_V1"], "dev_gate": {"dev_suite_id": "x", "min_correctness_delta_passes": 0, "min_density_ratio_num": 105, "min_density_ratio_den": 100}},
            "build": {"targets": [{"target_id": "t", "kind": "CLANG_TARGET", "path": "@ROOT/x.c", "baseline_flagset_id": "b", "flagsets": []}], "toolchain_capture": {"capture_commands": ["echo"]}},
        }
        pack["root"]["pack_hash"] = compute_pack_hash(pack)
        write_canon_json(run_root / "rsi_real_thermo_pack_v1.json", pack)

        manifest = {
            "created_utc": "x",
            "host": {"hostname": "h", "hw_model": "m", "arch": "arm64", "os_product_version": "x", "os_build_version": "y"},
            "toolchain": {"python_version": "x", "clang_version": "x", "rustc_version": None, "xcodebuild_version": None},
            "measurement": {"powermetrics_path": "/usr/bin/powermetrics", "powermetrics_help_hash": "sha256:" + "0" * 64},
        }
        manifest_path = run_root / "thermo" / "env" / "toolchain_manifest_v1.json"
        write_canon_json(manifest_path, manifest)
        manifest_hash = sha256_prefixed(canon_bytes(manifest))

        pm_path = run_root / "thermo" / "probes" / "raw" / "sha256_bad.powermetrics.txt"
        pm_path.write_text("no combined power line\n", encoding="utf-8")
        th_path = run_root / "thermo" / "probes" / "raw" / "sha256_ok.thermalstate.log"
        th_path.write_text("fair\n", encoding="utf-8")

        receipt = {
            "schema": "thermo_probe_receipt_v1",
            "spec_version": "v5_0",
            "receipt_hash": "",
            "probe_kind": "SOLVE_WINDOW",
            "probe_status": "INVALID_PARSE",
            "powermetrics_raw_path": "@ROOT/thermo/probes/raw/" + pm_path.name,
            "powermetrics_raw_hash": sha256_file_prefixed(pm_path),
            "thermal_log_raw_path": "@ROOT/thermo/probes/raw/" + th_path.name,
            "thermal_log_raw_hash": sha256_file_prefixed(th_path),
            "sample_interval_ms": 1000,
            "sample_count": 1,
            "mean_combined_power_mW": 0,
            "wall_time_s": 1,
            "energy_mJ": 0,
            "passes": 0,
        }
        receipt["receipt_hash"] = compute_receipt_hash(receipt)
        receipt_path = run_root / "thermo" / "probes" / f"sha256_{receipt['receipt_hash'].split(':', 1)[1]}.thermo_probe_receipt_v1.json"
        (run_root / "thermo" / "probes").mkdir(parents=True, exist_ok=True)
        write_canon_json(receipt_path, receipt)

        # Create STOP file so the stop provenance check passes.
        stop_file = run_root / "thermo" / "STOP"
        stop_file.write_text("stop\n", encoding="utf-8")

        ledger = run_root / "thermo" / "thermo_ledger_v1.jsonl"
        ledger.write_text("", encoding="utf-8")
        prev = "GENESIS"

        def append(event_type: str, payload: dict) -> str:
            nonlocal prev
            event = {"schema": "thermo_ledger_event_v1", "spec_version": "v5_0", "event_ref_hash": "", "prev_event_ref_hash": prev, "event_type": event_type, "payload": payload}
            from cdel.v5_0.thermo_ledger import compute_event_ref_hash

            event["event_ref_hash"] = compute_event_ref_hash(event)
            write_jsonl_line(ledger, event)
            prev = event["event_ref_hash"]
            return prev

        append("THERMO_ENV_SNAPSHOT", {"toolchain_manifest_path": "@ROOT/thermo/env/toolchain_manifest_v1.json", "toolchain_manifest_hash": manifest_hash})
        append("THERMO_PROBE_END", {"probe_receipt_path": "@ROOT/thermo/probes/" + receipt_path.name, "probe_receipt_hash": receipt["receipt_hash"], "probe_status": "INVALID_PARSE"})
        append("THERMO_STOP", {"stop_kind": "EXTERNAL_SIGNAL", "stop_provenance_path": "@ROOT/thermo/STOP", "stop_provenance_hash": sha256_file_prefixed(stop_file)})

        with pytest.raises(Exception) as excinfo:
            verify(run_root)
        assert "THERMO_POWER_PARSE_MISSING_FATAL" in str(excinfo.value)
    finally:
        shutil.rmtree(run_root, ignore_errors=True)

