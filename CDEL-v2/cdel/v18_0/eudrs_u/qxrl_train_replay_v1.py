"""QXRL deterministic training replay (v1, Phase 4).

Implements:
  - weights_manifest_v1 + q32_tensor_block_v1.bin decoding/encoding (Phase 4 contract)
  - per-step per-stream XORSHIFT128+ PRNG selection of masks + negatives
  - QRE forward, hinge losses, backward, SGD+momentum updates
  - eudrs_u_train_step_digest_v1 (Phase 4 layout) and H_train tail computation

This module is RE2: deterministic, fail-closed, no floats, no filesystem discovery.
"""

from __future__ import annotations

import hashlib
import struct
import sys
from array import array
from dataclasses import dataclass
from typing import Any, Final

from ..omega_common_v1 import Q32_ONE, fail, validate_schema
from .eudrs_u_artifact_refs_v1 import require_artifact_ref_v1
from .eudrs_u_hash_v1 import gcj1_canon_bytes, gcj1_loads_and_verify_canonical, sha256_prefixed
from .eudrs_u_merkle_v1 import merkle_fanout_v1
from .qxrl_backward_v1 import (
    backward_encoder_qre_v1_add_grads,
    backward_mlm_hinge_for_masked_pos_add_grads,
    backward_mlm_hinge_for_masked_pos_add_grads_tsae_v1,
    backward_encoder_tsae_v1_add_grads,
    ctr_hinge_and_dz_for_batch,
)
from .qxrl_common_v1 import (
    DOT_KIND_SHIFT_EACH,
    DOT_KIND_SHIFT_END,
    ENCODER_KIND_TSAE_V1,
    OPTIMIZER_KIND_ADAMW_Q32_V1,
    OPTIMIZER_KIND_SGD_MOMENTUM_Q32_V1,
    parse_qxrl_invsqrt_lut_manifest_v1,
    PRNG_STREAM_TRAIN_MASKS_V1,
    PRNG_STREAM_TRAIN_NEGS_V1,
    REASON_QXRL_PRNG_COUNTER_MISMATCH,
    REASON_QXRL_SCHEMA_INVALID,
    REASON_QXRL_SEGMENT_DECODE_FAIL,
    SCHEMA_QXRL_TRAINING_MANIFEST_V1,
    compute_self_hash_id,
    digest32_to_hex,
    hex64_to_bytes32,
    mask_id_for_tokenizer,
    prng_for_step_stream,
    q32_obj,
    require_q32_obj,
    sha256_id_to_digest32,
)
from .qxrl_dataset_v1 import QXRLDatasetExampleV1
from .qxrl_forward_qre_v1 import QXRLForwardCacheV1, QXRLModelSpecV1, QXRLWeightsViewV1, forward_encoder_qre_v1
from .qxrl_forward_tsae_v1 import QXRLTSAEForwardCacheV1, QXRLWeightsViewTSAEV1, forward_encoder_tsae_v1
from .qxrl_opset_math_v1 import parse_invsqrt_lut_bin_v1
from .qxrl_optimizer_v1 import sgd_momentum_update_inplace_q32_v1
from .qxrl_ops_v1 import QXRLStepCountersV1, add_sat, mul_q32, q32_vec_to_bytes


_Q32T_MAGIC: Final[bytes] = b"Q32T"
_Q32T_VERSION_V1: Final[int] = 1
_Q32T_HEADER_STRUCT = struct.Struct("<4sII")  # magic, version, elem_count

_TRD_MAGIC: Final[bytes] = b"TRD1"
_TRD_VERSION_V1: Final[int] = 1


@dataclass(frozen=True, slots=True)
class WeightsBlockDescV1:
    elem_offset_u64: int
    elem_count_u32: int
    block_ref: dict[str, str]


@dataclass(frozen=True, slots=True)
class WeightsTensorDescV1:
    name: str
    dtype: str
    shape_u32: list[int]
    blocks: list[WeightsBlockDescV1]
    data_q32_s64: list[int]  # flattened


@dataclass(frozen=True, slots=True)
class WeightsManifestV1:
    obj: dict[str, Any]  # original JSON
    dc1_id: str
    opset_id: str
    merkle_fanout_u32: int
    weights_merkle_root32_hex: str
    tensors: list[WeightsTensorDescV1]  # sorted by name


@dataclass(frozen=True, slots=True)
class QXRLTrainStepExampleSelectionV1:
    example_id_u64: int
    mask_bitmap_bytes: bytes
    masked_positions_u32: list[int]
    true_token_ids_u32: list[int]
    neg_token_ids_by_mask_pos: list[list[int]]  # parallel to masked_positions


@dataclass(frozen=True, slots=True)
class QXRLTrainStepDebugV1:
    step_index_u64: int
    selections: list[QXRLTrainStepExampleSelectionV1]
    batch_hash32: bytes
    wm_batch_hash32: bytes
    prng_draws_masks_u64: int
    prng_draws_negs_u64: int
    prng_counter_u64: int


def _require_int(value: Any, *, reason: str) -> int:
    if not isinstance(value, int):
        fail(reason)
    return int(value)


def _require_u32(value: Any, *, reason: str) -> int:
    if not isinstance(value, int) or value < 0 or value > 0xFFFFFFFF:
        fail(reason)
    return int(value)


def _require_u64(value: Any, *, reason: str) -> int:
    if not isinstance(value, int) or value < 0:
        fail(reason)
    return int(value)


def _prod_shape(shape_u32: list[int]) -> int:
    if not isinstance(shape_u32, list) or not shape_u32:
        fail(REASON_QXRL_SCHEMA_INVALID)
    p = 1
    for d in shape_u32:
        if not isinstance(d, int) or d <= 0:
            fail(REASON_QXRL_SCHEMA_INVALID)
        p *= int(d)
        if p < 0:
            fail(REASON_QXRL_SCHEMA_INVALID)
    return int(p)


def _decode_q32_tensor_block_v1(raw: bytes, *, expected_elem_count_u32: int) -> list[int]:
    mv = memoryview(raw)
    if mv.ndim != 1 or len(mv) < _Q32T_HEADER_STRUCT.size:
        fail(REASON_QXRL_SCHEMA_INVALID)
    magic, version_u32, elem_count_u32 = _Q32T_HEADER_STRUCT.unpack_from(mv, 0)
    if bytes(magic) != _Q32T_MAGIC:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if int(version_u32) != _Q32T_VERSION_V1:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if int(elem_count_u32) != int(expected_elem_count_u32):
        fail(REASON_QXRL_SCHEMA_INVALID)
    n = int(elem_count_u32)
    expected_len = _Q32T_HEADER_STRUCT.size + (n * 8)
    if expected_len != len(mv):
        fail(REASON_QXRL_SCHEMA_INVALID)
    arr = array("q")
    arr.frombytes(mv[_Q32T_HEADER_STRUCT.size :].tobytes())
    if sys.byteorder != "little":
        arr.byteswap()
    return [int(v) for v in arr]


