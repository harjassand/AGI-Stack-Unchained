"""Verifier for coordinator ISA programs (v1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common_v1 import canon_hash_obj, ensure_sha256, fail, load_canon_dict, validate_schema


def verify_program(payload: dict[str, Any]) -> str:
    validate_schema(payload, "coordinator_isa_program_v1")
    declared_id = ensure_sha256(payload.get("program_id"), reason="SCHEMA_FAIL")
    no_id = dict(payload)
    no_id.pop("program_id", None)
    if canon_hash_obj(no_id) != declared_id:
        fail("PIN_HASH_MISMATCH")
    if int(payload.get("isa_version", 0)) != 1:
        fail("SCHEMA_FAIL")
    return "VALID"


def verify_program_file(path: Path) -> str:
    payload = load_canon_dict(path)
    return verify_program(payload)


__all__ = ["verify_program", "verify_program_file"]
