"""Verifier error codes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RejectCode(str, Enum):
    SCHEMA_INVALID = "SCHEMA_INVALID"
    HASH_CANON_MISMATCH = "HASH_CANON_MISMATCH"
    PARENT_MISMATCH = "PARENT_MISMATCH"
    DUPLICATE_SYMBOL = "DUPLICATE_SYMBOL"
    FRESHNESS_VIOLATION = "FRESHNESS_VIOLATION"
    DEPS_MISMATCH = "DEPS_MISMATCH"
    TYPE_ERROR = "TYPE_ERROR"
    TERMINATION_FAIL = "TERMINATION_FAIL"
    SPEC_FAIL = "SPEC_FAIL"
    CAPACITY_EXCEEDED = "CAPACITY_EXCEEDED"
    MUTUAL_RECURSION_FORBIDDEN = "MUTUAL_RECURSION_FORBIDDEN"


@dataclass(frozen=True)
class Rejection:
    code: RejectCode
    reason: str
    details: str | None = None
