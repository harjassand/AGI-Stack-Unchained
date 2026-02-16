"""DMPL forward transition composition (v1).

Phase 2 contract: see §5.8 (PatchCompose).
"""

from __future__ import annotations

from typing import Any, Callable

from ..omega_common_v1 import OmegaV18Error, require_no_absolute_paths, validate_schema
from .dmpl_config_load_v1 import DmplRuntime
from .dmpl_gate_v1 import GateOutput
from .dmpl_tensor_io_v1 import parse_tensor_q32_v1, require_shape
from .dmpl_types_v1 import (
    DMPLError,
    DMPL_E_CONCEPT_PATCH_POLICY_VIOLATION,
    DMPL_E_DIM_MISMATCH,
    DMPL_E_HASH_MISMATCH,
    DMPL_E_NONCANON_GCJ1,
    DMPL_E_OPSET_MISMATCH,
    Q32_ONE,
    _active_resolver,
    _add_sat_count,
    _clamp_q32_count,
    _mul_q32_count,
    _sha25632_count,
    _sha256_id_from_hex_digest32,
)


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


def _matvec(*, M_vals: list[int], rows: int, cols: int, x: list[int]) -> list[int]:
    if len(x) != int(cols):
        raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "matvec x"})
    if len(M_vals) != int(rows) * int(cols):
        raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "matvec M"})
    out: list[int] = []
    for i in range(int(rows)):
        acc = 0
        off = i * int(cols)
        for j in range(int(cols)):
            acc = _add_sat_count(acc, _mul_q32_count(int(M_vals[off + j]), int(x[j])))
        out.append(int(acc))
    return out


def _vec_add_inplace(dst: list[int], src: list[int]) -> None:
    if len(dst) != len(src):
        raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "vec add"})
    for i in range(len(dst)):
        dst[i] = _add_sat_count(int(dst[i]), int(src[i]))


def _lowrank_matvec(*, U_vals: list[int], V_vals: list[int], out_rows: int, rank: int, in_cols: int, x: list[int]) -> list[int]:
    # tmp = V @ x  (rank)
    tmp = _matvec(M_vals=V_vals, rows=int(rank), cols=int(in_cols), x=x)
    # y = U @ tmp  (out_rows)
    return _matvec(M_vals=U_vals, rows=int(out_rows), cols=int(rank), x=tmp)


