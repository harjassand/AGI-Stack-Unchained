"""DMPL training replay verifier (v1).

Phase 4 contract: given (TrainRun, TrainTrace, TrainReceipt) artifacts and a
resolver, replay deterministic training and verify:
  - Dataset pack decoding + ordering.
  - TrainTrace internal consistency (chunk merkle root + trace chain final).
  - Each TRAIN_STEP record fields and updated tensor IDs match recomputation.
  - Final bundles/config/droot match TrainReceipt and root tuple droot.

This module is RE2: deterministic and fail-closed via DMPLError.
"""

from __future__ import annotations

import hashlib
import struct
from typing import Any

from ..omega_common_v1 import OmegaV18Error, require_no_absolute_paths, validate_schema
from .dmpl_config_load_v1 import load_runtime_from_droot_v1
from .dmpl_merkle_v1 import compute_params_bundle_merkle_root_v1, compute_chunk_merkle_root_v1
from .dmpl_tensor_io_v1 import parse_tensor_q32_v1, require_shape
from .dmpl_train_sgd_v1 import (
    ConceptPatchEntryV1,
    TrainableStateV1,
    encode_tensor_q32_v1,
    sha256_prefixed_bytes,
    train_step_sgd_det_v1,
)
from .dmpl_train_trace_v1 import parse_lenpref_canonjson_stream_v1, train_trace_h0_v1
from .dmpl_types_v1 import (
    DMPLError,
    DMPL_E_BUDGET_EXCEEDED,
    DMPL_E_DATASET_OOB,
    DMPL_E_DIM_MISMATCH,
    DMPL_E_HASH_MISMATCH,
    DMPL_E_NONCANON_GCJ1,
    DMPL_E_OPSET_MISMATCH,
    DMPL_E_REDUCTION_ORDER_VIOLATION,
    DMPL_OK,
    Q32_ONE,
)
from .eudrs_u_hash_v1 import gcj1_canon_bytes, gcj1_loads_and_verify_canonical, sha256_prefixed
from .verify_dmpl_opset_v1 import verify_dmpl_opset_v1


_U32LE = struct.Struct("<I")

_EMPTY_CHUNKS_DOMAIN = b"DMPL/CHUNKS/EMPTY/v1\x00"
_DATASET_CHAIN_PREFIX = b"DMPL/DATASET/v1\x00"


def _sha25632(data: bytes) -> bytes:
    return hashlib.sha256(bytes(data)).digest()


def _sha256_id(data: bytes) -> str:
    return f"sha256:{_sha25632(data).hex()}"


def _require_sha256_id(value: Any, *, reason: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != (len("sha256:") + 64):
        raise DMPLError(reason_code=reason, details={"value": str(value)})
    try:
        bytes.fromhex(value.split(":", 1)[1])
    except Exception:
        raise DMPLError(reason_code=reason, details={"value": str(value)})
    return str(value)


def _load_json_by_ref(*, resolver: Any, artifact_ref: dict[str, Any], schema_name: str) -> tuple[dict[str, Any], bytes]:
    try:
        fn = getattr(resolver, "load_artifact_ref_bytes")
    except Exception:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver missing load_artifact_ref_bytes"})
    if not callable(fn):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver.load_artifact_ref_bytes not callable"})
    raw = fn(dict(artifact_ref))
    if not isinstance(raw, (bytes, bytearray, memoryview)):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver returned non-bytes"})
    b = bytes(raw)
    try:
        obj = gcj1_loads_and_verify_canonical(b)
    except OmegaV18Error:
        raise DMPLError(reason_code=DMPL_E_NONCANON_GCJ1, details={"hint": "noncanonical json", "schema": str(schema_name)})
    if not isinstance(obj, dict):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "not dict", "schema": str(schema_name)})
    require_no_absolute_paths(obj)
    try:
        validate_schema(obj, str(schema_name))
    except Exception:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "schema validation", "schema": str(schema_name)})
    if str(obj.get("schema_id", "")).strip() != str(schema_name):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "schema_id mismatch", "schema": str(schema_name)})
    return dict(obj), b


def _load_json_by_id_and_type(*, resolver: Any, artifact_id: str, artifact_type: str) -> dict[str, Any]:
    try:
        fn = getattr(resolver, "load_artifact_bytes")
    except Exception:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver missing load_artifact_bytes"})
    if not callable(fn):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver.load_artifact_bytes not callable"})
    raw = fn(artifact_id=str(artifact_id), artifact_type=str(artifact_type), ext="json")
    if not isinstance(raw, (bytes, bytearray, memoryview)):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver returned non-bytes"})
    b = bytes(raw)
    if _sha256_id(b) != str(artifact_id).strip():
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"artifact_id": str(artifact_id), "artifact_type": str(artifact_type)})
    try:
        obj = gcj1_loads_and_verify_canonical(b)
    except OmegaV18Error:
        raise DMPLError(reason_code=DMPL_E_NONCANON_GCJ1, details={"artifact_id": str(artifact_id), "artifact_type": str(artifact_type)})
    if not isinstance(obj, dict):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"artifact_type": str(artifact_type), "hint": "not dict"})
    require_no_absolute_paths(obj)
    try:
        validate_schema(obj, str(artifact_type))
    except Exception:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"artifact_id": str(artifact_id), "artifact_type": str(artifact_type)})
    if str(obj.get("schema_id", "")).strip() != str(artifact_type):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "schema_id mismatch", "artifact_type": str(artifact_type)})
    return dict(obj)


