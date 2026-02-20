"""Verifier for coordinator opcode tables (v1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common_v1 import canon_hash_obj, ensure_sha256, fail, load_canon_dict, repo_root, validate_schema


def _native_blob_exists(binary_sha256: str) -> bool:
    hex64 = binary_sha256.split(":", 1)[1]
    store = repo_root() / ".omega_cache" / "native_blobs"
    for ext in (".dylib", ".so"):
        candidate = store / f"sha256_{hex64}{ext}"
        if candidate.exists() and candidate.is_file():
            return True
    return False


def verify_opcode_table(payload: dict[str, Any]) -> str:
    validate_schema(payload, "coordinator_opcode_table_v1")
    declared_id = ensure_sha256(payload.get("opcode_table_id"), reason="SCHEMA_FAIL")
    no_id = dict(payload)
    no_id.pop("opcode_table_id", None)
    if canon_hash_obj(no_id) != declared_id:
        fail("PIN_HASH_MISMATCH")
    if int(payload.get("isa_version", 0)) != 1:
        fail("SCHEMA_FAIL")
    forbidden = payload.get("forbidden_in_phase1")
    if not isinstance(forbidden, list):
        fail("SCHEMA_FAIL")
    for row in forbidden:
        if not isinstance(row, str) or not row.strip():
            fail("SCHEMA_FAIL")

    entries = payload.get("entries")
    if entries is None:
        # Legacy shape.
        opcodes = payload.get("opcodes")
        if not isinstance(opcodes, dict) or not opcodes:
            fail("SCHEMA_FAIL")
        return "VALID"

    _table_id = ensure_sha256(payload.get("table_id"), reason="SCHEMA_FAIL")
    if not isinstance(entries, list) or not entries:
        fail("SCHEMA_FAIL")

    seen_u16: set[int] = set()
    seen_names: set[str] = set()
    normalized_rows: list[tuple[int, str]] = []
    for row in entries:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        opcode_u16 = int(row.get("opcode_u16", -1))
        opcode_name = str(row.get("opcode_name", "")).strip().upper()
        if opcode_u16 < 0 or opcode_u16 > 0xFFFF or not opcode_name:
            fail("SCHEMA_FAIL")
        if opcode_u16 in seen_u16 or opcode_name in seen_names:
            fail("SCHEMA_FAIL")
        seen_u16.add(opcode_u16)
        seen_names.add(opcode_name)
        normalized_rows.append((opcode_u16, opcode_name))

        kind = str(row.get("kind", "")).strip().upper()
        if kind not in {"BUILTIN", "NATIVE"}:
            fail("SCHEMA_FAIL")
        impl = row.get("impl")
        if not isinstance(impl, dict):
            fail("SCHEMA_FAIL")
        impl_kind = str(impl.get("impl_kind", "")).strip().upper()
        if impl_kind != kind:
            fail("SCHEMA_FAIL")
        if kind == "BUILTIN":
            if not str(impl.get("module_id", "")).strip() or not str(impl.get("function_id", "")).strip():
                fail("SCHEMA_FAIL")
        else:
            binary_sha256 = ensure_sha256(impl.get("binary_sha256"), reason="SCHEMA_FAIL")
            if not str(impl.get("op_id", "")).strip():
                fail("SCHEMA_FAIL")
            if int(impl.get("abi_version_u32", -1)) < 0:
                fail("SCHEMA_FAIL")
            ensure_sha256(impl.get("healthcheck_id"), reason="SCHEMA_FAIL")
            if bool(row.get("active_b", False)) and not _native_blob_exists(binary_sha256):
                fail("MISSING_STATE_INPUT")
        introduced_tick = int(row.get("introduced_tick_u64", -1))
        deprecated_tick = int(row.get("deprecated_tick_u64", -1))
        if introduced_tick < 0 or deprecated_tick < 0:
            fail("SCHEMA_FAIL")
        if bool(row.get("active_b", False)) and deprecated_tick != 0:
            fail("SCHEMA_FAIL")
        if (not bool(row.get("active_b", False))) and deprecated_tick < introduced_tick:
            fail("SCHEMA_FAIL")

    if normalized_rows != sorted(normalized_rows, key=lambda item: (item[0], item[1])):
        fail("NONDETERMINISTIC")
    return "VALID"


def verify_opcode_table_file(path: Path) -> str:
    payload = load_canon_dict(path)
    return verify_opcode_table(payload)


__all__ = ["verify_opcode_table", "verify_opcode_table_file"]
