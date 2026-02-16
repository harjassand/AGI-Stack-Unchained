"""Macro guard validation helpers."""

from __future__ import annotations

from typing import Any

from ..canon import CanonError


def validate_guard(guard: dict[str, Any], *, max_ctx: int) -> list[str]:
    if not isinstance(guard, dict):
        raise CanonError("macro guard must be object")
    if guard.get("schema") != "macro_guard_ctx_v1":
        raise CanonError("macro guard schema mismatch")
    if int(guard.get("schema_version", 0)) != 1:
        raise CanonError("macro guard schema_version mismatch")
    ctx_hashes = guard.get("ctx_hashes")
    if not isinstance(ctx_hashes, list) or not all(isinstance(x, str) for x in ctx_hashes):
        raise CanonError("macro guard ctx_hashes invalid")
    if len(ctx_hashes) > max_ctx:
        raise CanonError("macro guard ctx_hashes exceeds MACRO_V2_MAX_GUARD_CTX")
    if len(set(ctx_hashes)) != len(ctx_hashes):
        raise CanonError("macro guard ctx_hashes not unique")
    if ctx_hashes != sorted(ctx_hashes):
        raise CanonError("macro guard ctx_hashes not sorted")
    return ctx_hashes
