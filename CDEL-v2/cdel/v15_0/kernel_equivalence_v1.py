"""Snapshot and promotion parity comparators for SAS-Kernel v15.0."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json


class KernelEquivalenceError(RuntimeError):
    pass


def _fail(reason: str) -> None:
    raise KernelEquivalenceError(reason)


def canonical_hash_json(path: Path) -> str:
    obj = load_canon_json(path)
    return sha256_prefixed(canon_bytes(obj))


def compare_snapshot_parity(ref_snapshot: dict[str, Any], kernel_snapshot: dict[str, Any]) -> None:
    if ref_snapshot.get("root_hash_sha256") != kernel_snapshot.get("root_hash_sha256"):
        _fail("INVALID:SNAPSHOT_PARITY")
    if ref_snapshot.get("files") != kernel_snapshot.get("files"):
        _fail("INVALID:SNAPSHOT_PARITY")


def compare_promotion_parity(ref_bundle_path: Path, kernel_bundle_path: Path) -> None:
    ref_hash = canonical_hash_json(ref_bundle_path)
    kernel_hash = canonical_hash_json(kernel_bundle_path)
    if ref_hash != kernel_hash:
        _fail("INVALID:PROMOTION_PARITY")


def build_equiv_report(
    *,
    capability_id: str,
    snapshot_ref_path: Path,
    snapshot_kernel_path: Path,
    promotion_ref_path: Path,
    promotion_kernel_path: Path,
) -> dict[str, Any]:
    ref_snapshot = load_canon_json(snapshot_ref_path)
    kernel_snapshot = load_canon_json(snapshot_kernel_path)
    if not isinstance(ref_snapshot, dict) or not isinstance(kernel_snapshot, dict):
        _fail("INVALID:SCHEMA_FAIL")
    compare_snapshot_parity(ref_snapshot, kernel_snapshot)

    ref_promo_hash = canonical_hash_json(promotion_ref_path)
    kernel_promo_hash = canonical_hash_json(promotion_kernel_path)
    if ref_promo_hash != kernel_promo_hash:
        _fail("INVALID:PROMOTION_PARITY")

    return {
        "schema_version": "kernel_equiv_report_v1",
        "capability_id": capability_id,
        "snapshot_ref_root_hash": ref_snapshot.get("root_hash_sha256"),
        "snapshot_kernel_root_hash": kernel_snapshot.get("root_hash_sha256"),
        "promotion_bundle_hash_ref": ref_promo_hash,
        "promotion_bundle_hash_kernel": kernel_promo_hash,
        "all_pass": True,
    }


def write_equiv_report(path: Path, payload: dict[str, Any]) -> None:
    write_canon_json(path, payload)


__all__ = [
    "KernelEquivalenceError",
    "canonical_hash_json",
    "compare_snapshot_parity",
    "compare_promotion_parity",
    "build_equiv_report",
    "write_equiv_report",
]
