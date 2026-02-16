from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from cdel.v1_7r.canon import load_canon_json, write_canon_json
from cdel.v18_0.ccap_runtime_v1 import ccap_payload_id


def _sha(char: str) -> str:
    return f"sha256:{char * 64}"


def _write_fixture_receipt_run(runs_root: Path) -> None:
    run_root = runs_root / "fixture_run_a"
    ccap_dir = run_root / "state" / "ccap"
    blobs_dir = ccap_dir / "blobs"
    blobs_dir.mkdir(parents=True, exist_ok=True)

    patch_bytes = (
        "diff --git a/tools/omega/omega_benchmark_suite_v1.py b/tools/omega/omega_benchmark_suite_v1.py\n"
        "--- a/tools/omega/omega_benchmark_suite_v1.py\n"
        "+++ b/tools/omega/omega_benchmark_suite_v1.py\n"
        "@@ -1 +1 @@\n"
        "-# marker\n"
        "+# marker fixture\n"
    ).encode("utf-8")

    import hashlib

    patch_blob_id = f"sha256:{hashlib.sha256(patch_bytes).hexdigest()}"
    patch_hex = patch_blob_id.split(":", 1)[1]
    patch_path = blobs_dir / f"sha256_{patch_hex}.patch"
    patch_path.write_bytes(patch_bytes)

    ccap_obj = {
        "meta": {
            "ccap_version": 1,
            "base_tree_id": _sha("a"),
            "auth_hash": _sha("b"),
            "dsbx_profile_id": _sha("c"),
            "env_contract_id": _sha("d"),
            "toolchain_root_id": _sha("e"),
            "ek_id": _sha("1"),
            "op_pool_id": _sha("2"),
            "canon_version_ids": {
                "ccap_can_v": _sha("3"),
                "ir_can_v": _sha("4"),
                "op_can_v": _sha("5"),
                "obs_can_v": _sha("6"),
            },
        },
        "payload": {"kind": "PATCH", "patch_blob_id": patch_blob_id},
        "build": {
            "build_recipe_id": _sha("7"),
            "build_targets": [],
            "artifact_bindings": {},
        },
        "eval": {"stages": [], "final_suite_id": _sha("8")},
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
    ccap_id = ccap_payload_id(ccap_obj)
    ccap_hex = ccap_id.split(":", 1)[1]
    write_canon_json(ccap_dir / f"sha256_{ccap_hex}.ccap_v1.json", ccap_obj)

    receipt = {
        "schema_version": "ccap_receipt_v1",
        "ccap_id": ccap_id,
        "base_tree_id": _sha("a"),
        "applied_tree_id": _sha("9"),
        "realized_out_id": _sha("0"),
        "ek_id": _sha("1"),
        "op_pool_id": _sha("2"),
        "auth_hash": _sha("b"),
        "determinism_check": "PASS",
        "eval_status": "PASS",
        "decision": "PROMOTE",
        "cost_vector": {
            "cpu_ms": 10,
            "wall_ms": 20,
            "mem_mb": 1,
            "disk_mb": 1,
            "fds": 1,
            "procs": 1,
            "threads": 1,
        },
        "logs_hash": _sha("a"),
    }
    write_canon_json(run_root / "state" / "ccap_receipt_v1.json", receipt)


def test_ge_symbiotic_optimizer_v0_3_deterministic(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    runs_root = tmp_path / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    _write_fixture_receipt_run(runs_root)

    tool = repo_root / "tools" / "genesis_engine" / "ge_symbiotic_optimizer_v0_3.py"
    ge_config_path = repo_root / "tools" / "genesis_engine" / "config" / "ge_config_v1.json"
    authority_path = repo_root / "authority" / "authority_pins_v1.json"

    def _run(out_dir: Path) -> dict[str, object]:
        cmd = [
            sys.executable,
            str(tool),
            "--subrun_out_dir",
            str(out_dir),
            "--ge_config_path",
            str(ge_config_path),
            "--authority_pins_path",
            str(authority_path),
            "--recent_runs_root",
            str(runs_root),
            "--seed",
            "7",
            "--model_id",
            "ge-v0_3-test",
            "--max_ccaps",
            "1",
        ]
        result = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"
    run_a = _run(out_a)
    run_b = _run(out_b)

    assert run_a["status"] == "OK"
    assert run_a["inputs_hash"] == run_b["inputs_hash"]

    fp_a = load_canon_json(out_a / "ge_run_inputs_fingerprint_v2.json")
    fp_b = load_canon_json(out_b / "ge_run_inputs_fingerprint_v2.json")
    assert fp_a == fp_b

    assert (out_a / "ge_xs_snapshot_v1.json").read_bytes() == (out_b / "ge_xs_snapshot_v1.json").read_bytes()

    summary_a = load_canon_json(out_a / "ge_symbiotic_optimizer_summary_v0_3.json")
    summary_b = load_canon_json(out_b / "ge_symbiotic_optimizer_summary_v0_3.json")
    assert summary_a == summary_b

    ccap_rel = str(summary_a["ccaps"][0]["ccap_relpath"])
    patch_rel = str(summary_a["ccaps"][0]["patch_relpath"])
    assert (out_a / ccap_rel).read_bytes() == (out_b / ccap_rel).read_bytes()
    assert (out_a / patch_rel).read_bytes() == (out_b / patch_rel).read_bytes()
