"""Sealed proof check receipt helpers (v8.0)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed

RECEIPT_SCHEMA = "sealed_proof_check_receipt_v1"


def _fail(reason: str) -> None:
    raise CanonError(reason)


def compute_sealed_receipt_hash(receipt: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(receipt))


def load_sealed_receipt(path: str | Path) -> dict[str, Any]:
    receipt = load_canon_json(path)
    if not isinstance(receipt, dict):
        _fail("SCHEMA_INVALID")
    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        _fail("SCHEMA_INVALID")
    for key in [
        "toolchain_id",
        "problem_id",
        "attempt_id",
        "invocation_argv",
        "exit_code",
        "stdout_hash",
        "stderr_hash",
        "result",
        "time_ms",
        "sandbox_manifest_hash",
    ]:
        if key not in receipt:
            _fail("SCHEMA_INVALID")
    if not isinstance(receipt.get("invocation_argv"), list):
        _fail("SCHEMA_INVALID")
    if not isinstance(receipt.get("exit_code"), int):
        _fail("SCHEMA_INVALID")
    if not isinstance(receipt.get("time_ms"), int):
        _fail("SCHEMA_INVALID")
    return receipt


__all__ = ["compute_sealed_receipt_hash", "load_sealed_receipt"]
