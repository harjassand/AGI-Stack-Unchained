"""QXRL dataset manifests + segment decoding (v1).

Phase 4 dataset kind is fixed: PAIR_V1 (anchor, positive) with fixed seq_len.

This module is RE2: deterministic, fail-closed, no filesystem discovery.
"""

from __future__ import annotations

import hashlib
import struct
import sys
from array import array
from dataclasses import dataclass
from typing import Any, Final

from ..omega_common_v1 import fail, validate_schema
from .eudrs_u_artifact_refs_v1 import require_artifact_ref_v1
from .eudrs_u_hash_v1 import gcj1_loads_and_verify_canonical
from .qxrl_common_v1 import (
    DATASET_KIND_PAIR_V1,
    REASON_QXRL_DATASET_HASH_MISMATCH,
    REASON_QXRL_SCHEMA_INVALID,
    REASON_QXRL_SEGMENT_DECODE_FAIL,
    SCHEMA_QXRL_DATASET_MANIFEST_V1,
    TOKENIZER_KIND_BYTE_TOK_257_V1,
    TOKENIZER_KIND_PRETOKENIZED_U32_V1,
    compute_self_hash_id,
    hex64_to_bytes32,
    mask_id_for_tokenizer,
    sha256_id_to_digest32,
)

_SEG_MAGIC: Final[bytes] = b"QXDS"
_SEG_VERSION_V1: Final[int] = 1
_TOKENIZER_KIND_U32_BYTE: Final[int] = 1
_TOKENIZER_KIND_U32_PRETOK: Final[int] = 2
_DATASET_KIND_U32_PAIR: Final[int] = 1

_HEADER_STRUCT = struct.Struct("<4sIIIIII")


@dataclass(frozen=True, slots=True)
class QXRLDatasetExampleV1:
    example_id_u64: int
    anchor_tokens_u32: list[int]
    positive_tokens_u32: list[int]


def _u32_list_from_mv_le(mv: memoryview, off: int, count: int, *, reason: str) -> tuple[list[int], int]:
    n = int(count)
    if n < 0:
        fail(reason)
    end = off + (n * 4)
    if end < off or end > len(mv):
        fail(reason)
    arr = array("I")
    arr.frombytes(mv[off:end])
    if sys.byteorder != "little":
        arr.byteswap()
    return [int(v) for v in arr], end


def decode_qxrl_dataset_segment_v1(
    segment_bytes: bytes | bytearray | memoryview,
    *,
    expected_tokenizer_kind: str,
    expected_vocab_size_u32: int,
    expected_seq_len_u32: int,
    expected_record_count_u32: int,
) -> list[QXRLDatasetExampleV1]:
    mv = memoryview(segment_bytes)
    if mv.ndim != 1:
        fail(REASON_QXRL_SEGMENT_DECODE_FAIL)
    if len(mv) < _HEADER_STRUCT.size:
        fail(REASON_QXRL_SEGMENT_DECODE_FAIL)

    magic, version_u32, tokenizer_kind_u32, dataset_kind_u32, vocab_size_u32, seq_len_u32, record_count_u32 = _HEADER_STRUCT.unpack_from(mv, 0)
    if bytes(magic) != _SEG_MAGIC:
        fail(REASON_QXRL_SEGMENT_DECODE_FAIL)
    if int(version_u32) != _SEG_VERSION_V1:
        fail(REASON_QXRL_SEGMENT_DECODE_FAIL)

    exp_kind = str(expected_tokenizer_kind).strip()
    if exp_kind == TOKENIZER_KIND_BYTE_TOK_257_V1:
        if int(tokenizer_kind_u32) != _TOKENIZER_KIND_U32_BYTE:
            fail(REASON_QXRL_SEGMENT_DECODE_FAIL)
    elif exp_kind == TOKENIZER_KIND_PRETOKENIZED_U32_V1:
        if int(tokenizer_kind_u32) != _TOKENIZER_KIND_U32_PRETOK:
            fail(REASON_QXRL_SEGMENT_DECODE_FAIL)
    else:
        fail(REASON_QXRL_SCHEMA_INVALID)

    if int(dataset_kind_u32) != _DATASET_KIND_U32_PAIR:
        fail(REASON_QXRL_SEGMENT_DECODE_FAIL)

    if int(vocab_size_u32) != int(expected_vocab_size_u32):
        fail(REASON_QXRL_SEGMENT_DECODE_FAIL)
    if int(seq_len_u32) != int(expected_seq_len_u32):
        fail(REASON_QXRL_SEGMENT_DECODE_FAIL)
    if int(record_count_u32) != int(expected_record_count_u32):
        fail(REASON_QXRL_SEGMENT_DECODE_FAIL)

    seq_len = int(seq_len_u32)
    record_count = int(record_count_u32)
    # record: u64 + seq_len*u32 + seq_len*u32
    rec_nbytes = 8 + (seq_len * 4) + (seq_len * 4)
    expected_total = _HEADER_STRUCT.size + (record_count * rec_nbytes)
    if expected_total != len(mv):
        fail(REASON_QXRL_SEGMENT_DECODE_FAIL)

    off = _HEADER_STRUCT.size
    out: list[QXRLDatasetExampleV1] = []
    prev_id: int | None = None
    for _i in range(record_count):
        if off + 8 > len(mv):
            fail(REASON_QXRL_SEGMENT_DECODE_FAIL)
        example_id_u64 = int(struct.unpack_from("<Q", mv, off)[0])
        off += 8
        if prev_id is not None and example_id_u64 <= prev_id:
            fail(REASON_QXRL_SEGMENT_DECODE_FAIL)
        prev_id = example_id_u64

        anchor, off = _u32_list_from_mv_le(mv, off, seq_len, reason=REASON_QXRL_SEGMENT_DECODE_FAIL)
        positive, off = _u32_list_from_mv_le(mv, off, seq_len, reason=REASON_QXRL_SEGMENT_DECODE_FAIL)

        # Validate token id ranges.
        vocab = int(vocab_size_u32)
        for tok in anchor:
            if int(tok) < 0 or int(tok) >= vocab:
                fail(REASON_QXRL_SEGMENT_DECODE_FAIL)
        for tok in positive:
            if int(tok) < 0 or int(tok) >= vocab:
                fail(REASON_QXRL_SEGMENT_DECODE_FAIL)

        out.append(QXRLDatasetExampleV1(example_id_u64=example_id_u64, anchor_tokens_u32=anchor, positive_tokens_u32=positive))
    if off != len(mv):
        fail(REASON_QXRL_SEGMENT_DECODE_FAIL)
    return out


