"""Scoped protected-root hashing for v19 shadow execution."""

from __future__ import annotations

import fnmatch
import hashlib
import os
from pathlib import Path
from typing import Any

from .common_v1 import canon_hash_obj, validate_schema


_HEX64 = set("0123456789abcdef")


def _sha256_prefixed(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _normalize_relpath(path: str) -> str:
    raw = str(path or "").strip().replace("\\", "/")
    if raw.startswith("/") or raw == "" or "/../" in f"/{raw}/" or raw.startswith("../"):
        raise RuntimeError("SCHEMA_FAIL")
    return raw.rstrip("/")


def _is_excluded(relpath: str, excluded_roots: list[str]) -> bool:
    rel = _normalize_relpath(relpath)
    for row in excluded_roots:
        pat = _normalize_relpath(row)
        if "*" in pat:
            if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(rel + "/", pat):
                return True
            continue
        if rel == pat or rel.startswith(pat + "/"):
            return True
    return False


def _budget_counter(spec: dict[str, Any]) -> dict[str, int]:
    max_files = int(spec.get("max_files", 0))
    max_bytes_read = int(spec.get("max_bytes_read", 0))
    max_steps = int(spec.get("max_steps", 0))
    if max_files <= 0 or max_bytes_read <= 0 or max_steps <= 0:
        raise RuntimeError("SCHEMA_FAIL")
    return {
        "max_files": max_files,
        "max_bytes_read": max_bytes_read,
        "max_steps": max_steps,
        "files_u64": 0,
        "bytes_read_u64": 0,
        "steps_u64": 0,
    }


def _consume_budget(budget: dict[str, int], *, files: int = 0, bytes_read: int = 0, steps: int = 0) -> None:
    budget["files_u64"] += max(0, int(files))
    budget["bytes_read_u64"] += max(0, int(bytes_read))
    budget["steps_u64"] += max(0, int(steps))
    if budget["files_u64"] > budget["max_files"]:
        raise RuntimeError("SHADOW_HASH_BUDGET_EXHAUSTED")
    if budget["bytes_read_u64"] > budget["max_bytes_read"]:
        raise RuntimeError("SHADOW_HASH_BUDGET_EXHAUSTED")
    if budget["steps_u64"] > budget["max_steps"]:
        raise RuntimeError("SHADOW_HASH_BUDGET_EXHAUSTED")


def _assert_sha(value: str) -> None:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        raise RuntimeError("NONDETERMINISTIC")
    if any(ch not in _HEX64 for ch in value.split(":", 1)[1]):
        raise RuntimeError("NONDETERMINISTIC")


def _hash_file(path: Path, budget: dict[str, int]) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            _consume_budget(budget, bytes_read=len(chunk), steps=1)
            hasher.update(chunk)
    return "sha256:" + hasher.hexdigest()


def _hash_single_root(
    *,
    repo_root: Path,
    root_rel: str,
    excluded_roots: list[str],
    budget: dict[str, int],
    symlink_policy: str,
) -> tuple[str, dict[str, str]]:
    root_norm = _normalize_relpath(root_rel)
    root_abs = (repo_root / root_norm).resolve()
    try:
        root_abs.relative_to(repo_root.resolve())
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("SCHEMA_FAIL") from exc
    if not root_abs.exists() or not root_abs.is_dir():
        raise RuntimeError("MISSING_STATE_INPUT")
    if root_abs.is_symlink() and symlink_policy == "FAIL_CLOSED":
        raise RuntimeError("SHADOW_FORBIDDEN_WRITE")

    file_hashes: dict[str, str] = {}
    for current, dirs, files in os.walk(root_abs, topdown=True, followlinks=False):
        current_path = Path(current)
        current_rel = current_path.relative_to(repo_root).as_posix()
        _consume_budget(budget, steps=1)
        if _is_excluded(current_rel, excluded_roots):
            dirs[:] = []
            continue

        next_dirs: list[str] = []
        for dirname in sorted(dirs):
            child = current_path / dirname
            child_rel = child.relative_to(repo_root).as_posix()
            _consume_budget(budget, steps=1)
            if _is_excluded(child_rel, excluded_roots):
                continue
            if child.is_symlink() and symlink_policy == "FAIL_CLOSED":
                raise RuntimeError("SHADOW_FORBIDDEN_WRITE")
            next_dirs.append(dirname)
        dirs[:] = next_dirs

        for filename in sorted(files):
            file_path = current_path / filename
            file_rel = file_path.relative_to(repo_root).as_posix()
            _consume_budget(budget, steps=1)
            if _is_excluded(file_rel, excluded_roots):
                continue
            if file_path.is_symlink() and symlink_policy == "FAIL_CLOSED":
                raise RuntimeError("SHADOW_FORBIDDEN_WRITE")
            _consume_budget(budget, files=1)
            file_hashes[file_rel] = _hash_file(file_path, budget)

    lines = [f"{path}\0{digest}" for path, digest in sorted(file_hashes.items())]
    root_digest = _sha256_prefixed("\n".join(lines).encode("utf-8"))
    _assert_sha(root_digest)
    return root_digest, file_hashes


def default_shadow_protected_roots_profile() -> dict[str, Any]:
    """Pinned defaults for Phase 4C v4 protected-root scoping."""

    payload: dict[str, Any] = {
        "schema_name": "shadow_protected_roots_profile_v1",
        "schema_version": "v19_0",
        "profile_id": "sha256:" + ("0" * 64),
        "hash_scope_version": "PHASE4C_V4_SCOPED_ROOTS",
        "static_protected_roots": [
            "authority",
            "meta-core",
            "CDEL-v2",
            "Genesis"
        ],
        "dynamic_protected_roots": [
            "daemon/rsi_omega_daemon_v19_0/state"
        ],
        "excluded_roots": [
            "runs",
            ".omega_cache"
        ],
        "hash_budget_spec": {
            "max_files": 200000,
            "max_bytes_read": 1000000000,
            "max_steps": 500000
        },
        "symlink_policy": "FAIL_CLOSED"
    }
    payload["profile_id"] = canon_hash_obj({k: v for k, v in payload.items() if k != "profile_id"})
    validate_schema(payload, "shadow_protected_roots_profile_v1")
    return payload


def hash_protected_roots(
    *,
    repo_root: Path,
    roots: list[str],
    excluded_roots: list[str],
    hash_budget_spec: dict[str, Any],
    symlink_policy: str,
) -> dict[str, Any]:
    budget = _budget_counter(hash_budget_spec)
    root_hashes: dict[str, str] = {}
    file_hashes: dict[str, dict[str, str]] = {}
    for root_rel in sorted({_normalize_relpath(row) for row in roots}):
        digest, mapping = _hash_single_root(
            repo_root=repo_root,
            root_rel=root_rel,
            excluded_roots=excluded_roots,
            budget=budget,
            symlink_policy=symlink_policy,
        )
        root_hashes[root_rel] = digest
        file_hashes[root_rel] = mapping
    scope_hash = _sha256_prefixed(
        "\n".join(
            f"{root}\0{digest}"
            for root, digest in sorted(root_hashes.items())
        ).encode("utf-8")
    )
    _assert_sha(scope_hash)
    return {
        "scope_hash": scope_hash,
        "root_hashes": root_hashes,
        "file_hashes": file_hashes,
        "budget": {
            "files_u64": int(budget["files_u64"]),
            "bytes_read_u64": int(budget["bytes_read_u64"]),
            "steps_u64": int(budget["steps_u64"]),
        },
    }


def diff_file_maps(before: dict[str, dict[str, str]], after: dict[str, dict[str, str]]) -> list[str]:
    mutated: set[str] = set()
    all_roots = set(before.keys()) | set(after.keys())
    for root in all_roots:
        left = before.get(root, {})
        right = after.get(root, {})
        all_paths = set(left.keys()) | set(right.keys())
        for rel in all_paths:
            if left.get(rel) != right.get(rel):
                mutated.add(rel)
    return sorted(mutated)


def build_integrity_report(
    *,
    tick_u64: int,
    candidate_regime_id: str,
    phase: str,
    scope_hash_pre: str,
    scope_hash_post: str,
    mutated_paths: list[str],
    budget: dict[str, int],
    reason_codes: list[str],
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_name": "shadow_fs_integrity_report_v1",
        "schema_version": "v19_0",
        "report_id": "sha256:" + ("0" * 64),
        "tick_u64": int(tick_u64),
        "candidate_regime_id": str(candidate_regime_id),
        "phase": str(phase),
        "scope_hash_pre": str(scope_hash_pre),
        "scope_hash_post": str(scope_hash_post),
        "budget": {
            "files_u64": int(budget.get("files_u64", 0)),
            "bytes_read_u64": int(budget.get("bytes_read_u64", 0)),
            "steps_u64": int(budget.get("steps_u64", 0)),
        },
        "mutated_paths": sorted(str(row) for row in mutated_paths),
        "reason_codes": sorted(set(str(row) for row in reason_codes if str(row))),
        "status": "PASS" if not mutated_paths and not reason_codes else "FAIL",
    }
    report["report_id"] = canon_hash_obj({k: v for k, v in report.items() if k != "report_id"})
    validate_schema(report, "shadow_fs_integrity_report_v1")
    return report


__all__ = [
    "build_integrity_report",
    "default_shadow_protected_roots_profile",
    "diff_file_maps",
    "hash_protected_roots",
]

