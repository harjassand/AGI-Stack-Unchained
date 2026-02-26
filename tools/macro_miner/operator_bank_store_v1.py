#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    _value = str(_entry)
    if _value not in sys.path:
        sys.path.insert(0, _value)

from cdel.v18_0.omega_common_v1 import write_hashed_json
from cdel.v19_0.common_v1 import canon_hash_obj, load_canon_dict, validate_schema


def canon_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def utc_now_rfc3339() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def write_operator_bank(*, out_dir: Path, bank_payload: dict[str, Any]) -> tuple[Path, dict[str, Any], str]:
    payload = dict(bank_payload)
    validate_schema(payload, "oracle_operator_bank_v1")
    path, obj, digest = write_hashed_json(out_dir, "oracle_operator_bank_v1.json", payload, id_field="id")
    validate_schema(obj, "oracle_operator_bank_v1")
    return path, obj, digest


def write_operator_bank_pointer(
    *,
    pointer_dir: Path,
    bank_hash: str,
    bank_relpath: str,
    created_at_utc: str | None = None,
    bank_version_u64: int | None = None,
) -> tuple[Path, dict[str, Any], str]:
    payload: dict[str, Any] = {
        "schema_id": "oracle_operator_bank_pointer_v1",
        "id": "sha256:" + ("0" * 64),
        "bank_hash": str(bank_hash),
        "bank_relpath": str(bank_relpath),
        "created_at_utc": str(created_at_utc or utc_now_rfc3339()),
    }
    if isinstance(bank_version_u64, int) and bank_version_u64 > 0:
        payload["bank_version_u64"] = int(bank_version_u64)
    validate_schema(payload, "oracle_operator_bank_pointer_v1")
    path, obj, digest = write_hashed_json(pointer_dir, "oracle_operator_bank_pointer_v1.json", payload, id_field="id")
    validate_schema(obj, "oracle_operator_bank_pointer_v1")

    active_ptr = pointer_dir / "ACTIVE_OPERATOR_BANK"
    _atomic_write_text(active_ptr, f"{digest}\n")
    return path, obj, digest


def load_operator_bank_by_pointer(*, pointer_dir: Path, bank_dir: Path) -> tuple[dict[str, Any], str]:
    pointer_file = pointer_dir / "ACTIVE_OPERATOR_BANK"
    if not pointer_file.exists() or not pointer_file.is_file():
        raise RuntimeError("MISSING_STATE_INPUT:ACTIVE_OPERATOR_BANK")
    digest = pointer_file.read_text(encoding="utf-8").strip()
    if not (isinstance(digest, str) and digest.startswith("sha256:") and len(digest) == 71):
        raise RuntimeError("SCHEMA_FAIL:ACTIVE_OPERATOR_BANK")

    pointer_path = pointer_dir / f"sha256_{digest.split(':', 1)[1]}.oracle_operator_bank_pointer_v1.json"
    pointer_payload = load_canon_dict(pointer_path)
    validate_schema(pointer_payload, "oracle_operator_bank_pointer_v1")
    if canon_hash_obj(pointer_payload) != digest:
        raise RuntimeError("NONDETERMINISTIC:operator_bank_pointer")

    bank_hash = str(pointer_payload.get("bank_hash", "")).strip()
    if not (bank_hash.startswith("sha256:") and len(bank_hash) == 71):
        raise RuntimeError("SCHEMA_FAIL:bank_hash")
    bank_path = bank_dir / f"sha256_{bank_hash.split(':', 1)[1]}.oracle_operator_bank_v1.json"
    bank_payload = load_canon_dict(bank_path)
    validate_schema(bank_payload, "oracle_operator_bank_v1")
    if canon_hash_obj(bank_payload) != bank_hash:
        raise RuntimeError("NONDETERMINISTIC:operator_bank")
    return bank_payload, bank_hash


__all__ = [
    "canon_bytes",
    "load_operator_bank_by_pointer",
    "utc_now_rfc3339",
    "write_operator_bank",
    "write_operator_bank_pointer",
]
