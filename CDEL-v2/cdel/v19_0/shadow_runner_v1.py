"""External shadow runner helpers for Phase 4C v4."""

from __future__ import annotations

import os
import subprocess
import fnmatch
from pathlib import Path
from typing import Any

from .shadow_fs_guard_v1 import diff_file_maps, hash_protected_roots


def _normalize_relpath(path: str) -> str:
    raw = str(path or "").strip().replace("\\", "/")
    if not raw or raw.startswith("/") or raw.startswith("../") or "/../" in f"/{raw}/":
        raise RuntimeError("SCHEMA_FAIL")
    return raw.rstrip("/")


def _as_repo_rel(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("SCHEMA_FAIL") from exc


def shadow_outbox_root(*, state_root: Path, candidate_regime_id: str) -> Path:
    daemon_root = state_root.parent
    return daemon_root / "shadow_outbox" / str(candidate_regime_id)


def shadow_cache_root(*, outbox_root: Path) -> Path:
    return outbox_root / ".shadow_cache"


def enforce_outbox_only_writes(
    *,
    observed_write_paths: list[str],
    outbox_root_rel: str,
    forbidden_cache_root_rel: str,
) -> None:
    outbox_rel = _normalize_relpath(outbox_root_rel)
    cache_rel = _normalize_relpath(forbidden_cache_root_rel)
    for raw_path in observed_write_paths:
        rel = _normalize_relpath(raw_path)
        if rel == cache_rel or rel.startswith(cache_rel + "/"):
            raise RuntimeError("SHADOW_FORBIDDEN_WRITE")
        if rel == outbox_rel or rel.startswith(outbox_rel + "/"):
            continue
        raise RuntimeError("SHADOW_FORBIDDEN_WRITE")


def run_shadow_tick(
    *,
    repo_root: Path,
    state_root: Path,
    candidate_regime_id: str,
    protected_profile: dict[str, Any],
    tick_u64: int,
    observed_write_paths: list[str] | None = None,
    candidate_command: list[str] | None = None,
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    outbox_root = shadow_outbox_root(state_root=state_root, candidate_regime_id=candidate_regime_id)
    cache_root = shadow_cache_root(outbox_root=outbox_root)
    outbox_root.mkdir(parents=True, exist_ok=True)
    cache_root.mkdir(parents=True, exist_ok=True)

    outbox_root_rel = _as_repo_rel(repo_root, outbox_root)
    cache_root_rel = _as_repo_rel(repo_root, cache_root)
    v19_cache_root_rel = _normalize_relpath(".omega_cache")
    observed = list(observed_write_paths or [])
    enforce_outbox_only_writes(
        observed_write_paths=observed,
        outbox_root_rel=outbox_root_rel,
        forbidden_cache_root_rel=v19_cache_root_rel,
    )

    dynamic_roots = [str(row) for row in protected_profile.get("dynamic_protected_roots", [])]
    excluded = [str(row) for row in protected_profile.get("excluded_roots", [])]
    effective_excluded: list[str] = []
    for row in excluded:
        keep = True
        for root_rel in dynamic_roots:
            root_norm = _normalize_relpath(root_rel)
            row_norm = _normalize_relpath(row)
            if "*" in row_norm:
                if fnmatch.fnmatch(root_norm, row_norm):
                    keep = False
                    break
            elif root_norm == row_norm or root_norm.startswith(row_norm + "/"):
                keep = False
                break
        if keep:
            effective_excluded.append(row)
    budget_spec = dict(protected_profile.get("hash_budget_spec", {}))
    symlink_policy = str(protected_profile.get("symlink_policy", "FAIL_CLOSED"))

    pre = hash_protected_roots(
        repo_root=repo_root,
        roots=dynamic_roots,
        excluded_roots=effective_excluded,
        hash_budget_spec=budget_spec,
        symlink_policy=symlink_policy,
    )

    return_code = 0
    if candidate_command:
        env = dict(os.environ)
        env["OMEGA_SHADOW_OUTBOX_ROOT"] = str(outbox_root)
        env["OMEGA_SHADOW_CACHE_ROOT"] = str(cache_root)
        env["OMEGA_V19_CACHE_ROOT"] = str((repo_root / ".omega_cache").resolve())
        proc = subprocess.run(  # noqa: S603
            [str(row) for row in candidate_command],
            cwd=str(repo_root),
            env=env,
            timeout=max(1, int(timeout_seconds)),
            check=False,
        )
        return_code = int(proc.returncode)

    post = hash_protected_roots(
        repo_root=repo_root,
        roots=dynamic_roots,
        excluded_roots=effective_excluded,
        hash_budget_spec=budget_spec,
        symlink_policy=symlink_policy,
    )
    mutated_paths = diff_file_maps(pre["file_hashes"], post["file_hashes"])

    reason_codes: list[str] = []
    if return_code != 0:
        reason_codes.append("SHADOW_RUNNER_FAILED")
    if mutated_paths:
        reason_codes.append("SHADOW_PROTECTED_ROOT_MUTATION")
    status = "PASS" if not reason_codes else "FAIL"
    return {
        "schema_name": "shadow_runner_receipt_v1",
        "schema_version": "v19_0",
        "tick_u64": int(tick_u64),
        "candidate_regime_id": str(candidate_regime_id),
        "status": status,
        "reason_codes": sorted(set(reason_codes)),
        "outbox_root_rel": outbox_root_rel,
        "shadow_cache_root_rel": cache_root_rel,
        "v19_cache_root_rel": v19_cache_root_rel,
        "dynamic_scope_hash_pre": str(pre["scope_hash"]),
        "dynamic_scope_hash_post": str(post["scope_hash"]),
        "dynamic_mutated_paths": mutated_paths,
        "budget": dict(post["budget"]),
    }


__all__ = [
    "enforce_outbox_only_writes",
    "run_shadow_tick",
    "shadow_cache_root",
    "shadow_outbox_root",
]
