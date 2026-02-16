"""DMPL deterministic value head (v1).

Phase 2 contract: see §5.9 (ValueDet).
"""

from __future__ import annotations

from typing import Any

from .dmpl_config_load_v1 import DmplRuntime
from .dmpl_gate_v1 import GateOutput
from .dmpl_tensor_io_v1 import parse_tensor_q32_v1, require_shape
from .dmpl_types_v1 import (
    DMPLError,
    DMPL_E_CONCEPT_PATCH_POLICY_VIOLATION,
    DMPL_E_DIM_MISMATCH,
    DMPL_E_HASH_MISMATCH,
    DMPL_E_OPSET_MISMATCH,
    _active_resolver,
    _add_sat_count,
    _mul_q32_count,
    _sha25632_count,
    _sha256_id_from_hex_digest32,
)

_SHA256_ZERO_ID = "sha256:" + ("0" * 64)


def _resolver_load_bin(*, artifact_id: str, artifact_type: str) -> bytes:
    resolver = _active_resolver()
    if resolver is None:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "no active resolver"})
    try:
        fn = getattr(resolver, "load_artifact_bytes")
    except Exception:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver missing load_artifact_bytes"})
    raw = fn(artifact_id=str(artifact_id), artifact_type=str(artifact_type), ext="bin")
    if not isinstance(raw, (bytes, bytearray, memoryview)):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver returned non-bytes"})
    b = bytes(raw)
    if _sha256_id_from_hex_digest32(_sha25632_count(b)) != str(artifact_id).strip():
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"artifact_id": str(artifact_id), "artifact_type": str(artifact_type)})
    return b


def _find_patch_entry(*, concept_obj: dict[str, Any], ladder_level_u32: int) -> dict[str, Any]:
    rows = concept_obj.get("patches_by_level")
    if not isinstance(rows, list) or not rows:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "patches_by_level"})
    for row in rows:
        if not isinstance(row, dict):
            continue
        if int(row.get("ladder_level_u32", -1)) == int(ladder_level_u32):
            return dict(row)
    raise DMPLError(reason_code=DMPL_E_CONCEPT_PATCH_POLICY_VIOLATION, details={"ladder_level_u32": int(ladder_level_u32)})


def _dot_q32(a: list[int], b: list[int]) -> int:
    if len(a) != len(b):
        raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "dot shape"})
    acc = 0
    for i in range(len(a)):
        acc = _add_sat_count(acc, _mul_q32_count(int(a[i]), int(b[i])))
    return int(acc)


def value_det_v1(runtime: DmplRuntime, z_t: list[int], gate: GateOutput, ladder_level_u32: int, concept_loader) -> int:
    if not isinstance(runtime, DmplRuntime):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "runtime type"})
    d = int(runtime.dims.d_u32)
    if not isinstance(z_t, list) or len(z_t) != d:
        raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "z_t shape"})
    if not isinstance(gate, GateOutput):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "gate type"})
    if not callable(concept_loader):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "concept_loader"})

    (w0_dims, w0) = runtime.base_value.get("w0", ([], []))
    (v0_dims, v0_vals) = runtime.base_value.get("v0", ([], []))
    require_shape(w0_dims, [d])
    require_shape(v0_dims, [1])
    if len(v0_vals) != 1:
        raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "v0 len"})
    v0 = int(v0_vals[0])

    V = _add_sat_count(int(v0), _dot_q32([int(x) for x in w0], [int(z) for z in z_t]))

    for item in list(gate.gate_active):
        cid = str(item.concept_shard_id)
        w_c = int(item.w_q32)
        concept_obj = concept_loader(cid)
        if not isinstance(concept_obj, dict):
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "concept_loader returned non-dict"})
        patch = _find_patch_entry(concept_obj=concept_obj, ladder_level_u32=int(ladder_level_u32))

        v_c0_q32 = patch.get("v_c0_q32")
        if not isinstance(v_c0_q32, dict) or set(v_c0_q32.keys()) != {"q"}:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "v_c0_q32"})
        inner = int(v_c0_q32.get("q", 0))

        w_bin_id = str(patch.get("w_bin_id", "")).strip()
        if not w_bin_id.startswith("sha256:"):
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "w_bin_id"})
        if w_bin_id != _SHA256_ZERO_ID:
            w_dims, w_vec = parse_tensor_q32_v1(_resolver_load_bin(artifact_id=w_bin_id, artifact_type="dmpl_tensor_q32_v1"))
            require_shape(w_dims, [d])
            inner = _add_sat_count(int(inner), _dot_q32([int(x) for x in w_vec], [int(z) for z in z_t]))

        V = _add_sat_count(int(V), _mul_q32_count(int(w_c), int(inner)))

    return int(V)


__all__ = [
    "value_det_v1",
]
