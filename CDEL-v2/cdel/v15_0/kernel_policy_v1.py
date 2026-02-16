"""Kernel policy schema helpers and enforcement checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, load_canon_json


class KernelPolicyError(CanonError):
    pass


def _fail(reason: str) -> None:
    raise KernelPolicyError(reason)


def _require_abs_list(values: Any, label: str) -> list[str]:
    if not isinstance(values, list) or not values:
        _fail("INVALID:POLICY_SCHEMA")
    out: list[str] = []
    for raw in values:
        if not isinstance(raw, str) or not raw:
            _fail("INVALID:POLICY_SCHEMA")
        p = Path(raw)
        if not p.is_absolute():
            _fail("INVALID:POLICY_SCHEMA")
        out.append(str(p))
    return out


def load_policy(path: Path) -> dict[str, Any]:
    obj = load_canon_json(path)
    if not isinstance(obj, dict) or obj.get("schema_version") != "kernel_policy_v1":
        _fail("INVALID:POLICY_SCHEMA")

    _require_abs_list(obj.get("fs_read_prefix_allowlist"), "fs_read_prefix_allowlist")
    _require_abs_list(obj.get("fs_write_prefix_allowlist"), "fs_write_prefix_allowlist")

    exec_allowlist = obj.get("exec_allowlist")
    if not isinstance(exec_allowlist, list):
        _fail("INVALID:POLICY_SCHEMA")
    for row in exec_allowlist:
        if not isinstance(row, dict):
            _fail("INVALID:POLICY_SCHEMA")
        if set(row.keys()) != {"exe_abs", "argv_prefix", "env_allowlist"}:
            _fail("INVALID:POLICY_SCHEMA")
        exe_abs = row.get("exe_abs")
        if not isinstance(exe_abs, str) or not Path(exe_abs).is_absolute():
            _fail("INVALID:POLICY_SCHEMA")
        argv_prefix = row.get("argv_prefix")
        if not isinstance(argv_prefix, list) or not all(isinstance(x, str) for x in argv_prefix):
            _fail("INVALID:POLICY_SCHEMA")
        env_allowlist = row.get("env_allowlist")
        if not isinstance(env_allowlist, list) or not all(isinstance(x, str) for x in env_allowlist):
            _fail("INVALID:POLICY_SCHEMA")
    return obj


def ensure_path_allowed(path: Path, allow_prefixes: list[str], *, reason: str) -> None:
    path_abs = str(path.resolve())
    for prefix in allow_prefixes:
        prefix_abs = str(Path(prefix).resolve())
        if path_abs == prefix_abs or path_abs.startswith(prefix_abs + "/"):
            return
    _fail(reason)


def ensure_write_in_out_dir(path: Path, out_dir: Path) -> None:
    path_abs = str(path.resolve())
    out_abs = str(out_dir.resolve())
    if path_abs == out_abs or path_abs.startswith(out_abs + "/"):
        return
    _fail("INVALID:OUTSIDE_ROOT_WRITE")


def policy_match_exec(
    policy: dict[str, Any],
    *,
    exe_abs: str,
    argv: list[str],
    env: dict[str, str] | None = None,
) -> bool:
    env = env or {}
    for row in policy.get("exec_allowlist", []):
        if row.get("exe_abs") != exe_abs:
            continue
        prefix = row.get("argv_prefix") or []
        if argv[: len(prefix)] != prefix:
            continue
        env_allowlist = set(row.get("env_allowlist") or [])
        if any(key not in env_allowlist for key in env):
            continue
        return True
    return False


__all__ = [
    "KernelPolicyError",
    "load_policy",
    "ensure_path_allowed",
    "ensure_write_in_out_dir",
    "policy_match_exec",
]