def _require_str_enum(value: Any, allowed: set[str], *, reason: str) -> str:
    if not isinstance(value, str):
        fail(reason)
    v = str(value).strip()
    if v not in allowed:
        fail(reason)
    return v


def load_qxrl_dataset_manifest_v1(
    manifest_bytes: bytes,
    *,
    schema_validate: bool = True,
) -> dict[str, Any]:
    obj = gcj1_loads_and_verify_canonical(manifest_bytes)
    if not isinstance(obj, dict):
        fail(REASON_QXRL_SCHEMA_INVALID)
    if schema_validate:
        try:
            validate_schema(obj, SCHEMA_QXRL_DATASET_MANIFEST_V1)
        except Exception:  # noqa: BLE001 - fail-closed
            fail(REASON_QXRL_SCHEMA_INVALID)
    if str(obj.get("schema_id", "")).strip() != SCHEMA_QXRL_DATASET_MANIFEST_V1:
        fail(REASON_QXRL_SCHEMA_INVALID)
    return dict(obj)


def _compute_dataset_root_hash32_from_segment_refs(segments: list[dict[str, Any]]) -> bytes:
    hasher = hashlib.sha256()
    hasher.update(b"QXRL_DATASET_ROOT_V1")
    for seg in segments:
        seg_ref = require_artifact_ref_v1(seg.get("segment_ref"))
        hasher.update(sha256_id_to_digest32(seg_ref.get("artifact_id")))
    return hasher.digest()


