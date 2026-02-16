"""QXRL TSAE encoder forward pass (v1, Phase 5).

Implements TSAE_V1:
  - Top-K sparse attention with deterministic tie-breaks
  - RMSNorm with opset-pinned Div/InvSqrt

This module is RE2: deterministic, fail-closed, no floats.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..omega_common_v1 import fail
from .qxrl_common_v1 import ENCODER_KIND_TSAE_V1, QXRLModelSpecV1, REASON_QXRL_SCHEMA_INVALID
from .qxrl_opset_math_v1 import div_q32_pos_rne_v1, invsqrt_q32_nr_lut_v1
from .qxrl_ops_v1 import QXRLStepCountersV1, add_sat, add_sat_vec, dot_q32_v1_flat, mul_q32, relu_vec, topk_det


@dataclass(frozen=True, slots=True)
class QXRLTSAELayerWeightsV1:
    wq: list[int]  # [d_model, d_model]
    wk: list[int]  # [d_model, d_model]
    wv: list[int]  # [d_model, d_model]
    wo: list[int]  # [d_model, d_model]

    rms1_gamma: list[int]  # [d_model]
    rms2_gamma: list[int]  # [d_model]

    ff_w1: list[int]  # [d_ff, d_model]
    ff_b1: list[int]  # [d_ff]
    ff_w2: list[int]  # [d_model, d_ff]
    ff_b2: list[int]  # [d_model]


@dataclass(frozen=True, slots=True)
class QXRLWeightsViewTSAEV1:
    tok_emb: list[int]  # [vocab, d_model]
    pos_emb: list[int]  # [seq_len, d_model]

    layers: list[QXRLTSAELayerWeightsV1]

    proj_w: list[int]  # [d_embed, d_model]
    proj_b: list[int]  # [d_embed]

    tok_proj_w: list[int]  # [d_embed, d_model]
    tok_proj_b: list[int]  # [d_embed]

    out_emb: list[int]  # [vocab, d_embed]
    out_b: list[int]  # [vocab]


@dataclass(frozen=True, slots=True)
class QXRLTSAELayerCacheV1:
    x_in_flat_q32_s64: list[int]  # [S * d_model]
    x1_flat_q32_s64: list[int]  # [S * d_model]

    rms1_r_by_pos_q32_s64: list[int]  # [S]
    rms2_r_by_pos_q32_s64: list[int]  # [S]

    q_all_flat_q32_s64: list[int]  # [S * d_model]
    k_all_flat_q32_s64: list[int]  # [S * d_model]
    v_all_flat_q32_s64: list[int]  # [S * d_model]

    topk_idx_u32: list[int]  # [S * n_heads * K] (selected key indices)
    attn_a_q32_s64: list[int]  # [S * n_heads * K] (ReLU(score))
    attn_sum_a_q32_s64: list[int]  # [S * n_heads]

    attn_out_flat_q32_s64: list[int]  # [S * d_model]
    ff_h_flat_q32_s64: list[int]  # [S * d_ff] (ReLU output)


@dataclass(frozen=True, slots=True)
class QXRLTSAEForwardCacheV1:
    tokens_u32: list[int]  # [S]
    xL_flat_q32_s64: list[int]  # [S * d_model]
    pooled_q32_s64: list[int]  # [d_model]
    z_q32_s64: list[int]  # [d_embed]
    attn_scale_q32_s64: int
    layers: list[QXRLTSAELayerCacheV1]


def _require_tokens(tokens_u32: list[int], *, vocab_size_u32: int, seq_len_u32: int) -> None:
    if not isinstance(tokens_u32, list) or len(tokens_u32) != int(seq_len_u32):
        fail(REASON_QXRL_SCHEMA_INVALID)
    vocab = int(vocab_size_u32)
    for tok in tokens_u32:
        if not isinstance(tok, int) or tok < 0 or tok >= vocab:
            fail(REASON_QXRL_SCHEMA_INVALID)


def _rmsnorm_q32_v1(
    *,
    x_q32_s64: list[int],
    gamma_q32_s64: list[int],
    eps_q32_s64: int,
    d_model_u32: int,
    lut_table_q32_s64: list[int],
    ctr: QXRLStepCountersV1,
) -> tuple[list[int], int]:
    dm = int(d_model_u32)
    if len(x_q32_s64) != dm or len(gamma_q32_s64) != dm:
        fail(REASON_QXRL_SCHEMA_INVALID)
    eps = int(eps_q32_s64)
    if eps <= 0:
        fail(REASON_QXRL_SCHEMA_INVALID)

    sum_sq = 0
    for i in range(dm):
        sum_sq = add_sat(int(sum_sq), int(mul_q32(int(x_q32_s64[i]), int(x_q32_s64[i]), ctr)), ctr)

    d_model_q32 = int(dm) << 32
    mean_sq = div_q32_pos_rne_v1(numer_q32_s64=int(sum_sq), denom_q32_pos_s64=int(d_model_q32), ctr=ctr)
    denom = add_sat(int(mean_sq), int(eps), ctr)
    r = invsqrt_q32_nr_lut_v1(x_q32_pos_s64=int(denom), lut_table_q32_s64=lut_table_q32_s64, ctr=ctr)

    out: list[int] = [0] * dm
    for i in range(dm):
        y = mul_q32(int(x_q32_s64[i]), int(r), ctr)
        out[i] = mul_q32(int(y), int(gamma_q32_s64[i]), ctr)
    return out, int(r)


def _matmul_no_bias(
    *,
    W_q32_s64: list[int],
    rows_u32: int,
    cols_u32: int,
    x_q32_s64: list[int],
    dot_kind: str,
    ctr: QXRLStepCountersV1,
) -> list[int]:
    R = int(rows_u32)
    C = int(cols_u32)
    if len(W_q32_s64) != R * C:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if len(x_q32_s64) != C:
        fail(REASON_QXRL_SCHEMA_INVALID)
    out: list[int] = [0] * R
    for r in range(R):
        out[r] = dot_q32_v1_flat(
            dot_kind=str(dot_kind),
            x_q32_s64=W_q32_s64,
            x_off=r * C,
            y_q32_s64=x_q32_s64,
            y_off=0,
            n=C,
            ctr=ctr,
        )
    return out


def _matmul_bias(
    *,
    W_q32_s64: list[int],
    b_q32_s64: list[int],
    rows_u32: int,
    cols_u32: int,
    x_q32_s64: list[int],
    dot_kind: str,
    ctr: QXRLStepCountersV1,
) -> list[int]:
    R = int(rows_u32)
    if len(b_q32_s64) != R:
        fail(REASON_QXRL_SCHEMA_INVALID)
    out = _matmul_no_bias(W_q32_s64=W_q32_s64, rows_u32=rows_u32, cols_u32=cols_u32, x_q32_s64=x_q32_s64, dot_kind=dot_kind, ctr=ctr)
    for r in range(R):
        out[r] = add_sat(int(b_q32_s64[r]), int(out[r]), ctr)
    return out


def forward_encoder_tsae_v1(
    *,
    tokens_u32: list[int],
    model: QXRLModelSpecV1,
    weights: QXRLWeightsViewTSAEV1,
    lut_table_q32_s64: list[int],
    ctr: QXRLStepCountersV1,
    count_tokens: bool = True,
) -> QXRLTSAEForwardCacheV1:
    if str(model.encoder_kind).strip() != ENCODER_KIND_TSAE_V1:
        fail(REASON_QXRL_SCHEMA_INVALID)

    _require_tokens(tokens_u32, vocab_size_u32=model.vocab_size_u32, seq_len_u32=model.seq_len_u32)
    if count_tokens:
        ctr.token_count_u64 += int(model.seq_len_u32)

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

    if len(weights.tok_emb) != vocab * d_model:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if len(weights.pos_emb) != S * d_model:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if not isinstance(weights.layers, list) or len(weights.layers) != n_layers:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if len(weights.proj_w) != d_embed * d_model or len(weights.proj_b) != d_embed:
        fail(REASON_QXRL_SCHEMA_INVALID)

    # Attention scale: invsqrt(d_head).
    d_head_q32 = int(d_head) << 32
    attn_scale = invsqrt_q32_nr_lut_v1(x_q32_pos_s64=int(d_head_q32), lut_table_q32_s64=lut_table_q32_s64, ctr=ctr)

    # x0[p] = tok_emb[tok[p]] + pos_emb[p]
    x_flat: list[int] = [0] * (S * d_model)
    for p in range(S):
        tok_id = int(tokens_u32[p])
        tok_off = tok_id * d_model
        pos_off = p * d_model
        for d in range(d_model):
            x_flat[pos_off + d] = add_sat(int(weights.tok_emb[tok_off + d]), int(weights.pos_emb[pos_off + d]), ctr)

    layers_cache: list[QXRLTSAELayerCacheV1] = []

    eps_q32 = int(model.rms_epsilon_q32)
    dot_kind = str(model.dot_kind).strip()

    for layer_index in range(n_layers):
        w = weights.layers[layer_index]

        # Pre-norm 1.
        rms1_r_by_pos: list[int] = [0] * S
        xn_flat: list[int] = [0] * (S * d_model)
        for p in range(S):
            x_vec = [int(x_flat[p * d_model + d]) for d in range(d_model)]
            out_vec, r = _rmsnorm_q32_v1(
                x_q32_s64=x_vec,
                gamma_q32_s64=w.rms1_gamma,
                eps_q32_s64=eps_q32,
                d_model_u32=d_model,
                lut_table_q32_s64=lut_table_q32_s64,
                ctr=ctr,
            )
            rms1_r_by_pos[p] = int(r)
            for d in range(d_model):
                xn_flat[p * d_model + d] = int(out_vec[d])

        # Q/K/V projections.
        q_all: list[int] = [0] * (S * d_model)
        k_all: list[int] = [0] * (S * d_model)
        v_all: list[int] = [0] * (S * d_model)
        for p in range(S):
            xn = [int(xn_flat[p * d_model + d]) for d in range(d_model)]
            q = _matmul_no_bias(W_q32_s64=w.wq, rows_u32=d_model, cols_u32=d_model, x_q32_s64=xn, dot_kind=dot_kind, ctr=ctr)
            k = _matmul_no_bias(W_q32_s64=w.wk, rows_u32=d_model, cols_u32=d_model, x_q32_s64=xn, dot_kind=dot_kind, ctr=ctr)
            v = _matmul_no_bias(W_q32_s64=w.wv, rows_u32=d_model, cols_u32=d_model, x_q32_s64=xn, dot_kind=dot_kind, ctr=ctr)
            for d in range(d_model):
                q_all[p * d_model + d] = int(q[d])
                k_all[p * d_model + d] = int(k[d])
                v_all[p * d_model + d] = int(v[d])

        # Top-K attention.
        topk_idx: list[int] = [0] * (S * n_heads * K)
        attn_a: list[int] = [0] * (S * n_heads * K)
        attn_sum_a: list[int] = [0] * (S * n_heads)
        attn_out_flat: list[int] = [0] * (S * d_model)

        for i in range(S):
            for h in range(n_heads):
                q_off = (i * d_model) + (h * d_head)
                pairs: list[tuple[int, int]] = []
                for j in range(S):
                    k_off = (j * d_model) + (h * d_head)
                    raw = dot_q32_v1_flat(
                        dot_kind=dot_kind,
                        x_q32_s64=q_all,
                        x_off=q_off,
                        y_q32_s64=k_all,
                        y_off=k_off,
                        n=d_head,
                        ctr=ctr,
                    )
                    score = mul_q32(int(attn_scale), int(raw), ctr)
                    pairs.append((int(score), int(j)))

                topk_pairs = topk_det(pairs, K, ctr)
                if len(topk_pairs) != K:
                    fail(REASON_QXRL_SCHEMA_INVALID)

                sum_a = 0
                base = (i * n_heads + h) * K
                for t, (score, j) in enumerate(topk_pairs):
                    topk_idx[base + t] = int(j)
                    a = int(score) if int(score) > 0 else 0
                    attn_a[base + t] = int(a)
                    sum_a = add_sat(int(sum_a), int(a), ctr)

                attn_sum_a[i * n_heads + h] = int(sum_a)

                # out_head: [d_head]
                out_head: list[int] = [0] * d_head
                if int(sum_a) > 0:
                    num_vec: list[int] = [0] * d_head
                    for t in range(K):
                        j = int(topk_idx[base + t])
                        a = int(attn_a[base + t])
                        v_off = (j * d_model) + (h * d_head)
                        for d in range(d_head):
                            num_vec[d] = add_sat(int(num_vec[d]), int(mul_q32(int(a), int(v_all[v_off + d]), ctr)), ctr)
                    for d in range(d_head):
                        out_head[d] = div_q32_pos_rne_v1(numer_q32_s64=int(num_vec[d]), denom_q32_pos_s64=int(sum_a), ctr=ctr)
                else:
                    sum_v: list[int] = [0] * d_head
                    for t in range(K):
                        j = int(topk_idx[base + t])
                        v_off = (j * d_model) + (h * d_head)
                        for d in range(d_head):
                            sum_v[d] = add_sat(int(sum_v[d]), int(v_all[v_off + d]), ctr)
                    K_q32 = int(K) << 32
                    for d in range(d_head):
                        out_head[d] = div_q32_pos_rne_v1(numer_q32_s64=int(sum_v[d]), denom_q32_pos_s64=int(K_q32), ctr=ctr)

                # Write into attn_out_flat at [i, h, :]
                out_off = (i * d_model) + (h * d_head)
                for d in range(d_head):
                    attn_out_flat[out_off + d] = int(out_head[d])

        # Output projection.
        x1_flat: list[int] = [0] * (S * d_model)
        for p in range(S):
            attn_vec = [int(attn_out_flat[p * d_model + d]) for d in range(d_model)]
            proj = _matmul_no_bias(W_q32_s64=w.wo, rows_u32=d_model, cols_u32=d_model, x_q32_s64=attn_vec, dot_kind=dot_kind, ctr=ctr)
            x_vec = [int(x_flat[p * d_model + d]) for d in range(d_model)]
            x1 = add_sat_vec(x_vec, proj, ctr)
            for d in range(d_model):
                x1_flat[p * d_model + d] = int(x1[d])

        # Pre-norm 2.
        rms2_r_by_pos: list[int] = [0] * S
        x1n_flat: list[int] = [0] * (S * d_model)
        for p in range(S):
            x1_vec = [int(x1_flat[p * d_model + d]) for d in range(d_model)]
            out_vec, r = _rmsnorm_q32_v1(
                x_q32_s64=x1_vec,
                gamma_q32_s64=w.rms2_gamma,
                eps_q32_s64=eps_q32,
                d_model_u32=d_model,
                lut_table_q32_s64=lut_table_q32_s64,
                ctr=ctr,
            )
            rms2_r_by_pos[p] = int(r)
            for d in range(d_model):
                x1n_flat[p * d_model + d] = int(out_vec[d])

        # Feedforward.
        ff_h_flat: list[int] = [0] * (S * d_ff)
        x_next_flat: list[int] = [0] * (S * d_model)
        for p in range(S):
            x1n = [int(x1n_flat[p * d_model + d]) for d in range(d_model)]
            u = _matmul_bias(W_q32_s64=w.ff_w1, b_q32_s64=w.ff_b1, rows_u32=d_ff, cols_u32=d_model, x_q32_s64=x1n, dot_kind=dot_kind, ctr=ctr)
            h = relu_vec(u)
            for j in range(d_ff):
                ff_h_flat[p * d_ff + j] = int(h[j])
            ff_out = _matmul_bias(W_q32_s64=w.ff_w2, b_q32_s64=w.ff_b2, rows_u32=d_model, cols_u32=d_ff, x_q32_s64=h, dot_kind=dot_kind, ctr=ctr)
            x1_vec = [int(x1_flat[p * d_model + d]) for d in range(d_model)]
            x_next = add_sat_vec(x1_vec, ff_out, ctr)
            for d in range(d_model):
                x_next_flat[p * d_model + d] = int(x_next[d])

        layers_cache.append(
            QXRLTSAELayerCacheV1(
                x_in_flat_q32_s64=[int(v) for v in x_flat],
                x1_flat_q32_s64=[int(v) for v in x1_flat],
                rms1_r_by_pos_q32_s64=[int(v) for v in rms1_r_by_pos],
                rms2_r_by_pos_q32_s64=[int(v) for v in rms2_r_by_pos],
                q_all_flat_q32_s64=[int(v) for v in q_all],
                k_all_flat_q32_s64=[int(v) for v in k_all],
                v_all_flat_q32_s64=[int(v) for v in v_all],
                topk_idx_u32=[int(v) for v in topk_idx],
                attn_a_q32_s64=[int(v) for v in attn_a],
                attn_sum_a_q32_s64=[int(v) for v in attn_sum_a],
                attn_out_flat_q32_s64=[int(v) for v in attn_out_flat],
                ff_h_flat_q32_s64=[int(v) for v in ff_h_flat],
            )
        )

        # Advance layer input.
        x_flat = x_next_flat

    xL_flat = [int(v) for v in x_flat]

    # Pooling: pooled = (sum_p xL[p]) * inv_seq_len
    sum_vec: list[int] = [0] * d_model
    for p in range(S):
        for d in range(d_model):
            sum_vec[d] = add_sat(int(sum_vec[d]), int(xL_flat[p * d_model + d]), ctr)
    pooled = [mul_q32(int(sum_vec[d]), int(model.inv_seq_len_q32), ctr) for d in range(d_model)]

    # z = proj_w * pooled + proj_b
    z = _matmul_bias(W_q32_s64=weights.proj_w, b_q32_s64=weights.proj_b, rows_u32=d_embed, cols_u32=d_model, x_q32_s64=pooled, dot_kind=dot_kind, ctr=ctr)

    return QXRLTSAEForwardCacheV1(
        tokens_u32=[int(t) for t in tokens_u32],
        xL_flat_q32_s64=xL_flat,
        pooled_q32_s64=[int(v) for v in pooled],
        z_q32_s64=[int(v) for v in z],
        attn_scale_q32_s64=int(attn_scale),
        layers=layers_cache,
    )


__all__ = [
    "QXRLTSAEForwardCacheV1",
    "QXRLTSAELayerCacheV1",
    "QXRLTSAELayerWeightsV1",
    "QXRLWeightsViewTSAEV1",
    "forward_encoder_tsae_v1",
]

