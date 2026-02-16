"""Root manifest writer for SAS-CODE (v12.0)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import canon_bytes, sha256_prefixed, write_canon_json


def _now_utc() -> str:
    seed = int(os.environ.get("OMEGA_RUN_SEED_U64", "0"))
    return f"1970-01-01T00:00:{seed % 60:02d}Z"


def write_root_manifest(state_dir: Path, canon: dict[str, Any]) -> Path:
    manifest = dict(canon)
    manifest.update(
        {
            "schema_version": "sas_root_manifest_v1",
            "canon_time_utc": _now_utc(),
            "agi_root_canon_hash": sha256_prefixed(str(canon["agi_root_canon"]).encode("utf-8")),
            "sas_root_canon_hash": sha256_prefixed(str(canon["sas_root_canon"]).encode("utf-8")),
        }
    )
    manifest_hash = sha256_prefixed(canon_bytes(manifest))
    out_dir = state_dir / "health"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"sha256_{manifest_hash.split(':',1)[1]}.sas_root_manifest_v1.json"
    write_canon_json(out_path, manifest)
    return out_path


__all__ = ["write_root_manifest"]
