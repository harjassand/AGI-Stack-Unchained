"""Verifier for hint_bundle_v1 artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common_v1 import canon_hash_obj, ensure_sha256, fail, load_canon_dict, validate_schema


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


def verify_hint_bundle(payload: dict[str, Any]) -> str:
    validate_schema(payload, "hint_bundle_v1")
    ensure_sha256(payload.get("inputs_descriptor_hash"), reason="SCHEMA_FAIL")
    ensure_sha256(payload.get("policy_program_id"), reason="SCHEMA_FAIL")
    commitment = ensure_sha256(payload.get("hint_commitment_hash"), reason="SCHEMA_FAIL")
    no_commitment = dict(payload)
    no_commitment.pop("hint_commitment_hash", None)
    if canon_hash_obj(no_commitment) != commitment:
        fail("NONDETERMINISTIC")
    items = payload.get("hint_items")
    if not isinstance(items, list):
        fail("SCHEMA_FAIL")
    if items != sorted(items, key=_sort_key):
        fail("NONDETERMINISTIC")
    for item in items:
        if not isinstance(item, dict):
            fail("SCHEMA_FAIL")
        if str(item.get("kind", "")).strip() == "SET":
            values = item.get("values")
            if not isinstance(values, list):
                fail("SCHEMA_FAIL")
            if values != sorted({str(row) for row in values}):
                fail("NONDETERMINISTIC")
    return "VALID"


def verify_hint_bundle_file(path: Path) -> str:
    payload = load_canon_dict(path)
    return verify_hint_bundle(payload)


__all__ = ["verify_hint_bundle", "verify_hint_bundle_file"]
