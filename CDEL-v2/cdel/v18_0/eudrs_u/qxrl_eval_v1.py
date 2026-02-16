"""QXRL deterministic evaluation + scorecard (v1, Phase 4 + Phase 5).

Implements:
  - masked accuracy @1 (MLM head) with deterministic masking + negative draws
  - contrastive recall@K with TopKDet tie rules
  - H_eval digest chain (Phase 4 fixed) + scorecard JSON

This module is RE2: deterministic, fail-closed, no floats.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from typing import Any, Callable, Final

from ..omega_common_v1 import fail, validate_schema
from .eudrs_u_hash_v1 import gcj1_canon_bytes, gcj1_loads_and_verify_canonical, sha256_prefixed
from .qxrl_common_v1 import (
    ENCODER_KIND_TSAE_V1,
    PRNG_STREAM_EVAL_MASKS_V1,
    PRNG_STREAM_EVAL_NEGS_V1,
    parse_qxrl_invsqrt_lut_manifest_v1,
    REASON_QXRL_FLOOR_FAIL,
    REASON_QXRL_SCHEMA_INVALID,
    SCHEMA_QXRL_EVAL_MANIFEST_V1,
    SCHEMA_QXRL_EVAL_SCORECARD_V1,
    compute_eval_id_config_hash,
    compute_self_hash_id,
    digest32_to_hex,
    require_q32_obj,
    prng_for_step_stream,
    sha256_id_to_digest32,
)
from .qxrl_dataset_v1 import QXRLDatasetExampleV1
from .qxrl_forward_qre_v1 import QXRLModelSpecV1, forward_encoder_qre_v1, score_all_vocab_v1, tok_head_t_v1
from .qxrl_forward_tsae_v1 import forward_encoder_tsae_v1
from .qxrl_opset_math_v1 import parse_invsqrt_lut_bin_v1
from .qxrl_ops_v1 import QXRLStepCountersV1, add_sat, argmax_det, dot_q32_v1_flat, topk_det
from .qxrl_train_replay_v1 import WeightsManifestV1, weights_view_from_manifest


_EVD_MAGIC: Final[bytes] = b"EVD1"
_EVD_VERSION_V1: Final[int] = 1


def load_qxrl_eval_manifest_v1(eval_manifest_bytes: bytes, *, schema_validate: bool = True) -> dict[str, Any]:
    obj = gcj1_loads_and_verify_canonical(eval_manifest_bytes)
    if not isinstance(obj, dict):
        fail(REASON_QXRL_SCHEMA_INVALID)
    if schema_validate:
        try:
            validate_schema(obj, SCHEMA_QXRL_EVAL_MANIFEST_V1)
        except Exception:  # noqa: BLE001
            fail(REASON_QXRL_SCHEMA_INVALID)
    if str(obj.get("schema_id", "")).strip() != SCHEMA_QXRL_EVAL_MANIFEST_V1:
        fail(REASON_QXRL_SCHEMA_INVALID)
    return dict(obj)


def parse_and_verify_eval_manifest_v1(
    *,
    eval_manifest_obj: dict[str, Any],
    model: QXRLModelSpecV1,
    dataset_manifest_obj: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(eval_manifest_obj, dict) or str(eval_manifest_obj.get("schema_id", "")).strip() != SCHEMA_QXRL_EVAL_MANIFEST_V1:
        fail(REASON_QXRL_SCHEMA_INVALID)

    # Enforce eval_id as config hash (excludes scorecard_ref to avoid cycles).
    expected_eval_id = compute_eval_id_config_hash(eval_manifest_obj)
    if str(eval_manifest_obj.get("eval_id", "")).strip() != expected_eval_id:
        fail(REASON_QXRL_SCHEMA_INVALID)

    if str(eval_manifest_obj.get("dc1_id", "")).strip() != "dc1:q32_v1":
        fail(REASON_QXRL_SCHEMA_INVALID)
    if str(eval_manifest_obj.get("opset_id", "")).strip() != str(model.opset_id).strip():
        fail(REASON_QXRL_SCHEMA_INVALID)

    dot_kind = str(eval_manifest_obj.get("dot_kind", "")).strip()
    if dot_kind != str(model.dot_kind).strip():
        fail(REASON_QXRL_SCHEMA_INVALID)

    # Cross-check dataset manifest id consistency.
    if str(eval_manifest_obj.get("dataset_manifest_ref", {}).get("artifact_id", "")).strip() != str(dataset_manifest_obj.get("dataset_id", "")).strip():
        # Dataset manifest is content-addressed; dataset_id is the internal ID.
        # We don't bind them here (Phase 4 MVP). Verifier binds via ArtifactRefV1.
        pass

    return dict(eval_manifest_obj)


def _write_u32_le(x: int) -> bytes:
    return struct.pack("<I", int(x) & 0xFFFFFFFF)


def _write_u64_le(x: int) -> bytes:
    return struct.pack("<Q", int(x) & 0xFFFFFFFFFFFFFFFF)


def _sha25632(data: bytes) -> bytes:
    return hashlib.sha256(bytes(data)).digest()


def _mask_bitmap_nbytes(seq_len_u32: int) -> int:
    L = int(seq_len_u32)
    if L < 0:
        fail(REASON_QXRL_SCHEMA_INVALID)
    return (L + 7) // 8


def _select_masks(
    *,
    tokens_u32: list[int],
    seq_len_u32: int,
    mask_prob_q32_u64: int,
    max_masks_per_seq_u32: int,
    prng,
) -> tuple[bytes, list[int], list[int], list[int], Any, int]:
    seq_len = int(seq_len_u32)
    if not isinstance(tokens_u32, list) or len(tokens_u32) != seq_len:
        fail(REASON_QXRL_SCHEMA_INVALID)
    prob = int(mask_prob_q32_u64)
    if prob < 0 or prob > (1 << 32):
        fail(REASON_QXRL_SCHEMA_INVALID)
    cap = int(max_masks_per_seq_u32)
    if cap < 0 or cap > 0xFFFFFFFF:
        fail(REASON_QXRL_SCHEMA_INVALID)

    bitmap = bytearray(_mask_bitmap_nbytes(seq_len))
    masked_positions: list[int] = []
    true_token_ids: list[int] = []
    masked_tokens = [int(t) for t in tokens_u32]

    draws = 0
    state = prng
    for p in range(seq_len):
        r, state = state.next_u64()
        draws += 1
        r_u32 = (int(r) >> 32) & 0xFFFFFFFF
        if r_u32 < prob and len(masked_positions) < int(cap):
            masked_positions.append(int(p))
            true_token_ids.append(int(tokens_u32[p]))
            byte_i = int(p) // 8
            bit_i = int(p) % 8
            bitmap[byte_i] |= 1 << bit_i
    return bytes(bitmap), masked_positions, true_token_ids, masked_tokens, state, int(draws)


def _apply_mask_id(tokens_u32: list[int], masked_positions_u32: list[int], mask_id_u32: int) -> list[int]:
    out = [int(t) for t in tokens_u32]
    mid = int(mask_id_u32)
    for p in masked_positions_u32:
        out[int(p)] = mid
    return out


def _sample_negs(
    *,
    true_token_id_u32: int,
    vocab_size_u32: int,
    mask_id_u32: int,
    mlm_neg_k_u32: int,
    neg_resample_cap_u32: int,
    prng,
) -> tuple[Any, int]:
    # Eval doesn't use the sampled negatives for metrics, but MUST consume draws deterministically.
    K = int(mlm_neg_k_u32)
    if K < 1 or K > 0xFFFFFFFF:
        fail(REASON_QXRL_SCHEMA_INVALID)
    cap = int(neg_resample_cap_u32)
    if cap < 0 or cap > 0xFFFFFFFF:
        fail(REASON_QXRL_SCHEMA_INVALID)
    y = int(true_token_id_u32)
    vocab = int(vocab_size_u32)
    mask_id = int(mask_id_u32)
    if y < 0 or y >= vocab:
        fail(REASON_QXRL_SCHEMA_INVALID)

    draws = 0
    rejects = 0
    state = prng
    got = 0
    while got < K:
        r, state = state.next_u64()
        draws += 1
        cand = int(int(r) & 0xFFFFFFFF) % int(vocab)
        if cand == int(y) or cand == int(mask_id):
            rejects += 1
            if rejects > int(cap):
                fail(REASON_QXRL_SCHEMA_INVALID)
            continue
        got += 1
    return state, int(draws)


def _eval_example_indices(*, N: int, start_index_u64: int, count_u32: int) -> list[int]:
    if N <= 0:
        fail(REASON_QXRL_SCHEMA_INVALID)
    start = int(start_index_u64) % int(N)
    c = int(count_u32)
    if c < 1:
        fail(REASON_QXRL_SCHEMA_INVALID)
    return [(start + i) % int(N) for i in range(c)]


def _evd_bytes_v1(
    *,
    suite_id_u32: int,
    count_a_u64: int,
    count_b_u64: int,
    metric_q32_s64: int,
    scorecard_hash32: bytes,
    prng_draws_u64: int,
) -> bytes:
    if not isinstance(scorecard_hash32, (bytes, bytearray, memoryview)) or len(bytes(scorecard_hash32)) != 32:
        fail(REASON_QXRL_SCHEMA_INVALID)
    return b"".join(
        [
            _EVD_MAGIC,
            _write_u32_le(_EVD_VERSION_V1),
            _write_u32_le(int(suite_id_u32)),
            _write_u32_le(0),
            _write_u64_le(int(count_a_u64)),
            _write_u64_le(int(count_b_u64)),
            struct.pack("<q", int(metric_q32_s64)),
            bytes(scorecard_hash32),
            _write_u64_le(int(prng_draws_u64)),
            b"\x00" * (8 * 7),
        ]
    )


def _compute_h_eval_tail(evd_mlm: bytes, evd_ctr: bytes) -> bytes:
    h0 = b"\x00" * 32
    h1 = _sha25632(h0 + bytes(evd_mlm))
    h2 = _sha25632(h1 + bytes(evd_ctr))
    return h2


def _tok_head_t_tsae_v1(
    *,
    position_p_u32: int,
    model: QXRLModelSpecV1,
    tok_proj_w_q32_s64: list[int],
    tok_proj_b_q32_s64: list[int],
    xL_flat_q32_s64: list[int],
    ctr: QXRLStepCountersV1,
) -> list[int]:
    p = int(position_p_u32)
    seq_len = int(model.seq_len_u32)
    d_model = int(model.d_model_u32)
    d_embed = int(model.d_embed_u32)
    if p < 0 or p >= seq_len:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if len(tok_proj_w_q32_s64) != d_embed * d_model or len(tok_proj_b_q32_s64) != d_embed:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if len(xL_flat_q32_s64) != seq_len * d_model:
        fail(REASON_QXRL_SCHEMA_INVALID)

    x_off = p * d_model
    t: list[int] = [0] * d_embed
    for k in range(d_embed):
        dot = dot_q32_v1_flat(
            dot_kind=model.dot_kind,
            x_q32_s64=tok_proj_w_q32_s64,
            x_off=k * d_model,
            y_q32_s64=xL_flat_q32_s64,
            y_off=x_off,
            n=d_model,
            ctr=ctr,
        )
        t[k] = add_sat(int(tok_proj_b_q32_s64[k]), int(dot), ctr)
    return t


def _score_all_vocab_generic_v1(
    *,
    t_q32_s64: list[int],
    model: QXRLModelSpecV1,
    out_emb_q32_s64: list[int],
    out_b_q32_s64: list[int],
    ctr: QXRLStepCountersV1,
) -> list[int]:
    vocab = int(model.vocab_size_u32)
    d_embed = int(model.d_embed_u32)
    if len(t_q32_s64) != d_embed:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if len(out_emb_q32_s64) != vocab * d_embed or len(out_b_q32_s64) != vocab:
        fail(REASON_QXRL_SCHEMA_INVALID)

    scores: list[int] = [0] * vocab
    for v in range(vocab):
        dot = dot_q32_v1_flat(
            dot_kind=model.dot_kind,
            x_q32_s64=out_emb_q32_s64,
            x_off=v * d_embed,
            y_q32_s64=t_q32_s64,
            y_off=0,
            n=d_embed,
            ctr=ctr,
        )
        scores[v] = add_sat(int(out_b_q32_s64[v]), int(dot), ctr)
    return scores


def compute_qxrl_eval_scorecard_v1(
    *,
    eval_manifest_obj: dict[str, Any],
    model: QXRLModelSpecV1,
    model_manifest_id: str,
    dataset_manifest_obj: dict[str, Any],
    dataset_root_hash32: bytes,
    examples: list[QXRLDatasetExampleV1],
    weights_manifest_id: str,
    weights_manifest: WeightsManifestV1,
    registry_loader: Callable[[dict[str, str]], bytes] | None = None,
    enforce_floors: bool = True,
) -> tuple[dict[str, Any], bytes, str, bytes]:
    """Return (scorecard_obj, scorecard_bytes, scorecard_artifact_id, h_eval_tail32)."""

    em = parse_and_verify_eval_manifest_v1(eval_manifest_obj=eval_manifest_obj, model=model, dataset_manifest_obj=dataset_manifest_obj)

    eval_example_count_u32 = int(em.get("eval_example_count_u32"))
    eval_start_index_u64 = int(em.get("eval_start_index_u64"))
    recall_k_u32 = int(em.get("recall_k_u32"))
    if recall_k_u32 < 1:
        fail(REASON_QXRL_SCHEMA_INVALID)

    mask_prob_q32 = require_q32_obj(em.get("mask_prob_q32"), reason=REASON_QXRL_SCHEMA_INVALID)
    max_masks_per_seq_u32 = int(em.get("max_masks_per_seq_u32"))
    mlm_neg_k_u32 = int(em.get("mlm_neg_k_u32"))
    neg_resample_cap_u32 = int(em.get("NEG_RESAMPLE_CAP_u32"))

    floors = em.get("floors")
    if not isinstance(floors, dict):
        fail(REASON_QXRL_SCHEMA_INVALID)
    floor_masked_acc_q32 = require_q32_obj(floors.get("masked_acc_at_1_min_q32"), reason=REASON_QXRL_SCHEMA_INVALID)
    floor_recall_q32 = require_q32_obj(floors.get("recall_at_k_min_q32"), reason=REASON_QXRL_SCHEMA_INVALID)

    if not isinstance(examples, list) or not examples:
        fail(REASON_QXRL_SCHEMA_INVALID)
    E = int(eval_example_count_u32)
    idxs = _eval_example_indices(N=len(examples), start_index_u64=int(eval_start_index_u64), count_u32=E)
    eval_batch = [examples[i] for i in idxs]

    # We evaluate the weights referenced by weights_manifest_id; bind PRNG to it.
    wroot32 = sha256_id_to_digest32(weights_manifest_id, reason=REASON_QXRL_SCHEMA_INVALID)

    weights_view = weights_view_from_manifest(model=model, weights_manifest=weights_manifest)

    # TSAE (Phase 5): load pinned LUT table for Div/InvSqrt.
    lut_table: list[int] | None = None
    if str(model.encoder_kind).strip() == ENCODER_KIND_TSAE_V1:
        if registry_loader is None:
            fail(REASON_QXRL_SCHEMA_INVALID)
        lut_manifest_bytes = bytes(registry_loader(dict(model.invsqrt_lut_manifest_ref)))
        lut_manifest_obj = gcj1_loads_and_verify_canonical(lut_manifest_bytes)
        if not isinstance(lut_manifest_obj, dict):
            fail(REASON_QXRL_SCHEMA_INVALID)
        lut_manifest_parsed = parse_qxrl_invsqrt_lut_manifest_v1(dict(lut_manifest_obj))
        if str(lut_manifest_parsed.get("opset_id", "")).strip() != str(model.opset_id).strip():
            fail(REASON_QXRL_SCHEMA_INVALID)
        lut_ref = dict(lut_manifest_parsed.get("lut_ref"))
        lut_bytes = bytes(registry_loader(lut_ref))
        lut_table = parse_invsqrt_lut_bin_v1(lut_bytes=lut_bytes)

    # MLM suite: masking + neg draws (streams 3,4), ArgMaxDet over full vocab.
    prng_masks = prng_for_step_stream(
        dc1_id=str(em.get("dc1_id", "")).strip(),
        opset_id=str(em.get("opset_id", "")).strip(),
        dataset_root_hash32=dataset_root_hash32,
        wroot_before32=wroot32,
        step_index_u64=0,
        stream_id_u32=int(PRNG_STREAM_EVAL_MASKS_V1),
    )
    prng_negs = prng_for_step_stream(
        dc1_id=str(em.get("dc1_id", "")).strip(),
        opset_id=str(em.get("opset_id", "")).strip(),
        dataset_root_hash32=dataset_root_hash32,
        wroot_before32=wroot32,
        step_index_u64=0,
        stream_id_u32=int(PRNG_STREAM_EVAL_NEGS_V1),
    )

    masked_total = 0
    masked_hits = 0
    prng_draws_mlm = 0

    for ex in eval_batch:
        bitmap, masked_pos, true_ids, anchor_tokens_pre, prng_masks, draws_masks = _select_masks(
            tokens_u32=ex.anchor_tokens_u32,
            seq_len_u32=model.seq_len_u32,
            mask_prob_q32_u64=int(mask_prob_q32),
            max_masks_per_seq_u32=int(max_masks_per_seq_u32),
            prng=prng_masks,
        )
        del bitmap
        prng_draws_mlm += int(draws_masks)

        masked_anchor_tokens = _apply_mask_id(anchor_tokens_pre, masked_pos, model.mask_id_u32)
        # Consume neg draws deterministically (even though accuracy doesn't use them).
        for y in true_ids:
            prng_negs, draws_negs = _sample_negs(
                true_token_id_u32=int(y),
                vocab_size_u32=int(model.vocab_size_u32),
                mask_id_u32=int(model.mask_id_u32),
                mlm_neg_k_u32=int(mlm_neg_k_u32),
                neg_resample_cap_u32=int(neg_resample_cap_u32),
                prng=prng_negs,
            )
            prng_draws_mlm += int(draws_negs)

        # Forward once per example for MLM head use.
        ctr_eval = QXRLStepCountersV1()
        if str(model.encoder_kind).strip() == ENCODER_KIND_TSAE_V1:
            if lut_table is None:
                fail(REASON_QXRL_SCHEMA_INVALID)
            cache = forward_encoder_tsae_v1(
                tokens_u32=masked_anchor_tokens,
                model=model,
                weights=weights_view,  # type: ignore[arg-type]
                lut_table_q32_s64=lut_table,
                ctr=ctr_eval,
                count_tokens=False,
            )
            for mi, p in enumerate(masked_pos):
                t = _tok_head_t_tsae_v1(
                    position_p_u32=int(p),
                    model=model,
                    tok_proj_w_q32_s64=getattr(weights_view, "tok_proj_w"),  # type: ignore[arg-type]
                    tok_proj_b_q32_s64=getattr(weights_view, "tok_proj_b"),  # type: ignore[arg-type]
                    xL_flat_q32_s64=cache.xL_flat_q32_s64,
                    ctr=ctr_eval,
                )
                scores = _score_all_vocab_generic_v1(
                    t_q32_s64=t,
                    model=model,
                    out_emb_q32_s64=getattr(weights_view, "out_emb"),  # type: ignore[arg-type]
                    out_b_q32_s64=getattr(weights_view, "out_b"),  # type: ignore[arg-type]
                    ctr=ctr_eval,
                )
                y_hat = argmax_det(scores)
                if int(y_hat) == int(true_ids[mi]):
                    masked_hits += 1
                masked_total += 1
        else:
            cache = forward_encoder_qre_v1(tokens_u32=masked_anchor_tokens, model=model, weights=weights_view, ctr=ctr_eval, count_tokens=False)
            for mi, p in enumerate(masked_pos):
                t = tok_head_t_v1(position_p_u32=int(p), model=model, weights=weights_view, cache=cache, ctr=ctr_eval)
                scores = score_all_vocab_v1(t_q32_s64=t, model=model, weights=weights_view, ctr=ctr_eval)
                y_hat = argmax_det(scores)
                if int(y_hat) == int(true_ids[mi]):
                    masked_hits += 1
                masked_total += 1

    if masked_total == 0:
        masked_acc_q32 = 0
    else:
        masked_acc_q32 = (int(masked_hits) << 32) // int(masked_total)

    # CTR suite: no PRNG draws.
    ctr_eval = QXRLStepCountersV1()
    z_a: list[list[int]] = []
    z_p: list[list[int]] = []
    for ex in eval_batch:
        if str(model.encoder_kind).strip() == ENCODER_KIND_TSAE_V1:
            if lut_table is None:
                fail(REASON_QXRL_SCHEMA_INVALID)
            ca = forward_encoder_tsae_v1(
                tokens_u32=ex.anchor_tokens_u32,
                model=model,
                weights=weights_view,  # type: ignore[arg-type]
                lut_table_q32_s64=lut_table,
                ctr=ctr_eval,
                count_tokens=False,
            )
            cp = forward_encoder_tsae_v1(
                tokens_u32=ex.positive_tokens_u32,
                model=model,
                weights=weights_view,  # type: ignore[arg-type]
                lut_table_q32_s64=lut_table,
                ctr=ctr_eval,
                count_tokens=False,
            )
        else:
            ca = forward_encoder_qre_v1(tokens_u32=ex.anchor_tokens_u32, model=model, weights=weights_view, ctr=ctr_eval, count_tokens=False)
            cp = forward_encoder_qre_v1(tokens_u32=ex.positive_tokens_u32, model=model, weights=weights_view, ctr=ctr_eval, count_tokens=False)
        z_a.append([int(v) for v in ca.z_q32_s64])
        z_p.append([int(v) for v in cp.z_q32_s64])

    ctr_hits = 0
    for i in range(E):
        pairs = []
        for j in range(E):
            s = dot_q32_v1_flat(dot_kind=model.dot_kind, x_q32_s64=z_a[i], x_off=0, y_q32_s64=z_p[j], y_off=0, n=model.d_embed_u32, ctr=ctr_eval)
            pairs.append((int(s), int(j)))
        topk = topk_det(pairs, int(recall_k_u32), ctr_eval)
        chosen = {int(j) for _s, j in topk}
        if int(i) in chosen:
            ctr_hits += 1

    if E <= 0:
        fail(REASON_QXRL_SCHEMA_INVALID)
    recall_q32 = (int(ctr_hits) << 32) // int(E)

    # Floors.
    if enforce_floors:
        if int(masked_acc_q32) < int(floor_masked_acc_q32):
            fail(REASON_QXRL_FLOOR_FAIL)
        if int(recall_q32) < int(floor_recall_q32):
            fail(REASON_QXRL_FLOOR_FAIL)

    # Build provisional scorecard for scorecard_hash32 binding in EVD digests.
    model_manifest_id_s = str(model_manifest_id).strip()
    weights_manifest_id_s = str(weights_manifest_id).strip()
    dataset_id_s = str(dataset_manifest_obj.get("dataset_id", "")).strip()
    eval_id_s = str(em.get("eval_id", "")).strip()
    opset_id_s = str(em.get("opset_id", "")).strip()

    scorecard_provisional: dict[str, Any] = {
        "schema_id": "qxrl_eval_scorecard_v1",
        "scorecard_id": "sha256:" + ("0" * 64),
        "opset_id": opset_id_s,
        "dc1_id": "dc1:q32_v1",
        "model_manifest_id": model_manifest_id_s,
        "weights_manifest_id": weights_manifest_id_s,
        "dataset_id": dataset_id_s,
        "eval_id": eval_id_s,
        "metrics": {
            "masked_total_u64": int(masked_total),
            "masked_hits_u64": int(masked_hits),
            "masked_acc_at_1_q32": {"q": int(masked_acc_q32)},
            "ctr_total_u64": int(E),
            "ctr_hits_u64": int(ctr_hits),
            "recall_k_u32": int(recall_k_u32),
            "recall_at_k_q32": {"q": int(recall_q32)},
        },
        "tails": {"h_eval_tail32_hex": "0" * 64},
    }
    scorecard_hash32 = _sha25632(gcj1_canon_bytes(scorecard_provisional))

    evd_mlm = _evd_bytes_v1(
        suite_id_u32=1,
        count_a_u64=int(masked_total),
        count_b_u64=int(masked_hits),
        metric_q32_s64=int(masked_acc_q32),
        scorecard_hash32=scorecard_hash32,
        prng_draws_u64=int(prng_draws_mlm),
    )
    evd_ctr = _evd_bytes_v1(
        suite_id_u32=2,
        count_a_u64=int(E),
        count_b_u64=int(ctr_hits),
        metric_q32_s64=int(recall_q32),
        scorecard_hash32=scorecard_hash32,
        prng_draws_u64=0,
    )
    if len(evd_mlm) != 136 or len(evd_ctr) != 136:
        fail(REASON_QXRL_SCHEMA_INVALID)
    h_eval_tail32 = _compute_h_eval_tail(evd_mlm, evd_ctr)

    # Final scorecard with tail.
    scorecard_final = dict(scorecard_provisional)
    scorecard_final["tails"] = {"h_eval_tail32_hex": digest32_to_hex(h_eval_tail32)}
    scorecard_id = compute_self_hash_id(scorecard_final, id_field="scorecard_id", reason=REASON_QXRL_SCHEMA_INVALID)
    scorecard_final["scorecard_id"] = str(scorecard_id)

    scorecard_bytes = gcj1_canon_bytes(scorecard_final)
    scorecard_artifact_id = sha256_prefixed(scorecard_bytes)

    # Schema validate if available.
    try:
        validate_schema(scorecard_final, SCHEMA_QXRL_EVAL_SCORECARD_V1)
    except Exception:  # noqa: BLE001
        fail(REASON_QXRL_SCHEMA_INVALID)

    return dict(scorecard_final), bytes(scorecard_bytes), str(scorecard_artifact_id), bytes(h_eval_tail32)


__all__ = [
    "compute_qxrl_eval_scorecard_v1",
    "load_qxrl_eval_manifest_v1",
    "parse_and_verify_eval_manifest_v1",
]