def _load_canon_json_by_id_no_schema(*, resolver: Any, artifact_id: str, artifact_type: str) -> dict[str, Any]:
    # For JSON artifacts without Genesis schemas (e.g. dmpl_action_v1).
    try:
        fn = getattr(resolver, "load_artifact_bytes")
    except Exception:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver missing load_artifact_bytes"})
    if not callable(fn):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver.load_artifact_bytes not callable"})
    raw = fn(artifact_id=str(artifact_id), artifact_type=str(artifact_type), ext="json")
    if not isinstance(raw, (bytes, bytearray, memoryview)):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver returned non-bytes"})
    b = bytes(raw)
    if _sha256_id(b) != str(artifact_id).strip():
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"artifact_id": str(artifact_id), "artifact_type": str(artifact_type)})
    try:
        obj = gcj1_loads_and_verify_canonical(b)
    except OmegaV18Error:
        raise DMPLError(reason_code=DMPL_E_NONCANON_GCJ1, details={"artifact_id": str(artifact_id), "artifact_type": str(artifact_type)})
    if not isinstance(obj, dict):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"artifact_type": str(artifact_type), "hint": "not dict"})
    require_no_absolute_paths(obj)
    if str(obj.get("schema_id", "")).strip() != str(artifact_type):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "schema_id mismatch", "artifact_type": str(artifact_type)})
    return dict(obj)


def _load_bin_by_id_and_type(*, resolver: Any, artifact_id: str, artifact_type: str, expected_len: int | None = None) -> bytes:
    try:
        fn = getattr(resolver, "load_artifact_bytes")
    except Exception:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver missing load_artifact_bytes"})
    if not callable(fn):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver.load_artifact_bytes not callable"})
    raw = fn(artifact_id=str(artifact_id), artifact_type=str(artifact_type), ext="bin")
    if not isinstance(raw, (bytes, bytearray, memoryview)):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver returned non-bytes"})
    b = bytes(raw)
    if expected_len is not None and int(len(b)) != int(expected_len):
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "bin len mismatch", "expected": int(expected_len), "got": int(len(b))})
    if _sha256_id(b) != str(artifact_id).strip():
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"artifact_id": str(artifact_id), "artifact_type": str(artifact_type)})
    return b


def _require_sorted_contiguous_chunks(chunks_obj: Any) -> list[dict[str, Any]]:
    if not isinstance(chunks_obj, list):
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "chunks not list"})
    chunks: list[dict[str, Any]] = []
    for row in chunks_obj:
        if not isinstance(row, dict):
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "chunk row type"})
        chunks.append(dict(row))
    chunks.sort(key=lambda r: int(r.get("chunk_index_u32", -1)))
    for i, row in enumerate(chunks):
        idx = row.get("chunk_index_u32")
        if not isinstance(idx, int) or int(idx) != int(i):
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "chunk indices", "at": int(i), "got": idx})
    return chunks


def _load_chunks_stream(
    *,
    resolver: Any,
    chunks: list[dict[str, Any]],
    artifact_type: str,
) -> tuple[list[bytes], bytes, list[bytes]]:
    chunk_bytes_list: list[bytes] = []
    chunk_hashes32: list[bytes] = []
    for row in chunks:
        chunk_bin_id = str(row.get("chunk_bin_id", "")).strip()
        chunk_bytes_u32 = row.get("chunk_bytes_u32")
        if not isinstance(chunk_bytes_u32, int):
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "chunk_bytes_u32 type"})
        b = _load_bin_by_id_and_type(resolver=resolver, artifact_id=str(chunk_bin_id), artifact_type=str(artifact_type), expected_len=int(chunk_bytes_u32))
        chunk_bytes_list.append(b)
        chunk_hashes32.append(_sha25632(b))
    stream = b"".join(chunk_bytes_list)
    return chunk_bytes_list, stream, chunk_hashes32


def _recompute_chunks_merkle_root_id(*, record_count_u64: int, chunk_hashes32: list[bytes]) -> str:
    if int(record_count_u64) == 0:
        root32 = _sha25632(_EMPTY_CHUNKS_DOMAIN)
    else:
        root32 = compute_chunk_merkle_root_v1([bytes(h) for h in chunk_hashes32])
    if not isinstance(root32, (bytes, bytearray, memoryview)) or len(bytes(root32)) != 32:
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "bad merkle root"})
    return f"sha256:{bytes(root32).hex()}"


def _recompute_dataset_chain_final_id(*, opset_id: str, record_bytes: list[bytes]) -> str:
    h = _sha25632(_DATASET_CHAIN_PREFIX + str(opset_id).encode("utf-8", errors="strict"))
    for raw in record_bytes:
        ri_hash32 = _sha25632(bytes(raw))
        h = _sha25632(bytes(h) + bytes(ri_hash32))
    return f"sha256:{h.hex()}"


def _recompute_train_trace_chain_final_id(*, train_run_hash32: bytes, opset_id: str, record_bytes: list[bytes]) -> str:
    h = train_trace_h0_v1(bytes(train_run_hash32), str(opset_id))
    for raw in record_bytes:
        ri_hash32 = _sha25632(bytes(raw))
        h = _sha25632(bytes(h) + bytes(ri_hash32))
    return f"sha256:{h.hex()}"


def _require_ordered_unique_strings(values: Any) -> list[str]:
    if not isinstance(values, list):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "not list"})
    out: list[str] = []
    prev: str | None = None
    for item in values:
        if not isinstance(item, str):
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "not str"})
        s = str(item)
        if prev is not None and s <= prev:
            raise DMPLError(reason_code=DMPL_E_REDUCTION_ORDER_VIOLATION, details={"hint": "not sorted/unique"})
        prev = s
        _require_sha256_id(s, reason=DMPL_E_HASH_MISMATCH)
        out.append(s)
    return out


