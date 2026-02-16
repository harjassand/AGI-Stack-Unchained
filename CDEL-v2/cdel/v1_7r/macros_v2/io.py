"""Canonical IO + hashing helpers for macro v2."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from ..canon import CanonError, canon_bytes, load_canon_json, write_canon_json
from ..hashutil import compute_self_hash


def compute_macro_id(macro_def: dict[str, Any]) -> str:
    return compute_self_hash(macro_def, "macro_id")


def compute_rent_bits(macro_def: dict[str, Any]) -> int:
    temp = deepcopy(macro_def)
    temp["rent_bits"] = 0
    return len(canon_bytes(temp)) * 8


def verify_macro_def_id(macro_def: dict[str, Any]) -> None:
    expected = compute_macro_id(macro_def)
    if macro_def.get("macro_id") != expected:
        raise CanonError("macro_id mismatch")


def verify_macro_rent_bits(macro_def: dict[str, Any]) -> None:
    expected = compute_rent_bits(macro_def)
    if int(macro_def.get("rent_bits", -1)) != expected:
        raise CanonError("macro rent_bits mismatch")


def ensure_macro_dirs(root: Path) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    ledger_dir = root / "ledger"
    active_dir = root / "active"
    defs_dir = root / "defs" / "by_macro_id"
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


def load_macro_def(macro_id: str, *, defs_root: Path) -> dict[str, Any]:
    hex_part = macro_id.split(":", 1)[1] if ":" in macro_id else macro_id
    path = defs_root / f"{hex_part}.json"
    if not path.exists():
        raise FileNotFoundError(f"missing macro_def: {macro_id}")
    payload = load_canon_json(path)
    if payload.get("macro_id") != macro_id:
        raise CanonError("macro_id mismatch")
    return payload


def write_macro_def_if_missing(macro_def: dict[str, Any], defs_root: Path) -> Path:
    macro_id = macro_def.get("macro_id")
    if not isinstance(macro_id, str):
        raise CanonError("macro_id missing")
    hex_part = macro_id.split(":", 1)[1] if ":" in macro_id else macro_id
    out_path = defs_root / f"{hex_part}.json"
    if not out_path.exists():
        write_canon_json(out_path, macro_def)
    return out_path
