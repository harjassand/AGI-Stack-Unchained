"""UFC artifact helpers + verifier (v1).

This module implements deterministic structural verification for `ufc_v1.json`
as specified in the repo-anchored EUDRS-U v1.0 spec (Section 15.2).

The full derivation of UFC from logs is OpSet-defined and is not implemented in
this checkout; this verifier focuses on schema-pinned invariants that are
necessary for replay-verification plumbing.
"""

from __future__ import annotations

import hashlib
from typing import Any

from ..omega_common_v1 import fail


def _require_sha256_id(value: Any) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != len("sha256:") + 64:
        fail("SCHEMA_FAIL")
    try:
        raw = bytes.fromhex(value.split(":", 1)[1])
    except Exception:
        fail("SCHEMA_FAIL")
    if len(raw) != 32:
        fail("SCHEMA_FAIL")
    return str(value)


def _require_q32_obj(obj: Any) -> dict[str, int]:
    if not isinstance(obj, dict) or set(obj.keys()) != {"q"}:
        fail("SCHEMA_FAIL")
    q = obj.get("q")
    if not isinstance(q, int):
        fail("SCHEMA_FAIL")
    return {"q": int(q)}


def verify_ufc_v1(*, ufc_obj: dict[str, Any]) -> None:
    if not isinstance(ufc_obj, dict):
        fail("SCHEMA_FAIL")
    if str(ufc_obj.get("schema_id", "")).strip() != "ufc_v1":
        fail("SCHEMA_FAIL")

    _require_sha256_id(ufc_obj.get("eval_suite_id"))
    _require_sha256_id(ufc_obj.get("episode_list_hash"))
    _require_sha256_id(ufc_obj.get("ufc_records_root_sha256"))
    _require_sha256_id(ufc_obj.get("u_by_concept_root_sha256"))
    _require_sha256_id(ufc_obj.get("u_by_strategy_root_sha256"))

    _require_q32_obj(ufc_obj.get("u_total_q32"))

    u_by_level = ufc_obj.get("u_by_level")
    if not isinstance(u_by_level, list):
        fail("SCHEMA_FAIL")

    prev_level: int | None = None
    for row in u_by_level:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        level_u16 = row.get("level_u16")
        if not isinstance(level_u16, int) or level_u16 < 0 or level_u16 > 0xFFFF:
            fail("SCHEMA_FAIL")
        if prev_level is not None and int(level_u16) <= int(prev_level):
            fail("SCHEMA_FAIL")
        prev_level = int(level_u16)
        _require_q32_obj(row.get("u_q32"))

    # Defensive: ensure deterministic hash of the u_by_level rows is stable if callers choose to commit to it.
    # (Not wired to any schema field in v1.)
    _ = hashlib.sha256()


__all__ = [
    "verify_ufc_v1",
]

