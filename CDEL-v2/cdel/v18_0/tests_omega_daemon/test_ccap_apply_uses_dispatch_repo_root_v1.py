from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from cdel.v18_0.ccap_runtime_v1 import (
    apply_patch_bytes,
    ccap_payload_id,
    compute_repo_base_tree_id,
    compute_workspace_tree_id,
    materialize_repo_snapshot,
)
from cdel.v18_0.omega_promoter_v1 import _verify_ccap_apply_matches_receipt
from cdel.v1_7r.canon import write_canon_json


def _git(cwd: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)


def _init_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    run = _git(root, ["init", "-q"])
    assert int(run.returncode) == 0, run.stderr
    _git(root, ["config", "user.email", "test@example.com"])
    _git(root, ["config", "user.name", "Test User"])


def _commit_file(root: Path, rel: str, content: str, msg: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    run = _git(root, ["add", rel])
    assert int(run.returncode) == 0, run.stderr
    run = _git(root, ["commit", "-q", "-m", msg])
    assert int(run.returncode) == 0, run.stderr


def _diff_patch_bytes(root: Path) -> bytes:
    run = _git(root, ["diff"])
    assert int(run.returncode) == 0, run.stderr
    return run.stdout.encode("utf-8")


def test_ccap_apply_replay_uses_repo_root_from_dispatch_ctx(tmp_path: Path, monkeypatch) -> None:
    # Build an "expected" git repo with a patch that applies cleanly.
    expected_repo = tmp_path / "expected_repo"
    _init_repo(expected_repo)
    _commit_file(expected_repo, "foo.txt", "hello\n", msg="init")

    (expected_repo / "foo.txt").write_text("hello world\n", encoding="utf-8")
    patch_bytes = _diff_patch_bytes(expected_repo)
    assert patch_bytes

    # Restore repo to the base tree that the patch targets.
    run = _git(expected_repo, ["checkout", "-q", "--", "foo.txt"])
    assert int(run.returncode) == 0, run.stderr

    base_tree_id = compute_repo_base_tree_id(expected_repo)
    with_tmp = tmp_path / "applied_workspace"
    materialize_repo_snapshot(expected_repo, with_tmp)
    apply_patch_bytes(workspace_root=with_tmp, patch_bytes=patch_bytes)
    applied_tree_id = compute_workspace_tree_id(with_tmp)

    patch_blob_id = f"sha256:{hashlib.sha256(patch_bytes).hexdigest()}"
    ccap_payload = {
        "meta": {
            "ccap_version": 1,
            "base_tree_id": base_tree_id,
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
            "patch_blob_id": patch_blob_id,
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
    ccap_id = ccap_payload_id(ccap_payload)

    subrun_root = tmp_path / "subrun_root"
    ccap_rel = "ccap/sha256_" + ccap_id.split(":", 1)[1] + ".ccap_v1.json"
    patch_rel = "ccap/blobs/sha256_" + patch_blob_id.split(":", 1)[1] + ".patch"
    (subrun_root / Path(patch_rel).parent).mkdir(parents=True, exist_ok=True)
    (subrun_root / patch_rel).write_bytes(patch_bytes)
    write_canon_json(subrun_root / ccap_rel, ccap_payload)

    receipt = {
        "schema_version": "ccap_receipt_v1",
        "ccap_id": ccap_id,
        "base_tree_id": base_tree_id,
        "applied_tree_id": applied_tree_id,
        "realized_out_id": "sha256:" + ("f" * 64),
        "ek_id": str(ccap_payload["meta"]["ek_id"]),
        "op_pool_id": str(ccap_payload["meta"]["op_pool_id"]),
        "auth_hash": str(ccap_payload["meta"]["auth_hash"]),
        "determinism_check": "PASS",
        "eval_status": "PASS",
        "decision": "PROMOTE",
        "cost_vector": {"cpu_ms": 1, "wall_ms": 1, "mem_mb": 1, "disk_mb": 1, "fds": 1, "procs": 0, "threads": 0},
        "logs_hash": "sha256:" + ("0" * 64),
    }

    bundle_obj = {
        "schema_version": "omega_promotion_bundle_ccap_v1",
        "ccap_id": ccap_id,
        "ccap_relpath": ccap_rel,
        "patch_relpath": patch_rel,
        "touched_paths": [ccap_rel, patch_rel],
        "activation_key": "ccap_activation_key_v1",
    }

    # Provide a different repo root via repo_root() to prove the replay uses dispatch_ctx.
    wrong_repo = tmp_path / "wrong_repo"
    _init_repo(wrong_repo)
    _commit_file(wrong_repo, "foo.txt", "not the same\n", msg="init")
    monkeypatch.setattr("cdel.v18_0.omega_promoter_v1.repo_root", lambda: wrong_repo)

    dispatch_ctx = {
        "subrun_root_abs": subrun_root,
        "repo_root_abs": expected_repo,
    }
    out_dir = tmp_path / "out"

    ok = _verify_ccap_apply_matches_receipt(
        bundle_obj=bundle_obj,
        receipt=receipt,
        dispatch_ctx=dispatch_ctx,
        out_dir=out_dir,
        require_receipt_applied_tree=True,
    )
    assert ok is True
    assert out_dir.exists()
