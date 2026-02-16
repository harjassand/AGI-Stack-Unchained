"""Model weights bundle helpers (v10.0)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed

BUNDLE_SCHEMA = "model_weights_bundle_v1"


def _fail(reason: str) -> None:
    raise CanonError(reason)


def compute_bundle_id(bundle: dict[str, Any]) -> str:
    payload = dict(bundle)
    payload.pop("bundle_id", None)
    return sha256_prefixed(canon_bytes(payload))


def load_bundle(path: str | Path) -> dict[str, Any]:
    bundle = load_canon_json(path)
    if not isinstance(bundle, dict) or bundle.get("schema_version") != BUNDLE_SCHEMA:
        _fail("SCHEMA_INVALID")
    for key in [
        "bundle_id",
        "base_model_id",
        "weights_hash",
        "weights_path",
        "training_receipt_hash",
        "training_ledger_head_hash",
        "corpus_manifest_hash",
        "toolchain_manifest_hash",
        "training_config_hash",
    ]:
        if key not in bundle:
            _fail("SCHEMA_INVALID")
    return bundle


__all__ = ["compute_bundle_id", "load_bundle"]
