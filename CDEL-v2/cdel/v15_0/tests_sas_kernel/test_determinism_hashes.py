from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from cdel.v1_7r.canon import load_canon_json, write_canon_json

from .utils import repo_root


def test_determinism_hashes(tmp_path: Path) -> None:
    root = repo_root()
    kernel_bin = root / "CDEL-v2" / "cdel" / "v15_0" / "rust" / "agi_kernel_rs_v1" / "target" / "release" / "agi_kernel_v15"
    if not kernel_bin.exists():
        subprocess.run(
            ["cargo", "build", "--release", "--locked", "--offline"],
            cwd=root / "CDEL-v2" / "cdel" / "v15_0" / "rust" / "agi_kernel_rs_v1",
            check=True,
        )

    run1 = tmp_path / "run1"
    run2 = tmp_path / "run2"
    run1_rel = str(run1.relative_to(root)) if str(run1).startswith(str(root)) else "runs/_pytest_v15_run1"
    run2_rel = str(run2.relative_to(root)) if str(run2).startswith(str(root)) else "runs/_pytest_v15_run2"
    if not str(run1).startswith(str(root)):
        run1 = root / run1_rel
        run2 = root / run2_rel

    spec = {
        "schema_version": "kernel_run_spec_v1",
        "run_id": "pytest_det",
        "seed_u64": 7,
        "capability_id": "RSI_SAS_SYSTEM_V14_0",
        "capability_registry_rel": "campaigns/rsi_sas_kernel_v15_0/capability_registry_v2.json",
        "paths": {"repo_root_rel": ".", "daemon_root_rel": "daemon", "out_dir_rel": run1_rel},
        "sealed": {
            "sealed_config_toml_rel": "Extension-1/agi-orchestrator/configs/sealed_io_dev.toml",
            "mount_policy_id": "MOUNT_POLICY_V1",
        },
        "toolchains": {
            "kernel_manifest_rel": "campaigns/rsi_sas_kernel_v15_0/toolchain_manifest_kernel_v1.json",
            "py_manifest_rel": "campaigns/rsi_sas_kernel_v15_0/toolchain_manifest_py_v1.json",
            "rust_manifest_rel": "campaigns/rsi_sas_kernel_v15_0/toolchain_manifest_rust_v1.json",
            "lean_manifest_rel": "campaigns/rsi_sas_kernel_v15_0/toolchain_manifest_lean_v1.json",
        },
        "kernel_policy_rel": "campaigns/rsi_sas_kernel_v15_0/sas_kernel_policy_v1.json",
    }

    spec1 = tmp_path / "run1.kernel_run_spec_v1.json"
    spec2 = tmp_path / "run2.kernel_run_spec_v1.json"
    write_canon_json(spec1, spec)
    spec2_obj = dict(spec)
    spec2_obj["paths"] = dict(spec["paths"])
    spec2_obj["paths"]["out_dir_rel"] = run2_rel
    write_canon_json(spec2, spec2_obj)

    for out in [run1, run2]:
        if out.exists():
            shutil.rmtree(out)

    subprocess.run([str(kernel_bin), "run", "--run_spec", str(spec1)], cwd=root, check=True)
    subprocess.run([str(kernel_bin), "run", "--run_spec", str(spec2)], cwd=root, check=True)

    r1 = load_canon_json(run1 / "kernel" / "receipts" / "kernel_run_receipt_v1.json")
    r2 = load_canon_json(run2 / "kernel" / "receipts" / "kernel_run_receipt_v1.json")
    assert r1["ledger_head_hash"] == r2["ledger_head_hash"]
    assert r1["trace_head_hash"] == r2["trace_head_hash"]
    assert r1["snapshot_root_hash"] == r2["snapshot_root_hash"]
    assert r1["receipt_hash"] == r2["receipt_hash"]