def _encode_q32_tensor_block_v1(values_q32_s64: list[int]) -> bytes:
    if not isinstance(values_q32_s64, list):
        fail(REASON_QXRL_SCHEMA_INVALID)
    n = len(values_q32_s64)
    header = _Q32T_HEADER_STRUCT.pack(_Q32T_MAGIC, int(_Q32T_VERSION_V1) & 0xFFFFFFFF, int(n) & 0xFFFFFFFF)
    arr = array("q", (int(v) for v in values_q32_s64))
    if sys.byteorder != "little":
        arr.byteswap()
    return header + arr.tobytes()


def _weights_block_relpath_from_id(block_artifact_id: str) -> str:
    hex64 = sha256_id_to_digest32(block_artifact_id, reason=REASON_QXRL_SCHEMA_INVALID).hex()
    return f"polymath/registry/eudrs_u/weights/blocks/sha256_{hex64}.q32_tensor_block_v1.bin"


def _weights_manifest_relpath_from_id(weights_manifest_id: str) -> str:
    hex64 = sha256_id_to_digest32(weights_manifest_id, reason=REASON_QXRL_SCHEMA_INVALID).hex()
    return f"polymath/registry/eudrs_u/weights/sha256_{hex64}.weights_manifest_v1.json"


def load_qxrl_training_manifest_v1(training_manifest_bytes: bytes, *, schema_validate: bool = True) -> dict[str, Any]:
    obj = gcj1_loads_and_verify_canonical(training_manifest_bytes)
    if not isinstance(obj, dict):
        fail(REASON_QXRL_SCHEMA_INVALID)
    if schema_validate:
        try:
            validate_schema(obj, SCHEMA_QXRL_TRAINING_MANIFEST_V1)
        except Exception:  # noqa: BLE001 - fail-closed
            fail(REASON_QXRL_SCHEMA_INVALID)
    if str(obj.get("schema_id", "")).strip() != SCHEMA_QXRL_TRAINING_MANIFEST_V1:
        fail(REASON_QXRL_SCHEMA_INVALID)
    return dict(obj)


