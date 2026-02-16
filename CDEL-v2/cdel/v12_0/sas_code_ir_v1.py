"""SAS-CODE algorithm IR helpers (v12.0)."""

from __future__ import annotations

from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, sha256_prefixed

SCHEMA_VERSION = "sas_code_ir_v1"
DOMAIN = "SAS_CODE_SORT_V1"
ALGO_KINDS = {
    "BUBBLE_SORT_V1",
    "MERGE_SORT_V1",
    "INSERTION_SORT_V1",
    "QUICK_SORT_V1",
}


class SASCodeIRError(CanonError):
    pass


def _fail(reason: str) -> None:
    raise SASCodeIRError(reason)


def compute_algo_id(ir: dict[str, Any]) -> str:
    payload = dict(ir)
    payload["algo_id"] = ""
    return sha256_prefixed(canon_bytes(payload))


def validate_ir(ir: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(ir, dict) or ir.get("schema_version") != SCHEMA_VERSION:
        _fail("SCHEMA_INVALID")
    if ir.get("domain") != DOMAIN:
        _fail("SCHEMA_INVALID")
    algo_kind = ir.get("algo_kind")
    if algo_kind not in ALGO_KINDS:
        _fail("SCHEMA_INVALID")
    algo_id = ir.get("algo_id")
    if not isinstance(algo_id, str):
        _fail("SCHEMA_INVALID")
    expected = compute_algo_id(ir)
    if algo_id != expected:
        _fail("ALGO_ID_MISMATCH")
    params = ir.get("params")
    if not isinstance(params, dict):
        _fail("SCHEMA_INVALID")
    types = ir.get("types")
    if not isinstance(types, dict):
        _fail("SCHEMA_INVALID")
    tags = ir.get("tags")
    if not isinstance(tags, list):
        _fail("SCHEMA_INVALID")
    return ir


__all__ = ["SCHEMA_VERSION", "DOMAIN", "ALGO_KINDS", "compute_algo_id", "validate_ir", "SASCodeIRError"]
