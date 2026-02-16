from __future__ import annotations

from pathlib import Path

from cdel.v1_7r.canon import canon_bytes, write_canon_json
from cdel.v18_0.authority.authority_hash_v1 import load_authority_pins
from cdel.v18_0.ccap_runtime_v1 import ccap_payload_id

from tools.genesis_engine.sh1_xs_v1 import build_xs_snapshot, load_ge_config


def _sha(char: str) -> str:
    return f"sha256:{char * 64}"


def _authority_hash(repo_root: Path) -> str:
    import hashlib

    pins = load_authority_pins(repo_root)
    return f"sha256:{hashlib.sha256(canon_bytes(pins)).hexdigest()}"


def _write_run(root: Path, *, run_name: str, marker: str) -> None:
    run_root = root / run_name
    ccap_dir = run_root / "state" / "ccap"
    blobs_dir = ccap_dir / "blobs"
    blobs_dir.mkdir(parents=True, exist_ok=True)

    patch_bytes = (
        "diff --git a/tools/omega/omega_benchmark_suite_v1.py b/tools/omega/omega_benchmark_suite_v1.py\n"
        "--- a/tools/omega/omega_benchmark_suite_v1.py\n"
        "+++ b/tools/omega/omega_benchmark_suite_v1.py\n"
        "@@ -1 +1 @@\n"
        "-# marker\n"
        f"+# marker {marker}\n"
    ).encode("utf-8")

    import hashlib

    patch_blob_id = f"sha256:{hashlib.sha256(patch_bytes).hexdigest()}"
    patch_hex = patch_blob_id.split(":", 1)[1]
    (blobs_dir / f"sha256_{patch_hex}.patch").write_bytes(patch_bytes)

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
        "build": {"build_recipe_id": _sha("7"), "build_targets": [], "artifact_bindings": {}},
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
        "decision": "REJECT",
        "cost_vector": {
            "cpu_ms": 11,
            "wall_ms": 22,
            "mem_mb": 1,
            "disk_mb": 1,
            "fds": 1,
            "procs": 1,
            "threads": 1,
        },
        "logs_hash": _sha("a"),
    }
    write_canon_json(run_root / "state" / "ccap_receipt_v1.json", receipt)


def test_ge_xs_snapshot_deterministic_v1(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    ge_config = load_ge_config(repo_root / "tools" / "genesis_engine" / "config" / "ge_config_v1.json")
    authority_hash = _authority_hash(repo_root)

    root_a = tmp_path / "runs_a"
    root_b = tmp_path / "runs_b"
    _write_run(root_a, run_name="run_x", marker="m1")
    _write_run(root_b, run_name="run_x", marker="m1")

    path_b = root_b / "run_x" / "state" / "ccap_receipt_v1.json"
    path_b.touch()

    snapshot_a, _events_a = build_xs_snapshot(
        recent_runs_root=root_a,
        ge_config=ge_config,
        authority_pins_hash=authority_hash,
    )
    snapshot_b, _events_b = build_xs_snapshot(
        recent_runs_root=root_b,
        ge_config=ge_config,
        authority_pins_hash=authority_hash,
    )

    assert canon_bytes(snapshot_a) == canon_bytes(snapshot_b)