def _load_concept_patch_entry(
    *,
    resolver: Any,
    concept_shard_id: str,
    ladder_level_u32: int,
    d_u32: int,
    p_u32: int,
    embed_dim_u32: int,
    cache: dict[tuple[str, int], ConceptPatchEntryV1],
) -> ConceptPatchEntryV1:
    key = (str(concept_shard_id), int(ladder_level_u32))
    cached = cache.get(key)
    if cached is not None:
        return cached

    concept_obj = _load_json_by_id_and_type(resolver=resolver, artifact_id=str(concept_shard_id), artifact_type="dmpl_concept_shard_v1")

    embed_bin_id = str(concept_obj.get("embed_tensor_bin_id", "")).strip()
    embed_raw = _load_bin_by_id_and_type(resolver=resolver, artifact_id=embed_bin_id, artifact_type="dmpl_tensor_q32_v1")
    embed_dims, embed_vals = parse_tensor_q32_v1(embed_raw)
    require_shape(embed_dims, [int(embed_dim_u32)])

    patches = concept_obj.get("patches_by_level")
    if not isinstance(patches, list) or not patches:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "patches_by_level"})
    patch_row: dict[str, Any] | None = None
    for row in patches:
        if not isinstance(row, dict):
            continue
        if int(row.get("ladder_level_u32", -1)) == int(ladder_level_u32):
            patch_row = dict(row)
            break
    if patch_row is None:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "missing ladder level"})

    patch_kind = str(patch_row.get("patch_kind", "")).strip()

    # Value patch.
    v_c0_q32_obj = patch_row.get("v_c0_q32")
    if not isinstance(v_c0_q32_obj, dict) or set(v_c0_q32_obj.keys()) != {"q"}:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "v_c0_q32"})
    v_c0_q32 = int(v_c0_q32_obj.get("q", 0))

    w_vec: list[int] | None = None
    w_bin_id = str(patch_row.get("w_bin_id", "")).strip()
    if w_bin_id != "sha256:" + ("0" * 64):
        w_raw = _load_bin_by_id_and_type(resolver=resolver, artifact_id=w_bin_id, artifact_type="dmpl_tensor_q32_v1")
        w_dims, w_vals = parse_tensor_q32_v1(w_raw)
        require_shape(w_dims, [int(d_u32)])
        w_vec = [int(v) for v in w_vals]

    # Forward patch tensors (optional).
    A_vals: list[int] | None = None
    B_vals: list[int] | None = None
    b_vals: list[int] | None = None
    rank_u32: int | None = None
    A_u_vals: list[int] | None = None
    A_v_vals: list[int] | None = None
    B_u_vals: list[int] | None = None
    B_v_vals: list[int] | None = None

    if patch_kind == "none":
        pass
    elif patch_kind == "matrix_patch":
        A_id = str(patch_row.get("A_bin_id", "")).strip()
        B_id = str(patch_row.get("B_bin_id", "")).strip()
        b_id = str(patch_row.get("b_bin_id", "")).strip()
        A_raw = _load_bin_by_id_and_type(resolver=resolver, artifact_id=A_id, artifact_type="dmpl_tensor_q32_v1")
        B_raw = _load_bin_by_id_and_type(resolver=resolver, artifact_id=B_id, artifact_type="dmpl_tensor_q32_v1")
        b_raw = _load_bin_by_id_and_type(resolver=resolver, artifact_id=b_id, artifact_type="dmpl_tensor_q32_v1")
        A_dims, A_vals2 = parse_tensor_q32_v1(A_raw)
        B_dims, B_vals2 = parse_tensor_q32_v1(B_raw)
        b_dims, b_vals2 = parse_tensor_q32_v1(b_raw)
        require_shape(A_dims, [int(d_u32), int(d_u32)])
        require_shape(B_dims, [int(d_u32), int(p_u32)])
        require_shape(b_dims, [int(d_u32)])
        A_vals = [int(v) for v in A_vals2]
        B_vals = [int(v) for v in B_vals2]
        b_vals = [int(v) for v in b_vals2]
    elif patch_kind == "lowrank_patch":
        rank_u32 = int(patch_row.get("rank_u32", 0))
        if rank_u32 <= 0:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "rank"})
        A_u_id = str(patch_row.get("A_u_bin_id", "")).strip()
        A_v_id = str(patch_row.get("A_v_bin_id", "")).strip()
        B_u_id = str(patch_row.get("B_u_bin_id", "")).strip()
        B_v_id = str(patch_row.get("B_v_bin_id", "")).strip()
        b_id = str(patch_row.get("b_bin_id", "")).strip()
        A_u_raw = _load_bin_by_id_and_type(resolver=resolver, artifact_id=A_u_id, artifact_type="dmpl_tensor_q32_v1")
        A_v_raw = _load_bin_by_id_and_type(resolver=resolver, artifact_id=A_v_id, artifact_type="dmpl_tensor_q32_v1")
        B_u_raw = _load_bin_by_id_and_type(resolver=resolver, artifact_id=B_u_id, artifact_type="dmpl_tensor_q32_v1")
        B_v_raw = _load_bin_by_id_and_type(resolver=resolver, artifact_id=B_v_id, artifact_type="dmpl_tensor_q32_v1")
        b_raw = _load_bin_by_id_and_type(resolver=resolver, artifact_id=b_id, artifact_type="dmpl_tensor_q32_v1")
        A_u_dims, A_u_vals2 = parse_tensor_q32_v1(A_u_raw)
        A_v_dims, A_v_vals2 = parse_tensor_q32_v1(A_v_raw)
        B_u_dims, B_u_vals2 = parse_tensor_q32_v1(B_u_raw)
        B_v_dims, B_v_vals2 = parse_tensor_q32_v1(B_v_raw)
        b_dims, b_vals2 = parse_tensor_q32_v1(b_raw)
        require_shape(A_u_dims, [int(d_u32), int(rank_u32)])
        require_shape(A_v_dims, [int(rank_u32), int(d_u32)])
        require_shape(B_u_dims, [int(d_u32), int(rank_u32)])
        require_shape(B_v_dims, [int(rank_u32), int(p_u32)])
        require_shape(b_dims, [int(d_u32)])
        A_u_vals = [int(v) for v in A_u_vals2]
        A_v_vals = [int(v) for v in A_v_vals2]
        B_u_vals = [int(v) for v in B_u_vals2]
        B_v_vals = [int(v) for v in B_v_vals2]
        b_vals = [int(v) for v in b_vals2]
    else:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "unknown patch_kind", "patch_kind": patch_kind})

    out = ConceptPatchEntryV1(
        concept_shard_id=str(concept_shard_id),
        embed_vec_q32=[int(v) for v in embed_vals],
        patch_kind=str(patch_kind),
        A_vals_q32=A_vals,
        B_vals_q32=B_vals,
        b_vals_q32=b_vals,
        rank_u32=rank_u32,
        A_u_vals_q32=A_u_vals,
        A_v_vals_q32=A_v_vals,
        B_u_vals_q32=B_u_vals,
        B_v_vals_q32=B_v_vals,
        v_c0_q32=int(v_c0_q32),
        w_vec_q32=w_vec,
    )
    cache[key] = out
    return out


