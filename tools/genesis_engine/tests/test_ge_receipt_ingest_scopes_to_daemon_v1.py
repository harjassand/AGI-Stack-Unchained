from __future__ import annotations

from pathlib import Path

from tools.genesis_engine import sh1_xs_v1 as xs


def _sha(char: str) -> str:
    return f"sha256:{char * 64}"


def test_ge_collect_matching_paths_scopes_to_daemon_v1(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir()

    run = runs_root / "run_1"
    (run / "daemon" / "x").mkdir(parents=True, exist_ok=True)
    (run / "_worktree" / "y").mkdir(parents=True, exist_ok=True)

    daemon_receipt = run / "daemon" / "x" / "ccap_receipt_v1.json"
    daemon_receipt.write_text("{}", encoding="utf-8")
    worktree_receipt = run / "_worktree" / "y" / "ccap_receipt_v1.json"
    worktree_receipt.write_text("{}", encoding="utf-8")

    paths = xs._collect_matching_paths(
        recent_runs_root=runs_root,
        globs=["**/ccap_receipt_v1.json"],
    )
    assert daemon_receipt in paths
    assert worktree_receipt not in paths


def test_ge_collect_matching_paths_scopes_single_run_v1(tmp_path: Path) -> None:
    run = tmp_path / "run_1"
    (run / "daemon" / "x").mkdir(parents=True, exist_ok=True)
    (run / "_worktree" / "y").mkdir(parents=True, exist_ok=True)

    daemon_receipt = run / "daemon" / "x" / "ccap_receipt_v1.json"
    daemon_receipt.write_text("{}", encoding="utf-8")
    worktree_receipt = run / "_worktree" / "y" / "ccap_receipt_v1.json"
    worktree_receipt.write_text("{}", encoding="utf-8")

    paths = xs._collect_matching_paths(
        recent_runs_root=run,
        globs=["**/ccap_receipt_v1.json"],
    )
    assert daemon_receipt in paths
    assert worktree_receipt not in paths


def test_ge_find_ccap_bundle_scopes_to_daemon_v1(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir()

    run = runs_root / "run_1"
    receipt_dir = run / "daemon" / "state" / "dispatch" / "d1" / "verifier"
    receipt_dir.mkdir(parents=True, exist_ok=True)

    receipt_path = receipt_dir / "ccap_receipt_v1.json"
    receipt_path.write_text("{}", encoding="utf-8")

    ccap_id = _sha("a")
    ccap_hex = ccap_id.split(":", 1)[1]
    daemon_ccap_path = receipt_dir / "ccap" / f"sha256_{ccap_hex}.ccap_v1.json"
    daemon_ccap_path.parent.mkdir(parents=True, exist_ok=True)
    daemon_ccap_path.write_text("{}", encoding="utf-8")

    worktree_ccap_path = run / "_worktree" / f"sha256_{ccap_hex}.ccap_v1.json"
    worktree_ccap_path.parent.mkdir(parents=True, exist_ok=True)
    worktree_ccap_path.write_text("{}", encoding="utf-8")

    picked = xs._find_ccap_bundle_path(
        recent_runs_root=runs_root,
        receipt_path=receipt_path,
        ccap_id=ccap_id,
    )
    assert picked == daemon_ccap_path


def test_ge_find_patch_scopes_to_daemon_v1(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir()

    run = runs_root / "run_1"
    receipt_dir = run / "daemon" / "state" / "dispatch" / "d1" / "verifier"
    receipt_dir.mkdir(parents=True, exist_ok=True)

    ccap_id = _sha("a")
    ccap_hex = ccap_id.split(":", 1)[1]
    ccap_path = receipt_dir / "ccap" / f"sha256_{ccap_hex}.ccap_v1.json"
    ccap_path.parent.mkdir(parents=True, exist_ok=True)
    ccap_path.write_text("{}", encoding="utf-8")

    patch_blob_id = _sha("b")
    patch_hex = patch_blob_id.split(":", 1)[1]
    filename = f"sha256_{patch_hex}.patch"

    daemon_patch = run / "daemon" / "patches" / filename
    daemon_patch.parent.mkdir(parents=True, exist_ok=True)
    daemon_patch.write_text("diff --git a/x b/x\n", encoding="utf-8")

    worktree_patch = run / "_worktree" / "patches" / filename
    worktree_patch.parent.mkdir(parents=True, exist_ok=True)
    worktree_patch.write_text("diff --git a/y b/y\n", encoding="utf-8")

    picked = xs._find_patch_path_for_ccap(
        recent_runs_root=runs_root,
        ccap_path=ccap_path,
        patch_blob_id=patch_blob_id,
    )
    assert picked == daemon_patch

