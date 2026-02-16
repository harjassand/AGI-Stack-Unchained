"""DMPL Phase 2 core types + deterministic error plumbing (v1).

Normative constraints (inherited from AGENTS.md + Phase 2 contract):
  - GCJ-1 canonical JSON only (floats forbidden).
  - Q32 is signed int64, value = q / 2^32.
  - All unexpected conditions fail-closed with deterministic reason codes.
"""

from __future__ import annotations

from dataclasses import dataclass
import contextvars
import hashlib
import struct
from typing import Any, Final

from ..omega_common_v1 import fail
from .eudrs_u_q32ops_v1 import add_sat as _add_sat_impl
from .eudrs_u_q32ops_v1 import mul_q32 as _mul_q32_impl
from .qxrl_opset_math_v1 import div_q32_pos_rne_v1 as _div_q32_pos_rne_impl

Q32_ONE: Final[int] = 1 << 32
I64_MIN: Final[int] = -(1 << 63)
I64_MAX: Final[int] = (1 << 63) - 1

# Reason codes (Phase 1 + Phase 2 additions used by this checkout).
DMPL_OK: Final[str] = "DMPL_OK"
DMPL_E_NONCANON_GCJ1: Final[str] = "DMPL_E_NONCANON_GCJ1"
DMPL_E_REDUCTION_ORDER_VIOLATION: Final[str] = "DMPL_E_REDUCTION_ORDER_VIOLATION"
DMPL_E_DIM_MISMATCH: Final[str] = "DMPL_E_DIM_MISMATCH"
DMPL_E_Q32_VIOLATION: Final[str] = "DMPL_E_Q32_VIOLATION"
DMPL_E_OPSET_MISMATCH: Final[str] = "DMPL_E_OPSET_MISMATCH"
DMPL_E_HASH_MISMATCH: Final[str] = "DMPL_E_HASH_MISMATCH"
DMPL_E_RETRIEVAL_DIGEST_MISMATCH: Final[str] = "DMPL_E_RETRIEVAL_DIGEST_MISMATCH"
DMPL_E_TRACE_CHAIN_BREAK: Final[str] = "DMPL_E_TRACE_CHAIN_BREAK"
DMPL_E_CONCEPT_PATCH_POLICY_VIOLATION: Final[str] = "DMPL_E_CONCEPT_PATCH_POLICY_VIOLATION"
DMPL_E_BUDGET_EXCEEDED: Final[str] = "DMPL_E_BUDGET_EXCEEDED"
DMPL_E_DISABLED: Final[str] = "DMPL_E_DISABLED"

# Phase 4 reason codes (promotion-critical gating and training replay).
DMPL_E_CAC_FAIL: Final[str] = "DMPL_E_CAC_FAIL"
DMPL_E_UFC_INVALID: Final[str] = "DMPL_E_UFC_INVALID"
DMPL_E_STAB_GATE_FAIL_G0: Final[str] = "DMPL_E_STAB_GATE_FAIL_G0"
DMPL_E_STAB_GATE_FAIL_G1: Final[str] = "DMPL_E_STAB_GATE_FAIL_G1"
DMPL_E_STAB_GATE_FAIL_G2: Final[str] = "DMPL_E_STAB_GATE_FAIL_G2"
DMPL_E_STAB_GATE_FAIL_G3: Final[str] = "DMPL_E_STAB_GATE_FAIL_G3"
DMPL_E_STAB_GATE_FAIL_G4: Final[str] = "DMPL_E_STAB_GATE_FAIL_G4"
DMPL_E_STAB_GATE_FAIL_G5: Final[str] = "DMPL_E_STAB_GATE_FAIL_G5"
DMPL_E_LASUM_BROKEN: Final[str] = "DMPL_E_LASUM_BROKEN"
DMPL_E_AUX_OVERRIDE_FORBIDDEN: Final[str] = "DMPL_E_AUX_OVERRIDE_FORBIDDEN"
DMPL_E_DATASET_OOB: Final[str] = "DMPL_E_DATASET_OOB"