def parse_and_verify_training_manifest_v1(training_manifest_obj: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(training_manifest_obj, dict):
        fail(REASON_QXRL_SCHEMA_INVALID)
    if str(training_manifest_obj.get("schema_id", "")).strip() != SCHEMA_QXRL_TRAINING_MANIFEST_V1:
        fail(REASON_QXRL_SCHEMA_INVALID)

    expected_id = compute_self_hash_id(training_manifest_obj, id_field="training_id", reason=REASON_QXRL_SCHEMA_INVALID)
    if str(training_manifest_obj.get("training_id", "")).strip() != expected_id:
        fail(REASON_QXRL_SCHEMA_INVALID)

    # Phase 4 restriction: checkpoint every step.
    if int(training_manifest_obj.get("checkpoint_every_steps_u32", 0)) != 1:
        fail(REASON_QXRL_SCHEMA_INVALID)

    dot_kind = str(training_manifest_obj.get("dot_kind", "")).strip()
    if dot_kind not in {DOT_KIND_SHIFT_END, DOT_KIND_SHIFT_EACH}:
        fail(REASON_QXRL_SCHEMA_INVALID)

    optimizer_kind = str(training_manifest_obj.get("optimizer_kind", "")).strip()
    if optimizer_kind not in {OPTIMIZER_KIND_SGD_MOMENTUM_Q32_V1, OPTIMIZER_KIND_ADAMW_Q32_V1}:
        fail(REASON_QXRL_SCHEMA_INVALID)

    return dict(training_manifest_obj)


def _require_weights_manifest_obj(obj: dict[str, Any]) -> None:
    if not isinstance(obj, dict) or str(obj.get("schema_id", "")).strip() != "weights_manifest_v1":
        fail(REASON_QXRL_SCHEMA_INVALID)

    dc1_id = str(obj.get("dc1_id", "")).strip()
    opset_id = str(obj.get("opset_id", "")).strip()
    if dc1_id != "dc1:q32_v1" or not opset_id:
        fail(REASON_QXRL_SCHEMA_INVALID)

    fanout = obj.get("merkle_fanout_u32")
    if not isinstance(fanout, int) or fanout <= 0:
        fail(REASON_QXRL_SCHEMA_INVALID)

    root_hex = str(obj.get("weights_merkle_root32_hex", "")).strip()
    if len(root_hex) != 64:
        fail(REASON_QXRL_SCHEMA_INVALID)
    _ = hex64_to_bytes32(root_hex, reason=REASON_QXRL_SCHEMA_INVALID)

    tensors = obj.get("tensors")
    if not isinstance(tensors, list) or not tensors:
        fail(REASON_QXRL_SCHEMA_INVALID)


def load_and_verify_weights_manifest_v1(
    *,
    weights_manifest_obj: dict[str, Any],
    registry_loader: callable,  # ArtifactRefV1 -> bytes
) -> WeightsManifestV1:
    _require_weights_manifest_obj(weights_manifest_obj)

    dc1_id = str(weights_manifest_obj.get("dc1_id", "")).strip()
    opset_id = str(weights_manifest_obj.get("opset_id", "")).strip()
    merkle_fanout_u32 = int(weights_manifest_obj.get("merkle_fanout_u32"))
    weights_merkle_root32_hex = str(weights_manifest_obj.get("weights_merkle_root32_hex", "")).strip()

    tensors_raw = list(weights_manifest_obj.get("tensors"))
    # Enforce sorted by name ascending.
    names = [str(t.get("name", "")).strip() for t in tensors_raw if isinstance(t, dict)]
    if names != sorted(names):
        fail(REASON_QXRL_SCHEMA_INVALID)

    tensors: list[WeightsTensorDescV1] = []
    leaf_hash32: list[bytes] = []

    for t in tensors_raw:
        if not isinstance(t, dict):
            fail(REASON_QXRL_SCHEMA_INVALID)
        name = str(t.get("name", "")).strip()
        if not name:
            fail(REASON_QXRL_SCHEMA_INVALID)
        dtype = str(t.get("dtype", "")).strip()
        if dtype != "Q32_S64_V1":
            fail(REASON_QXRL_SCHEMA_INVALID)
        shape = t.get("shape_u32")
        if not isinstance(shape, list) or not shape:
            fail(REASON_QXRL_SCHEMA_INVALID)
        shape_u32 = [_require_u32(d, reason=REASON_QXRL_SCHEMA_INVALID) for d in shape]
        total = _prod_shape(shape_u32)

        blocks_raw = t.get("blocks")
        if not isinstance(blocks_raw, list) or not blocks_raw:
            fail(REASON_QXRL_SCHEMA_INVALID)
        # Enforce sorted by elem_offset_u64 ascending and contiguous.
        blocks: list[WeightsBlockDescV1] = []
        data: list[int] = [0] * total

        expected_off = 0
        for b in blocks_raw:
            if not isinstance(b, dict):
                fail(REASON_QXRL_SCHEMA_INVALID)
            elem_offset_u64 = _require_u64(b.get("elem_offset_u64"), reason=REASON_QXRL_SCHEMA_INVALID)
            elem_count_u32 = _require_u32(b.get("elem_count_u32"), reason=REASON_QXRL_SCHEMA_INVALID)
            if elem_count_u32 <= 0:
                fail(REASON_QXRL_SCHEMA_INVALID)
            if elem_offset_u64 != expected_off:
                fail(REASON_QXRL_SCHEMA_INVALID)
            if elem_offset_u64 + elem_count_u32 > total:
                fail(REASON_QXRL_SCHEMA_INVALID)
            block_ref = require_artifact_ref_v1(b.get("block_ref"))
            block_bytes = bytes(registry_loader(block_ref))
            leaf_hash32.append(hashlib.sha256(block_bytes).digest())
            block_vals = _decode_q32_tensor_block_v1(block_bytes, expected_elem_count_u32=elem_count_u32)
            data[int(elem_offset_u64) : int(elem_offset_u64) + int(elem_count_u32)] = [int(v) for v in block_vals]
            blocks.append(WeightsBlockDescV1(elem_offset_u64=int(elem_offset_u64), elem_count_u32=int(elem_count_u32), block_ref=block_ref))
            expected_off = int(elem_offset_u64) + int(elem_count_u32)

        if expected_off != total:
            fail(REASON_QXRL_SCHEMA_INVALID)

        tensors.append(WeightsTensorDescV1(name=name, dtype=dtype, shape_u32=shape_u32, blocks=blocks, data_q32_s64=data))

    # Verify Merkle root.
    root32 = merkle_fanout_v1(leaf_hash32=leaf_hash32, fanout_u32=int(merkle_fanout_u32))
    if digest32_to_hex(root32) != weights_merkle_root32_hex:
        fail(REASON_QXRL_SCHEMA_INVALID)

    return WeightsManifestV1(
        obj=dict(weights_manifest_obj),
        dc1_id=dc1_id,
        opset_id=opset_id,
        merkle_fanout_u32=int(merkle_fanout_u32),
        weights_merkle_root32_hex=weights_merkle_root32_hex,
        tensors=tensors,
    )


def weights_view_from_manifest(*, model: QXRLModelSpecV1, weights_manifest: WeightsManifestV1) -> QXRLWeightsViewV1:
    by_name = {t.name: t for t in weights_manifest.tensors}

    def _req(name: str, expected_shape: list[int]) -> list[int]:
        row = by_name.get(name)
        if row is None:
            fail(REASON_QXRL_SCHEMA_INVALID)
        if [int(d) for d in row.shape_u32] != [int(d) for d in expected_shape]:
            fail(REASON_QXRL_SCHEMA_INVALID)
        data = row.data_q32_s64
        return data

    vocab = int(model.vocab_size_u32)
    seq_len = int(model.seq_len_u32)
    d_model = int(model.d_model_u32)
    d_embed = int(model.d_embed_u32)
    if str(model.encoder_kind).strip() == ENCODER_KIND_TSAE_V1:
        n_layers = int(model.n_layers_u32)
        d_ff = int(model.d_ff_u32)
        # Build per-layer weights.
        from .qxrl_forward_tsae_v1 import QXRLTSAELayerWeightsV1

        layers_w: list[QXRLTSAELayerWeightsV1] = []
        for l in range(n_layers):
            layers_w.append(
                QXRLTSAELayerWeightsV1(
                    wq=_req(f"qxrl/tsae/l{l}/wq", [d_model, d_model]),
                    wk=_req(f"qxrl/tsae/l{l}/wk", [d_model, d_model]),
                    wv=_req(f"qxrl/tsae/l{l}/wv", [d_model, d_model]),
                    wo=_req(f"qxrl/tsae/l{l}/wo", [d_model, d_model]),
                    rms1_gamma=_req(f"qxrl/tsae/l{l}/rms1_gamma", [d_model]),
                    rms2_gamma=_req(f"qxrl/tsae/l{l}/rms2_gamma", [d_model]),
                    ff_w1=_req(f"qxrl/tsae/l{l}/ff_w1", [d_ff, d_model]),
                    ff_b1=_req(f"qxrl/tsae/l{l}/ff_b1", [d_ff]),
                    ff_w2=_req(f"qxrl/tsae/l{l}/ff_w2", [d_model, d_ff]),
                    ff_b2=_req(f"qxrl/tsae/l{l}/ff_b2", [d_model]),
                )
            )

        return QXRLWeightsViewTSAEV1(
            tok_emb=_req("qxrl/tok_emb", [vocab, d_model]),
            pos_emb=_req("qxrl/pos_emb", [seq_len, d_model]),
            layers=layers_w,
            proj_w=_req("qxrl/tsae/proj_w", [d_embed, d_model]),
            proj_b=_req("qxrl/tsae/proj_b", [d_embed]),
            tok_proj_w=_req("qxrl/tok_proj_w", [d_embed, d_model]),
            tok_proj_b=_req("qxrl/tok_proj_b", [d_embed]),
            out_emb=_req("qxrl/out_emb", [vocab, d_embed]),
            out_b=_req("qxrl/out_b", [vocab]),
        )

    d_hidden = int(model.d_hidden_u32)
    return QXRLWeightsViewV1(
        tok_emb=_req("qxrl/tok_emb", [vocab, d_model]),
        pos_emb=_req("qxrl/pos_emb", [seq_len, d_model]),
        enc_w1=_req("qxrl/enc_w1", [d_hidden, d_model]),
        enc_b1=_req("qxrl/enc_b1", [d_hidden]),
        enc_w2=_req("qxrl/enc_w2", [d_embed, d_hidden]),
        enc_b2=_req("qxrl/enc_b2", [d_embed]),
        tok_proj_w=_req("qxrl/tok_proj_w", [d_embed, d_model]),
        tok_proj_b=_req("qxrl/tok_proj_b", [d_embed]),
        out_emb=_req("qxrl/out_emb", [vocab, d_embed]),
        out_b=_req("qxrl/out_b", [vocab]),
    )


def _momentum_name_for_param(param_name: str) -> str:
    if not isinstance(param_name, str) or not param_name.startswith("qxrl/"):
        fail(REASON_QXRL_SCHEMA_INVALID)
    return "qxrl/opt/mom/" + param_name[len("qxrl/") :]


def _require_momentum_tensors_present(weights_manifest: WeightsManifestV1, *, param_names: list[str]) -> None:
    names = {t.name for t in weights_manifest.tensors}
    for p in param_names:
        m = _momentum_name_for_param(p)
        if m not in names:
            fail(REASON_QXRL_SCHEMA_INVALID)


def _write_u32_le(x: int) -> bytes:
    return struct.pack("<I", int(x) & 0xFFFFFFFF)


def _write_u64_le(x: int) -> bytes:
    return struct.pack("<Q", int(x) & 0xFFFFFFFFFFFFFFFF)


def _mask_bitmap_nbytes(seq_len_u32: int) -> int:
    L = int(seq_len_u32)
    if L < 0:
        fail(REASON_QXRL_SCHEMA_INVALID)
    return (L + 7) // 8


def _select_masks_for_anchor(
    *,
    anchor_tokens_u32: list[int],
    seq_len_u32: int,
    mask_prob_q32_u64: int,
    max_masks_per_seq_u32: int,
    prng,
) -> tuple[bytes, list[int], list[int], list[int], Any, int]:
    """Return (mask_bitmap_bytes, masked_positions, true_token_ids, masked_anchor_tokens, prng_after, draws)."""

    seq_len = int(seq_len_u32)
    if not isinstance(anchor_tokens_u32, list) or len(anchor_tokens_u32) != seq_len:
        fail(REASON_QXRL_SCHEMA_INVALID)
    prob = int(mask_prob_q32_u64)
    if prob < 0 or prob > (1 << 32):
        fail(REASON_QXRL_SCHEMA_INVALID)
    cap = _require_u32(max_masks_per_seq_u32, reason=REASON_QXRL_SCHEMA_INVALID)
    bitmap = bytearray(_mask_bitmap_nbytes(seq_len))
    masked_positions: list[int] = []
    true_token_ids: list[int] = []
    masked_anchor = [int(t) for t in anchor_tokens_u32]

    draws = 0
    state = prng
    for p in range(seq_len):
        r, state = state.next_u64()
        draws += 1
        r_u32 = (int(r) >> 32) & 0xFFFFFFFF
        if r_u32 < prob and len(masked_positions) < int(cap):
            masked_positions.append(int(p))
            true_token_ids.append(int(anchor_tokens_u32[p]))
            byte_i = int(p) // 8
            bit_i = int(p) % 8
            bitmap[byte_i] |= 1 << bit_i
    return bytes(bitmap), masked_positions, true_token_ids, masked_anchor, state, int(draws)


def _apply_mask_id(masked_anchor_tokens_u32: list[int], masked_positions_u32: list[int], mask_id_u32: int) -> list[int]:
    out = [int(t) for t in masked_anchor_tokens_u32]
    mid = int(mask_id_u32)
    for p in masked_positions_u32:
        out[int(p)] = mid
    return out


def _sample_negs_for_masked_pos(
    *,
    true_token_id_u32: int,
    vocab_size_u32: int,
    mask_id_u32: int,
    mlm_neg_k_u32: int,
    neg_resample_cap_u32: int,
    prng,
) -> tuple[list[int], Any, int]:
    K = _require_u32(mlm_neg_k_u32, reason=REASON_QXRL_SCHEMA_INVALID)
    if K < 1:
        fail(REASON_QXRL_SCHEMA_INVALID)
    cap = _require_u32(neg_resample_cap_u32, reason=REASON_QXRL_SCHEMA_INVALID)
    y = _require_u32(true_token_id_u32, reason=REASON_QXRL_SCHEMA_INVALID)
    vocab = _require_u32(vocab_size_u32, reason=REASON_QXRL_SCHEMA_INVALID)
    mask_id = _require_u32(mask_id_u32, reason=REASON_QXRL_SCHEMA_INVALID)

    out: list[int] = []
    draws = 0
    rejects = 0
    state = prng
    while len(out) < int(K):
        r, state = state.next_u64()
        draws += 1
        cand = int(int(r) & 0xFFFFFFFF) % int(vocab)
        if cand == int(y) or cand == int(mask_id):
            rejects += 1
            if rejects > int(cap):
                fail(REASON_QXRL_SCHEMA_INVALID)
            continue
        out.append(int(cand))
    return out, state, int(draws)


def _batch_indices_for_step(*, step_u64: int, batch_size_u32: int, N: int) -> list[int]:
    u = _require_u64(step_u64, reason=REASON_QXRL_SCHEMA_INVALID)
    bsz = _require_u32(batch_size_u32, reason=REASON_QXRL_SCHEMA_INVALID)
    if N <= 0 or bsz <= 0:
        fail(REASON_QXRL_SCHEMA_INVALID)
    start = ((int(u) - 1) * int(bsz)) % int(N)
    idx: list[int] = []
    for k in range(int(bsz)):
        idx.append((start + k) % int(N))
    return idx


def _train_step_digest_bytes_v1(
    *,
    step_index_u64: int,
    batch_hash32: bytes,
    wm_batch_hash32: bytes,
    wroot_before32: bytes,
    wroot_after32: bytes,
    optroot_after32: bytes,
    prng_counter_u64: int,
    token_count_u64: int,
    dot_ops_u64: int,
    topk_ops_u64: int,
    prng_draws_u64: int,
    saturation_events_u64: int,
) -> bytes:
    if any(len(x) != 32 for x in [batch_hash32, wm_batch_hash32, wroot_before32, wroot_after32, optroot_after32]):
        fail(REASON_QXRL_SCHEMA_INVALID)
    zero32 = b"\x00" * 32
    reserved = b"\x00" * (8 * 4)
    return b"".join(
        [
            _TRD_MAGIC,
            _write_u32_le(_TRD_VERSION_V1),
            _write_u64_le(step_index_u64),
            bytes(batch_hash32),
            bytes(wm_batch_hash32),
            zero32,  # retrieval_trace_root32 (Phase 4: all-zero)
            bytes(wroot_before32),
            bytes(wroot_after32),
            bytes(optroot_after32),
            _write_u64_le(prng_counter_u64),
            _write_u64_le(token_count_u64),
            _write_u64_le(dot_ops_u64),
            _write_u64_le(topk_ops_u64),
            _write_u64_le(prng_draws_u64),
            _write_u64_le(saturation_events_u64),
            reserved,
        ]
    )


def _sha25632(data: bytes) -> bytes:
    return hashlib.sha256(bytes(data)).digest()


def _compute_h_train_tail(digests: list[bytes]) -> bytes:
    h = b"\x00" * 32
    for row in digests:
        h = _sha25632(h + bytes(row))
    return h


def _build_weights_manifest_bytes_from_descs(
    *,
    dc1_id: str,
    opset_id: str,
    merkle_fanout_u32: int,
    tensor_descs: list[WeightsTensorDescV1],
) -> tuple[dict[str, Any], bytes, str, list[tuple[dict[str, str], bytes]]]:
    # Deterministic tensor ordering.
    rows = sorted(tensor_descs, key=lambda t: str(t.name))
    if [t.name for t in rows] != [t.name for t in tensor_descs]:
        # Caller must supply sorted tensors.
        rows = rows

    blocks_out: list[tuple[dict[str, str], bytes]] = []
    leaf_hash32: list[bytes] = []

    tensors_obj: list[dict[str, Any]] = []
    for t in rows:
        total = _prod_shape(t.shape_u32)
        if len(t.data_q32_s64) != total:
            fail(REASON_QXRL_SCHEMA_INVALID)
        blocks_obj: list[dict[str, Any]] = []
        for b in t.blocks:
            off = int(b.elem_offset_u64)
            cnt = int(b.elem_count_u32)
            if off < 0 or cnt <= 0 or off + cnt > total:
                fail(REASON_QXRL_SCHEMA_INVALID)
            vals = [int(v) for v in t.data_q32_s64[off : off + cnt]]
            block_bytes = _encode_q32_tensor_block_v1(vals)
            leaf_hash32.append(_sha25632(block_bytes))
            block_id = sha256_prefixed(block_bytes)
            block_ref = {"artifact_id": block_id, "artifact_relpath": _weights_block_relpath_from_id(block_id)}
            blocks_out.append((block_ref, block_bytes))
            blocks_obj.append({"elem_offset_u64": int(off), "elem_count_u32": int(cnt), "block_ref": block_ref})

        tensors_obj.append(
            {
                "name": str(t.name),
                "dtype": "Q32_S64_V1",
                "shape_u32": [int(d) for d in t.shape_u32],
                "blocks": blocks_obj,
            }
        )

    root32 = merkle_fanout_v1(leaf_hash32=leaf_hash32, fanout_u32=int(merkle_fanout_u32))
    manifest_obj: dict[str, Any] = {
        "schema_id": "weights_manifest_v1",
        "dc1_id": str(dc1_id),
        "opset_id": str(opset_id),
        "merkle_fanout_u32": int(merkle_fanout_u32),
        "tensors": tensors_obj,
        "weights_merkle_root32_hex": digest32_to_hex(root32),
    }
    manifest_bytes = gcj1_canon_bytes(manifest_obj)
    manifest_id = sha256_prefixed(manifest_bytes)
    return manifest_obj, manifest_bytes, manifest_id, blocks_out


def replay_qxrl_training_v1(
    *,
    training_manifest_obj: dict[str, Any],
    model: QXRLModelSpecV1,
    dataset_root_hash32: bytes,
    examples: list[QXRLDatasetExampleV1],
    initial_weights_manifest_id: str,
    initial_weights_manifest: WeightsManifestV1,
    registry_loader: callable,  # ArtifactRefV1 -> bytes (for decoding initial weights blocks already loaded)
    return_debug: bool = False,
) -> tuple[bytes, str, dict[str, Any], list[tuple[dict[str, str], bytes]] | None, bytes, list[QXRLTrainStepDebugV1] | None]:
    """Replay training and return:

    (final_weights_manifest_bytes, final_weights_manifest_id, final_weights_manifest_obj,
     final_blocks_to_write (optional), h_train_tail32, debug_steps (optional))
    """

    tm = parse_and_verify_training_manifest_v1(training_manifest_obj)

    if str(tm.get("dc1_id", "")).strip() != "dc1:q32_v1":
        fail(REASON_QXRL_SCHEMA_INVALID)
    if str(tm.get("opset_id", "")).strip() != str(model.opset_id).strip():
        fail(REASON_QXRL_SCHEMA_INVALID)

    dot_kind = str(tm.get("dot_kind", "")).strip()
    if dot_kind != str(model.dot_kind).strip():
        fail(REASON_QXRL_SCHEMA_INVALID)

    optimizer_kind = str(tm.get("optimizer_kind", "")).strip()
    if optimizer_kind != OPTIMIZER_KIND_SGD_MOMENTUM_Q32_V1:
        # Phase 5 verifier rejects ADAMW; training replay remains fail-closed.
        fail(REASON_QXRL_SCHEMA_INVALID)

    train_steps_u64 = _require_u64(tm.get("train_steps_u64"), reason=REASON_QXRL_SCHEMA_INVALID)
    batch_size_u32 = _require_u32(tm.get("batch_size_u32"), reason=REASON_QXRL_SCHEMA_INVALID)
    checkpoint_every_steps_u32 = _require_u32(tm.get("checkpoint_every_steps_u32"), reason=REASON_QXRL_SCHEMA_INVALID)
    if checkpoint_every_steps_u32 != 1:
        fail(REASON_QXRL_SCHEMA_INVALID)

    mask_prob_q32 = require_q32_obj(tm.get("mask_prob_q32"), reason=REASON_QXRL_SCHEMA_INVALID)
    max_masks_per_seq_u32 = _require_u32(tm.get("max_masks_per_seq_u32"), reason=REASON_QXRL_SCHEMA_INVALID)
    mlm_neg_k_u32 = _require_u32(tm.get("mlm_neg_k_u32"), reason=REASON_QXRL_SCHEMA_INVALID)
    neg_resample_cap_u32 = _require_u32(tm.get("NEG_RESAMPLE_CAP_u32"), reason=REASON_QXRL_SCHEMA_INVALID)

    mlm_margin_q32 = require_q32_obj(tm.get("mlm_margin_q32"), reason=REASON_QXRL_SCHEMA_INVALID)
    ctr_margin_q32 = require_q32_obj(tm.get("ctr_margin_q32"), reason=REASON_QXRL_SCHEMA_INVALID)
    mlm_loss_weight_q32 = require_q32_obj(tm.get("mlm_loss_weight_q32"), reason=REASON_QXRL_SCHEMA_INVALID)
    ctr_loss_weight_q32 = require_q32_obj(tm.get("ctr_loss_weight_q32"), reason=REASON_QXRL_SCHEMA_INVALID)

    lr_q32 = require_q32_obj(tm.get("lr_q32"), reason=REASON_QXRL_SCHEMA_INVALID)
    momentum_q32 = require_q32_obj(tm.get("momentum_q32"), reason=REASON_QXRL_SCHEMA_INVALID)
    grad_clip_abs_q32 = None
    if "grad_clip_abs_q32" in tm:
        grad_clip_abs_q32 = require_q32_obj(tm.get("grad_clip_abs_q32"), reason=REASON_QXRL_SCHEMA_INVALID)

    if not isinstance(examples, list) or not examples:
        fail(REASON_QXRL_SCHEMA_INVALID)

    # Ensure required tensors and momentum exist.
    w = initial_weights_manifest
    param_names = [str(name) for name in list(model.trainable_names)]
    _require_momentum_tensors_present(w, param_names=param_names)

    wroot_before_id = str(initial_weights_manifest_id).strip()
    wroot_before32 = sha256_id_to_digest32(wroot_before_id, reason=REASON_QXRL_SCHEMA_INVALID)

    # Step 0 digest (no update, no PRNG).
    digests: list[bytes] = []
    empty_batch_hash32 = _sha25632(b"QXRL_EMPTY_BATCH_V1")
    empty_wm_hash32 = _sha25632(b"QXRL_EMPTY_WM_BATCH_V1")
    digests.append(
        _train_step_digest_bytes_v1(
            step_index_u64=0,
            batch_hash32=empty_batch_hash32,
            wm_batch_hash32=empty_wm_hash32,
            wroot_before32=wroot_before32,
            wroot_after32=wroot_before32,
            optroot_after32=wroot_before32,
            prng_counter_u64=0,
            token_count_u64=0,
            dot_ops_u64=0,
            topk_ops_u64=0,
            prng_draws_u64=0,
            saturation_events_u64=0,
        )
    )

    debug_steps: list[QXRLTrainStepDebugV1] = []

    # Training steps u=1..train_steps.
    current_manifest = w
    current_manifest_id = wroot_before_id
    current_manifest32 = wroot_before32
    last_manifest_obj: dict[str, Any] | None = None
    last_manifest_bytes: bytes | None = None
    last_manifest_id: str | None = None
    last_blocks: list[tuple[dict[str, str], bytes]] | None = None

    for u in range(1, int(train_steps_u64) + 1):
        ctr = QXRLStepCountersV1()

        # Map tensors by name for this step's mutable weights/momentum arrays.
        tensors_by_name: dict[str, WeightsTensorDescV1] = {t.name: t for t in current_manifest.tensors}

        def _tensor_data(name: str) -> list[int]:
            t = tensors_by_name.get(name)
            if t is None:
                fail(REASON_QXRL_SCHEMA_INVALID)
            return t.data_q32_s64

        def _momentum_data_for(param_name: str) -> list[int]:
            return _tensor_data(_momentum_name_for_param(param_name))

        # Per-step PRNG streams.
        prng_masks = prng_for_step_stream(
            dc1_id=str(tm.get("dc1_id", "")).strip(),
            opset_id=str(tm.get("opset_id", "")).strip(),
            dataset_root_hash32=dataset_root_hash32,
            wroot_before32=current_manifest32,
            step_index_u64=int(u),
            stream_id_u32=int(PRNG_STREAM_TRAIN_MASKS_V1),
        )
        prng_negs = prng_for_step_stream(
            dc1_id=str(tm.get("dc1_id", "")).strip(),
            opset_id=str(tm.get("opset_id", "")).strip(),
            dataset_root_hash32=dataset_root_hash32,
            wroot_before32=current_manifest32,
            step_index_u64=int(u),
            stream_id_u32=int(PRNG_STREAM_TRAIN_NEGS_V1),
        )

        batch_indices = _batch_indices_for_step(step_u64=u, batch_size_u32=batch_size_u32, N=len(examples))
        batch: list[QXRLDatasetExampleV1] = [examples[i] for i in batch_indices]

        selections: list[QXRLTrainStepExampleSelectionV1] = []
        draws_masks_total = 0
        draws_negs_total = 0

        # Gradients for params (flattened).
        grads: dict[str, list[int]] = {}
        for name in param_names:
            grads[name] = [0] * len(_tensor_data(name))

        # Forward caches.
        cache_masked_anchor: list[object] = []
        cache_anchor: list[object] = []
        cache_pos: list[object] = []
        z_a: list[list[int]] = []
        z_p: list[list[int]] = []
        L_mlm_sum_example: list[int] = [0] * len(batch)
        dx_mlm_masked_anchor: list[list[int]] = [[0] * (int(model.seq_len_u32) * int(model.d_model_u32)) for _ in range(len(batch))]

        # TSAE LUT (Phase 5): load once per step if needed.
        lut_table: list[int] | None = None
        if str(model.encoder_kind).strip() == ENCODER_KIND_TSAE_V1:
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

        # Mask selection + MLM backprop per example.
        for bi, ex in enumerate(batch):
            bitmap, masked_pos, true_ids, anchor_tokens_pre, prng_masks, draws_masks = _select_masks_for_anchor(
                anchor_tokens_u32=ex.anchor_tokens_u32,
                seq_len_u32=model.seq_len_u32,
                mask_prob_q32_u64=int(mask_prob_q32),
                max_masks_per_seq_u32=max_masks_per_seq_u32,
                prng=prng_masks,
            )
            draws_masks_total += int(draws_masks)

            # Apply MASK_ID.
            masked_anchor_tokens = _apply_mask_id(anchor_tokens_pre, masked_pos, model.mask_id_u32)

            # Negative sampling.
            negs_by_pos: list[list[int]] = []
            for y in true_ids:
                negs, prng_negs, draws_negs = _sample_negs_for_masked_pos(
                    true_token_id_u32=int(y),
                    vocab_size_u32=int(model.vocab_size_u32),
                    mask_id_u32=int(model.mask_id_u32),
                    mlm_neg_k_u32=int(mlm_neg_k_u32),
                    neg_resample_cap_u32=int(neg_resample_cap_u32),
                    prng=prng_negs,
                )
                draws_negs_total += int(draws_negs)
                negs_by_pos.append(negs)

            selections.append(
                QXRLTrainStepExampleSelectionV1(
                    example_id_u64=int(ex.example_id_u64),
                    mask_bitmap_bytes=bytes(bitmap),
                    masked_positions_u32=[int(p) for p in masked_pos],
                    true_token_ids_u32=[int(y) for y in true_ids],
                    neg_token_ids_by_mask_pos=[[int(n) for n in row] for row in negs_by_pos],
                )
            )

            # Forward passes (masked anchor for MLM head; unmasked anchor/pos for embeddings).
            weights_view = weights_view_from_manifest(model=model, weights_manifest=current_manifest)
            if str(model.encoder_kind).strip() == ENCODER_KIND_TSAE_V1:
                if lut_table is None:
                    fail(REASON_QXRL_SCHEMA_INVALID)
                cache_m = forward_encoder_tsae_v1(
                    tokens_u32=masked_anchor_tokens,
                    model=model,
                    weights=weights_view,  # type: ignore[arg-type]
                    lut_table_q32_s64=lut_table,
                    ctr=ctr,
                    count_tokens=True,
                )
                cache_a = forward_encoder_tsae_v1(
                    tokens_u32=ex.anchor_tokens_u32,
                    model=model,
                    weights=weights_view,  # type: ignore[arg-type]
                    lut_table_q32_s64=lut_table,
                    ctr=ctr,
                    count_tokens=True,
                )
                cache_p = forward_encoder_tsae_v1(
                    tokens_u32=ex.positive_tokens_u32,
                    model=model,
                    weights=weights_view,  # type: ignore[arg-type]
                    lut_table_q32_s64=lut_table,
                    ctr=ctr,
                    count_tokens=True,
                )
            else:
                cache_m = forward_encoder_qre_v1(tokens_u32=masked_anchor_tokens, model=model, weights=weights_view, ctr=ctr, count_tokens=True)
                cache_a = forward_encoder_qre_v1(tokens_u32=ex.anchor_tokens_u32, model=model, weights=weights_view, ctr=ctr, count_tokens=True)
                cache_p = forward_encoder_qre_v1(tokens_u32=ex.positive_tokens_u32, model=model, weights=weights_view, ctr=ctr, count_tokens=True)
            cache_masked_anchor.append(cache_m)
            cache_anchor.append(cache_a)
            cache_pos.append(cache_p)
            if isinstance(cache_a, QXRLTSAEForwardCacheV1):
                z_a.append([int(v) for v in cache_a.z_q32_s64])
                z_p.append([int(v) for v in cache_p.z_q32_s64])  # type: ignore[attr-defined]
            else:
                z_a.append([int(v) for v in cache_a.z_q32_s64])  # type: ignore[attr-defined]
                z_p.append([int(v) for v in cache_p.z_q32_s64])  # type: ignore[attr-defined]

            # MLM losses + grads for each masked position.
            for mi, p in enumerate(masked_pos):
                if isinstance(cache_m, QXRLTSAEForwardCacheV1):
                    loss_m = backward_mlm_hinge_for_masked_pos_add_grads_tsae_v1(
                        model=model,
                        weights=weights_view,  # type: ignore[arg-type]
                        cache_masked_anchor=cache_m,
                        masked_pos_u32=int(p),
                        true_token_id_u32=int(true_ids[mi]),
                        neg_token_ids_u32=negs_by_pos[mi],
                        mlm_margin_q32_s64=int(mlm_margin_q32),
                        mlm_loss_weight_q32_s64=int(mlm_loss_weight_q32),
                        grad_tok_proj_w=grads["qxrl/tok_proj_w"],
                        grad_tok_proj_b=grads["qxrl/tok_proj_b"],
                        grad_out_emb=grads["qxrl/out_emb"],
                        grad_out_b=grads["qxrl/out_b"],
                        dxL_flat_q32_s64=dx_mlm_masked_anchor[bi],
                        ctr=ctr,
                    )
                else:
                    loss_m = backward_mlm_hinge_for_masked_pos_add_grads(
                        model=model,
                        weights=weights_view,
                        cache_masked_anchor=cache_m,  # type: ignore[arg-type]
                        masked_pos_u32=int(p),
                        true_token_id_u32=int(true_ids[mi]),
                        neg_token_ids_u32=negs_by_pos[mi],
                        mlm_margin_q32_s64=int(mlm_margin_q32),
                        mlm_loss_weight_q32_s64=int(mlm_loss_weight_q32),
                        grad_tok_emb=grads["qxrl/tok_emb"],
                        grad_pos_emb=grads["qxrl/pos_emb"],
                        grad_tok_proj_w=grads["qxrl/tok_proj_w"],
                        grad_tok_proj_b=grads["qxrl/tok_proj_b"],
                        grad_out_emb=grads["qxrl/out_emb"],
                        grad_out_b=grads["qxrl/out_b"],
                        ctr=ctr,
                    )
                L_mlm_sum_example[bi] = add_sat(int(L_mlm_sum_example[bi]), int(loss_m), ctr)

        # Contrastive hinge: compute dz and losses.
        dz_a, dz_p, L_ctr_example = ctr_hinge_and_dz_for_batch(
            z_a_by_example=z_a,
            z_p_by_example=z_p,
            ctr_margin_q32_s64=int(ctr_margin_q32),
            ctr_loss_weight_q32_s64=int(ctr_loss_weight_q32),
            dot_kind=model.dot_kind,
            ctr=ctr,
        )

        # Encoder backprop for anchor + positive.
        for i in range(len(batch)):
            weights_view = weights_view_from_manifest(model=model, weights_manifest=current_manifest)
            if isinstance(cache_anchor[i], QXRLTSAEForwardCacheV1):
                backward_encoder_tsae_v1_add_grads(
                    model=model,
                    weights=weights_view,  # type: ignore[arg-type]
                    cache=cache_anchor[i],  # type: ignore[arg-type]
                    dz_q32_s64=dz_a[i],
                    dxL_flat_q32_s64=None,
                    grads_by_name=grads,
                    ctr=ctr,
                )
                backward_encoder_tsae_v1_add_grads(
                    model=model,
                    weights=weights_view,  # type: ignore[arg-type]
                    cache=cache_pos[i],  # type: ignore[arg-type]
                    dz_q32_s64=dz_p[i],
                    dxL_flat_q32_s64=None,
                    grads_by_name=grads,
                    ctr=ctr,
                )
                backward_encoder_tsae_v1_add_grads(
                    model=model,
                    weights=weights_view,  # type: ignore[arg-type]
                    cache=cache_masked_anchor[i],  # type: ignore[arg-type]
                    dz_q32_s64=None,
                    dxL_flat_q32_s64=dx_mlm_masked_anchor[i],
                    grads_by_name=grads,
                    ctr=ctr,
                )
            else:
                backward_encoder_qre_v1_add_grads(
                    model=model,
                    weights=weights_view,
                    cache=cache_anchor[i],  # type: ignore[arg-type]
                    dz_q32_s64=dz_a[i],
                    grad_tok_emb=grads["qxrl/tok_emb"],
                    grad_pos_emb=grads["qxrl/pos_emb"],
                    grad_enc_w1=grads["qxrl/enc_w1"],
                    grad_enc_b1=grads["qxrl/enc_b1"],
                    grad_enc_w2=grads["qxrl/enc_w2"],
                    grad_enc_b2=grads["qxrl/enc_b2"],
                    ctr=ctr,
                )
                backward_encoder_qre_v1_add_grads(
                    model=model,
                    weights=weights_view,
                    cache=cache_pos[i],  # type: ignore[arg-type]
                    dz_q32_s64=dz_p[i],
                    grad_tok_emb=grads["qxrl/tok_emb"],
                    grad_pos_emb=grads["qxrl/pos_emb"],
                    grad_enc_w1=grads["qxrl/enc_w1"],
                    grad_enc_b1=grads["qxrl/enc_b1"],
                    grad_enc_w2=grads["qxrl/enc_w2"],
                    grad_enc_b2=grads["qxrl/enc_b2"],
                    ctr=ctr,
                )

        # Compute batch_hash32 (selection evidence).
        bb = bytearray()
        bb += b"QXRL_BATCH_V1"
        bb += _write_u64_le(u)
        bb += _write_u32_le(batch_size_u32)
        for sel in selections:
            bb += _write_u64_le(sel.example_id_u64)
            bb += bytes(sel.mask_bitmap_bytes)
            bb += _write_u32_le(len(sel.masked_positions_u32))
            for mi, p in enumerate(sel.masked_positions_u32):
                bb += _write_u32_le(int(p))
                bb += _write_u32_le(int(sel.true_token_ids_u32[mi]))
                bb += _write_u32_le(int(mlm_neg_k_u32))
                for neg in sel.neg_token_ids_by_mask_pos[mi]:
                    bb += _write_u32_le(int(neg))
        batch_hash32 = _sha25632(bytes(bb))

        # Compute wm_batch_hash32.
        wm = bytearray()
        wm += b"QXRL_WM_BATCH_V1"
        for i in range(len(batch)):
            za_hash32 = _sha25632(q32_vec_to_bytes(cache_anchor[i].z_q32_s64))
            zp_hash32 = _sha25632(q32_vec_to_bytes(cache_pos[i].z_q32_s64))

            # Per-example losses:
            L_ctr = int(L_ctr_example[i])
            L_mlm = int(L_mlm_sum_example[i])
            L_total = add_sat(int(mul_q32(int(mlm_loss_weight_q32), int(L_mlm), ctr)), int(mul_q32(int(ctr_loss_weight_q32), int(L_ctr), ctr)), ctr)
            loss_bytes = struct.pack("<qqq", int(L_mlm), int(L_ctr), int(L_total))
            wm += za_hash32
            wm += zp_hash32
            wm += loss_bytes
        wm_batch_hash32 = _sha25632(bytes(wm))

        # PRNG counter rule (per-step).
        prng_counter_u64 = int(draws_masks_total) + int(draws_negs_total)
        if prng_counter_u64 != int(draws_masks_total) + int(draws_negs_total):
            fail(REASON_QXRL_PRNG_COUNTER_MISMATCH)

        # Apply optimizer updates in-place (params + momentum tensors), producing a new weights manifest.
        # Update each param tensor and its momentum tensor.
        for name in param_names:
            w_data = _tensor_data(name)
            m_data = _momentum_data_for(name)
            g_data = grads[name]
            sgd_momentum_update_inplace_q32_v1(
                w_q32_s64=w_data,
                m_q32_s64=m_data,
                g_q32_s64=g_data,
                lr_q32_s64=int(lr_q32),
                momentum_q32_s64=int(momentum_q32),
                grad_clip_abs_q32_s64=grad_clip_abs_q32,
                ctr=ctr,
            )

        # Rebuild weights manifest bytes deterministically from updated tensor data, preserving block layouts.
        updated_descs: list[WeightsTensorDescV1] = []
        for t in current_manifest.tensors:
            updated_descs.append(
                WeightsTensorDescV1(
                    name=str(t.name),
                    dtype=str(t.dtype),
                    shape_u32=[int(d) for d in t.shape_u32],
                    blocks=[WeightsBlockDescV1(elem_offset_u64=int(b.elem_offset_u64), elem_count_u32=int(b.elem_count_u32), block_ref=dict(b.block_ref)) for b in t.blocks],
                    data_q32_s64=list(t.data_q32_s64),
                )
            )

        new_manifest_obj, new_manifest_bytes, new_manifest_id, new_blocks = _build_weights_manifest_bytes_from_descs(
            dc1_id=current_manifest.dc1_id,
            opset_id=current_manifest.opset_id,
            merkle_fanout_u32=current_manifest.merkle_fanout_u32,
            tensor_descs=updated_descs,
        )
        new_manifest32 = sha256_id_to_digest32(new_manifest_id, reason=REASON_QXRL_SCHEMA_INVALID)
        last_manifest_obj = dict(new_manifest_obj)
        last_manifest_bytes = bytes(new_manifest_bytes)
        last_manifest_id = str(new_manifest_id)
        last_blocks = list(new_blocks)

        # Step digest.
        step_digest = _train_step_digest_bytes_v1(
            step_index_u64=int(u),
            batch_hash32=batch_hash32,
            wm_batch_hash32=wm_batch_hash32,
            wroot_before32=current_manifest32,
            wroot_after32=new_manifest32,
            optroot_after32=new_manifest32,
            prng_counter_u64=int(prng_counter_u64),
            token_count_u64=int(ctr.token_count_u64),
            dot_ops_u64=int(ctr.dot_ops_u64),
            topk_ops_u64=int(ctr.topk_ops_u64),
            prng_draws_u64=int(prng_counter_u64),
            saturation_events_u64=int(ctr.saturation_events_u64),
        )
        if len(step_digest) != 288:
            fail(REASON_QXRL_SCHEMA_INVALID)
        digests.append(step_digest)

        if return_debug:
            debug_steps.append(
                QXRLTrainStepDebugV1(
                    step_index_u64=int(u),
                    selections=selections,
                    batch_hash32=batch_hash32,
                    wm_batch_hash32=wm_batch_hash32,
                    prng_draws_masks_u64=int(draws_masks_total),
                    prng_draws_negs_u64=int(draws_negs_total),
                    prng_counter_u64=int(prng_counter_u64),
                )
            )

        # Advance current manifest for next step (weights already updated in-place).
        current_manifest = WeightsManifestV1(
            obj=dict(new_manifest_obj),
            dc1_id=str(current_manifest.dc1_id),
            opset_id=str(current_manifest.opset_id),
            merkle_fanout_u32=int(current_manifest.merkle_fanout_u32),
            weights_merkle_root32_hex=str(new_manifest_obj.get("weights_merkle_root32_hex", "")).strip(),
            tensors=updated_descs,
        )
        current_manifest_id = str(new_manifest_id)
        current_manifest32 = bytes(new_manifest32)

    # Final.
    h_train_tail32 = _compute_h_train_tail(digests)

    if int(train_steps_u64) >= 1:
        if last_manifest_obj is None or last_manifest_bytes is None or last_manifest_id is None or last_blocks is None:
            fail(REASON_QXRL_SCHEMA_INVALID)
        final_manifest_obj = dict(last_manifest_obj)
        final_manifest_bytes = bytes(last_manifest_bytes)
        final_manifest_id = str(last_manifest_id)
        final_blocks_out = list(last_blocks)
    else:
        final_manifest_obj = dict(initial_weights_manifest.obj)
        final_manifest_bytes = gcj1_canon_bytes(initial_weights_manifest.obj)
        final_manifest_id = str(initial_weights_manifest_id)
        final_blocks_out = []
    return (
        bytes(final_manifest_bytes),
        str(final_manifest_id),
        dict(final_manifest_obj),
        list(final_blocks_out),
        bytes(h_train_tail32),
        debug_steps if return_debug else None,
    )


__all__ = [
    "QXRLTrainStepDebugV1",
    "WeightsManifestV1",
    "load_and_verify_weights_manifest_v1",
    "load_qxrl_training_manifest_v1",
    "parse_and_verify_training_manifest_v1",
    "replay_qxrl_training_v1",
    "weights_view_from_manifest",
]
