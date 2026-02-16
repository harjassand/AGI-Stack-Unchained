"""Kernel run spec v1 parser and validator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed


class KernelRunSpecError(CanonError):
    pass


def _fail(reason: str) -> None:
    raise KernelRunSpecError(reason)


def _is_safe_rel_path(value: str) -> bool:
    if value.startswith("/"):
        return False
    path = Path(value)
    if path.is_absolute():
        return False
    for part in path.parts:
        if part == "..":
            return False
    return True


def _require_rel(value: Any) -> str:
    if not isinstance(value, str) or not value:
        _fail("INVALID:RUN_SPEC")
    if not _is_safe_rel_path(value):
        _fail("INVALID:RUN_SPEC_PATH")
    return value


def _require_u64(value: Any) -> int:
    if not isinstance(value, int):
        _fail("INVALID:RUN_SPEC")
    if value < 0 or value > (2**64 - 1):
        _fail("INVALID:RUN_SPEC")
    return value


def validate_run_spec(obj: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "run_id",
        "seed_u64",
        "capability_id",
        "capability_registry_rel",
        "paths",
        "sealed",
        "toolchains",
        "kernel_policy_rel",
    }
    if set(obj.keys()) != required:
        _fail("INVALID:RUN_SPEC")
    if obj.get("schema_version") != "kernel_run_spec_v1":
        _fail("INVALID:RUN_SPEC")

    if not isinstance(obj.get("run_id"), str):
        _fail("INVALID:RUN_SPEC")
    _require_u64(obj.get("seed_u64"))

    capability_id = obj.get("capability_id")
    if not isinstance(capability_id, str) or not capability_id:
        _fail("INVALID:RUN_SPEC")

    _require_rel(obj.get("capability_registry_rel"))
    _require_rel(obj.get("kernel_policy_rel"))

    paths = obj.get("paths")
    if not isinstance(paths, dict):
        _fail("INVALID:RUN_SPEC")
    if set(paths.keys()) != {"repo_root_rel", "daemon_root_rel", "out_dir_rel"}:
        _fail("INVALID:RUN_SPEC")
    if paths.get("repo_root_rel") != ".":
        _fail("INVALID:RUN_SPEC")
    if paths.get("daemon_root_rel") != "daemon":
        _fail("INVALID:RUN_SPEC")
    _require_rel(paths.get("out_dir_rel"))

    sealed = obj.get("sealed")
    if not isinstance(sealed, dict):
        _fail("INVALID:RUN_SPEC")
    if set(sealed.keys()) != {"sealed_config_toml_rel", "mount_policy_id"}:
        _fail("INVALID:RUN_SPEC")
    _require_rel(sealed.get("sealed_config_toml_rel"))
    if not isinstance(sealed.get("mount_policy_id"), str) or not sealed["mount_policy_id"]:
        _fail("INVALID:RUN_SPEC")

    toolchains = obj.get("toolchains")
    if not isinstance(toolchains, dict):
        _fail("INVALID:RUN_SPEC")
    expected = {
        "kernel_manifest_rel",
        "py_manifest_rel",
        "rust_manifest_rel",
        "lean_manifest_rel",
    }
    if set(toolchains.keys()) != expected:
        _fail("INVALID:RUN_SPEC")
    for key in expected:
        _require_rel(toolchains.get(key))

    return obj


def load_run_spec(path: Path) -> dict[str, Any]:
    obj = load_canon_json(path)
    if not isinstance(obj, dict):
        _fail("INVALID:RUN_SPEC")
    return validate_run_spec(obj)


def stable_run_spec_hash(run_spec: dict[str, Any]) -> str:
    payload = dict(run_spec)
    payload.pop("run_id", None)
    return sha256_prefixed(canon_bytes(payload))


__all__ = [
    "KernelRunSpecError",
    "load_run_spec",
    "validate_run_spec",
    "stable_run_spec_hash",
]