def _require_i64(value: int, *, reason: str) -> int:
    v = int(value)
    if v < int(I64_MIN) or v > int(I64_MAX):
        raise DMPLError(reason_code=reason, details={"value": v})
    return v


def _validate_details_obj(obj: Any) -> None:
    # JSON-serializable, no floats.
    if obj is None or isinstance(obj, (str, bool, int)):
        return
    if isinstance(obj, float):
        raise DMPLError(reason_code=DMPL_E_NONCANON_GCJ1, details={"hint": "float in DMPLError.details"})
    if isinstance(obj, list):
        for item in obj:
            _validate_details_obj(item)
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                raise DMPLError(reason_code=DMPL_E_NONCANON_GCJ1, details={"hint": "non-str key in DMPLError.details"})
            _validate_details_obj(v)
        return
    # Reject bytes, Path, etc.
    raise DMPLError(reason_code=DMPL_E_NONCANON_GCJ1, details={"hint": f"non-json type in DMPLError.details: {type(obj).__name__}"})


@dataclass(frozen=True, slots=True)
class DMPLError(Exception):
    reason_code: str
    details: dict

    def __post_init__(self) -> None:
        if not isinstance(self.reason_code, str) or not self.reason_code:
            fail("SCHEMA_FAIL")
        if not isinstance(self.details, dict):
            fail("SCHEMA_FAIL")
        _validate_details_obj(self.details)

    def __str__(self) -> str:  # pragma: no cover - exercised indirectly
        # Keep deterministic: reason code only (details are for structured logs).
        return str(self.reason_code)


# Internal opcount context (not part of the public DMPL API).
_op_ctr_var: contextvars.ContextVar[Any] = contextvars.ContextVar("dmpl_op_ctr_v1", default=None)
_resolver_var: contextvars.ContextVar[Any] = contextvars.ContextVar("dmpl_resolver_v1", default=None)
_artifact_writer_var: contextvars.ContextVar[Any] = contextvars.ContextVar("dmpl_artifact_writer_v1", default=None)


def _set_active_op_counter(counter: Any) -> contextvars.Token[Any]:
    return _op_ctr_var.set(counter)


def _reset_active_op_counter(token: contextvars.Token[Any]) -> None:
    _op_ctr_var.reset(token)

def _set_active_resolver(resolver: Any) -> contextvars.Token[Any]:
    return _resolver_var.set(resolver)


def _reset_active_resolver(token: contextvars.Token[Any]) -> None:
    _resolver_var.reset(token)


def _active_resolver() -> Any:
    return _resolver_var.get()


def _set_active_artifact_writer(writer: Any) -> contextvars.Token[Any]:
    return _artifact_writer_var.set(writer)


def _reset_active_artifact_writer(token: contextvars.Token[Any]) -> None:
    _artifact_writer_var.reset(token)


def _active_artifact_writer() -> Any:
    return _artifact_writer_var.get()


def _bump_ops(n: int = 1) -> None:
    ctr = _op_ctr_var.get()
    if ctr is None:
        return
    try:
        ctr.ops_u64 += int(n)
    except Exception:
        # Counter must be well-formed; fail closed.
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "bad op counter"})


def _sha25632_count(data: bytes) -> bytes:
    _bump_ops(1)
    return hashlib.sha256(bytes(data)).digest()


def _sha256_id_from_bytes_count(data: bytes) -> str:
    return f"sha256:{_sha25632_count(data).hex()}"


def _sha256_id_from_hex_digest32(digest32: bytes) -> str:
    b = bytes(digest32)
    if len(b) != 32:
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "digest32 len != 32"})
    return f"sha256:{b.hex()}"


def _sha256_id_to_digest32(value: str, *, reason: str = DMPL_E_HASH_MISMATCH) -> bytes:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != (len("sha256:") + 64):
        raise DMPLError(reason_code=reason, details={"value": str(value)})
    try:
        raw = bytes.fromhex(value.split(":", 1)[1])
    except Exception:
        raise DMPLError(reason_code=reason, details={"value": str(value)})
    if len(raw) != 32:
        raise DMPLError(reason_code=reason, details={"value": str(value)})
    return raw


