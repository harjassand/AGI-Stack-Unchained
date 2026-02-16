"""Dataset manifest helpers (v9.0)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed

SCHEMA_VERSION = "dataset_manifest_v1"


def _fail(reason: str) -> None:
    raise CanonError(reason)


def compute_manifest_hash(manifest: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(manifest))


def load_dataset_manifest(path: str | Path) -> dict[str, Any]:
    manifest = load_canon_json(path)
    if not isinstance(manifest, dict):
        _fail("SCHEMA_INVALID")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        _fail("SCHEMA_INVALID")
    datasets = manifest.get("datasets")
    if not isinstance(datasets, list) or not datasets:
        _fail("SCHEMA_INVALID")
    for ds in datasets:
        if not isinstance(ds, dict):
            _fail("SCHEMA_INVALID")
        for key in ["dataset_id", "path", "sha256", "domain"]:
            if key not in ds or not isinstance(ds.get(key), str):
                _fail("SCHEMA_INVALID")
        if not str(ds.get("dataset_id", "")).startswith("sha256:"):
            _fail("SCHEMA_INVALID")
        if not str(ds.get("sha256", "")).startswith("sha256:"):
            _fail("SCHEMA_INVALID")
    return manifest


def find_dataset(manifest: dict[str, Any], dataset_id: str) -> dict[str, Any] | None:
    for ds in manifest.get("datasets", []) or []:
        if isinstance(ds, dict) and ds.get("dataset_id") == dataset_id:
            return ds
    return None


__all__ = ["compute_manifest_hash", "find_dataset", "load_dataset_manifest"]
