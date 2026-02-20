from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v19_0.shadow_fs_guard_v1 import (
    default_shadow_protected_roots_profile,
    diff_file_maps,
    hash_protected_roots,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _bootstrap_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    _write(repo / "authority" / "pins.json", "{}")
    _write(repo / "meta-core" / "engine" / "activation.py", "x = 1\n")
    _write(repo / "CDEL-v2" / "cdel" / "v19_0" / "module.py", "x = 1\n")
    _write(repo / "Genesis" / "schema" / "v19_0" / "a.json", "{}\n")
    _write(repo / "runs" / "r1" / "artifact.json", "{}\n")
    _write(repo / "daemon" / "rsi_omega_daemon_v19_0" / "state" / "s.json", "{}\n")
    _write(repo / "daemon" / "other" / "state" / "x.json", "{}\n")
    return repo


def test_protected_scope_ignores_runs_changes(tmp_path: Path) -> None:
    repo = _bootstrap_repo(tmp_path)
    profile = default_shadow_protected_roots_profile()

    pre = hash_protected_roots(
        repo_root=repo,
        roots=profile["static_protected_roots"],
        excluded_roots=profile["excluded_roots"],
        hash_budget_spec=profile["hash_budget_spec"],
        symlink_policy=profile["symlink_policy"],
    )
    _write(repo / "runs" / "r1" / "artifact.json", '{"changed":true}\n')
    post = hash_protected_roots(
        repo_root=repo,
        roots=profile["static_protected_roots"],
        excluded_roots=profile["excluded_roots"],
        hash_budget_spec=profile["hash_budget_spec"],
        symlink_policy=profile["symlink_policy"],
    )
    assert diff_file_maps(pre["file_hashes"], post["file_hashes"]) == []


def test_dynamic_root_is_precise(tmp_path: Path) -> None:
    repo = _bootstrap_repo(tmp_path)
    profile = default_shadow_protected_roots_profile()
    dynamic_root = "daemon/rsi_omega_daemon_v19_0/state"

    pre = hash_protected_roots(
        repo_root=repo,
        roots=[dynamic_root],
        excluded_roots=[],
        hash_budget_spec=profile["hash_budget_spec"],
        symlink_policy=profile["symlink_policy"],
    )
    _write(repo / "daemon" / "other" / "state" / "x.json", '{"changed":true}\n')
    post = hash_protected_roots(
        repo_root=repo,
        roots=[dynamic_root],
        excluded_roots=[],
        hash_budget_spec=profile["hash_budget_spec"],
        symlink_policy=profile["symlink_policy"],
    )
    assert diff_file_maps(pre["file_hashes"], post["file_hashes"]) == []


def test_hash_budget_exhausted_is_fail_closed(tmp_path: Path) -> None:
    repo = _bootstrap_repo(tmp_path)
    profile = default_shadow_protected_roots_profile()
    tiny_budget = {"max_files": 1, "max_bytes_read": 1, "max_steps": 1}
    with pytest.raises(RuntimeError, match="SHADOW_HASH_BUDGET_EXHAUSTED"):
        hash_protected_roots(
            repo_root=repo,
            roots=profile["static_protected_roots"],
            excluded_roots=profile["excluded_roots"],
            hash_budget_spec=tiny_budget,
            symlink_policy=profile["symlink_policy"],
        )