def load_and_verify_qxrl_dataset_v1(
    *,
    dataset_manifest_obj: dict[str, Any],
    registry_loader: callable,  # ArtifactRefV1 -> bytes
) -> tuple[list[QXRLDatasetExampleV1], bytes]:
    """Return (examples_in_global_order, dataset_root_hash32)."""

    if not isinstance(dataset_manifest_obj, dict):
        fail(REASON_QXRL_SCHEMA_INVALID)

    if str(dataset_manifest_obj.get("schema_id", "")).strip() != SCHEMA_QXRL_DATASET_MANIFEST_V1:
        fail(REASON_QXRL_SCHEMA_INVALID)

    # Enforce dataset_id self-hash.
    expected_id = compute_self_hash_id(dataset_manifest_obj, id_field="dataset_id", reason=REASON_QXRL_SCHEMA_INVALID)
    if str(dataset_manifest_obj.get("dataset_id", "")).strip() != expected_id:
        fail(REASON_QXRL_SCHEMA_INVALID)

    tokenizer_kind = _require_str_enum(
        dataset_manifest_obj.get("tokenizer_kind"),
        {TOKENIZER_KIND_BYTE_TOK_257_V1, TOKENIZER_KIND_PRETOKENIZED_U32_V1},
        reason=REASON_QXRL_SCHEMA_INVALID,
    )
    dataset_kind = _require_str_enum(dataset_manifest_obj.get("dataset_kind"), {DATASET_KIND_PAIR_V1}, reason=REASON_QXRL_SCHEMA_INVALID)

    vocab_size_u32 = int(dataset_manifest_obj.get("vocab_size_u32"))
    seq_len_u32 = int(dataset_manifest_obj.get("seq_len_u32"))

    # Validate MASK_ID derivation (forbidden neg set depends on it).
    _mask_id = mask_id_for_tokenizer(tokenizer_kind=tokenizer_kind, vocab_size_u32=vocab_size_u32)
    del _mask_id
    del dataset_kind

    segments = dataset_manifest_obj.get("segments")
    if not isinstance(segments, list) or not segments:
        fail(REASON_QXRL_SCHEMA_INVALID)

    # Sort + validate segment indices.
    seg_rows: list[dict[str, Any]] = [dict(row) for row in segments]
    seg_rows.sort(key=lambda row: int(row.get("segment_index_u32", -1)))

    # Require strictly-increasing indices and non-overlapping example id ranges.
    prev_seg_index: int | None = None
    prev_last: int | None = None

    all_examples: list[QXRLDatasetExampleV1] = []
    for seg in seg_rows:
        seg_index_u32 = seg.get("segment_index_u32")
        record_count_u32 = seg.get("record_count_u32")
        first_example_id_u64 = seg.get("first_example_id_u64")
        last_example_id_u64 = seg.get("last_example_id_u64")
        if not isinstance(seg_index_u32, int) or seg_index_u32 < 0:
            fail(REASON_QXRL_SCHEMA_INVALID)
        if prev_seg_index is not None and int(seg_index_u32) <= int(prev_seg_index):
            fail(REASON_QXRL_SCHEMA_INVALID)
        prev_seg_index = int(seg_index_u32)

        if not isinstance(record_count_u32, int) or record_count_u32 < 0:
            fail(REASON_QXRL_SCHEMA_INVALID)
        if not isinstance(first_example_id_u64, int) or first_example_id_u64 < 0:
            fail(REASON_QXRL_SCHEMA_INVALID)
        if not isinstance(last_example_id_u64, int) or last_example_id_u64 < 0:
            fail(REASON_QXRL_SCHEMA_INVALID)
        if int(record_count_u32) > 0 and int(last_example_id_u64) < int(first_example_id_u64):
            fail(REASON_QXRL_SCHEMA_INVALID)
        if prev_last is not None and int(first_example_id_u64) <= int(prev_last):
            fail(REASON_QXRL_SCHEMA_INVALID)
        prev_last = int(last_example_id_u64)

        seg_ref = require_artifact_ref_v1(seg.get("segment_ref"))
        raw = bytes(registry_loader(seg_ref))
        examples = decode_qxrl_dataset_segment_v1(
            raw,
            expected_tokenizer_kind=tokenizer_kind,
            expected_vocab_size_u32=vocab_size_u32,
            expected_seq_len_u32=seq_len_u32,
            expected_record_count_u32=int(record_count_u32),
        )
        if examples:
            if int(examples[0].example_id_u64) != int(first_example_id_u64):
                fail(REASON_QXRL_SEGMENT_DECODE_FAIL)
            if int(examples[-1].example_id_u64) != int(last_example_id_u64):
                fail(REASON_QXRL_SEGMENT_DECODE_FAIL)
        else:
            # record_count=0 => first/last must be equal (both are metadata only)
            if int(record_count_u32) != 0:
                fail(REASON_QXRL_SEGMENT_DECODE_FAIL)

        all_examples.extend(examples)

    # Verify dataset_root_hash32_hex.
    root_expected = _compute_dataset_root_hash32_from_segment_refs(seg_rows)
    root_hex = str(dataset_manifest_obj.get("dataset_root_hash32_hex", "")).strip()
    root_claimed = hex64_to_bytes32(root_hex, reason=REASON_QXRL_DATASET_HASH_MISMATCH)
    if root_claimed != root_expected:
        fail(REASON_QXRL_DATASET_HASH_MISMATCH)

    return all_examples, root_expected


__all__ = [
    "QXRLDatasetExampleV1",
    "decode_qxrl_dataset_segment_v1",
    "load_and_verify_qxrl_dataset_v1",
    "load_qxrl_dataset_manifest_v1",
]