def verify_dmpl_train_replay_v1(
    *,
    root_tuple_obj: dict[str, Any],
    train_run_ref: dict[str, str],
    train_trace_ref: dict[str, str],
    train_receipt_ref: dict[str, str],
    resolver: Any,
) -> None:
    if not isinstance(root_tuple_obj, dict):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "root_tuple_obj type"})

    # Load and validate TrainRun/Trace/Receipt via ArtifactRef bytes.
    train_run_obj, train_run_bytes = _load_json_by_ref(resolver=resolver, artifact_ref=train_run_ref, schema_name="dmpl_train_run_v1")
    train_trace_obj, train_trace_bytes = _load_json_by_ref(resolver=resolver, artifact_ref=train_trace_ref, schema_name="dmpl_train_trace_v1")
    train_receipt_obj, _train_receipt_bytes = _load_json_by_ref(resolver=resolver, artifact_ref=train_receipt_ref, schema_name="dmpl_train_receipt_v1")

    train_run_id = sha256_prefixed(bytes(train_run_bytes))
    train_trace_id = sha256_prefixed(bytes(train_trace_bytes))

    if str(train_trace_obj.get("train_run_id", "")).strip() != str(train_run_id).strip():
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "train_trace train_run_id"})
    if str(train_receipt_obj.get("train_run_id", "")).strip() != str(train_run_id).strip():
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "train_receipt train_run_id"})
    if str(train_receipt_obj.get("train_trace_id", "")).strip() != str(train_trace_id).strip():
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "train_receipt train_trace_id"})

    # Load baseline droot/config/modelpack and enforce opset pins.
    baseline_droot_id = _require_sha256_id(train_run_obj.get("baseline_droot_id"), reason=DMPL_E_OPSET_MISMATCH)
    droot_obj = _load_json_by_id_and_type(resolver=resolver, artifact_id=baseline_droot_id, artifact_type="dmpl_droot_v1")
    config_id = _require_sha256_id(droot_obj.get("dmpl_config_id"), reason=DMPL_E_OPSET_MISMATCH)
    config_obj = _load_json_by_id_and_type(resolver=resolver, artifact_id=config_id, artifact_type="dmpl_config_v1")
    modelpack_id = _require_sha256_id(config_obj.get("active_modelpack_id"), reason=DMPL_E_OPSET_MISMATCH)
    modelpack_obj = _load_json_by_id_and_type(resolver=resolver, artifact_id=modelpack_id, artifact_type="dmpl_modelpack_v1")
    verify_dmpl_opset_v1(droot_obj=dict(droot_obj), config_obj=dict(config_obj), modelpack_obj=dict(modelpack_obj))

    # TrainRun bindings to config caps + initial bundles.
    caps_obj = config_obj.get("caps")
    if not isinstance(caps_obj, dict):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "caps type"})
    train_steps_u32 = int(train_run_obj.get("train_steps_u32", -1))
    batch_size_u32 = int(train_run_obj.get("batch_size_u32", -1))
    if int(train_steps_u32) != int(caps_obj.get("train_steps_u32", -2)):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "train_steps cap mismatch"})
    if int(batch_size_u32) != int(caps_obj.get("batch_size_u32", -2)):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "batch_size cap mismatch"})

    lr_q32_obj = train_run_obj.get("lr_q32")
    max_gn_obj = train_run_obj.get("max_grad_norm_q32")
    if not isinstance(lr_q32_obj, dict) or not isinstance(max_gn_obj, dict):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "lr/max_grad_norm types"})
    lr_q32 = int(lr_q32_obj.get("q", 0))
    max_grad_norm_q32 = int(max_gn_obj.get("q", 0))
    if int(lr_q32) != int((caps_obj.get("lr_q32") or {}).get("q", -999999999999)):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "lr cap mismatch"})
    if int(max_grad_norm_q32) != int((caps_obj.get("max_grad_norm_q32") or {}).get("q", -999999999999)):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "max_grad_norm cap mismatch"})

    init_fparams_id = _require_sha256_id(train_run_obj.get("initial_fparams_bundle_id"), reason=DMPL_E_OPSET_MISMATCH)
    init_vparams_id = _require_sha256_id(train_run_obj.get("initial_vparams_bundle_id"), reason=DMPL_E_OPSET_MISMATCH)
    if str(init_fparams_id).strip() != str(config_obj.get("fparams_bundle_id", "")).strip():
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "initial_fparams != config"})
    if str(init_vparams_id).strip() != str(config_obj.get("vparams_bundle_id", "")).strip():
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "initial_vparams != config"})

    trainable = train_run_obj.get("trainable_tensors")
    if not isinstance(trainable, list):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "trainable_tensors type"})
    expected_set = {"A0", "B0", "b0", "Wg", "w0", "v0"}
    if set(str(x) for x in trainable) != expected_set:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "trainable_tensors set"})
    sorted_trainable = sorted([str(x) for x in trainable])
    if [str(x) for x in trainable] != sorted_trainable:
        raise DMPLError(reason_code=DMPL_E_REDUCTION_ORDER_VIOLATION, details={"hint": "trainable_tensors not sorted"})

    if str(train_run_obj.get("expected_output_kind", "")).strip() != "FULL_TENSORS_EACH_STEP_V1":
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "expected_output_kind"})

    # Load dataset pack by id and validate.
    dataset_pack_id = _require_sha256_id(train_run_obj.get("dataset_pack_id"), reason=DMPL_E_OPSET_MISMATCH)
    dataset_pack_obj = _load_json_by_id_and_type(resolver=resolver, artifact_id=dataset_pack_id, artifact_type="dmpl_dataset_pack_v1")

    sample_count_u64 = dataset_pack_obj.get("sample_count_u64")
    if not isinstance(sample_count_u64, int) or int(sample_count_u64) < 0:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "sample_count_u64"})
    if int(train_steps_u32) * int(batch_size_u32) > int(sample_count_u64):
        raise DMPLError(reason_code=DMPL_E_BUDGET_EXCEEDED, details={"hint": "train budget exceeds dataset"})

    if int(dataset_pack_obj.get("chunk_size_bytes_u32", 0)) != 1048576:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "dataset chunk_size"})
    dataset_chunks = _require_sorted_contiguous_chunks(dataset_pack_obj.get("chunks"))
    _chunk_bytes_list, dataset_stream, dataset_chunk_hashes32 = _load_chunks_stream(resolver=resolver, chunks=dataset_chunks, artifact_type="dmpl_dataset_chunk_v1")

    # Parse sample records.
    sample_objs, sample_raws = parse_lenpref_canonjson_stream_v1(stream_bytes=dataset_stream, record_count_u64=int(sample_count_u64))

    # Verify dataset ordering: (episode_id asc, t_u32 asc) strictly increasing.
    prev_key: tuple[str, int] | None = None
    for rec in sample_objs:
        if not isinstance(rec, dict) or str(rec.get("record_kind", "")).strip() != "SAMPLE":
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "dataset record_kind"})
        episode_id = rec.get("episode_id")
        t_u32 = rec.get("t_u32")
        if not isinstance(episode_id, str) or not episode_id:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "episode_id"})
        if not isinstance(t_u32, int) or int(t_u32) < 0 or int(t_u32) > 0xFFFFFFFF:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "t_u32"})
        key = (str(episode_id), int(t_u32))
        if prev_key is not None and key <= prev_key:
            raise DMPLError(reason_code=DMPL_E_REDUCTION_ORDER_VIOLATION, details={"hint": "dataset order"})
        prev_key = key

        active_concepts = rec.get("active_concepts")
        _ = _require_ordered_unique_strings(active_concepts) if active_concepts is not None else []

    # Verify dataset chain final + merkle root.
    samples_chain_final_exp = _recompute_dataset_chain_final_id(opset_id=str(dataset_pack_obj.get("opset_id", "")).strip(), record_bytes=sample_raws)
    if str(dataset_pack_obj.get("samples_chain_final", "")).strip() != str(samples_chain_final_exp).strip():
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "samples_chain_final"})
    chunks_merkle_root_exp = _recompute_chunks_merkle_root_id(record_count_u64=int(sample_count_u64), chunk_hashes32=dataset_chunk_hashes32)
    if str(dataset_pack_obj.get("chunks_merkle_root", "")).strip() != str(chunks_merkle_root_exp).strip():
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "dataset chunks_merkle_root"})

    # Load runtime from baseline droot.
    runtime = load_runtime_from_droot_v1(str(baseline_droot_id), resolver)
    d = int(runtime.dims.d_u32)
    p = int(runtime.dims.p_u32)
    embed_dim = int(runtime.dims.embed_dim_u32)

    # Enforce record_count in TrainTrace matches train_steps.
    if int(train_trace_obj.get("record_count_u64", -1)) != int(train_steps_u32):
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "train_trace record_count"})

    if int(train_trace_obj.get("chunk_size_bytes_u32", 0)) != 1048576:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "train_trace chunk_size"})
    trace_chunks = _require_sorted_contiguous_chunks(train_trace_obj.get("chunks"))
    _trace_chunk_bytes_list, trace_stream, trace_chunk_hashes32 = _load_chunks_stream(resolver=resolver, chunks=trace_chunks, artifact_type="dmpl_train_trace_chunk_v1")
    step_objs, step_raws = parse_lenpref_canonjson_stream_v1(stream_bytes=trace_stream, record_count_u64=int(train_steps_u32))

    # Verify trace chain final + chunks merkle root.
    train_run_hash32 = bytes.fromhex(train_run_id.split(":", 1)[1])
    trace_chain_final_exp = _recompute_train_trace_chain_final_id(train_run_hash32=train_run_hash32, opset_id=str(train_trace_obj.get("opset_id", "")).strip(), record_bytes=step_raws)
    if str(train_trace_obj.get("trace_chain_final", "")).strip() != str(trace_chain_final_exp).strip():
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "train_trace trace_chain_final"})
    trace_merkle_root_exp = _recompute_chunks_merkle_root_id(record_count_u64=int(train_steps_u32), chunk_hashes32=trace_chunk_hashes32)
    if str(train_trace_obj.get("chunks_merkle_root", "")).strip() != str(trace_merkle_root_exp).strip():
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "train_trace chunks_merkle_root"})

    # Prepare training state from runtime (baseline params).
    (A0_dims, A0_vals) = runtime.base_forward["A0"]
    (B0_dims, B0_vals) = runtime.base_forward["B0"]
    (b0_dims, b0_vals) = runtime.base_forward["b0"]
    (Wg_dims, Wg_vals) = runtime.base_forward["Wg"]
    (w0_dims, w0_vals) = runtime.base_value["w0"]
    (v0_dims, v0_vals) = runtime.base_value["v0"]
    require_shape(A0_dims, [d, d])
    require_shape(B0_dims, [d, p])
    require_shape(b0_dims, [d])
    require_shape(Wg_dims, [embed_dim, d])
    require_shape(w0_dims, [d])
    require_shape(v0_dims, [1])
    if len(v0_vals) != 1:
        raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "v0 len"})

    state = TrainableStateV1(
        A0_q32=[int(v) for v in A0_vals],
        B0_q32=[int(v) for v in B0_vals],
        b0_q32=[int(v) for v in b0_vals],
        Wg_q32=[int(v) for v in Wg_vals],
        w0_q32=[int(v) for v in w0_vals],
        v0_q32=int(v0_vals[0]),
    )

    # Config gating/objective for training math.
    gating_spec = config_obj.get("gating_spec")
    if not isinstance(gating_spec, dict):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "gating_spec"})
    normalize_weights_b = bool(gating_spec.get("normalize_weights_b", False))
    epsilon_q32_obj = gating_spec.get("epsilon_q32")
    if not isinstance(epsilon_q32_obj, dict) or set(epsilon_q32_obj.keys()) != {"q"}:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "epsilon_q32"})
    epsilon_q32 = int(epsilon_q32_obj.get("q", 0))

    objective_spec = config_obj.get("objective_spec")
    if not isinstance(objective_spec, dict):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "objective_spec"})
    gamma_q32_obj = objective_spec.get("gamma_q32")
    if not isinstance(gamma_q32_obj, dict) or set(gamma_q32_obj.keys()) != {"q"}:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "gamma_q32"})
    gamma_q32 = int(gamma_q32_obj.get("q", 0))

    # Concept patch cache (keyed by (concept_id, ladder_level_u32)).
    concept_cache: dict[tuple[str, int], ConceptPatchEntryV1] = {}

    # Replay each step and compare to stored TRAIN_STEP records.
    updated_ids: dict[str, str] | None = None
    for step_u32 in range(int(train_steps_u32)):
        stored = step_objs[step_u32]
        if not isinstance(stored, dict) or str(stored.get("record_kind", "")).strip() != "TRAIN_STEP":
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "train record_kind"})

        # Deterministic batch slice.
        batch_start = int(step_u32) * int(batch_size_u32)
        batch_end = batch_start + int(batch_size_u32)
        if batch_end > len(sample_objs):
            raise DMPLError(reason_code=DMPL_E_DATASET_OOB, details={"step_u32": int(step_u32)})
        batch_recs = sample_objs[batch_start:batch_end]

        # Build inputs for SGD step.
        action_objs: list[dict[str, Any]] = []
        z_t_vecs: list[list[int]] = []
        z_true_vecs: list[list[int]] = []
        concepts_by_sample: list[list[ConceptPatchEntryV1]] = []

        batch_ids_exp: list[dict[str, Any]] = []

        for rec in batch_recs:
            if not isinstance(rec, dict):
                raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "sample rec type"})
            episode_id = rec.get("episode_id")
            t_u32_val = rec.get("t_u32")
            if not isinstance(episode_id, str) or not isinstance(t_u32_val, int):
                raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "batch id types"})
            batch_ids_exp.append({"episode_id": str(episode_id), "t_u32": int(t_u32_val) & 0xFFFFFFFF})

            ladder_level_u32 = rec.get("ladder_level_u32")
            if not isinstance(ladder_level_u32, int) or ladder_level_u32 < 0 or ladder_level_u32 > 0xFFFFFFFF:
                raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "ladder_level_u32"})

            z_t_bin_id = _require_sha256_id(rec.get("z_t_bin_id"), reason=DMPL_E_HASH_MISMATCH)
            z_tp1_bin_id = _require_sha256_id(rec.get("z_tp1_true_bin_id"), reason=DMPL_E_HASH_MISMATCH)
            z_t_raw = _load_bin_by_id_and_type(resolver=resolver, artifact_id=z_t_bin_id, artifact_type="dmpl_tensor_q32_v1")
            z_true_raw = _load_bin_by_id_and_type(resolver=resolver, artifact_id=z_tp1_bin_id, artifact_type="dmpl_tensor_q32_v1")
            z_t_dims, z_t_vals = parse_tensor_q32_v1(z_t_raw)
            z_true_dims, z_true_vals = parse_tensor_q32_v1(z_true_raw)
            require_shape(z_t_dims, [d])
            require_shape(z_true_dims, [d])
            z_t_vecs.append([int(v) for v in z_t_vals])
            z_true_vecs.append([int(v) for v in z_true_vals])

            action_record_id = _require_sha256_id(rec.get("action_record_id"), reason=DMPL_E_HASH_MISMATCH)
            action_obj = _load_canon_json_by_id_no_schema(resolver=resolver, artifact_id=action_record_id, artifact_type="dmpl_action_v1")
            action_objs.append(dict(action_obj))

            # Active concept set -> ConceptPatchEntryV1 list (in provided order).
            active_concepts = rec.get("active_concepts")
            if not isinstance(active_concepts, list):
                raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "active_concepts"})
            concept_ids = _require_ordered_unique_strings(active_concepts)
            patches: list[ConceptPatchEntryV1] = []
            for cid in concept_ids:
                patches.append(
                    _load_concept_patch_entry(
                        resolver=resolver,
                        concept_shard_id=str(cid),
                        ladder_level_u32=int(ladder_level_u32),
                        d_u32=int(d),
                        p_u32=int(p),
                        embed_dim_u32=int(embed_dim),
                        cache=concept_cache,
                    )
                )
            concepts_by_sample.append(patches)

        # Execute SGD step.
        step_res = train_step_sgd_det_v1(
            d_u32=int(d),
            p_u32=int(p),
            embed_dim_u32=int(embed_dim),
            gamma_q32=int(gamma_q32),
            normalize_weights_b=bool(normalize_weights_b),
            epsilon_q32=int(epsilon_q32),
            max_grad_norm_q32=int(max_grad_norm_q32),
            lr_q32=int(lr_q32),
            state=state,
            batch=batch_recs,
            concept_patches_by_sample=concepts_by_sample,
            action_objs=action_objs,
            z_t_vecs_q32=z_t_vecs,
            z_tp1_true_vecs_q32=z_true_vecs,
        )

        # Compute expected updated tensor ids and verify stored tensor artifacts match the bytes.
        updated_bytes: dict[str, bytes] = {}
        updated_ids_step: dict[str, str] = {}
        # A0, B0, b0, Wg, w0, v0
        updated_bytes["A0"] = encode_tensor_q32_v1(dims_u32=[d, d], values_i64=[int(v) for v in state.A0_q32])
        updated_bytes["B0"] = encode_tensor_q32_v1(dims_u32=[d, p], values_i64=[int(v) for v in state.B0_q32])
        updated_bytes["b0"] = encode_tensor_q32_v1(dims_u32=[d], values_i64=[int(v) for v in state.b0_q32])
        updated_bytes["Wg"] = encode_tensor_q32_v1(dims_u32=[embed_dim, d], values_i64=[int(v) for v in state.Wg_q32])
        updated_bytes["w0"] = encode_tensor_q32_v1(dims_u32=[d], values_i64=[int(v) for v in state.w0_q32])
        updated_bytes["v0"] = encode_tensor_q32_v1(dims_u32=[1], values_i64=[int(state.v0_q32)])
        for name, b in updated_bytes.items():
            updated_ids_step[name] = sha256_prefixed_bytes(b)
            stored_bin = _load_bin_by_id_and_type(resolver=resolver, artifact_id=updated_ids_step[name], artifact_type="dmpl_tensor_q32_v1")
            if bytes(stored_bin) != bytes(b):
                raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "tensor bytes mismatch", "tensor": str(name)})

        # Compare stored TRAIN_STEP record fields.
        if int(stored.get("step_u32", -1)) != int(step_u32):
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "step_u32"})
        if int(stored.get("batch_start_index_u64", -1)) != int(batch_start):
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "batch_start_index_u64"})
        if stored.get("batch_ids") != batch_ids_exp:
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "batch_ids mismatch"})

        def _q32_field(obj: dict[str, Any], key: str) -> int:
            v = obj.get(key)
            if not isinstance(v, dict) or set(v.keys()) != {"q"}:
                raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": f"bad q32 field {key}"})
            q = v.get("q")
            if not isinstance(q, int):
                raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": f"bad q32 field {key}"})
            return int(q)

        if int(_q32_field(stored, "loss_pred_q32")) != int(step_res.loss_pred_q32):
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "loss_pred mismatch"})
        if int(_q32_field(stored, "loss_value_q32")) != int(step_res.loss_value_q32):
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "loss_value mismatch"})
        if int(_q32_field(stored, "loss_total_q32")) != int(step_res.loss_total_q32):
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "loss_total mismatch"})
        if int(_q32_field(stored, "grad_norm_q32")) != int(step_res.grad_norm_q32):
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "grad_norm mismatch"})
        if bool(stored.get("clipped_b", False)) != bool(step_res.clipped_b):
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "clipped_b mismatch"})

        if int(_q32_field(stored, "lr_q32")) != int(lr_q32):
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "lr_q32 mismatch"})
        if int(_q32_field(stored, "max_grad_norm_q32")) != int(max_grad_norm_q32):
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "max_grad_norm_q32 mismatch"})

        updated_obj = stored.get("updated_tensor_bin_ids")
        if not isinstance(updated_obj, dict):
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "updated_tensor_bin_ids type"})
        if set(updated_obj.keys()) != set(updated_ids_step.keys()):
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "updated_tensor_bin_ids keys"})
        for name, exp_id in updated_ids_step.items():
            if str(updated_obj.get(name, "")).strip() != str(exp_id).strip():
                raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "updated_tensor_bin_id mismatch", "tensor": str(name)})

        cap_counters = stored.get("cap_counters")
        if not isinstance(cap_counters, dict) or set(cap_counters.keys()) != {"ops_u64", "bytes_u64"}:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "cap_counters"})
        if not isinstance(cap_counters.get("ops_u64"), int) or not isinstance(cap_counters.get("bytes_u64"), int):
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "cap_counters types"})

        updated_ids = dict(updated_ids_step)

    if updated_ids is None:
        # 0-step training: candidate tensors must match baseline initial bundle tensor IDs.
        f_bundle_init = _load_json_by_id_and_type(resolver=resolver, artifact_id=init_fparams_id, artifact_type="dmpl_params_bundle_v1")
        v_bundle_init = _load_json_by_id_and_type(resolver=resolver, artifact_id=init_vparams_id, artifact_type="dmpl_params_bundle_v1")
        updated_ids = {}
        for row in list(f_bundle_init.get("tensors", [])):
            if not isinstance(row, dict):
                continue
            name = str(row.get("name", "")).strip()
            if name in {"A0", "B0", "b0", "Wg"}:
                updated_ids[name] = _require_sha256_id(row.get("tensor_bin_id"), reason=DMPL_E_HASH_MISMATCH)
        for row in list(v_bundle_init.get("tensors", [])):
            if not isinstance(row, dict):
                continue
            name = str(row.get("name", "")).strip()
            if name in {"w0", "v0"}:
                updated_ids[name] = _require_sha256_id(row.get("tensor_bin_id"), reason=DMPL_E_HASH_MISMATCH)
        if set(updated_ids.keys()) != {"A0", "B0", "b0", "Wg", "w0", "v0"}:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "initial bundle missing trainable tensors"})

    # Assemble candidate bundles/config/droot and verify TrainReceipt + root tuple bind.
    # Candidate bundles.
    candidate_tensors_f = [
        {"name": "A0", "shape_u32": [d, d], "tensor_bin_id": updated_ids["A0"]},
        {"name": "B0", "shape_u32": [d, p], "tensor_bin_id": updated_ids["B0"]},
        {"name": "Wg", "shape_u32": [embed_dim, d], "tensor_bin_id": updated_ids["Wg"]},
        {"name": "b0", "shape_u32": [d], "tensor_bin_id": updated_ids["b0"]},
    ]
    candidate_tensors_v = [
        {"name": "v0", "shape_u32": [1], "tensor_bin_id": updated_ids["v0"]},
        {"name": "w0", "shape_u32": [d], "tensor_bin_id": updated_ids["w0"]},
    ]
    candidate_tensors_f.sort(key=lambda r: str(r["name"]))
    candidate_tensors_v.sort(key=lambda r: str(r["name"]))

    f_bundle_obj = {
        "schema_id": "dmpl_params_bundle_v1",
        "dc1_id": str(runtime.dc1_id),
        "opset_id": str(runtime.opset_id),
        "bundle_kind": "F",
        "modelpack_id": str(modelpack_id),
        "tensors": candidate_tensors_f,
        "merkle_root": "",
    }
    v_bundle_obj = {
        "schema_id": "dmpl_params_bundle_v1",
        "dc1_id": str(runtime.dc1_id),
        "opset_id": str(runtime.opset_id),
        "bundle_kind": "V",
        "modelpack_id": str(modelpack_id),
        "tensors": candidate_tensors_v,
        "merkle_root": "",
    }
    froot = compute_params_bundle_merkle_root_v1(bundle_obj=f_bundle_obj, resolver=resolver)
    vroot = compute_params_bundle_merkle_root_v1(bundle_obj=v_bundle_obj, resolver=resolver)
    f_bundle_obj["merkle_root"] = str(froot)
    v_bundle_obj["merkle_root"] = str(vroot)
    candidate_fparams_bundle_id = sha256_prefixed(gcj1_canon_bytes(f_bundle_obj))
    candidate_vparams_bundle_id = sha256_prefixed(gcj1_canon_bytes(v_bundle_obj))

    # Candidate config: copy baseline config, replace bundle IDs (all else unchanged).
    candidate_config_obj = dict(config_obj)
    candidate_config_obj["fparams_bundle_id"] = str(candidate_fparams_bundle_id)
    candidate_config_obj["vparams_bundle_id"] = str(candidate_vparams_bundle_id)
    candidate_config_id = sha256_prefixed(gcj1_canon_bytes(candidate_config_obj))

    # Candidate droot.
    caps_digest = str(droot_obj.get("caps_digest", "")).strip()
    candidate_droot_obj = {
        "schema_id": "dmpl_droot_v1",
        "dc1_id": str(runtime.dc1_id),
        "opset_id": str(runtime.opset_id),
        "dmpl_config_id": str(candidate_config_id),
        "froot": str(froot),
        "vroot": str(vroot),
        "caps_digest": str(caps_digest),
        "opset_semantics_id": str(runtime.opset_id),
    }
    candidate_droot_id = sha256_prefixed(gcj1_canon_bytes(candidate_droot_obj))

    if str(train_receipt_obj.get("baseline_droot_id", "")).strip() != str(baseline_droot_id).strip():
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "receipt baseline_droot_id"})
    if str(train_receipt_obj.get("candidate_droot_id", "")).strip() != str(candidate_droot_id).strip():
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "receipt candidate_droot_id"})
    if str(train_receipt_obj.get("candidate_config_id", "")).strip() != str(candidate_config_id).strip():
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "receipt candidate_config_id"})
    if str(train_receipt_obj.get("candidate_fparams_bundle_id", "")).strip() != str(candidate_fparams_bundle_id).strip():
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "receipt candidate_fparams_bundle_id"})
    if str(train_receipt_obj.get("candidate_vparams_bundle_id", "")).strip() != str(candidate_vparams_bundle_id).strip():
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "receipt candidate_vparams_bundle_id"})
    if str(train_receipt_obj.get("candidate_froot", "")).strip() != str(froot).strip():
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "receipt candidate_froot"})
    if str(train_receipt_obj.get("candidate_vroot", "")).strip() != str(vroot).strip():
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "receipt candidate_vroot"})

    status = train_receipt_obj.get("status")
    if not isinstance(status, dict) or set(status.keys()) != {"ok_b", "reason_code"}:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "receipt status"})
    if bool(status.get("ok_b", False)) is not True or str(status.get("reason_code", "")).strip() != DMPL_OK:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "receipt status not OK"})

    # Bind candidate droot to root tuple.
    droot_ref = root_tuple_obj.get("droot")
    if not isinstance(droot_ref, dict):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "root_tuple droot ref"})
    if str(droot_ref.get("artifact_id", "")).strip() != str(candidate_droot_id).strip():
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "root_tuple droot mismatch"})

    # Ensure stored candidate JSON artifacts match recomputation (fail-closed on mismatch).
    stored_f_bundle = _load_json_by_id_and_type(resolver=resolver, artifact_id=candidate_fparams_bundle_id, artifact_type="dmpl_params_bundle_v1")
    stored_v_bundle = _load_json_by_id_and_type(resolver=resolver, artifact_id=candidate_vparams_bundle_id, artifact_type="dmpl_params_bundle_v1")
    if stored_f_bundle != f_bundle_obj:
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "fparams bundle mismatch"})
    if stored_v_bundle != v_bundle_obj:
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "vparams bundle mismatch"})

    stored_cfg = _load_json_by_id_and_type(resolver=resolver, artifact_id=candidate_config_id, artifact_type="dmpl_config_v1")
    if stored_cfg != candidate_config_obj:
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "candidate config mismatch"})

    stored_droot = _load_json_by_id_and_type(resolver=resolver, artifact_id=candidate_droot_id, artifact_type="dmpl_droot_v1")
    if stored_droot != candidate_droot_obj:
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "candidate droot mismatch"})
