"""Capability registry v2 loader for SAS-Kernel v15.0."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, load_canon_json


KERNEL_SUPPORT_VALUES = {"REQUIRED", "OPTIONAL", "NONE"}


class KernelRegistryError(CanonError):
    pass


def _fail(reason: str) -> None:
    raise KernelRegistryError(reason)


def _validate_entry(entry: Any) -> dict[str, Any]:
    if not isinstance(entry, dict):
        _fail("INVALID:SCHEMA_FAIL")
    required = {
        "capability_id",
        "daemon_root_rel",
        "pack_rel",
        "verifier_module",
        "kernel_support",
        "python_driver",
    }
    if set(entry.keys()) != required:
        _fail("INVALID:SCHEMA_FAIL")

    for key in ["capability_id", "daemon_root_rel", "pack_rel", "verifier_module"]:
        if not isinstance(entry.get(key), str) or not entry[key]:
            _fail("INVALID:SCHEMA_FAIL")
    if entry.get("kernel_support") not in KERNEL_SUPPORT_VALUES:
        _fail("INVALID:SCHEMA_FAIL")

    python_driver = entry.get("python_driver")
    if python_driver is not None and not isinstance(python_driver, str):
        _fail("INVALID:SCHEMA_FAIL")
    return entry


def load_registry(path: Path) -> dict[str, Any]:
    obj = load_canon_json(path)
    if not isinstance(obj, dict) or obj.get("schema_version") != "capability_registry_v2":
        _fail("INVALID:SCHEMA_FAIL")
    if set(obj.keys()) != {"schema_version", "capabilities"}:
        _fail("INVALID:SCHEMA_FAIL")
    caps = obj.get("capabilities")
    if not isinstance(caps, list) or not caps:
        _fail("INVALID:SCHEMA_FAIL")
    seen: set[str] = set()
    for item in caps:
        row = _validate_entry(item)
        cid = row["capability_id"]
        if cid in seen:
            _fail("INVALID:SCHEMA_FAIL")
        seen.add(cid)
    return obj


def resolve_capability(registry: dict[str, Any], capability_id: str) -> dict[str, Any]:
    caps = registry.get("capabilities")
    if not isinstance(caps, list):
        _fail("INVALID:SCHEMA_FAIL")
    for row in caps:
        if isinstance(row, dict) and row.get("capability_id") == capability_id:
            return row
    _fail("INVALID:CAPABILITY_NOT_FOUND")
    return {}


def required_capabilities(registry: dict[str, Any]) -> list[str]:
    caps = registry.get("capabilities")
    if not isinstance(caps, list):
        _fail("INVALID:SCHEMA_FAIL")
    return [str(row["capability_id"]) for row in caps if isinstance(row, dict) and row.get("kernel_support") == "REQUIRED"]


__all__ = [
    "KERNEL_SUPPORT_VALUES",
    "KernelRegistryError",
    "load_registry",
    "resolve_capability",
    "required_capabilities",
]
