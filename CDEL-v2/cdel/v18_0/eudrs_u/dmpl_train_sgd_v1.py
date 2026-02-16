"""DMPL deterministic SGD training math (v1).

Phase 4 contract:
  - Q32 only (signed int64 / 2^32).
  - Deterministic reduction order (ascending indices).
  - Subgradients:
      sign(x): +1 if x>0, -1 if x<0, 0 if x==0
      d/dx max(x,0): 1 if x>0 else 0
      d/dx hard_tanh(x): 1 if -1 < x < 1 else 0 (boundaries -> 0)
  - Gradient clipping: L1 norm (sum abs) across all grads.
  - SGD: param = param - lr * grad (mul_q32 then add_sat).

This module is RE2: deterministic and fail-closed via DMPLError.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from typing import Any

from .dmpl_action_encode_v1 import actenc_det_v1, hash_action_record_v1
from .dmpl_types_v1 import (
    DMPLError,
    DMPL_E_DIM_MISMATCH,
    DMPL_E_HASH_MISMATCH,
    DMPL_E_OPSET_MISMATCH,
    Q32_ONE,
    abs_q32,
    sign_q32,
)
from .eudrs_u_q32ops_v1 import add_sat, mul_q32, sat64
from .qxrl_opset_math_v1 import div_q32_pos_rne_v1


_MAGIC = b"DMPLTQ32"
_HDR16 = struct.Struct("<8sII")  # magic[8], version_u32, ndim_u32


def encode_tensor_q32_v1(*, dims_u32: list[int], values_i64: list[int]) -> bytes:
    if not isinstance(dims_u32, list) or not isinstance(values_i64, list):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "encode_tensor types"})
    out = bytearray()
    out += _MAGIC
    out += struct.pack("<II", 1, int(len(dims_u32)) & 0xFFFFFFFF)
    prod = 1
    for d in dims_u32:
        if not isinstance(d, int) or int(d) < 0 or int(d) > 0xFFFFFFFF:
            raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "dim"})
        out += struct.pack("<I", int(d) & 0xFFFFFFFF)
        prod *= int(d)
    if int(prod) != int(len(values_i64)):
        raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "value count", "expected": int(prod), "got": int(len(values_i64))})
    for v in values_i64:
        out += struct.pack("<q", int(v))
    return bytes(out)


def sha256_prefixed_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(bytes(data)).hexdigest()}"


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
            acc = add_sat(int(acc), int(mul_q32(int(M_vals[off + j]), int(x[j]))))
        out.append(int(acc))
    return out


def _dot_q32(a: list[int], b: list[int]) -> int:
    if len(a) != len(b):
        raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "dot shape"})
    acc = 0
    for i in range(len(a)):
        acc = add_sat(int(acc), int(mul_q32(int(a[i]), int(b[i]))))
    return int(acc)


def _hard_tanh_q32(x_q32: int) -> int:
    x = int(x_q32)
    if x < -int(Q32_ONE):
        return -int(Q32_ONE)
    if x > int(Q32_ONE):
        return int(Q32_ONE)
    return int(x)


def _hard_tanh_deriv_mask(x_pre_q32: int) -> int:
    # Returns 1 if -1 < x < 1 else 0, using Q32 bounds.
    x = int(x_pre_q32)
    if -int(Q32_ONE) < x < int(Q32_ONE):
        return 1
    return 0


def _q32_from_u32_pos(v_u32: int) -> int:
    v = int(v_u32)
    if v <= 0:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "u32 pos"})
    return int(v) << 32


def _div_q32_pos(*, numer_q32: int, denom_q32_pos: int) -> int:
    # Wrapper with DMPL errors.
    denom = int(denom_q32_pos)
    if denom <= 0:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "div denom <= 0"})
    try:
        return int(div_q32_pos_rne_v1(numer_q32_s64=int(numer_q32), denom_q32_pos_s64=int(denom), ctr=None))
    except Exception:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "div failed"})


@dataclass(frozen=True, slots=True)
class ConceptPatchEntryV1:
    concept_shard_id: str
    embed_vec_q32: list[int]  # [embed_dim]
    patch_kind: str  # "none"|"matrix_patch"|"lowrank_patch"
    # Forward patch tensors (all Q32, fixed artifacts).
    A_vals_q32: list[int] | None
    B_vals_q32: list[int] | None
    b_vals_q32: list[int] | None
    # Lowrank components (optional).
    rank_u32: int | None
    A_u_vals_q32: list[int] | None
    A_v_vals_q32: list[int] | None
    B_u_vals_q32: list[int] | None
    B_v_vals_q32: list[int] | None
    # Value patch.
    v_c0_q32: int
    w_vec_q32: list[int] | None  # [d] or None when w_bin_id==sha256:00..


def compute_gate_weights_v1(
    *,
    Wg_vals_q32: list[int],
    embed_dim_u32: int,
    d_u32: int,
    z_vec_q32: list[int],
    active_concepts: list[ConceptPatchEntryV1],
    normalize_weights_b: bool,
    epsilon_q32: int,
) -> tuple[list[int], list[int], list[int], int, int | None]:
    """Return (q_vec, g_list, alpha_list, Z_q32, invZ_q32_or_None) in concept order."""

    embed_dim = int(embed_dim_u32)
    d = int(d_u32)
    if len(z_vec_q32) != d:
        raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "z shape"})
    if len(Wg_vals_q32) != int(embed_dim) * int(d):
        raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "Wg shape"})

    # q = Wg @ z
    q_vec: list[int] = []
    for i in range(embed_dim):
        acc = 0
        row_off = i * d
        for j in range(d):
            acc = add_sat(int(acc), int(mul_q32(int(Wg_vals_q32[row_off + j]), int(z_vec_q32[j]))))
        q_vec.append(int(acc))

    g_list: list[int] = []
    alpha_list: list[int] = []
    for entry in list(active_concepts):
        g = _dot_q32(q_vec, entry.embed_vec_q32)
        g_list.append(int(g))
        alpha_list.append(int(g) if int(g) > 0 else 0)

    if not bool(normalize_weights_b):
        Z = 0
        if int(Z) != 0:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "Z init"})
        return q_vec, g_list, alpha_list, int(Z), None

    Z = int(epsilon_q32)
    for a in alpha_list:
        Z = add_sat(int(Z), int(a))
    if int(Z) <= 0:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "Z<=0"})
    invZ = _div_q32_pos(numer_q32=int(Q32_ONE), denom_q32_pos=int(Z))
    return q_vec, g_list, alpha_list, int(Z), int(invZ)


def compute_weights_from_alpha_v1(
    *,
    alpha_list_q32: list[int],
    normalize_weights_b: bool,
    invZ_q32: int | None,
) -> list[int]:
    if not bool(normalize_weights_b):
        return [int(a) for a in alpha_list_q32]
    if invZ_q32 is None:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "invZ missing"})
    w: list[int] = []
    invZ = int(invZ_q32)
    for a in alpha_list_q32:
        w.append(int(mul_q32(int(a), invZ)))
    return w


def backprop_gate_Wg_v1(
    *,
    dL_dw_q32: list[int],
    z_vec_q32: list[int],
    Wg_grad_q32: list[int],  # in/out, shape [embed_dim*d]
    embed_dim_u32: int,
    d_u32: int,
    active_concepts: list[ConceptPatchEntryV1],
    g_list_q32: list[int],
    alpha_list_q32: list[int],
    normalize_weights_b: bool,
    invZ_q32: int | None,
) -> None:
    """Accumulate dL/dWg into Wg_grad_q32 (saturating)."""

    embed_dim = int(embed_dim_u32)
    d = int(d_u32)
    if len(z_vec_q32) != d:
        raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "z shape"})
    if len(Wg_grad_q32) != int(embed_dim) * int(d):
        raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "Wg_grad shape"})
    if len(dL_dw_q32) != len(active_concepts) or len(g_list_q32) != len(active_concepts) or len(alpha_list_q32) != len(active_concepts):
        raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "gate list lens"})

    # Compute dL/dalpha.
    dL_dalpha: list[int] = []
    if not bool(normalize_weights_b):
        dL_dalpha = [int(v) for v in dL_dw_q32]
    else:
        if invZ_q32 is None:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "invZ missing"})
        invZ = int(invZ_q32)
        invZ_sq = int(mul_q32(invZ, invZ))
        S = 0
        for dLdw, alpha in zip(dL_dw_q32, alpha_list_q32, strict=True):
            S = add_sat(int(S), int(mul_q32(int(dLdw), int(alpha))))
        for dLdw in dL_dw_q32:
            term1 = int(mul_q32(int(dLdw), invZ))
            term2 = int(mul_q32(int(S), invZ_sq))
            dL_dalpha.append(int(add_sat(int(term1), int(-term2))))

    # dL/dg = dL/dalpha * I[g>0]
    dL_dg: list[int] = []
    for g, da in zip(g_list_q32, dL_dalpha, strict=True):
        dL_dg.append(int(da) if int(g) > 0 else 0)

    # dL/dq_k = sum_c dL/dg_c * e_c[k]
    dL_dq: list[int] = [0] * embed_dim
    for k in range(embed_dim):
        acc = 0
        for c_idx, entry in enumerate(active_concepts):
            acc = add_sat(int(acc), int(mul_q32(int(dL_dg[c_idx]), int(entry.embed_vec_q32[k]))))
        dL_dq[k] = int(acc)

    # q_k = sum_j Wg[k,j] * z_j -> dL/dWg[k,j] += dL/dq_k * z_j
    for k in range(embed_dim):
        dq = int(dL_dq[k])
        row_off = k * d
        for j in range(d):
            idx = row_off + j
            Wg_grad_q32[idx] = add_sat(int(Wg_grad_q32[idx]), int(mul_q32(dq, int(z_vec_q32[j]))))


def _compute_patch_t_vec_v1(
    *,
    patch: ConceptPatchEntryV1,
    z_vec_q32: list[int],
    u_vec_q32: list[int],
    d_u32: int,
    p_u32: int,
) -> list[int]:
    d = int(d_u32)
    p = int(p_u32)
    if len(z_vec_q32) != d or len(u_vec_q32) != p:
        raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "patch inputs"})
    kind = str(patch.patch_kind)
    if kind == "none":
        return [0] * d
    if kind == "matrix_patch":
        if patch.A_vals_q32 is None or patch.B_vals_q32 is None or patch.b_vals_q32 is None:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "matrix patch missing tensors"})
        t = _matvec(M_vals=patch.A_vals_q32, rows=d, cols=d, x=z_vec_q32)
        Bu = _matvec(M_vals=patch.B_vals_q32, rows=d, cols=p, x=u_vec_q32)
        for i in range(d):
            t[i] = add_sat(int(t[i]), int(Bu[i]))
            t[i] = add_sat(int(t[i]), int(patch.b_vals_q32[i]))
        return [int(v) for v in t]
    if kind == "lowrank_patch":
        r = int(patch.rank_u32 or 0)
        if r <= 0:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "lowrank rank"})
        if patch.A_u_vals_q32 is None or patch.A_v_vals_q32 is None or patch.B_u_vals_q32 is None or patch.B_v_vals_q32 is None or patch.b_vals_q32 is None:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "lowrank patch missing tensors"})
        # Az = A_u @ (A_v @ z)
        tmp_A = _matvec(M_vals=patch.A_v_vals_q32, rows=r, cols=d, x=z_vec_q32)
        Az = _matvec(M_vals=patch.A_u_vals_q32, rows=d, cols=r, x=tmp_A)
        # Bu = B_u @ (B_v @ u)
        tmp_B = _matvec(M_vals=patch.B_v_vals_q32, rows=r, cols=p, x=u_vec_q32)
        Bu = _matvec(M_vals=patch.B_u_vals_q32, rows=d, cols=r, x=tmp_B)
        t = [0] * d
        for i in range(d):
            t[i] = add_sat(int(t[i]), int(Az[i]))
            t[i] = add_sat(int(t[i]), int(Bu[i]))
            t[i] = add_sat(int(t[i]), int(patch.b_vals_q32[i]))
        return [int(v) for v in t]
    raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "unknown patch kind", "patch_kind": kind})


def _compute_inner_value_v1(*, patch: ConceptPatchEntryV1, z_vec_q32: list[int]) -> int:
    inner = int(patch.v_c0_q32)
    if patch.w_vec_q32 is None:
        return int(inner)
    return int(add_sat(int(inner), int(_dot_q32(patch.w_vec_q32, z_vec_q32))))


def _mean_L1_q32(*, z_pred_q32: list[int], z_true_q32: list[int]) -> int:
    if len(z_pred_q32) != len(z_true_q32):
        raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "L1 shape"})
    d = len(z_pred_q32)
    if d <= 0:
        raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "d<=0"})
    acc = 0
    for i in range(d):
        diff = add_sat(int(z_pred_q32[i]), int(-int(z_true_q32[i])))
        acc = add_sat(int(acc), int(abs_q32(diff)))
    denom = _q32_from_u32_pos(d)
    return _div_q32_pos(numer_q32=int(acc), denom_q32_pos=int(denom))


@dataclass(slots=True)
class TrainableStateV1:
    # Flat row-major Q32.
    A0_q32: list[int]  # [d*d]
    B0_q32: list[int]  # [d*p]
    b0_q32: list[int]  # [d]
    Wg_q32: list[int]  # [embed_dim*d]
    w0_q32: list[int]  # [d]
    v0_q32: int  # scalar Q32 (stored as i64)


@dataclass(frozen=True, slots=True)
class TrainStepResultV1:
    loss_pred_q32: int
    loss_value_q32: int
    loss_total_q32: int
    grad_norm_q32: int
    clipped_b: bool


def train_step_sgd_det_v1(
    *,
    d_u32: int,
    p_u32: int,
    embed_dim_u32: int,
    gamma_q32: int,
    normalize_weights_b: bool,
    epsilon_q32: int,
    max_grad_norm_q32: int,
    lr_q32: int,
    state: TrainableStateV1,
    batch: list[dict[str, Any]],
    concept_patches_by_sample: list[list[ConceptPatchEntryV1]],
    # For each sample: (action_obj dict already validated, z_t vec, z_tp1_true vec, ladder_level_u32)
    action_objs: list[dict[str, Any]],
    z_t_vecs_q32: list[list[int]],
    z_tp1_true_vecs_q32: list[list[int]],
) -> TrainStepResultV1:
    """Compute one deterministic SGD step and update `state` in-place."""

    d = int(d_u32)
    p = int(p_u32)
    embed_dim = int(embed_dim_u32)
    if d <= 0 or p < 0 or embed_dim <= 0:
        raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "dims"})

    if not isinstance(batch, list) or not batch:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "empty batch"})
    if len(concept_patches_by_sample) != len(batch) or len(action_objs) != len(batch) or len(z_t_vecs_q32) != len(batch) or len(z_tp1_true_vecs_q32) != len(batch):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "batch aux lens"})

    # Gradient accumulators.
    gA0: list[int] = [0] * (d * d)
    gB0: list[int] = [0] * (d * p)
    gb0: list[int] = [0] * d
    gWg: list[int] = [0] * (embed_dim * d)
    gw0: list[int] = [0] * d
    gv0: int = 0

    loss_pred_sum = 0
    loss_value_sum = 0

    for s_idx in range(len(batch)):
        z_t = z_t_vecs_q32[s_idx]
        z_true = z_tp1_true_vecs_q32[s_idx]
        if len(z_t) != d or len(z_true) != d:
            raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "z dims"})

        # ActEncDet from action record hash.
        a_hash_id, a_hash32 = hash_action_record_v1(action_objs[s_idx])
        del a_hash_id
        u_t = actenc_det_v1(a_hash32, int(p))

        # Gate weights for this sample's active concepts.
        concepts_t = concept_patches_by_sample[s_idx]
        q_vec, g_list, alpha_list, _Z, invZ = compute_gate_weights_v1(
            Wg_vals_q32=state.Wg_q32,
            embed_dim_u32=int(embed_dim),
            d_u32=int(d),
            z_vec_q32=z_t,
            active_concepts=concepts_t,
            normalize_weights_b=bool(normalize_weights_b),
            epsilon_q32=int(epsilon_q32),
        )
        weights = compute_weights_from_alpha_v1(alpha_list_q32=alpha_list, normalize_weights_b=bool(normalize_weights_b), invZ_q32=invZ)
        del q_vec

        # Forward prediction:
        # x_pre = A0 z + B0 u + b0 + sum_c w_c * t_c(z,u)
        x_pre = _matvec(M_vals=state.A0_q32, rows=d, cols=d, x=z_t)
        Bu = _matvec(M_vals=state.B0_q32, rows=d, cols=p, x=u_t)
        for i in range(d):
            x_pre[i] = add_sat(int(x_pre[i]), int(Bu[i]))
            x_pre[i] = add_sat(int(x_pre[i]), int(state.b0_q32[i]))

        t_vecs: list[list[int]] = []
        for c_idx, concept in enumerate(concepts_t):
            t = _compute_patch_t_vec_v1(patch=concept, z_vec_q32=z_t, u_vec_q32=u_t, d_u32=int(d), p_u32=int(p))
            t_vecs.append(t)
            w = int(weights[c_idx])
            for i in range(d):
                x_pre[i] = add_sat(int(x_pre[i]), int(mul_q32(w, int(t[i]))))

        z_pred: list[int] = []
        deriv_mask: list[int] = []
        for i in range(d):
            z_pred.append(_hard_tanh_q32(int(x_pre[i])))
            deriv_mask.append(_hard_tanh_deriv_mask(int(x_pre[i])))

        # Prediction loss (mean L1 over dims, then sum over batch).
        L_pred = _mean_L1_q32(z_pred_q32=z_pred, z_true_q32=z_true)
        loss_pred_sum = add_sat(int(loss_pred_sum), int(L_pred))

        # Backprop pred loss to x_pre.
        # dL/dz_pred_i = sign(diff_i) / d
        denom_d = _q32_from_u32_pos(d)
        grad_x: list[int] = [0] * d
        for i in range(d):
            diff = add_sat(int(z_pred[i]), int(-int(z_true[i])))
            sgn = sign_q32(diff)  # +/-Q32_ONE or 0
            dz = _div_q32_pos(numer_q32=int(sgn), denom_q32_pos=int(denom_d))
            grad_x[i] = int(dz) if int(deriv_mask[i]) == 1 else 0

        # Gradients for A0, B0, b0.
        for i in range(d):
            gx = int(grad_x[i])
            gb0[i] = add_sat(int(gb0[i]), gx)
            # A0 row i.
            row_off = i * d
            for j in range(d):
                gA0[row_off + j] = add_sat(int(gA0[row_off + j]), int(mul_q32(gx, int(z_t[j]))))
            # B0 row i.
            row_off_B = i * p
            for k in range(p):
                gB0[row_off_B + k] = add_sat(int(gB0[row_off_B + k]), int(mul_q32(gx, int(u_t[k]))))

        # Gradients wrt gate weights from pred loss (dL/dw_c = dot(grad_x, t_c)).
        dL_dw_pred: list[int] = []
        for c_idx in range(len(concepts_t)):
            dL_dw_pred.append(int(_dot_q32(grad_x, t_vecs[c_idx])))

        # Value forward on z_t (weights already computed) and on z_true (recompute gate).
        # Base V(z) = v0 + dot(w0, z) + sum_c w_c * inner_c(z)
        V_t = add_sat(int(state.v0_q32), int(_dot_q32(state.w0_q32, z_t)))
        inner_t: list[int] = []
        for c_idx, concept in enumerate(concepts_t):
            inner = _compute_inner_value_v1(patch=concept, z_vec_q32=z_t)
            inner_t.append(int(inner))
            V_t = add_sat(int(V_t), int(mul_q32(int(weights[c_idx]), int(inner))))

        # Gate + weights at tp1 (same concept set).
        _q2, g_list_tp1, alpha_list_tp1, _Z2, invZ2 = compute_gate_weights_v1(
            Wg_vals_q32=state.Wg_q32,
            embed_dim_u32=int(embed_dim),
            d_u32=int(d),
            z_vec_q32=z_true,
            active_concepts=concepts_t,
            normalize_weights_b=bool(normalize_weights_b),
            epsilon_q32=int(epsilon_q32),
        )
        del _q2
        weights_tp1 = compute_weights_from_alpha_v1(alpha_list_q32=alpha_list_tp1, normalize_weights_b=bool(normalize_weights_b), invZ_q32=invZ2)

        V_tp1 = add_sat(int(state.v0_q32), int(_dot_q32(state.w0_q32, z_true)))
        inner_tp1: list[int] = []
        for c_idx, concept in enumerate(concepts_t):
            inner = _compute_inner_value_v1(patch=concept, z_vec_q32=z_true)
            inner_tp1.append(int(inner))
            V_tp1 = add_sat(int(V_tp1), int(mul_q32(int(weights_tp1[c_idx]), int(inner))))

        target = mul_q32(int(gamma_q32), int(V_tp1))
        err = add_sat(int(V_t), int(-int(target)))
        L_v = abs_q32(err)
        loss_value_sum = add_sat(int(loss_value_sum), int(L_v))

        # Value loss gradients:
        # dL/dV_t = sign(err)
        # dL/dV_tp1 = -sign(err) * gamma
        s_err = sign_q32(err)  # Q32
        dL_dVt = int(s_err)
        dL_dVtp1 = int(-mul_q32(int(s_err), int(gamma_q32)))

        # v0, w0 grads.
        gv0 = add_sat(int(gv0), int(dL_dVt))
        gv0 = add_sat(int(gv0), int(dL_dVtp1))
        for j in range(d):
            gw0[j] = add_sat(int(gw0[j]), int(mul_q32(int(dL_dVt), int(z_t[j]))))
            gw0[j] = add_sat(int(gw0[j]), int(mul_q32(int(dL_dVtp1), int(z_true[j]))))

        # Gate grads from value loss at t and tp1.
        dL_dw_val_t: list[int] = []
        for c_idx in range(len(concepts_t)):
            dL_dw_val_t.append(int(mul_q32(int(dL_dVt), int(inner_t[c_idx]))))
        dL_dw_val_tp1: list[int] = []
        for c_idx in range(len(concepts_t)):
            dL_dw_val_tp1.append(int(mul_q32(int(dL_dVtp1), int(inner_tp1[c_idx]))))

        # Combine gate grads for z_t from pred and value.
        dL_dw_total_t: list[int] = []
        for a, b in zip(dL_dw_pred, dL_dw_val_t, strict=True):
            dL_dw_total_t.append(add_sat(int(a), int(b)))

        backprop_gate_Wg_v1(
            dL_dw_q32=dL_dw_total_t,
            z_vec_q32=z_t,
            Wg_grad_q32=gWg,
            embed_dim_u32=int(embed_dim),
            d_u32=int(d),
            active_concepts=concepts_t,
            g_list_q32=g_list,
            alpha_list_q32=alpha_list,
            normalize_weights_b=bool(normalize_weights_b),
            invZ_q32=invZ,
        )
        backprop_gate_Wg_v1(
            dL_dw_q32=dL_dw_val_tp1,
            z_vec_q32=z_true,
            Wg_grad_q32=gWg,
            embed_dim_u32=int(embed_dim),
            d_u32=int(d),
            active_concepts=concepts_t,
            g_list_q32=g_list_tp1,
            alpha_list_q32=alpha_list_tp1,
            normalize_weights_b=bool(normalize_weights_b),
            invZ_q32=invZ2,
        )

    # Total loss over batch.
    loss_total_sum = add_sat(int(loss_pred_sum), int(loss_value_sum))

    # Grad norm (L1 across all grads).
    grad_norm = 0
    for g in gA0:
        grad_norm = add_sat(int(grad_norm), int(abs_q32(g)))
    for g in gB0:
        grad_norm = add_sat(int(grad_norm), int(abs_q32(g)))
    for g in gb0:
        grad_norm = add_sat(int(grad_norm), int(abs_q32(g)))
    for g in gWg:
        grad_norm = add_sat(int(grad_norm), int(abs_q32(g)))
    for g in gw0:
        grad_norm = add_sat(int(grad_norm), int(abs_q32(g)))
    grad_norm = add_sat(int(grad_norm), int(abs_q32(gv0)))

    clipped_b = False
    if int(grad_norm) > int(max_grad_norm_q32) and int(grad_norm) > 0 and int(max_grad_norm_q32) >= 0:
        clipped_b = True
        scale = _div_q32_pos(numer_q32=int(max_grad_norm_q32), denom_q32_pos=int(grad_norm))
        for i in range(len(gA0)):
            gA0[i] = int(mul_q32(int(gA0[i]), int(scale)))
        for i in range(len(gB0)):
            gB0[i] = int(mul_q32(int(gB0[i]), int(scale)))
        for i in range(len(gb0)):
            gb0[i] = int(mul_q32(int(gb0[i]), int(scale)))
        for i in range(len(gWg)):
            gWg[i] = int(mul_q32(int(gWg[i]), int(scale)))
        for i in range(len(gw0)):
            gw0[i] = int(mul_q32(int(gw0[i]), int(scale)))
        gv0 = int(mul_q32(int(gv0), int(scale)))

    # SGD update in-place.
    lr = int(lr_q32)
    for i in range(len(state.A0_q32)):
        delta = int(mul_q32(lr, int(gA0[i])))
        state.A0_q32[i] = int(add_sat(int(state.A0_q32[i]), int(-delta)))
    for i in range(len(state.B0_q32)):
        delta = int(mul_q32(lr, int(gB0[i])))
        state.B0_q32[i] = int(add_sat(int(state.B0_q32[i]), int(-delta)))
    for i in range(len(state.b0_q32)):
        delta = int(mul_q32(lr, int(gb0[i])))
        state.b0_q32[i] = int(add_sat(int(state.b0_q32[i]), int(-delta)))
    for i in range(len(state.Wg_q32)):
        delta = int(mul_q32(lr, int(gWg[i])))
        state.Wg_q32[i] = int(add_sat(int(state.Wg_q32[i]), int(-delta)))
    for i in range(len(state.w0_q32)):
        delta = int(mul_q32(lr, int(gw0[i])))
        state.w0_q32[i] = int(add_sat(int(state.w0_q32[i]), int(-delta)))
    state.v0_q32 = int(add_sat(int(state.v0_q32), int(-int(mul_q32(lr, int(gv0))))))

    return TrainStepResultV1(
        loss_pred_q32=int(loss_pred_sum),
        loss_value_q32=int(loss_value_sum),
        loss_total_q32=int(loss_total_sum),
        grad_norm_q32=int(grad_norm),
        clipped_b=bool(clipped_b),
    )


__all__ = [
    "ConceptPatchEntryV1",
    "TrainStepResultV1",
    "TrainableStateV1",
    "encode_tensor_q32_v1",
    "sha256_prefixed_bytes",
    "train_step_sgd_det_v1",
]

