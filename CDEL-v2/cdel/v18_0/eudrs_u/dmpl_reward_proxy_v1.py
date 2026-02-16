"""DMPL reward proxy stub (v1).

Phase 2 contract:
  - Deterministic stub for `ufc_proxy_v1`.
  - No training; no UFC decomposition implemented yet.
"""

from __future__ import annotations

from typing import Any

from .dmpl_config_load_v1 import DmplRuntime
from .dmpl_types_v1 import DMPLError, DMPL_E_HASH_MISMATCH, DMPL_E_OPSET_MISMATCH


def ufc_proxy_v1(
    runtime: DmplRuntime,
    state_hash32: bytes,
    z_t: list[int],
    action_hash32: bytes,
    z_tp1: list[int],
) -> tuple[int, dict]:
    if not isinstance(runtime, DmplRuntime):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "runtime type"})
    if not isinstance(state_hash32, (bytes, bytearray, memoryview)) or len(bytes(state_hash32)) != 32:
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "state_hash32"})
    if not isinstance(action_hash32, (bytes, bytearray, memoryview)) or len(bytes(action_hash32)) != 32:
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "action_hash32"})
    if not isinstance(z_t, list) or not isinstance(z_tp1, list):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "z type"})

    r_hat_q32 = 0
    ufc_terms_obj: dict[str, Any] = {"schema_id": "dmpl_ufc_terms_v1", "terms": {}}
    return int(r_hat_q32), dict(ufc_terms_obj)


__all__ = [
    "ufc_proxy_v1",
]