def _u32_le(value: int) -> bytes:
    v = int(value)
    if v < 0 or v > 0xFFFFFFFF:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"u32": v})
    return struct.pack("<I", v & 0xFFFFFFFF)


def _i64_le(value: int) -> bytes:
    try:
        return struct.pack("<q", int(value))
    except Exception:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"i64": int(value)})


def _mul_q32_count(a_q32_s64: int, b_q32_s64: int) -> int:
    _bump_ops(1)
    return int(_mul_q32_impl(int(a_q32_s64), int(b_q32_s64)))


def _add_sat_count(a_s64: int, b_s64: int) -> int:
    _bump_ops(1)
    return int(_add_sat_impl(int(a_s64), int(b_s64)))


def _div_q32_pos_rne_count(*, numer_q32_s64: int, denom_q32_pos_s64: int) -> int:
    _bump_ops(1)
    return int(_div_q32_pos_rne_impl(numer_q32_s64=int(numer_q32_s64), denom_q32_pos_s64=int(denom_q32_pos_s64), ctr=None))


def _clamp_q32_count(x_q32_s64: int) -> int:
    _bump_ops(1)
    x = int(x_q32_s64)
    if x < -int(Q32_ONE):
        return -int(Q32_ONE)
    if x > int(Q32_ONE):
        return int(Q32_ONE)
    return int(x)


def abs_q32(x_q32_s64: int) -> int:
    # Saturating abs on signed int64 (Q32 scalar).
    x = int(x_q32_s64)
    if x >= 0:
        return int(x)
    # abs(I64_MIN) would overflow; saturate to I64_MAX deterministically.
    if x == int(I64_MIN):
        return int(I64_MAX)
    return int(-x)


def sign_q32(x_q32_s64: int) -> int:
    x = int(x_q32_s64)
    if x > 0:
        return int(Q32_ONE)
    if x < 0:
        return -int(Q32_ONE)
    return 0


def sub_sat(a_s64: int, b_s64: int) -> int:
    # Deterministic saturating subtract via add_sat(a, -b) with saturating negation.
    b = int(b_s64)
    neg_b = int(I64_MAX) if b == int(I64_MIN) else int(-b)
    return int(_add_sat_impl(int(a_s64), int(neg_b)))


__all__ = [
    "Q32_ONE",
    "I64_MIN",
    "I64_MAX",
    "DMPL_OK",
    "DMPL_E_NONCANON_GCJ1",
    "DMPL_E_REDUCTION_ORDER_VIOLATION",
    "DMPL_E_DIM_MISMATCH",
    "DMPL_E_Q32_VIOLATION",
    "DMPL_E_OPSET_MISMATCH",
    "DMPL_E_HASH_MISMATCH",
    "DMPL_E_RETRIEVAL_DIGEST_MISMATCH",
    "DMPL_E_TRACE_CHAIN_BREAK",
    "DMPL_E_CONCEPT_PATCH_POLICY_VIOLATION",
    "DMPL_E_BUDGET_EXCEEDED",
    "DMPL_E_DISABLED",
    "DMPL_E_CAC_FAIL",
    "DMPL_E_UFC_INVALID",
    "DMPL_E_STAB_GATE_FAIL_G0",
    "DMPL_E_STAB_GATE_FAIL_G1",
    "DMPL_E_STAB_GATE_FAIL_G2",
    "DMPL_E_STAB_GATE_FAIL_G3",
    "DMPL_E_STAB_GATE_FAIL_G4",
    "DMPL_E_STAB_GATE_FAIL_G5",
    "DMPL_E_LASUM_BROKEN",
    "DMPL_E_AUX_OVERRIDE_FORBIDDEN",
    "DMPL_E_DATASET_OOB",
    "DMPLError",
    "abs_q32",
    "sign_q32",
    "sub_sat",
]
