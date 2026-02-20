"""QXRL common helpers (v1).

This module is RE2: deterministic, fail-closed, and must not depend on floats.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from typing import Any, Final

from ..omega_common_v1 import fail, validate_schema
from .eudrs_u_artifact_refs_v1 import require_artifact_ref_v1
from .eudrs_u_hash_v1 import gcj1_canon_bytes, gcj1_loads_and_verify_canonical, sha256_prefixed

EUDRSU_OK: Final[str] = "EUDRSU_OK"

REASON_QXRL_SCHEMA_INVALID: Final[str] = "EUDRSU_QXRL_SCHEMA_INVALID"
REASON_QXRL_DATASET_HASH_MISMATCH: Final[str] = "EUDRSU_QXRL_DATASET_HASH_MISMATCH"
REASON_QXRL_SEGMENT_DECODE_FAIL: Final[str] = "EUDRSU_QXRL_SEGMENT_DECODE_FAIL"
REASON_QXRL_TRAIN_TAIL_MISMATCH: Final[str] = "EUDRSU_QXRL_TRAIN_TAIL_MISMATCH"
REASON_QXRL_PRNG_COUNTER_MISMATCH: Final[str] = "EUDRSU_QXRL_PRNG_COUNTER_MISMATCH"
REASON_QXRL_SCORECARD_MISMATCH: Final[str] = "EUDRSU_QXRL_SCORECARD_MISMATCH"
REASON_QXRL_EVAL_TAIL_MISMATCH: Final[str] = "EUDRSU_QXRL_EVAL_TAIL_MISMATCH"
REASON_QXRL_FLOOR_FAIL: Final[str] = "EUDRSU_QXRL_FLOOR_FAIL"
REASON_QXRL_TOPK_TIEBREAK_VIOLATION: Final[str] = "EUDRSU_QXRL_TOPK_TIEBREAK_VIOLATION"
REASON_QXRL_OPSET_LUT_MISMATCH: Final[str] = "EUDRSU_QXRL_OPSET_LUT_MISMATCH"
REASON_QXRL_OPTIMIZER_KIND_FORBIDDEN: Final[str] = "EUDRSU_QXRL_OPTIMIZER_KIND_FORBIDDEN"

SCHEMA_QXRL_MODEL_MANIFEST_V1: Final[str] = "qxrl_model_manifest_v1"
SCHEMA_QXRL_DATASET_MANIFEST_V1: Final[str] = "qxrl_dataset_manifest_v1"
SCHEMA_QXRL_TRAINING_MANIFEST_V1: Final[str] = "qxrl_training_manifest_v1"
SCHEMA_QXRL_EVAL_MANIFEST_V1: Final[str] = "qxrl_eval_manifest_v1"
SCHEMA_QXRL_EVAL_SCORECARD_V1: Final[str] = "qxrl_eval_scorecard_v1"
SCHEMA_QXRL_INVSQRT_LUT_MANIFEST_V1: Final[str] = "qxrl_invsqrt_lut_manifest_v1"

TOKENIZER_KIND_BYTE_TOK_257_V1: Final[str] = "BYTE_TOK_257_V1"
TOKENIZER_KIND_PRETOKENIZED_U32_V1: Final[str] = "PRETOKENIZED_U32_V1"

DATASET_KIND_PAIR_V1: Final[str] = "PAIR_V1"

ENCODER_KIND_QRE_V1: Final[str] = "QRE_V1"
ENCODER_KIND_TSAE_V1: Final[str] = "TSAE_V1"

DOT_KIND_SHIFT_END: Final[str] = "DOT_Q32_SHIFT_END_V1"
DOT_KIND_SHIFT_EACH: Final[str] = "DOT_Q32_SHIFT_EACH_DIM_V1"

DIV_KIND_Q32_POS_RNE_V1: Final[str] = "DIV_Q32_POS_RNE_V1"
INVSQRT_KIND_Q32_NR_LUT_V1: Final[str] = "INVSQRT_Q32_NR_LUT_V1"

LUT_KIND_INVSQRT_Q32_NR_LUT_V1: Final[str] = "INVSQRT_Q32_NR_LUT_V1"
LUT_BITS_PHASE5_U32: Final[int] = 10
INVSQRT_ITERS_PHASE5_U32: Final[int] = 2
INVSQRT_LUT_ARTIFACT_ID_PHASE5: Final[str] = "sha256:f6b7eac00dae22340aefefc36692994958acb88933698f97968ae9cb37e97864"

OPTIMIZER_KIND_SGD_MOMENTUM_Q32_V1: Final[str] = "SGD_MOMENTUM_Q32_V1"
OPTIMIZER_KIND_ADAMW_Q32_V1: Final[str] = "ADAMW_Q32_V1"

PREFERENCE_FEATURE_KIND_PROPOSAL_HASH_HEAD32_Q32_V1: Final[str] = "PROPOSAL_HASH_HEAD32_Q32_V1"
PREFERENCE_HEAD_WEIGHT_TENSOR_NAME: Final[str] = "qxrl/pref_head/w"

PRNG_STREAM_TRAIN_MASKS_V1: Final[int] = 1
PRNG_STREAM_TRAIN_NEGS_V1: Final[int] = 2
PRNG_STREAM_EVAL_MASKS_V1: Final[int] = 3
PRNG_STREAM_EVAL_NEGS_V1: Final[int] = 4


def _require_u32(value: Any, *, reason: str) -> int:
    if not isinstance(value, int) or value < 0 or value > 0xFFFFFFFF:
        fail(reason)
    return int(value)


def _require_u64(value: Any, *, reason: str) -> int:
    if not isinstance(value, int) or value < 0:
        fail(reason)
    return int(value)


def require_q32_obj(value: Any, *, reason: str = REASON_QXRL_SCHEMA_INVALID) -> int:
    if not isinstance(value, dict) or set(value.keys()) != {"q"}:
        fail(reason)
    q = value.get("q")
    if not isinstance(q, int):
        fail(reason)
    return int(q)


def q32_obj(q: int) -> dict[str, int]:
    return {"q": int(q)}


def sha256_id_to_digest32(value: Any, *, reason: str = REASON_QXRL_SCHEMA_INVALID) -> bytes:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        fail(reason)
    hex64 = value.split(":", 1)[1]
    if len(hex64) != 64:
        fail(reason)
    try:
        raw = bytes.fromhex(hex64)
    except Exception:
        fail(reason)
    if len(raw) != 32:
        fail(reason)
    return raw


def digest32_to_hex(raw32: bytes, *, reason: str = REASON_QXRL_SCHEMA_INVALID) -> str:
    if not isinstance(raw32, (bytes, bytearray, memoryview)):
        fail(reason)
    b = bytes(raw32)
    if len(b) != 32:
        fail(reason)
    return b.hex()


def hex64_to_bytes32(value: Any, *, reason: str = REASON_QXRL_SCHEMA_INVALID) -> bytes:
    if not isinstance(value, str) or len(value) != 64:
        fail(reason)
    try:
        raw = bytes.fromhex(value)
    except Exception:
        fail(reason)
    if len(raw) != 32:
        fail(reason)
    return raw


def mask_id_for_tokenizer(*, tokenizer_kind: str, vocab_size_u32: int) -> int:
    kind = str(tokenizer_kind).strip()
    vocab_size = _require_u32(int(vocab_size_u32), reason=REASON_QXRL_SCHEMA_INVALID)
    if kind == TOKENIZER_KIND_BYTE_TOK_257_V1:
        if vocab_size != 257:
            fail(REASON_QXRL_SCHEMA_INVALID)
        return 256
    if kind == TOKENIZER_KIND_PRETOKENIZED_U32_V1:
        if vocab_size < 1:
            fail(REASON_QXRL_SCHEMA_INVALID)
        return int(vocab_size - 1)
    fail(REASON_QXRL_SCHEMA_INVALID)
    return 0


def compute_self_hash_id(obj: dict[str, Any], *, id_field: str, reason: str = REASON_QXRL_SCHEMA_INVALID) -> str:
    if not isinstance(obj, dict):
        fail(reason)
    if not isinstance(id_field, str) or not id_field:
        fail(reason)
    tmp = dict(obj)
    tmp[id_field] = "sha256:" + ("0" * 64)
    try:
        raw = gcj1_canon_bytes(tmp)
    except Exception:
        fail(reason)
    return sha256_prefixed(raw)


def compute_eval_id_config_hash(eval_manifest_obj: dict[str, Any]) -> str:
    """Compute a deterministic config hash for eval manifests.

    Note: The v1 MVP eval manifest includes `scorecard_ref`, while the scorecard
    includes `eval_id`, which makes a strict self-hash of the full eval JSON
    cyclic. Phase 4 verifiers treat `eval_id` as a config hash that excludes
    `scorecard_ref`.
    """

    if not isinstance(eval_manifest_obj, dict):
        fail(REASON_QXRL_SCHEMA_INVALID)
    tmp = dict(eval_manifest_obj)
    tmp["eval_id"] = "sha256:" + ("0" * 64)
    tmp.pop("scorecard_ref", None)
    raw = gcj1_canon_bytes(tmp)
    return sha256_prefixed(raw)


@dataclass(frozen=True, slots=True)
class QXRLTensorSpecV1:
    name: str
    shape_u32: tuple[int, ...]
    dtype: str
    trainable: bool


@dataclass(frozen=True, slots=True)
class QXRLModelSpecV1:
    model_id: str
    opset_id: str
    dc1_id: str

    tokenizer_kind: str
    vocab_size_u32: int
    seq_len_u32: int
    encoder_kind: str

    d_model_u32: int
    d_hidden_u32: int  # QRE only; 0 for TSAE
    d_embed_u32: int

    inv_seq_len_q32: int

    dot_kind: str
    div_kind: str
    invsqrt_kind: str
    invsqrt_lut_manifest_ref: dict[str, str]

    # TSAE config (Phase 5).
    n_layers_u32: int
    n_heads_u32: int
    d_head_u32: int
    d_ff_u32: int
    topk_u32: int
    rms_epsilon_q32: int

    mask_id_u32: int
    preference_head_enabled_b: bool
    preference_feature_kind: str
    tensor_specs: tuple[QXRLTensorSpecV1, ...]  # includes optimizer state tensors
    trainable_names: tuple[str, ...]  # sorted by name asc


def load_qxrl_model_manifest_v1(model_manifest_bytes: bytes, *, schema_validate: bool = True) -> dict[str, Any]:
    obj = gcj1_loads_and_verify_canonical(model_manifest_bytes)
    if not isinstance(obj, dict):
        fail(REASON_QXRL_SCHEMA_INVALID)
    if schema_validate:
        try:
            validate_schema(obj, SCHEMA_QXRL_MODEL_MANIFEST_V1)
        except Exception:  # noqa: BLE001 - fail-closed
            fail(REASON_QXRL_SCHEMA_INVALID)
    if str(obj.get("schema_id", "")).strip() != SCHEMA_QXRL_MODEL_MANIFEST_V1:
        fail(REASON_QXRL_SCHEMA_INVALID)
    return dict(obj)


def _expected_inv_seq_len_q32(*, seq_len_u32: int) -> int:
    L = _require_u32(seq_len_u32, reason=REASON_QXRL_SCHEMA_INVALID)
    if L <= 0:
        fail(REASON_QXRL_SCHEMA_INVALID)
    return (1 << 32) // int(L)


def _prod_shape_u32(shape_u32: list[int]) -> int:
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


def _momentum_name_for_param(param_name: str) -> str:
    if not isinstance(param_name, str) or not param_name.startswith("qxrl/"):
        fail(REASON_QXRL_SCHEMA_INVALID)
    return "qxrl/opt/mom/" + param_name[len("qxrl/") :]


def _required_trainable_tensors_for_model(*, encoder_kind: str, vocab_size_u32: int, seq_len_u32: int, d_model_u32: int, d_hidden_u32: int, d_embed_u32: int, n_layers_u32: int, d_ff_u32: int) -> dict[str, list[int]]:
    kind = str(encoder_kind).strip()
    vocab = _require_u32(vocab_size_u32, reason=REASON_QXRL_SCHEMA_INVALID)
    seq_len = _require_u32(seq_len_u32, reason=REASON_QXRL_SCHEMA_INVALID)
    d_model = _require_u32(d_model_u32, reason=REASON_QXRL_SCHEMA_INVALID)
    d_hidden = _require_u32(d_hidden_u32, reason=REASON_QXRL_SCHEMA_INVALID)
    d_embed = _require_u32(d_embed_u32, reason=REASON_QXRL_SCHEMA_INVALID)

    if kind == ENCODER_KIND_QRE_V1:
        return {
            "qxrl/tok_emb": [vocab, d_model],
            "qxrl/pos_emb": [seq_len, d_model],
            "qxrl/enc_w1": [d_hidden, d_model],
            "qxrl/enc_b1": [d_hidden],
            "qxrl/enc_w2": [d_embed, d_hidden],
            "qxrl/enc_b2": [d_embed],
            "qxrl/tok_proj_w": [d_embed, d_model],
            "qxrl/tok_proj_b": [d_embed],
            "qxrl/out_emb": [vocab, d_embed],
            "qxrl/out_b": [vocab],
        }

    if kind == ENCODER_KIND_TSAE_V1:
        layers = _require_u32(n_layers_u32, reason=REASON_QXRL_SCHEMA_INVALID)
        d_ff = _require_u32(d_ff_u32, reason=REASON_QXRL_SCHEMA_INVALID)
        req: dict[str, list[int]] = {
            "qxrl/tok_emb": [vocab, d_model],
            "qxrl/pos_emb": [seq_len, d_model],
        }
        for l in range(int(layers)):
            req[f"qxrl/tsae/l{l}/wq"] = [d_model, d_model]
            req[f"qxrl/tsae/l{l}/wk"] = [d_model, d_model]
            req[f"qxrl/tsae/l{l}/wv"] = [d_model, d_model]
            req[f"qxrl/tsae/l{l}/wo"] = [d_model, d_model]
            req[f"qxrl/tsae/l{l}/rms1_gamma"] = [d_model]
            req[f"qxrl/tsae/l{l}/rms2_gamma"] = [d_model]
            req[f"qxrl/tsae/l{l}/ff_w1"] = [d_ff, d_model]
            req[f"qxrl/tsae/l{l}/ff_b1"] = [d_ff]
            req[f"qxrl/tsae/l{l}/ff_w2"] = [d_model, d_ff]
            req[f"qxrl/tsae/l{l}/ff_b2"] = [d_model]

        req["qxrl/tsae/proj_w"] = [d_embed, d_model]
        req["qxrl/tsae/proj_b"] = [d_embed]

        req["qxrl/tok_proj_w"] = [d_embed, d_model]
        req["qxrl/tok_proj_b"] = [d_embed]
        req["qxrl/out_emb"] = [vocab, d_embed]
        req["qxrl/out_b"] = [vocab]
        return req

    fail(REASON_QXRL_SCHEMA_INVALID)
    return {}


def parse_qxrl_model_manifest_v1(model_manifest_obj: dict[str, Any]) -> QXRLModelSpecV1:
    if not isinstance(model_manifest_obj, dict):
        fail(REASON_QXRL_SCHEMA_INVALID)
    if str(model_manifest_obj.get("schema_id", "")).strip() != SCHEMA_QXRL_MODEL_MANIFEST_V1:
        fail(REASON_QXRL_SCHEMA_INVALID)

    expected_model_id = compute_self_hash_id(model_manifest_obj, id_field="model_id", reason=REASON_QXRL_SCHEMA_INVALID)
    if str(model_manifest_obj.get("model_id", "")).strip() != expected_model_id:
        fail(REASON_QXRL_SCHEMA_INVALID)

    opset_id = str(model_manifest_obj.get("opset_id", "")).strip()
    dc1_id = str(model_manifest_obj.get("dc1_id", "")).strip()
    if dc1_id != "dc1:q32_v1" or not opset_id:
        fail(REASON_QXRL_SCHEMA_INVALID)

    tokenizer_kind = str(model_manifest_obj.get("tokenizer_kind", "")).strip()
    if tokenizer_kind not in {TOKENIZER_KIND_BYTE_TOK_257_V1, TOKENIZER_KIND_PRETOKENIZED_U32_V1}:
        fail(REASON_QXRL_SCHEMA_INVALID)

    vocab_size_u32 = model_manifest_obj.get("vocab_size_u32")
    seq_len_u32 = model_manifest_obj.get("seq_len_u32")
    d_model_u32 = model_manifest_obj.get("d_model_u32")
    d_embed_u32 = model_manifest_obj.get("d_embed_u32")
    if not isinstance(vocab_size_u32, int) or vocab_size_u32 <= 0:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if not isinstance(seq_len_u32, int) or seq_len_u32 <= 0:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if not isinstance(d_model_u32, int) or d_model_u32 <= 0:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if not isinstance(d_embed_u32, int) or d_embed_u32 <= 0:
        fail(REASON_QXRL_SCHEMA_INVALID)

    encoder_kind = str(model_manifest_obj.get("encoder_kind", "")).strip()
    if encoder_kind not in {ENCODER_KIND_QRE_V1, ENCODER_KIND_TSAE_V1}:
        fail(REASON_QXRL_SCHEMA_INVALID)

    # Math block (Phase 5).
    math = model_manifest_obj.get("math")
    if not isinstance(math, dict):
        fail(REASON_QXRL_SCHEMA_INVALID)
    dot_kind = str(math.get("dot_kind", "")).strip()
    if dot_kind not in {DOT_KIND_SHIFT_END, DOT_KIND_SHIFT_EACH}:
        fail(REASON_QXRL_SCHEMA_INVALID)
    div_kind = str(math.get("div_kind", "")).strip()
    invsqrt_kind = str(math.get("invsqrt_kind", "")).strip()
    if div_kind != DIV_KIND_Q32_POS_RNE_V1:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if invsqrt_kind != INVSQRT_KIND_Q32_NR_LUT_V1:
        fail(REASON_QXRL_SCHEMA_INVALID)
    invsqrt_lut_manifest_ref = require_artifact_ref_v1(math.get("invsqrt_lut_manifest_ref"), reason=REASON_QXRL_SCHEMA_INVALID)

    # Encoder config.
    d_hidden_u32 = 0
    inv_seq_len_q32 = 0
    n_layers_u32 = 0
    n_heads_u32 = 0
    d_head_u32 = 0
    d_ff_u32 = 0
    topk_u32 = 0
    rms_epsilon_q32 = 0
    preference_head_enabled_b = False
    preference_feature_kind = ""

    expected_inv_seq_len_q32 = _expected_inv_seq_len_q32(seq_len_u32=int(seq_len_u32))

    if encoder_kind == ENCODER_KIND_QRE_V1:
        qre = model_manifest_obj.get("qre")
        if not isinstance(qre, dict):
            fail(REASON_QXRL_SCHEMA_INVALID)
        d_hidden_u32 = qre.get("d_hidden_u32")
        if not isinstance(d_hidden_u32, int) or d_hidden_u32 <= 0:
            fail(REASON_QXRL_SCHEMA_INVALID)
        inv_seq_len_q32 = require_q32_obj(qre.get("inv_seq_len_q32"), reason=REASON_QXRL_SCHEMA_INVALID)
        if int(inv_seq_len_q32) != int(expected_inv_seq_len_q32):
            fail(REASON_QXRL_SCHEMA_INVALID)
        # TSAE block must be absent or null.
        if "tsae" in model_manifest_obj and model_manifest_obj.get("tsae") is not None:
            fail(REASON_QXRL_SCHEMA_INVALID)

    if encoder_kind == ENCODER_KIND_TSAE_V1:
        tsae = model_manifest_obj.get("tsae")
        if not isinstance(tsae, dict):
            fail(REASON_QXRL_SCHEMA_INVALID)
        n_layers_u32 = tsae.get("n_layers_u32")
        n_heads_u32 = tsae.get("n_heads_u32")
        d_head_u32 = tsae.get("d_head_u32")
        d_ff_u32 = tsae.get("d_ff_u32")
        topk_u32 = tsae.get("topk_u32")
        if not isinstance(n_layers_u32, int) or n_layers_u32 <= 0:
            fail(REASON_QXRL_SCHEMA_INVALID)
        if not isinstance(n_heads_u32, int) or n_heads_u32 <= 0:
            fail(REASON_QXRL_SCHEMA_INVALID)
        if not isinstance(d_head_u32, int) or d_head_u32 <= 0:
            fail(REASON_QXRL_SCHEMA_INVALID)
        if not isinstance(d_ff_u32, int) or d_ff_u32 <= 0:
            fail(REASON_QXRL_SCHEMA_INVALID)
        if not isinstance(topk_u32, int) or topk_u32 <= 0:
            fail(REASON_QXRL_SCHEMA_INVALID)

        if int(d_model_u32) != int(n_heads_u32) * int(d_head_u32):
            fail(REASON_QXRL_SCHEMA_INVALID)
        if int(topk_u32) > int(seq_len_u32):
            fail(REASON_QXRL_SCHEMA_INVALID)

        rms_epsilon_q32 = require_q32_obj(tsae.get("rms_epsilon_q32"), reason=REASON_QXRL_SCHEMA_INVALID)
        if int(rms_epsilon_q32) < 1:
            fail(REASON_QXRL_SCHEMA_INVALID)
        inv_seq_len_q32 = require_q32_obj(tsae.get("inv_seq_len_q32"), reason=REASON_QXRL_SCHEMA_INVALID)
        if int(inv_seq_len_q32) != int(expected_inv_seq_len_q32):
            fail(REASON_QXRL_SCHEMA_INVALID)

        # QRE block must be absent or null.
        if "qre" in model_manifest_obj and model_manifest_obj.get("qre") is not None:
            fail(REASON_QXRL_SCHEMA_INVALID)

    mask_id_u32 = mask_id_for_tokenizer(tokenizer_kind=tokenizer_kind, vocab_size_u32=int(vocab_size_u32))

    preference_head_obj = model_manifest_obj.get("preference_head")
    if preference_head_obj is not None:
        if not isinstance(preference_head_obj, dict):
            fail(REASON_QXRL_SCHEMA_INVALID)
        enabled_b = preference_head_obj.get("enabled_b")
        if enabled_b is not True:
            fail(REASON_QXRL_SCHEMA_INVALID)
        feature_kind = str(preference_head_obj.get("feature_kind", "")).strip()
        if feature_kind != PREFERENCE_FEATURE_KIND_PROPOSAL_HASH_HEAD32_Q32_V1:
            fail(REASON_QXRL_SCHEMA_INVALID)
        preference_head_enabled_b = True
        preference_feature_kind = str(feature_kind)

    # Tensor specs (Phase 5: exact required set, including momentum tensors).
    tensor_specs_raw = model_manifest_obj.get("tensor_specs")
    if not isinstance(tensor_specs_raw, list):
        fail(REASON_QXRL_SCHEMA_INVALID)

    tensor_specs: list[QXRLTensorSpecV1] = []
    seen: set[str] = set()
    for row in tensor_specs_raw:
        if not isinstance(row, dict):
            fail(REASON_QXRL_SCHEMA_INVALID)
        name = str(row.get("name", "")).strip()
        if not name or name in seen:
            fail(REASON_QXRL_SCHEMA_INVALID)
        seen.add(name)
        dtype = str(row.get("dtype", "")).strip()
        if dtype != "Q32_S64_V1":
            fail(REASON_QXRL_SCHEMA_INVALID)
        shape = row.get("shape_u32")
        if not isinstance(shape, list) or not shape:
            fail(REASON_QXRL_SCHEMA_INVALID)
        shape_u32 = tuple(_require_u32(d, reason=REASON_QXRL_SCHEMA_INVALID) for d in shape)
        _ = _prod_shape_u32(list(shape_u32))
        trainable = row.get("trainable")
        if not isinstance(trainable, bool):
            fail(REASON_QXRL_SCHEMA_INVALID)
        tensor_specs.append(QXRLTensorSpecV1(name=name, shape_u32=shape_u32, dtype=dtype, trainable=bool(trainable)))

    names = [t.name for t in tensor_specs]
    if names != sorted(names):
        fail(REASON_QXRL_SCHEMA_INVALID)

    required_trainable = _required_trainable_tensors_for_model(
        encoder_kind=encoder_kind,
        vocab_size_u32=int(vocab_size_u32),
        seq_len_u32=int(seq_len_u32),
        d_model_u32=int(d_model_u32),
        d_hidden_u32=int(d_hidden_u32),
        d_embed_u32=int(d_embed_u32),
        n_layers_u32=int(n_layers_u32),
        d_ff_u32=int(d_ff_u32),
    )
    if preference_head_enabled_b:
        required_trainable[PREFERENCE_HEAD_WEIGHT_TENSOR_NAME] = [1]
    required_all: dict[str, tuple[list[int], bool]] = {}
    for name, shape in required_trainable.items():
        required_all[str(name)] = (list(shape), True)
        required_all[_momentum_name_for_param(str(name))] = (list(shape), False)

    if set(names) != set(required_all.keys()):
        fail(REASON_QXRL_SCHEMA_INVALID)

    by_name = {t.name: t for t in tensor_specs}
    for name, (shape, trainable) in required_all.items():
        t = by_name.get(name)
        if t is None:
            fail(REASON_QXRL_SCHEMA_INVALID)
        if bool(t.trainable) != bool(trainable):
            fail(REASON_QXRL_SCHEMA_INVALID)
        if [int(d) for d in t.shape_u32] != [int(d) for d in shape]:
            fail(REASON_QXRL_SCHEMA_INVALID)

    trainable_names = tuple(sorted([name for name, (_shape, tr) in required_all.items() if tr]))

    return QXRLModelSpecV1(
        model_id=str(expected_model_id),
        opset_id=str(opset_id),
        dc1_id=str(dc1_id),
        tokenizer_kind=str(tokenizer_kind),
        vocab_size_u32=int(vocab_size_u32),
        seq_len_u32=int(seq_len_u32),
        encoder_kind=str(encoder_kind),
        d_model_u32=int(d_model_u32),
        d_hidden_u32=int(d_hidden_u32),
        d_embed_u32=int(d_embed_u32),
        inv_seq_len_q32=int(inv_seq_len_q32),
        dot_kind=str(dot_kind),
        div_kind=str(div_kind),
        invsqrt_kind=str(invsqrt_kind),
        invsqrt_lut_manifest_ref=dict(invsqrt_lut_manifest_ref),
        n_layers_u32=int(n_layers_u32),
        n_heads_u32=int(n_heads_u32),
        d_head_u32=int(d_head_u32),
        d_ff_u32=int(d_ff_u32),
        topk_u32=int(topk_u32),
        rms_epsilon_q32=int(rms_epsilon_q32),
        mask_id_u32=int(mask_id_u32),
        preference_head_enabled_b=bool(preference_head_enabled_b),
        preference_feature_kind=str(preference_feature_kind),
        tensor_specs=tuple(tensor_specs),
        trainable_names=trainable_names,
    )


def parse_qxrl_invsqrt_lut_manifest_v1(lut_manifest_obj: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(lut_manifest_obj, dict):
        fail(REASON_QXRL_SCHEMA_INVALID)
    if str(lut_manifest_obj.get("schema_id", "")).strip() != SCHEMA_QXRL_INVSQRT_LUT_MANIFEST_V1:
        fail(REASON_QXRL_SCHEMA_INVALID)

    expected_id = compute_self_hash_id(lut_manifest_obj, id_field="lut_manifest_id", reason=REASON_QXRL_SCHEMA_INVALID)
    if str(lut_manifest_obj.get("lut_manifest_id", "")).strip() != expected_id:
        fail(REASON_QXRL_SCHEMA_INVALID)

    if str(lut_manifest_obj.get("dc1_id", "")).strip() != "dc1:q32_v1":
        fail(REASON_QXRL_SCHEMA_INVALID)
    opset_id = str(lut_manifest_obj.get("opset_id", "")).strip()
    if not opset_id:
        fail(REASON_QXRL_SCHEMA_INVALID)

    if str(lut_manifest_obj.get("lut_kind", "")).strip() != LUT_KIND_INVSQRT_Q32_NR_LUT_V1:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if int(lut_manifest_obj.get("lut_bits_u32", -1)) != int(LUT_BITS_PHASE5_U32):
        fail(REASON_QXRL_OPSET_LUT_MISMATCH)
    if int(lut_manifest_obj.get("invsqrt_iters_u32", -1)) != int(INVSQRT_ITERS_PHASE5_U32):
        fail(REASON_QXRL_OPSET_LUT_MISMATCH)

    lut_ref = require_artifact_ref_v1(lut_manifest_obj.get("lut_ref"), reason=REASON_QXRL_SCHEMA_INVALID)
    if str(lut_ref.get("artifact_id", "")).strip() != INVSQRT_LUT_ARTIFACT_ID_PHASE5:
        fail(REASON_QXRL_OPSET_LUT_MISMATCH)

    return {"opset_id": opset_id, "lut_ref": lut_ref, "lut_manifest_id": str(expected_id)}


@dataclass(frozen=True, slots=True)
class XORSHIFT128Plus:
    """XORSHIFT128+ PRNG (u64) with 128-bit state.

    All operations are modulo 2^64.
    """

    s0_u64: int
    s1_u64: int

    def next_u64(self) -> tuple[int, "XORSHIFT128Plus"]:
        mask = 0xFFFFFFFFFFFFFFFF
        s1 = int(self.s0_u64) & mask
        s0 = int(self.s1_u64) & mask
        s1 ^= (s1 << 23) & mask
        s1 ^= (s1 >> 17) & mask
        s1 ^= s0
        s1 ^= (s0 >> 26) & mask
        out = (s1 + s0) & mask
        return int(out), XORSHIFT128Plus(s0_u64=int(s0), s1_u64=int(s1))


def prng_for_step_stream(
    *,
    dc1_id: str,
    opset_id: str,
    dataset_root_hash32: bytes,
    wroot_before32: bytes,
    step_index_u64: int,
    stream_id_u32: int,
) -> XORSHIFT128Plus:
    """Instantiate the Phase 4 per-step per-stream PRNG.

    seed_bytes = SHA256(dc1_id_bytes || opset_id_bytes || dataset_root_hash32 || wroot_before32 ||
                        u64_le(step) || u32_le(stream_id))
    seed16 = seed_bytes[0:16]
    state = (u64_le(seed16[0:8]), u64_le(seed16[8:16]))
    """

    if not isinstance(dataset_root_hash32, (bytes, bytearray, memoryview)) or len(bytes(dataset_root_hash32)) != 32:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if not isinstance(wroot_before32, (bytes, bytearray, memoryview)) or len(bytes(wroot_before32)) != 32:
        fail(REASON_QXRL_SCHEMA_INVALID)

    step = _require_u64(step_index_u64, reason=REASON_QXRL_SCHEMA_INVALID)
    stream = _require_u32(stream_id_u32, reason=REASON_QXRL_SCHEMA_INVALID)

    hasher = hashlib.sha256()
    hasher.update(str(dc1_id).encode("utf-8", errors="strict"))
    hasher.update(str(opset_id).encode("utf-8", errors="strict"))
    hasher.update(bytes(dataset_root_hash32))
    hasher.update(bytes(wroot_before32))
    hasher.update(struct.pack("<Q", int(step) & 0xFFFFFFFFFFFFFFFF))
    hasher.update(struct.pack("<I", int(stream) & 0xFFFFFFFF))
    seed = hasher.digest()[:16]
    s0 = int.from_bytes(seed[0:8], byteorder="little", signed=False)
    s1 = int.from_bytes(seed[8:16], byteorder="little", signed=False)
    # Spec guard: all-zero seed state is forbidden (would yield a degenerate stream).
    if int(s0) == 0 and int(s1) == 0:
        s1 = 1
    return XORSHIFT128Plus(s0_u64=int(s0), s1_u64=int(s1))


__all__ = [
    "DATASET_KIND_PAIR_V1",
    "DIV_KIND_Q32_POS_RNE_V1",
    "DOT_KIND_SHIFT_EACH",
    "DOT_KIND_SHIFT_END",
    "ENCODER_KIND_QRE_V1",
    "ENCODER_KIND_TSAE_V1",
    "EUDRSU_OK",
    "INVSQRT_ITERS_PHASE5_U32",
    "INVSQRT_KIND_Q32_NR_LUT_V1",
    "INVSQRT_LUT_ARTIFACT_ID_PHASE5",
    "LUT_BITS_PHASE5_U32",
    "LUT_KIND_INVSQRT_Q32_NR_LUT_V1",
    "OPTIMIZER_KIND_ADAMW_Q32_V1",
    "OPTIMIZER_KIND_SGD_MOMENTUM_Q32_V1",
    "PREFERENCE_FEATURE_KIND_PROPOSAL_HASH_HEAD32_Q32_V1",
    "PREFERENCE_HEAD_WEIGHT_TENSOR_NAME",
    "PRNG_STREAM_EVAL_MASKS_V1",
    "PRNG_STREAM_EVAL_NEGS_V1",
    "PRNG_STREAM_TRAIN_MASKS_V1",
    "PRNG_STREAM_TRAIN_NEGS_V1",
    "REASON_QXRL_DATASET_HASH_MISMATCH",
    "REASON_QXRL_EVAL_TAIL_MISMATCH",
    "REASON_QXRL_FLOOR_FAIL",
    "REASON_QXRL_OPSET_LUT_MISMATCH",
    "REASON_QXRL_OPTIMIZER_KIND_FORBIDDEN",
    "REASON_QXRL_PRNG_COUNTER_MISMATCH",
    "REASON_QXRL_SCHEMA_INVALID",
    "REASON_QXRL_SCORECARD_MISMATCH",
    "REASON_QXRL_SEGMENT_DECODE_FAIL",
    "REASON_QXRL_TOPK_TIEBREAK_VIOLATION",
    "REASON_QXRL_TRAIN_TAIL_MISMATCH",
    "SCHEMA_QXRL_DATASET_MANIFEST_V1",
    "SCHEMA_QXRL_EVAL_MANIFEST_V1",
    "SCHEMA_QXRL_EVAL_SCORECARD_V1",
    "SCHEMA_QXRL_INVSQRT_LUT_MANIFEST_V1",
    "SCHEMA_QXRL_MODEL_MANIFEST_V1",
    "SCHEMA_QXRL_TRAINING_MANIFEST_V1",
    "TOKENIZER_KIND_BYTE_TOK_257_V1",
    "TOKENIZER_KIND_PRETOKENIZED_U32_V1",
    "QXRLModelSpecV1",
    "QXRLTensorSpecV1",
    "XORSHIFT128Plus",
    "compute_eval_id_config_hash",
    "compute_self_hash_id",
    "digest32_to_hex",
    "hex64_to_bytes32",
    "load_qxrl_model_manifest_v1",
    "mask_id_for_tokenizer",
    "parse_qxrl_model_manifest_v1",
    "parse_qxrl_invsqrt_lut_manifest_v1",
    "prng_for_step_stream",
    "q32_obj",
    "require_q32_obj",
    "sha256_id_to_digest32",
]
