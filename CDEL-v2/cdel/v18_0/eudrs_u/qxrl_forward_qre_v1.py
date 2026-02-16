"""QXRL QRE encoder forward pass (v1).

Implements Phase 4 QRE_V1 architecture using Q32 ops only.

This module is RE2: deterministic, fail-closed, no floats.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from ..omega_common_v1 import fail
from .qxrl_common_v1 import (
    REASON_QXRL_SCHEMA_INVALID,
    QXRLModelSpecV1,
    load_qxrl_model_manifest_v1,
    parse_qxrl_model_manifest_v1,
)
from .qxrl_ops_v1 import QXRLStepCountersV1, add_sat, dot_q32_v1_flat, mul_q32, relu_vec


@dataclass(frozen=True, slots=True)
class QXRLWeightsViewV1:
    tok_emb: list[int]  # [vocab, d_model]
    pos_emb: list[int]  # [seq_len, d_model]

    enc_w1: list[int]  # [d_hidden, d_model]
    enc_b1: list[int]  # [d_hidden]
    enc_w2: list[int]  # [d_embed, d_hidden]
    enc_b2: list[int]  # [d_embed]

    tok_proj_w: list[int]  # [d_embed, d_model]
    tok_proj_b: list[int]  # [d_embed]

    out_emb: list[int]  # [vocab, d_embed]
    out_b: list[int]  # [vocab]


@dataclass(frozen=True, slots=True)
class QXRLForwardCacheV1:
    tokens_u32: list[int]  # input tokens (length seq_len)
    h0_flat_q32_s64: list[int]  # [seq_len * d_model]
    pooled_q32_s64: list[int]  # [d_model]
    u1_q32_s64: list[int]  # [d_hidden]
    a1_q32_s64: list[int]  # [d_hidden]
    z_q32_s64: list[int]  # [d_embed]


def _require_tokens(tokens_u32: list[int], *, vocab_size_u32: int, seq_len_u32: int) -> None:
    if not isinstance(tokens_u32, list) or len(tokens_u32) != int(seq_len_u32):
        fail(REASON_QXRL_SCHEMA_INVALID)
    vocab = int(vocab_size_u32)
    for tok in tokens_u32:
        if not isinstance(tok, int) or tok < 0 or tok >= vocab:
            fail(REASON_QXRL_SCHEMA_INVALID)


def forward_encoder_qre_v1(
    *,
    tokens_u32: list[int],
    model: QXRLModelSpecV1,
    weights: QXRLWeightsViewV1,
    ctr: QXRLStepCountersV1,
    count_tokens: bool = True,
) -> QXRLForwardCacheV1:
    _require_tokens(tokens_u32, vocab_size_u32=model.vocab_size_u32, seq_len_u32=model.seq_len_u32)
    if count_tokens:
        ctr.token_count_u64 += int(model.seq_len_u32)

    vocab = int(model.vocab_size_u32)
    seq_len = int(model.seq_len_u32)
    d_model = int(model.d_model_u32)
    d_hidden = int(model.d_hidden_u32)
    d_embed = int(model.d_embed_u32)

    # Shapes (flattened):
    # tok_emb: vocab*d_model
    # pos_emb: seq_len*d_model
    if len(weights.tok_emb) != vocab * d_model:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if len(weights.pos_emb) != seq_len * d_model:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if len(weights.enc_w1) != d_hidden * d_model:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if len(weights.enc_b1) != d_hidden:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if len(weights.enc_w2) != d_embed * d_hidden:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if len(weights.enc_b2) != d_embed:
        fail(REASON_QXRL_SCHEMA_INVALID)

    # h0[p] = AddSat(tok_emb[tok[p]], pos_emb[p])
    h0_flat: list[int] = [0] * (seq_len * d_model)
    sum_h0: list[int] = [0] * d_model
    for p in range(seq_len):
        tok_id = int(tokens_u32[p])
        tok_off = tok_id * d_model
        pos_off = p * d_model
        for d in range(d_model):
            v = add_sat(int(weights.tok_emb[tok_off + d]), int(weights.pos_emb[pos_off + d]), ctr)
            h0_flat[pos_off + d] = int(v)
            sum_h0[d] = add_sat(int(sum_h0[d]), int(v), ctr)

    pooled = [mul_q32(int(sum_h0[d]), int(model.inv_seq_len_q32), ctr) for d in range(d_model)]

    # u1 = enc_w1 * pooled + enc_b1
    u1: list[int] = [0] * d_hidden
    for j in range(d_hidden):
        dot = dot_q32_v1_flat(
            dot_kind=model.dot_kind,
            x_q32_s64=weights.enc_w1,
            x_off=j * d_model,
            y_q32_s64=pooled,
            y_off=0,
            n=d_model,
            ctr=ctr,
        )
        u1[j] = add_sat(int(weights.enc_b1[j]), int(dot), ctr)

    a1 = relu_vec(u1)

    # z = enc_w2 * a1 + enc_b2
    z: list[int] = [0] * d_embed
    for k in range(d_embed):
        dot = dot_q32_v1_flat(
            dot_kind=model.dot_kind,
            x_q32_s64=weights.enc_w2,
            x_off=k * d_hidden,
            y_q32_s64=a1,
            y_off=0,
            n=d_hidden,
            ctr=ctr,
        )
        z[k] = add_sat(int(weights.enc_b2[k]), int(dot), ctr)

    return QXRLForwardCacheV1(
        tokens_u32=[int(t) for t in tokens_u32],
        h0_flat_q32_s64=h0_flat,
        pooled_q32_s64=pooled,
        u1_q32_s64=u1,
        a1_q32_s64=a1,
        z_q32_s64=z,
    )


def tok_head_t_v1(
    *,
    position_p_u32: int,
    model: QXRLModelSpecV1,
    weights: QXRLWeightsViewV1,
    cache: QXRLForwardCacheV1,
    ctr: QXRLStepCountersV1,
) -> list[int]:
    p = int(position_p_u32)
    seq_len = int(model.seq_len_u32)
    d_model = int(model.d_model_u32)
    d_embed = int(model.d_embed_u32)
    if p < 0 or p >= seq_len:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if len(weights.tok_proj_w) != d_embed * d_model or len(weights.tok_proj_b) != d_embed:
        fail(REASON_QXRL_SCHEMA_INVALID)

    h0_off = p * d_model
    t: list[int] = [0] * d_embed
    for k in range(d_embed):
        dot = dot_q32_v1_flat(
            dot_kind=model.dot_kind,
            x_q32_s64=weights.tok_proj_w,
            x_off=k * d_model,
            y_q32_s64=cache.h0_flat_q32_s64,
            y_off=h0_off,
            n=d_model,
            ctr=ctr,
        )
        t[k] = add_sat(int(weights.tok_proj_b[k]), int(dot), ctr)
    return t


def score_token_v1(
    *,
    token_id_u32: int,
    t_q32_s64: list[int],
    model: QXRLModelSpecV1,
    weights: QXRLWeightsViewV1,
    ctr: QXRLStepCountersV1,
) -> int:
    v = int(token_id_u32)
    vocab = int(model.vocab_size_u32)
    d_embed = int(model.d_embed_u32)
    if v < 0 or v >= vocab:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if len(t_q32_s64) != d_embed:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if len(weights.out_emb) != vocab * d_embed or len(weights.out_b) != vocab:
        fail(REASON_QXRL_SCHEMA_INVALID)

    dot = dot_q32_v1_flat(
        dot_kind=model.dot_kind,
        x_q32_s64=weights.out_emb,
        x_off=v * d_embed,
        y_q32_s64=t_q32_s64,
        y_off=0,
        n=d_embed,
        ctr=ctr,
    )
    return add_sat(int(weights.out_b[v]), int(dot), ctr)


def score_all_vocab_v1(
    *,
    t_q32_s64: list[int],
    model: QXRLModelSpecV1,
    weights: QXRLWeightsViewV1,
    ctr: QXRLStepCountersV1,
) -> list[int]:
    vocab = int(model.vocab_size_u32)
    return [score_token_v1(token_id_u32=v, t_q32_s64=t_q32_s64, model=model, weights=weights, ctr=ctr) for v in range(vocab)]


__all__ = [
    "QXRLForwardCacheV1",
    "QXRLModelSpecV1",
    "QXRLWeightsViewV1",
    "forward_encoder_qre_v1",
    "load_qxrl_model_manifest_v1",
    "parse_qxrl_model_manifest_v1",
    "score_all_vocab_v1",
    "score_token_v1",
    "tok_head_t_v1",
]
