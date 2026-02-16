"""QXRL backward pass + hinge loss subgradients (v1).

This module is RE2: deterministic, fail-closed, no floats.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from ..omega_common_v1 import Q32_ONE, fail
from .qxrl_common_v1 import ENCODER_KIND_TSAE_V1, REASON_QXRL_SCHEMA_INVALID
from .qxrl_forward_qre_v1 import QXRLForwardCacheV1, QXRLModelSpecV1, QXRLWeightsViewV1
from .qxrl_forward_tsae_v1 import QXRLTSAEForwardCacheV1, QXRLWeightsViewTSAEV1
from .qxrl_opset_math_v1 import NEG_HALF_Q32, div_q32_pos_rne_v1
from .qxrl_ops_v1 import QXRLStepCountersV1, add_sat, clip_abs_q32, dot_q32_v1_flat, mul_q32


@dataclass(frozen=True, slots=True)
class QXRLLossesV1:
    mlm_loss_q32_s64: int
    ctr_loss_q32_s64: int
    total_loss_q32_s64: int


def _require_len(vec: list[int], n: int) -> None:
    if not isinstance(vec, list) or len(vec) != int(n):
        fail(REASON_QXRL_SCHEMA_INVALID)


def _add_inplace(dst: list[int], off: int, src: list[int], ctr: QXRLStepCountersV1) -> None:
    if not isinstance(dst, list) or not isinstance(src, list):
        fail(REASON_QXRL_SCHEMA_INVALID)
    base = int(off)
    if base < 0 or base + len(src) > len(dst):
        fail(REASON_QXRL_SCHEMA_INVALID)
    for i, v in enumerate(src):
        dst[base + i] = add_sat(int(dst[base + i]), int(v), ctr)


def _mul_vec_scalar(vec: list[int], scalar_q32_s64: int, ctr: QXRLStepCountersV1) -> list[int]:
    return [mul_q32(int(v), int(scalar_q32_s64), ctr) for v in vec]


def _outer_add(
    *,
    grad_mat: list[int],
    rows: int,
    cols: int,
    row_index: int,
    scale_q32_s64: int,
    vec: list[int],
    ctr: QXRLStepCountersV1,
) -> None:
    # grad_mat[row, col] += scale * vec[col]
    r = int(row_index)
    R = int(rows)
    C = int(cols)
    if r < 0 or r >= R:
        fail(REASON_QXRL_SCHEMA_INVALID)
    _require_len(vec, C)
    if len(grad_mat) != R * C:
        fail(REASON_QXRL_SCHEMA_INVALID)
    base = r * C
    s = int(scale_q32_s64)
    for c in range(C):
        grad_mat[base + c] = add_sat(int(grad_mat[base + c]), int(mul_q32(s, int(vec[c]), ctr)), ctr)


def _matT_vec_add(
    *,
    dst_vec: list[int],
    mat: list[int],
    rows: int,
    cols: int,
    src_vec: list[int],
    ctr: QXRLStepCountersV1,
) -> None:
    # dst[c] += sum_r src[r] * mat[r,c]
    R = int(rows)
    C = int(cols)
    _require_len(dst_vec, C)
    _require_len(src_vec, R)
    if len(mat) != R * C:
        fail(REASON_QXRL_SCHEMA_INVALID)
    for r in range(R):
        s = int(src_vec[r])
        row_off = r * C
        for c in range(C):
            dst_vec[c] = add_sat(int(dst_vec[c]), int(mul_q32(s, int(mat[row_off + c]), ctr)), ctr)


def _hinge_loss(
    *,
    margin_q32_s64: int,
    s_pos_q32_s64: int,
    s_neg_max_q32_s64: int,
    ctr: QXRLStepCountersV1,
) -> tuple[int, bool]:
    # L = ReLU(margin - s_pos + s_neg_max)
    t = add_sat(int(margin_q32_s64), -int(s_pos_q32_s64), ctr)
    t = add_sat(int(t), int(s_neg_max_q32_s64), ctr)
    if int(t) <= 0:
        return 0, False
    return int(t), True


def backward_encoder_qre_v1_add_grads(
    *,
    model: QXRLModelSpecV1,
    weights: QXRLWeightsViewV1,
    cache: QXRLForwardCacheV1,
    dz_q32_s64: list[int],  # [d_embed]
    grad_tok_emb: list[int],
    grad_pos_emb: list[int],
    grad_enc_w1: list[int],
    grad_enc_b1: list[int],
    grad_enc_w2: list[int],
    grad_enc_b2: list[int],
    ctr: QXRLStepCountersV1,
) -> None:
    d_model = int(model.d_model_u32)
    d_hidden = int(model.d_hidden_u32)
    d_embed = int(model.d_embed_u32)
    seq_len = int(model.seq_len_u32)
    vocab = int(model.vocab_size_u32)

    _require_len(dz_q32_s64, d_embed)
    _require_len(cache.a1_q32_s64, d_hidden)
    _require_len(cache.u1_q32_s64, d_hidden)
    _require_len(cache.pooled_q32_s64, d_model)
    if len(cache.h0_flat_q32_s64) != seq_len * d_model:
        fail(REASON_QXRL_SCHEMA_INVALID)

    if len(grad_tok_emb) != vocab * d_model:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if len(grad_pos_emb) != seq_len * d_model:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if len(grad_enc_w1) != d_hidden * d_model or len(grad_enc_b1) != d_hidden:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if len(grad_enc_w2) != d_embed * d_hidden or len(grad_enc_b2) != d_embed:
        fail(REASON_QXRL_SCHEMA_INVALID)

    # z = enc_w2 * a1 + enc_b2
    # grads: enc_b2 += dz; enc_w2 += outer(dz, a1); da1 += W2^T * dz
    da1 = [0] * d_hidden
    for k in range(d_embed):
        dzk = int(dz_q32_s64[k])
        grad_enc_b2[k] = add_sat(int(grad_enc_b2[k]), dzk, ctr)
        _outer_add(
            grad_mat=grad_enc_w2,
            rows=d_embed,
            cols=d_hidden,
            row_index=k,
            scale_q32_s64=dzk,
            vec=cache.a1_q32_s64,
            ctr=ctr,
        )

        # da1 += dzk * enc_w2[k,*]
        row_off = k * d_hidden
        for j in range(d_hidden):
            da1[j] = add_sat(int(da1[j]), int(mul_q32(dzk, int(weights.enc_w2[row_off + j]), ctr)), ctr)

    # a1 = ReLU(u1)
    du1 = [0] * d_hidden
    for j in range(d_hidden):
        if int(cache.u1_q32_s64[j]) > 0:
            du1[j] = int(da1[j])
        else:
            du1[j] = 0

    # u1 = enc_w1 * pooled + enc_b1
    dpooled = [0] * d_model
    for j in range(d_hidden):
        du = int(du1[j])
        grad_enc_b1[j] = add_sat(int(grad_enc_b1[j]), du, ctr)
        _outer_add(
            grad_mat=grad_enc_w1,
            rows=d_hidden,
            cols=d_model,
            row_index=j,
            scale_q32_s64=du,
            vec=cache.pooled_q32_s64,
            ctr=ctr,
        )

        row_off = j * d_model
        for i in range(d_model):
            dpooled[i] = add_sat(int(dpooled[i]), int(mul_q32(du, int(weights.enc_w1[row_off + i]), ctr)), ctr)

    # pooled = sum_h0 * inv_seq_len
    dsum_h0 = [mul_q32(int(dpooled[i]), int(model.inv_seq_len_q32), ctr) for i in range(d_model)]

    # sum_h0 = Σ_p h0[p]; h0[p] = tok_emb[tok[p]] + pos_emb[p]
    for p in range(seq_len):
        tok_id = int(cache.tokens_u32[p])
        if tok_id < 0 or tok_id >= vocab:
            fail(REASON_QXRL_SCHEMA_INVALID)
        h0_off = p * d_model
        tok_off = tok_id * d_model
        pos_off = p * d_model
        for i in range(d_model):
            g = int(dsum_h0[i])
            grad_tok_emb[tok_off + i] = add_sat(int(grad_tok_emb[tok_off + i]), g, ctr)
            grad_pos_emb[pos_off + i] = add_sat(int(grad_pos_emb[pos_off + i]), g, ctr)


def backward_mlm_hinge_for_masked_pos_add_grads(
    *,
    model: QXRLModelSpecV1,
    weights: QXRLWeightsViewV1,
    cache_masked_anchor: QXRLForwardCacheV1,
    masked_pos_u32: int,
    true_token_id_u32: int,
    neg_token_ids_u32: list[int],
    mlm_margin_q32_s64: int,
    mlm_loss_weight_q32_s64: int,
    grad_tok_emb: list[int],
    grad_pos_emb: list[int],
    grad_tok_proj_w: list[int],
    grad_tok_proj_b: list[int],
    grad_out_emb: list[int],
    grad_out_b: list[int],
    ctr: QXRLStepCountersV1,
) -> int:
    """Backprop one masked-position MLM hinge; returns L_mlm (Q32 s64)."""

    p = int(masked_pos_u32)
    y = int(true_token_id_u32)
    vocab = int(model.vocab_size_u32)
    d_model = int(model.d_model_u32)
    d_embed = int(model.d_embed_u32)
    seq_len = int(model.seq_len_u32)

    if p < 0 or p >= seq_len:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if y < 0 or y >= vocab:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if not isinstance(neg_token_ids_u32, list) or not neg_token_ids_u32:
        fail(REASON_QXRL_SCHEMA_INVALID)

    if len(grad_tok_proj_w) != d_embed * d_model or len(grad_tok_proj_b) != d_embed:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if len(grad_out_emb) != vocab * d_embed or len(grad_out_b) != vocab:
        fail(REASON_QXRL_SCHEMA_INVALID)

    # Compute t = tok_proj_w * h0[p] + tok_proj_b.
    h0_off = p * d_model
    t = [0] * d_embed
    for k in range(d_embed):
        dot = dot_q32_v1_flat(
            dot_kind=model.dot_kind,
            x_q32_s64=weights.tok_proj_w,
            x_off=k * d_model,
            y_q32_s64=cache_masked_anchor.h0_flat_q32_s64,
            y_off=h0_off,
            n=d_model,
            ctr=ctr,
        )
        t[k] = add_sat(int(weights.tok_proj_b[k]), int(dot), ctr)

    # Compute s_pos and best negative.
    s_pos = add_sat(
        int(weights.out_b[y]),
        int(
            dot_q32_v1_flat(
                dot_kind=model.dot_kind,
                x_q32_s64=weights.out_emb,
                x_off=y * d_embed,
                y_q32_s64=t,
                y_off=0,
                n=d_embed,
                ctr=ctr,
            )
        ),
        ctr,
    )

    best_neg = None
    best_neg_score = None
    for n_tok in neg_token_ids_u32:
        n = int(n_tok)
        if n < 0 or n >= vocab:
            fail(REASON_QXRL_SCHEMA_INVALID)
        s = add_sat(
            int(weights.out_b[n]),
            int(
                dot_q32_v1_flat(
                    dot_kind=model.dot_kind,
                    x_q32_s64=weights.out_emb,
                    x_off=n * d_embed,
                    y_q32_s64=t,
                    y_off=0,
                    n=d_embed,
                    ctr=ctr,
                )
            ),
            ctr,
        )
        if best_neg is None or int(s) > int(best_neg_score) or (int(s) == int(best_neg_score) and int(n) < int(best_neg)):
            best_neg = int(n)
            best_neg_score = int(s)

    if best_neg is None or best_neg_score is None:
        fail(REASON_QXRL_SCHEMA_INVALID)

    loss, active = _hinge_loss(margin_q32_s64=int(mlm_margin_q32_s64), s_pos_q32_s64=int(s_pos), s_neg_max_q32_s64=int(best_neg_score), ctr=ctr)
    if not active:
        return int(loss)

    # dL/ds_pos = -mlm_loss_weight; dL/ds_neg = +mlm_loss_weight.
    dpos = -int(mlm_loss_weight_q32_s64)
    dneg = int(mlm_loss_weight_q32_s64)

    # Backprop through s = out_b[v] + dot(out_emb[v], t)
    dt = [0] * d_embed

    def _accum_score_grad(v: int, ds: int) -> None:
        grad_out_b[v] = add_sat(int(grad_out_b[v]), int(ds), ctr)
        row_off = v * d_embed
        # grad_out_emb[v,*] += ds * t
        for k in range(d_embed):
            grad_out_emb[row_off + k] = add_sat(int(grad_out_emb[row_off + k]), int(mul_q32(int(ds), int(t[k]), ctr)), ctr)
            dt[k] = add_sat(int(dt[k]), int(mul_q32(int(ds), int(weights.out_emb[row_off + k]), ctr)), ctr)

    _accum_score_grad(int(y), int(dpos))
    _accum_score_grad(int(best_neg), int(dneg))

    # Backprop through t = tok_proj_w * h0 + tok_proj_b
    for k in range(d_embed):
        grad_tok_proj_b[k] = add_sat(int(grad_tok_proj_b[k]), int(dt[k]), ctr)
        # grad_tok_proj_w[k,*] += dt[k] * h0[p,*]
        row_off = k * d_model
        for i in range(d_model):
            grad_tok_proj_w[row_off + i] = add_sat(
                int(grad_tok_proj_w[row_off + i]),
                int(mul_q32(int(dt[k]), int(cache_masked_anchor.h0_flat_q32_s64[h0_off + i]), ctr)),
                ctr,
            )

    # dh0 = tok_proj_w^T * dt
    dh0 = [0] * d_model
    for k in range(d_embed):
        row_off = k * d_model
        for i in range(d_model):
            dh0[i] = add_sat(int(dh0[i]), int(mul_q32(int(dt[k]), int(weights.tok_proj_w[row_off + i]), ctr)), ctr)

    # h0[p] = tok_emb[tok_id] + pos_emb[p]
    tok_id = int(cache_masked_anchor.tokens_u32[p])
    if tok_id < 0 or tok_id >= vocab:
        fail(REASON_QXRL_SCHEMA_INVALID)
    tok_off = tok_id * d_model
    pos_off = p * d_model
    for i in range(d_model):
        grad_tok_emb[tok_off + i] = add_sat(int(grad_tok_emb[tok_off + i]), int(dh0[i]), ctr)
        grad_pos_emb[pos_off + i] = add_sat(int(grad_pos_emb[pos_off + i]), int(dh0[i]), ctr)

    return int(loss)


def ctr_hinge_and_dz_for_batch(
    *,
    z_a_by_example: list[list[int]],
    z_p_by_example: list[list[int]],
    ctr_margin_q32_s64: int,
    ctr_loss_weight_q32_s64: int,
    dot_kind: str,
    ctr: QXRLStepCountersV1,
) -> tuple[list[list[int]], list[list[int]], list[int]]:
    """Compute CTR losses and return (dz_a, dz_p, L_ctr_by_example)."""

    if not isinstance(z_a_by_example, list) or not isinstance(z_p_by_example, list) or len(z_a_by_example) != len(z_p_by_example):
        fail(REASON_QXRL_SCHEMA_INVALID)
    B = len(z_a_by_example)
    if B <= 0:
        fail(REASON_QXRL_SCHEMA_INVALID)
    d_embed = len(z_a_by_example[0])
    if d_embed <= 0:
        fail(REASON_QXRL_SCHEMA_INVALID)
    for row in z_a_by_example:
        _require_len(row, d_embed)
    for row in z_p_by_example:
        _require_len(row, d_embed)

    dz_a = [[0] * d_embed for _ in range(B)]
    dz_p = [[0] * d_embed for _ in range(B)]
    losses: list[int] = [0] * B

    for i in range(B):
        s_pos = dot_q32_v1_flat(dot_kind=dot_kind, x_q32_s64=z_a_by_example[i], x_off=0, y_q32_s64=z_p_by_example[i], y_off=0, n=d_embed, ctr=ctr)
        best_j = None
        best_s = None
        for j in range(B):
            if j == i:
                continue
            s = dot_q32_v1_flat(dot_kind=dot_kind, x_q32_s64=z_a_by_example[i], x_off=0, y_q32_s64=z_p_by_example[j], y_off=0, n=d_embed, ctr=ctr)
            if best_j is None or int(s) > int(best_s) or (int(s) == int(best_s) and int(j) < int(best_j)):
                best_j = int(j)
                best_s = int(s)
        if best_j is None or best_s is None:
            fail(REASON_QXRL_SCHEMA_INVALID)

        loss, active = _hinge_loss(margin_q32_s64=int(ctr_margin_q32_s64), s_pos_q32_s64=int(s_pos), s_neg_max_q32_s64=int(best_s), ctr=ctr)
        losses[i] = int(loss)
        if not active:
            continue

        # dL/ds_pos=-w; dL/ds_neg=+w.
        dpos = -int(ctr_loss_weight_q32_s64)
        dneg = int(ctr_loss_weight_q32_s64)

        # dz_a[i] += dpos*z_p[i] + dneg*z_p[best_j]
        for k in range(d_embed):
            dz_a[i][k] = add_sat(int(dz_a[i][k]), int(mul_q32(int(dpos), int(z_p_by_example[i][k]), ctr)), ctr)
            dz_a[i][k] = add_sat(int(dz_a[i][k]), int(mul_q32(int(dneg), int(z_p_by_example[int(best_j)][k]), ctr)), ctr)

        # dz_p[i] += dpos*z_a[i]
        for k in range(d_embed):
            dz_p[i][k] = add_sat(int(dz_p[i][k]), int(mul_q32(int(dpos), int(z_a_by_example[i][k]), ctr)), ctr)

        # dz_p[best_j] += dneg*z_a[i]
        for k in range(d_embed):
            dz_p[int(best_j)][k] = add_sat(int(dz_p[int(best_j)][k]), int(mul_q32(int(dneg), int(z_a_by_example[i][k]), ctr)), ctr)

    return dz_a, dz_p, losses


def backward_mlm_hinge_for_masked_pos_add_grads_tsae_v1(
    *,
    model: QXRLModelSpecV1,
    weights: QXRLWeightsViewTSAEV1,
    cache_masked_anchor: QXRLTSAEForwardCacheV1,
    masked_pos_u32: int,
    true_token_id_u32: int,
    neg_token_ids_u32: list[int],
    mlm_margin_q32_s64: int,
    mlm_loss_weight_q32_s64: int,
    grad_tok_proj_w: list[int],
    grad_tok_proj_b: list[int],
    grad_out_emb: list[int],
    grad_out_b: list[int],
    dxL_flat_q32_s64: list[int],  # [S * d_model], accumulates dL/dxL
    ctr: QXRLStepCountersV1,
) -> int:
    """TSAE MLM hinge backprop: writes grads and accumulates dL/dxL for one masked position."""

    if str(model.encoder_kind).strip() != ENCODER_KIND_TSAE_V1:
        fail(REASON_QXRL_SCHEMA_INVALID)

    p = int(masked_pos_u32)
    y = int(true_token_id_u32)
    vocab = int(model.vocab_size_u32)
    S = int(model.seq_len_u32)
    d_model = int(model.d_model_u32)
    d_embed = int(model.d_embed_u32)

    if p < 0 or p >= S:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if y < 0 or y >= vocab:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if not isinstance(neg_token_ids_u32, list) or not neg_token_ids_u32:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if len(dxL_flat_q32_s64) != S * d_model:
        fail(REASON_QXRL_SCHEMA_INVALID)

    if len(grad_tok_proj_w) != d_embed * d_model or len(grad_tok_proj_b) != d_embed:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if len(grad_out_emb) != vocab * d_embed or len(grad_out_b) != vocab:
        fail(REASON_QXRL_SCHEMA_INVALID)

    # Compute t = tok_proj_w * xL[p] + tok_proj_b.
    x_off = p * d_model
    t = [0] * d_embed
    for k in range(d_embed):
        dot = dot_q32_v1_flat(
            dot_kind=model.dot_kind,
            x_q32_s64=weights.tok_proj_w,
            x_off=k * d_model,
            y_q32_s64=cache_masked_anchor.xL_flat_q32_s64,
            y_off=x_off,
            n=d_model,
            ctr=ctr,
        )
        t[k] = add_sat(int(weights.tok_proj_b[k]), int(dot), ctr)

    # Compute s_pos and best negative.
    s_pos = add_sat(
        int(weights.out_b[y]),
        int(dot_q32_v1_flat(dot_kind=model.dot_kind, x_q32_s64=weights.out_emb, x_off=y * d_embed, y_q32_s64=t, y_off=0, n=d_embed, ctr=ctr)),
        ctr,
    )

    best_neg = None
    best_neg_score = None
    for n_tok in neg_token_ids_u32:
        n = int(n_tok)
        if n < 0 or n >= vocab:
            fail(REASON_QXRL_SCHEMA_INVALID)
        s = add_sat(
            int(weights.out_b[n]),
            int(dot_q32_v1_flat(dot_kind=model.dot_kind, x_q32_s64=weights.out_emb, x_off=n * d_embed, y_q32_s64=t, y_off=0, n=d_embed, ctr=ctr)),
            ctr,
        )
        if best_neg is None or int(s) > int(best_neg_score) or (int(s) == int(best_neg_score) and int(n) < int(best_neg)):
            best_neg = int(n)
            best_neg_score = int(s)

    if best_neg is None or best_neg_score is None:
        fail(REASON_QXRL_SCHEMA_INVALID)

    loss, active = _hinge_loss(margin_q32_s64=int(mlm_margin_q32_s64), s_pos_q32_s64=int(s_pos), s_neg_max_q32_s64=int(best_neg_score), ctr=ctr)
    if not active:
        return int(loss)

    # dL/ds_pos = -w; dL/ds_neg = +w.
    dpos = -int(mlm_loss_weight_q32_s64)
    dneg = int(mlm_loss_weight_q32_s64)

    dt = [0] * d_embed

    def _accum_score_grad(v: int, ds: int) -> None:
        grad_out_b[v] = add_sat(int(grad_out_b[v]), int(ds), ctr)
        row_off = v * d_embed
        for k in range(d_embed):
            grad_out_emb[row_off + k] = add_sat(int(grad_out_emb[row_off + k]), int(mul_q32(int(ds), int(t[k]), ctr)), ctr)
            dt[k] = add_sat(int(dt[k]), int(mul_q32(int(ds), int(weights.out_emb[row_off + k]), ctr)), ctr)

    _accum_score_grad(int(y), int(dpos))
    _accum_score_grad(int(best_neg), int(dneg))

    # Backprop through t = tok_proj_w * xL + tok_proj_b.
    for k in range(d_embed):
        grad_tok_proj_b[k] = add_sat(int(grad_tok_proj_b[k]), int(dt[k]), ctr)
        row_off = k * d_model
        for i in range(d_model):
            grad_tok_proj_w[row_off + i] = add_sat(
                int(grad_tok_proj_w[row_off + i]),
                int(mul_q32(int(dt[k]), int(cache_masked_anchor.xL_flat_q32_s64[x_off + i]), ctr)),
                ctr,
            )

    # dxL[p] += tok_proj_w^T * dt.
    dx = [0] * d_model
    for k in range(d_embed):
        row_off = k * d_model
        for i in range(d_model):
            dx[i] = add_sat(int(dx[i]), int(mul_q32(int(dt[k]), int(weights.tok_proj_w[row_off + i]), ctr)), ctr)
    for i in range(d_model):
        dxL_flat_q32_s64[x_off + i] = add_sat(int(dxL_flat_q32_s64[x_off + i]), int(dx[i]), ctr)

    return int(loss)


def _rmsnorm_backward_v1(
    *,
    x_q32_s64: list[int],
    gamma_q32_s64: list[int],
    r_q32_s64: int,
    gout_q32_s64: list[int],
    grad_gamma_q32_s64: list[int],
    ctr: QXRLStepCountersV1,
) -> list[int]:
    """RMSNorm backward (Phase 5 exact rule). Returns dx and accumulates grad_gamma."""

    d_model = len(x_q32_s64)
    if d_model <= 0 or len(gamma_q32_s64) != d_model or len(gout_q32_s64) != d_model or len(grad_gamma_q32_s64) != d_model:
        fail(REASON_QXRL_SCHEMA_INVALID)

    r = int(r_q32_s64)
    # u_i = x_i * r
    u = [mul_q32(int(x_q32_s64[i]), int(r), ctr) for i in range(d_model)]

    # ggamma_i = gout_i * u_i; gu_i = gout_i * gamma_i
    gu = [0] * d_model
    for i in range(d_model):
        grad_gamma_q32_s64[i] = add_sat(int(grad_gamma_q32_s64[i]), int(mul_q32(int(gout_q32_s64[i]), int(u[i]), ctr)), ctr)
        gu[i] = mul_q32(int(gout_q32_s64[i]), int(gamma_q32_s64[i]), ctr)

    # dx_i_base = gu_i * r
    dx_base = [mul_q32(int(gu[i]), int(r), ctr) for i in range(d_model)]

    # gr = Σ_i gu_i * x_i
    gr = 0
    for i in range(d_model):
        gr = add_sat(int(gr), int(mul_q32(int(gu[i]), int(x_q32_s64[i]), ctr)), ctr)

    # g_mean_sq = gr * (-0.5) * r^3
    r2 = mul_q32(int(r), int(r), ctr)
    r3 = mul_q32(int(r2), int(r), ctr)
    g_mean_sq = mul_q32(int(gr), int(mul_q32(int(NEG_HALF_Q32), int(r3), ctr)), ctr)

    # two_over_d = (2/d)
    inv_d_q32 = div_q32_pos_rne_v1(numer_q32_s64=int(Q32_ONE), denom_q32_pos_s64=int(int(d_model) << 32), ctr=ctr)
    two_over_d_q32 = mul_q32(int(2 << 32), int(inv_d_q32), ctr)

    # dx_i_add = g_mean_sq * (2/d) * x_i
    dx_add_scale = mul_q32(int(g_mean_sq), int(two_over_d_q32), ctr)
    dx = [0] * d_model
    for i in range(d_model):
        dx_add = mul_q32(int(dx_add_scale), int(x_q32_s64[i]), ctr)
        dx[i] = add_sat(int(dx_base[i]), int(dx_add), ctr)
    return dx


def backward_encoder_tsae_v1_add_grads(
    *,
    model: QXRLModelSpecV1,
    weights: QXRLWeightsViewTSAEV1,
    cache: QXRLTSAEForwardCacheV1,
    dz_q32_s64: list[int] | None,  # [d_embed] or None
    dxL_flat_q32_s64: list[int] | None,  # [S*d_model] or None
    grads_by_name: dict[str, list[int]],
    ctr: QXRLStepCountersV1,
) -> None:
    """Backprop through TSAE encoder to accumulate grads for trainable tensors."""

    if str(model.encoder_kind).strip() != ENCODER_KIND_TSAE_V1:
        fail(REASON_QXRL_SCHEMA_INVALID)

    vocab = int(model.vocab_size_u32)
    S = int(model.seq_len_u32)
    d_model = int(model.d_model_u32)
    d_embed = int(model.d_embed_u32)
    n_layers = int(model.n_layers_u32)
    n_heads = int(model.n_heads_u32)
    d_head = int(model.d_head_u32)
    d_ff = int(model.d_ff_u32)
    K = int(model.topk_u32)

    if d_model != n_heads * d_head:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if K < 1 or K > S:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if not isinstance(cache.layers, list) or len(cache.layers) != n_layers:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if not isinstance(weights.layers, list) or len(weights.layers) != n_layers:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if len(cache.tokens_u32) != S or len(cache.xL_flat_q32_s64) != S * d_model:
        fail(REASON_QXRL_SCHEMA_INVALID)

    # Initialize dx = dL/dxL (token reps after final layer).
    dx = [0] * (S * d_model)
    if dxL_flat_q32_s64 is not None:
        if len(dxL_flat_q32_s64) != S * d_model:
            fail(REASON_QXRL_SCHEMA_INVALID)
        for i in range(S * d_model):
            dx[i] = int(dxL_flat_q32_s64[i])

    # dz path (contrastive): z = proj_w*pooled + proj_b; pooled=(sum xL)*inv_seq_len.
    if dz_q32_s64 is not None:
        if len(dz_q32_s64) != d_embed:
            fail(REASON_QXRL_SCHEMA_INVALID)
        grad_proj_w = grads_by_name.get("qxrl/tsae/proj_w")
        grad_proj_b = grads_by_name.get("qxrl/tsae/proj_b")
        if grad_proj_w is None or grad_proj_b is None:
            fail(REASON_QXRL_SCHEMA_INVALID)
        if len(grad_proj_w) != d_embed * d_model or len(grad_proj_b) != d_embed:
            fail(REASON_QXRL_SCHEMA_INVALID)

        gpooled = [0] * d_model
        for k in range(d_embed):
            dzk = int(dz_q32_s64[k])
            grad_proj_b[k] = add_sat(int(grad_proj_b[k]), int(dzk), ctr)
            row_off = k * d_model
            for i in range(d_model):
                grad_proj_w[row_off + i] = add_sat(int(grad_proj_w[row_off + i]), int(mul_q32(int(dzk), int(cache.pooled_q32_s64[i]), ctr)), ctr)
                gpooled[i] = add_sat(int(gpooled[i]), int(mul_q32(int(dzk), int(weights.proj_w[row_off + i]), ctr)), ctr)

        # pooled = sum_x * inv_seq_len => dsum = dpooled * inv_seq_len.
        dsum = [mul_q32(int(gpooled[i]), int(model.inv_seq_len_q32), ctr) for i in range(d_model)]
        for p in range(S):
            base = p * d_model
            for i in range(d_model):
                dx[base + i] = add_sat(int(dx[base + i]), int(dsum[i]), ctr)

    # Backprop through layers (reverse).
    for layer_index in range(n_layers - 1, -1, -1):
        layer_cache = cache.layers[layer_index]
        layer_w = weights.layers[layer_index]

        if len(layer_cache.x_in_flat_q32_s64) != S * d_model or len(layer_cache.x1_flat_q32_s64) != S * d_model:
            fail(REASON_QXRL_SCHEMA_INVALID)
        if len(layer_cache.rms1_r_by_pos_q32_s64) != S or len(layer_cache.rms2_r_by_pos_q32_s64) != S:
            fail(REASON_QXRL_SCHEMA_INVALID)
        if len(layer_cache.q_all_flat_q32_s64) != S * d_model or len(layer_cache.k_all_flat_q32_s64) != S * d_model or len(layer_cache.v_all_flat_q32_s64) != S * d_model:
            fail(REASON_QXRL_SCHEMA_INVALID)
        if len(layer_cache.attn_out_flat_q32_s64) != S * d_model:
            fail(REASON_QXRL_SCHEMA_INVALID)
        if len(layer_cache.topk_idx_u32) != S * n_heads * K or len(layer_cache.attn_a_q32_s64) != S * n_heads * K or len(layer_cache.attn_sum_a_q32_s64) != S * n_heads:
            fail(REASON_QXRL_SCHEMA_INVALID)
        if len(layer_cache.ff_h_flat_q32_s64) != S * d_ff:
            fail(REASON_QXRL_SCHEMA_INVALID)

        # --- Residual 2: x_next = x1 + ff_out ---
        dx1 = [int(v) for v in dx]
        dff_out = [int(v) for v in dx]

        # --- FFN backward ---
        grad_ff_w2 = grads_by_name.get(f"qxrl/tsae/l{layer_index}/ff_w2")
        grad_ff_b2 = grads_by_name.get(f"qxrl/tsae/l{layer_index}/ff_b2")
        grad_ff_w1 = grads_by_name.get(f"qxrl/tsae/l{layer_index}/ff_w1")
        grad_ff_b1 = grads_by_name.get(f"qxrl/tsae/l{layer_index}/ff_b1")
        grad_rms2_gamma = grads_by_name.get(f"qxrl/tsae/l{layer_index}/rms2_gamma")
        if grad_ff_w2 is None or grad_ff_b2 is None or grad_ff_w1 is None or grad_ff_b1 is None or grad_rms2_gamma is None:
            fail(REASON_QXRL_SCHEMA_INVALID)

        # Per-position: dy -> dh -> du -> dx1n -> dx1_from_rms2.
        for p in range(S):
            dy = [int(dff_out[p * d_model + i]) for i in range(d_model)]

            # ff_out = ff_w2*h + ff_b2
            for i in range(d_model):
                grad_ff_b2[i] = add_sat(int(grad_ff_b2[i]), int(dy[i]), ctr)

            # grad_ff_w2 rows: d_model, cols: d_ff.
            h = [int(layer_cache.ff_h_flat_q32_s64[p * d_ff + j]) for j in range(d_ff)]
            for out_i in range(d_model):
                _outer_add(grad_mat=grad_ff_w2, rows=d_model, cols=d_ff, row_index=out_i, scale_q32_s64=int(dy[out_i]), vec=h, ctr=ctr)

            dh = [0] * d_ff
            _matT_vec_add(dst_vec=dh, mat=layer_w.ff_w2, rows=d_model, cols=d_ff, src_vec=dy, ctr=ctr)

            # ReLU: h = ReLU(u)
            du = [int(dh[j]) if int(h[j]) > 0 else 0 for j in range(d_ff)]
            for j in range(d_ff):
                grad_ff_b1[j] = add_sat(int(grad_ff_b1[j]), int(du[j]), ctr)

            # x1n = RMSNorm(x1, rms2_gamma)
            x1_vec = [int(layer_cache.x1_flat_q32_s64[p * d_model + i]) for i in range(d_model)]
            r2 = int(layer_cache.rms2_r_by_pos_q32_s64[p])
            x1n = [mul_q32(int(mul_q32(int(x1_vec[i]), int(r2), ctr)), int(layer_w.rms2_gamma[i]), ctr) for i in range(d_model)]

            for j in range(d_ff):
                _outer_add(grad_mat=grad_ff_w1, rows=d_ff, cols=d_model, row_index=j, scale_q32_s64=int(du[j]), vec=x1n, ctr=ctr)

            dx1n = [0] * d_model
            _matT_vec_add(dst_vec=dx1n, mat=layer_w.ff_w1, rows=d_ff, cols=d_model, src_vec=du, ctr=ctr)

            # RMSNorm2 backward.
            dx1_from_rms2 = _rmsnorm_backward_v1(
                x_q32_s64=x1_vec,
                gamma_q32_s64=layer_w.rms2_gamma,
                r_q32_s64=r2,
                gout_q32_s64=dx1n,
                grad_gamma_q32_s64=grad_rms2_gamma,
                ctr=ctr,
            )

            # Accumulate into dx1[p].
            base = p * d_model
            for i in range(d_model):
                dx1[base + i] = add_sat(int(dx1[base + i]), int(dx1_from_rms2[i]), ctr)

        # --- Residual 1: x1 = x_in + attn_proj ---
        dx_in = [int(v) for v in dx1]
        dattn_proj = [int(v) for v in dx1]

        # --- Wo backward: attn_proj = Wo * attn_out ---
        grad_wo = grads_by_name.get(f"qxrl/tsae/l{layer_index}/wo")
        if grad_wo is None:
            fail(REASON_QXRL_SCHEMA_INVALID)
        dattn_out = [0] * (S * d_model)
        for p in range(S):
            dy = [int(dattn_proj[p * d_model + i]) for i in range(d_model)]
            attn_vec = [int(layer_cache.attn_out_flat_q32_s64[p * d_model + i]) for i in range(d_model)]
            for out_i in range(d_model):
                _outer_add(grad_mat=grad_wo, rows=d_model, cols=d_model, row_index=out_i, scale_q32_s64=int(dy[out_i]), vec=attn_vec, ctr=ctr)

            dx_attn = [0] * d_model
            _matT_vec_add(dst_vec=dx_attn, mat=layer_w.wo, rows=d_model, cols=d_model, src_vec=dy, ctr=ctr)
            for i in range(d_model):
                dattn_out[p * d_model + i] = add_sat(int(dattn_out[p * d_model + i]), int(dx_attn[i]), ctr)

        # --- Attention backward (TopK indices treated as constants) ---
        gq_all = [0] * (S * d_model)
        gk_all = [0] * (S * d_model)
        gv_all = [0] * (S * d_model)

        attn_scale = int(cache.attn_scale_q32_s64)
        for i in range(S):
            for h in range(n_heads):
                base = (i * n_heads + h) * K
                sum_a = int(layer_cache.attn_sum_a_q32_s64[i * n_heads + h])
                go = [int(dattn_out[i * d_model + h * d_head + d]) for d in range(d_head)]

                if int(sum_a) == 0:
                    K_q32 = int(K) << 32
                    for t in range(K):
                        j = int(layer_cache.topk_idx_u32[base + t])
                        v_off = j * d_model + h * d_head
                        for d in range(d_head):
                            gv = div_q32_pos_rne_v1(numer_q32_s64=int(go[d]), denom_q32_pos_s64=int(K_q32), ctr=ctr)
                            gv_all[v_off + d] = add_sat(int(gv_all[v_off + d]), int(gv), ctr)
                    continue

                # gnum = go / sum_a
                gnum = [div_q32_pos_rne_v1(numer_q32_s64=int(go[d]), denom_q32_pos_s64=int(sum_a), ctr=ctr) for d in range(d_head)]

                # num = Σ a_j v_j
                num = [0] * d_head
                for t in range(K):
                    j = int(layer_cache.topk_idx_u32[base + t])
                    a = int(layer_cache.attn_a_q32_s64[base + t])
                    v_off = j * d_model + h * d_head
                    for d in range(d_head):
                        num[d] = add_sat(int(num[d]), int(mul_q32(int(a), int(layer_cache.v_all_flat_q32_s64[v_off + d]), ctr)), ctr)

                tmp = 0
                for d in range(d_head):
                    tmp = add_sat(int(tmp), int(mul_q32(int(go[d]), int(num[d]), ctr)), ctr)
                sum_a2 = mul_q32(int(sum_a), int(sum_a), ctr)
                gsum_a = -div_q32_pos_rne_v1(numer_q32_s64=int(tmp), denom_q32_pos_s64=int(sum_a2), ctr=ctr)

                # Iterate selected keys.
                q_off = i * d_model + h * d_head
                q_i = [int(layer_cache.q_all_flat_q32_s64[q_off + d]) for d in range(d_head)]
                for t in range(K):
                    j = int(layer_cache.topk_idx_u32[base + t])
                    a = int(layer_cache.attn_a_q32_s64[base + t])
                    k_off = j * d_model + h * d_head
                    v_off = j * d_model + h * d_head
                    k_j = [int(layer_cache.k_all_flat_q32_s64[k_off + d]) for d in range(d_head)]
                    v_j = [int(layer_cache.v_all_flat_q32_s64[v_off + d]) for d in range(d_head)]

                    ga_from_num = 0
                    for d in range(d_head):
                        ga_from_num = add_sat(int(ga_from_num), int(mul_q32(int(gnum[d]), int(v_j[d]), ctr)), ctr)

                    # gv_j_from_num = gnum * a
                    for d in range(d_head):
                        gv = mul_q32(int(gnum[d]), int(a), ctr)
                        gv_all[v_off + d] = add_sat(int(gv_all[v_off + d]), int(gv), ctr)

                    ga = add_sat(int(ga_from_num), int(gsum_a), ctr)
                    if int(a) > 0:
                        gdot = mul_q32(int(attn_scale), int(ga), ctr)
                        for d in range(d_head):
                            gq_all[q_off + d] = add_sat(int(gq_all[q_off + d]), int(mul_q32(int(gdot), int(k_j[d]), ctr)), ctr)
                            gk_all[k_off + d] = add_sat(int(gk_all[k_off + d]), int(mul_q32(int(gdot), int(q_i[d]), ctr)), ctr)

        # --- Q/K/V projection backward ---
        grad_wq = grads_by_name.get(f"qxrl/tsae/l{layer_index}/wq")
        grad_wk = grads_by_name.get(f"qxrl/tsae/l{layer_index}/wk")
        grad_wv = grads_by_name.get(f"qxrl/tsae/l{layer_index}/wv")
        grad_rms1_gamma = grads_by_name.get(f"qxrl/tsae/l{layer_index}/rms1_gamma")
        if grad_wq is None or grad_wk is None or grad_wv is None or grad_rms1_gamma is None:
            fail(REASON_QXRL_SCHEMA_INVALID)

        # dxn accumulates from Q/K/V paths.
        dxn_all = [0] * (S * d_model)
        for p in range(S):
            x_in_vec = [int(layer_cache.x_in_flat_q32_s64[p * d_model + i]) for i in range(d_model)]
            r1 = int(layer_cache.rms1_r_by_pos_q32_s64[p])
            xn = [mul_q32(int(mul_q32(int(x_in_vec[i]), int(r1), ctr)), int(layer_w.rms1_gamma[i]), ctr) for i in range(d_model)]

            gq = [int(gq_all[p * d_model + i]) for i in range(d_model)]
            gk = [int(gk_all[p * d_model + i]) for i in range(d_model)]
            gv = [int(gv_all[p * d_model + i]) for i in range(d_model)]

            # grad_W += outer(gy, xn); dxn += W^T * gy
            for out_i in range(d_model):
                _outer_add(grad_mat=grad_wq, rows=d_model, cols=d_model, row_index=out_i, scale_q32_s64=int(gq[out_i]), vec=xn, ctr=ctr)
                _outer_add(grad_mat=grad_wk, rows=d_model, cols=d_model, row_index=out_i, scale_q32_s64=int(gk[out_i]), vec=xn, ctr=ctr)
                _outer_add(grad_mat=grad_wv, rows=d_model, cols=d_model, row_index=out_i, scale_q32_s64=int(gv[out_i]), vec=xn, ctr=ctr)

            dxn = [0] * d_model
            _matT_vec_add(dst_vec=dxn, mat=layer_w.wq, rows=d_model, cols=d_model, src_vec=gq, ctr=ctr)
            _matT_vec_add(dst_vec=dxn, mat=layer_w.wk, rows=d_model, cols=d_model, src_vec=gk, ctr=ctr)
            _matT_vec_add(dst_vec=dxn, mat=layer_w.wv, rows=d_model, cols=d_model, src_vec=gv, ctr=ctr)
            for i in range(d_model):
                dxn_all[p * d_model + i] = add_sat(int(dxn_all[p * d_model + i]), int(dxn[i]), ctr)

        # RMSNorm1 backward + accumulate into dx_in.
        for p in range(S):
            x_in_vec = [int(layer_cache.x_in_flat_q32_s64[p * d_model + i]) for i in range(d_model)]
            r1 = int(layer_cache.rms1_r_by_pos_q32_s64[p])
            gout = [int(dxn_all[p * d_model + i]) for i in range(d_model)]
            dx_from_rms1 = _rmsnorm_backward_v1(
                x_q32_s64=x_in_vec,
                gamma_q32_s64=layer_w.rms1_gamma,
                r_q32_s64=r1,
                gout_q32_s64=gout,
                grad_gamma_q32_s64=grad_rms1_gamma,
                ctr=ctr,
            )
            base = p * d_model
            for i in range(d_model):
                dx_in[base + i] = add_sat(int(dx_in[base + i]), int(dx_from_rms1[i]), ctr)

        # Advance gradient to previous layer output.
        dx = dx_in

    # Backprop token+pos embeddings: x0 = tok_emb[tok] + pos_emb[pos]
    grad_tok_emb = grads_by_name.get("qxrl/tok_emb")
    grad_pos_emb = grads_by_name.get("qxrl/pos_emb")
    if grad_tok_emb is None or grad_pos_emb is None:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if len(grad_tok_emb) != vocab * d_model or len(grad_pos_emb) != S * d_model:
        fail(REASON_QXRL_SCHEMA_INVALID)
    for p in range(S):
        tok_id = int(cache.tokens_u32[p])
        if tok_id < 0 or tok_id >= vocab:
            fail(REASON_QXRL_SCHEMA_INVALID)
        tok_off = tok_id * d_model
        pos_off = p * d_model
        for i in range(d_model):
            g = int(dx[pos_off + i])
            grad_tok_emb[tok_off + i] = add_sat(int(grad_tok_emb[tok_off + i]), int(g), ctr)
            grad_pos_emb[pos_off + i] = add_sat(int(grad_pos_emb[pos_off + i]), int(g), ctr)


__all__ = [
    "QXRLLossesV1",
    "backward_encoder_qre_v1_add_grads",
    "backward_mlm_hinge_for_masked_pos_add_grads",
    "backward_mlm_hinge_for_masked_pos_add_grads_tsae_v1",
    "backward_encoder_tsae_v1_add_grads",
    "clip_abs_q32",
    "ctr_hinge_and_dz_for_batch",
]