def z_transition_det_v1(
    runtime: DmplRuntime,
    z_t: list[int],
    u_t: list[int],
    gate: GateOutput,
    ladder_level_u32: int,
    concept_loader,
) -> list[int]:
    if not isinstance(runtime, DmplRuntime):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "runtime type"})
    d = int(runtime.dims.d_u32)
    p = int(runtime.dims.p_u32)
    if not isinstance(z_t, list) or len(z_t) != d:
        raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "z_t shape"})
    if not isinstance(u_t, list) or len(u_t) != p:
        raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "u_t shape"})
    if not isinstance(gate, GateOutput):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "gate type"})
    if not callable(concept_loader):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "concept_loader"})

    (A0_dims, A0) = runtime.base_forward.get("A0", ([], []))
    (B0_dims, B0) = runtime.base_forward.get("B0", ([], []))
    (b0_dims, b0) = runtime.base_forward.get("b0", ([], []))
    require_shape(A0_dims, [d, d])
    require_shape(B0_dims, [d, p])
    require_shape(b0_dims, [d])

    # Base: x = A0 z + B0 u + b0
    x = _matvec(M_vals=A0, rows=d, cols=d, x=z_t)
    Bu = _matvec(M_vals=B0, rows=d, cols=p, x=u_t)
    _vec_add_inplace(x, Bu)
    _vec_add_inplace(x, [int(v) for v in b0])

    # Concept patches in gate order.
    for item in list(gate.gate_active):
        cid = str(item.concept_shard_id)
        w_q32 = int(item.w_q32)
        concept_obj = concept_loader(cid)
        if not isinstance(concept_obj, dict):
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "concept_loader returned non-dict"})

        patch = _find_patch_entry(concept_obj=concept_obj, ladder_level_u32=int(ladder_level_u32))
        patch_kind = str(patch.get("patch_kind", "")).strip()
        if patch_kind == "none":
            continue

        if patch_kind == "matrix_patch":
            A_id = str(patch.get("A_bin_id", "")).strip()
            B_id = str(patch.get("B_bin_id", "")).strip()
            b_id = str(patch.get("b_bin_id", "")).strip()
            if not (A_id.startswith("sha256:") and B_id.startswith("sha256:") and b_id.startswith("sha256:")):
                raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "matrix patch ids"})
            A_dims, A_vals = parse_tensor_q32_v1(_resolver_load_bin(artifact_id=A_id, artifact_type="dmpl_tensor_q32_v1"))
            B_dims, B_vals = parse_tensor_q32_v1(_resolver_load_bin(artifact_id=B_id, artifact_type="dmpl_tensor_q32_v1"))
            b_dims2, b_vals2 = parse_tensor_q32_v1(_resolver_load_bin(artifact_id=b_id, artifact_type="dmpl_tensor_q32_v1"))
            require_shape(A_dims, [d, d])
            require_shape(B_dims, [d, p])
            require_shape(b_dims2, [d])

            t = _matvec(M_vals=A_vals, rows=d, cols=d, x=z_t)
            t2 = _matvec(M_vals=B_vals, rows=d, cols=p, x=u_t)
            _vec_add_inplace(t, t2)
            _vec_add_inplace(t, b_vals2)

            for i in range(d):
                x[i] = _add_sat_count(int(x[i]), _mul_q32_count(int(w_q32), int(t[i])))
            continue

        if patch_kind == "lowrank_patch":
            r = int(patch.get("rank_u32", -1))
            if r <= 0:
                raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "rank"})
            A_u_id = str(patch.get("A_u_bin_id", "")).strip()
            A_v_id = str(patch.get("A_v_bin_id", "")).strip()
            B_u_id = str(patch.get("B_u_bin_id", "")).strip()
            B_v_id = str(patch.get("B_v_bin_id", "")).strip()
            b_id = str(patch.get("b_bin_id", "")).strip()
            if not all(s.startswith("sha256:") for s in (A_u_id, A_v_id, B_u_id, B_v_id, b_id)):
                raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "lowrank ids"})

            A_u_dims, A_u_vals = parse_tensor_q32_v1(_resolver_load_bin(artifact_id=A_u_id, artifact_type="dmpl_tensor_q32_v1"))
            A_v_dims, A_v_vals = parse_tensor_q32_v1(_resolver_load_bin(artifact_id=A_v_id, artifact_type="dmpl_tensor_q32_v1"))
            B_u_dims, B_u_vals = parse_tensor_q32_v1(_resolver_load_bin(artifact_id=B_u_id, artifact_type="dmpl_tensor_q32_v1"))
            B_v_dims, B_v_vals = parse_tensor_q32_v1(_resolver_load_bin(artifact_id=B_v_id, artifact_type="dmpl_tensor_q32_v1"))
            b_dims2, b_vals2 = parse_tensor_q32_v1(_resolver_load_bin(artifact_id=b_id, artifact_type="dmpl_tensor_q32_v1"))

            require_shape(A_u_dims, [d, r])
            require_shape(A_v_dims, [r, d])
            require_shape(B_u_dims, [d, r])
            require_shape(B_v_dims, [r, p])
            require_shape(b_dims2, [d])

            Az = _lowrank_matvec(U_vals=A_u_vals, V_vals=A_v_vals, out_rows=d, rank=r, in_cols=d, x=z_t)
            Bu = _lowrank_matvec(U_vals=B_u_vals, V_vals=B_v_vals, out_rows=d, rank=r, in_cols=p, x=u_t)
            t = [0] * d
            _vec_add_inplace(t, Az)
            _vec_add_inplace(t, Bu)
            _vec_add_inplace(t, b_vals2)

            for i in range(d):
                x[i] = _add_sat_count(int(x[i]), _mul_q32_count(int(w_q32), int(t[i])))
            continue

        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "unknown patch_kind", "patch_kind": patch_kind})

    # Activation: hard_tanh_q32_v1 (clamp to [-1, 1] in Q32).
    for i in range(d):
        x[i] = _clamp_q32_count(int(x[i]))
    return [int(v) for v in x]


__all__ = [
    "z_transition_det_v1",
]
