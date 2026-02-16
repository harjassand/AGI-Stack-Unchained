"""Promotion bundle v2 helpers for SAS-Metasearch v16.1."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..v1_7r.canon import canon_bytes, sha256_prefixed, write_canon_json


def build_promotion_bundle(payload: dict[str, Any]) -> dict[str, Any]:
    out = {
        "schema_version": "sas_metasearch_promotion_bundle_v2",
        "created_utc": "1970-01-01T00:00:00Z",
        "bundle_id": "",
        **payload,
    }
    out["bundle_id"] = sha256_prefixed(canon_bytes({k: v for k, v in out.items() if k != "bundle_id"}))
    return out


def write_hashed_bundle(out_dir: Path, bundle: dict[str, Any]) -> tuple[Path, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    h = sha256_prefixed(canon_bytes(bundle))
    path = out_dir / f"sha256_{h.split(':',1)[1]}.sas_metasearch_promotion_bundle_v2.json"
    write_canon_json(path, bundle)
    return path, h


__all__ = ["build_promotion_bundle", "write_hashed_bundle"]
