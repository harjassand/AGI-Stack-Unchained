"""Activation receipt generation and checks for SAS-Kernel v15.0."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json


class KernelActivationError(RuntimeError):
    pass


def _fail(reason: str) -> None:
    raise KernelActivationError(reason)


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def stable_activation_hash(obj: dict[str, Any]) -> str:
    payload = dict(obj)
    payload.pop("activated_utc", None)
    payload.pop("activation_hash", None)
    return sha256_prefixed(canon_bytes(payload))


def build_activation_receipt(
    *,
    binary_sha256: str,
    promotion_bundle_sha256: str,
    activated_utc: str | None = None,
) -> dict[str, Any]:
    if activated_utc is None:
        activated_utc = _now_utc()
    receipt = {
        "schema_version": "kernel_activation_receipt_v1",
        "kernel_component_id": "SAS_KERNEL_V15",
        "binary_sha256": binary_sha256,
        "abi_version": "kernel_run_spec_v1",
        "activated_by_promotion_bundle_sha256": promotion_bundle_sha256,
        "activated_utc": activated_utc,
        "activation_hash": "",
    }
    receipt["activation_hash"] = stable_activation_hash(receipt)
    return receipt


def write_activation_receipt(path: Path, payload: dict[str, Any]) -> None:
    write_canon_json(path, payload)


def load_activation_receipt(path: Path) -> dict[str, Any]:
    obj = load_canon_json(path)
    if not isinstance(obj, dict) or obj.get("schema_version") != "kernel_activation_receipt_v1":
        _fail("INVALID:SCHEMA_FAIL")
    if obj.get("activation_hash") != stable_activation_hash(obj):
        _fail("INVALID:ACTIVATION_HASH")
    return obj


__all__ = [
    "KernelActivationError",
    "stable_activation_hash",
    "build_activation_receipt",
    "write_activation_receipt",
    "load_activation_receipt",
]
