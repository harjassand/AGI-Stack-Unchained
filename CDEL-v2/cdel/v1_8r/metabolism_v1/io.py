"""Canonical IO helpers for metabolism v1."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...v1_7r.canon import CanonError, hash_json, load_canon_json, write_canon_json
from .ledger import self_hash


def compute_patch_id(patch_def: dict[str, Any]) -> str:
    return self_hash(patch_def, "patch_id")


def patch_def_hash(patch_def: dict[str, Any]) -> str:
    return hash_json(patch_def)


def ensure_metabolism_dirs(root: Path) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    ledger_dir = root / "ledger"
    active_dir = root / "active"
    defs_dir = root / "defs" / "by_patch_id"
    reports_dir = root / "reports"
    receipts_dir = root / "receipts"
    for path in (ledger_dir, active_dir, defs_dir, reports_dir, receipts_dir):
        path.mkdir(parents=True, exist_ok=True)
    return {
        "root": root,
        "ledger": ledger_dir,
        "active": active_dir,
        "defs": defs_dir,
        "reports": reports_dir,
        "receipts": receipts_dir,
    }


def _hex_part(patch_id: str) -> str:
    return patch_id.split(":", 1)[1] if ":" in patch_id else patch_id


def load_patch_def(patch_id: str, *, defs_root: Path) -> dict[str, Any]:
    path = defs_root / f"{_hex_part(patch_id)}.json"
    if not path.exists():
        raise FileNotFoundError(f"missing meta patch def: {patch_id}")
    payload = load_canon_json(path)
    if payload.get("patch_id") != patch_id:
        raise CanonError("patch_id mismatch")
    return payload


def write_patch_def_if_missing(patch_def: dict[str, Any], defs_root: Path) -> Path:
    patch_id = patch_def.get("patch_id")
    if not isinstance(patch_id, str):
        raise CanonError("patch_id missing")
    out_path = defs_root / f"{_hex_part(patch_id)}.json"
    if not out_path.exists():
        write_canon_json(out_path, patch_def)
    return out_path


def load_active_set(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = load_canon_json(path)
    if not isinstance(payload, dict):
        return None
    return payload
