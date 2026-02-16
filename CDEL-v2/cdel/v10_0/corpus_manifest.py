"""Training corpus manifest helpers (v10.0)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed

MANIFEST_SCHEMA = "training_corpus_manifest_v1"
INDEX_SCHEMA = "training_corpus_index_v1"


def _fail(reason: str) -> None:
    raise CanonError(reason)


def compute_corpus_id(manifest: dict[str, Any]) -> str:
    payload = dict(manifest)
    payload.pop("corpus_id", None)
    return sha256_prefixed(canon_bytes(payload))


def load_corpus_manifest(path: str | Path) -> dict[str, Any]:
    manifest = load_canon_json(path)
    if not isinstance(manifest, dict) or manifest.get("schema_version") != MANIFEST_SCHEMA:
        _fail("SCHEMA_INVALID")
    for key in ["corpus_id", "shards", "counts_by_type", "source_run_receipts", "split_policy"]:
        if key not in manifest:
            _fail("SCHEMA_INVALID")
    return manifest


def load_corpus_index(path: str | Path) -> dict[str, Any]:
    index = load_canon_json(path)
    if not isinstance(index, dict) or index.get("schema_version") != INDEX_SCHEMA:
        _fail("SCHEMA_INVALID")
    return index


__all__ = ["compute_corpus_id", "load_corpus_manifest", "load_corpus_index"]
