"""Verifier for merged_hint_state_v1 artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common_v1 import ensure_sha256, fail, load_canon_dict, validate_schema


def _value_norm(item: dict[str, Any]) -> str:
    kind = str(item.get("kind", "")).strip()
    if kind == "Q32_SCORE":
        return str(int(item.get("q32", 0)))
    values = item.get("values")
    if not isinstance(values, list):
        fail("SCHEMA_FAIL")
    return "\x1f".join(str(row) for row in values)


def _sort_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (str(item.get("kind", "")).strip(), str(item.get("key", "")).strip(), _value_norm(item))


def verify_merged_hint_state(payload: dict[str, Any]) -> str:
    validate_schema(payload, "merged_hint_state_v1")
    ensure_sha256(payload.get("inputs_descriptor_hash"), reason="SCHEMA_FAIL")
    ensure_sha256(payload.get("merge_policy_id"), reason="SCHEMA_FAIL")
    hashes = payload.get("contributing_hint_hashes")
    if not isinstance(hashes, list):
        fail("SCHEMA_FAIL")
    normalized = [ensure_sha256(row, reason="SCHEMA_FAIL") for row in hashes]
    if normalized != sorted(normalized):
        fail("NONDETERMINISTIC")
    merged = payload.get("merged_hints")
    if not isinstance(merged, list):
        fail("SCHEMA_FAIL")
    if merged != sorted(merged, key=_sort_key):
        fail("NONDETERMINISTIC")
    for row in merged:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        if str(row.get("kind", "")).strip() == "SET":
            values = row.get("values")
            if not isinstance(values, list):
                fail("SCHEMA_FAIL")
            if values != sorted({str(item) for item in values}):
                fail("NONDETERMINISTIC")
    return "VALID"


def verify_merged_hint_state_file(path: Path) -> str:
    payload = load_canon_dict(path)
    return verify_merged_hint_state(payload)


__all__ = ["verify_merged_hint_state", "verify_merged_hint_state_file"]
