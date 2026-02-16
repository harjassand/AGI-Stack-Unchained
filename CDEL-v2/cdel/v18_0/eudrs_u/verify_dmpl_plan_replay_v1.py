"""DMPL plan replay verifier (v1).

Phase 3 contract: given a stored (PlanQuery, RolloutTrace, ActionReceipt) triple,
replay deterministic planning and verify byte-exact equivalence:
  - retrieval digests + retrieval_trace_root
  - gate digest + gate_active
  - EXPAND record bytes (GCJ-1 canonical)
  - chunk bytes + chunk merkle root
  - trace hash chain final
  - ActionReceipt bytes/hash

This module is RE2: deterministic and fail-closed via DMPLError.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from typing import Any

from ..omega_common_v1 import OmegaV18Error, require_no_absolute_paths, validate_schema
from .dmpl_action_encode_v1 import hash_action_record_v1
from .dmpl_config_load_v1 import load_runtime_from_droot_v1
from .dmpl_merkle_v1 import compute_chunk_merkle_root_v1
from .dmpl_planner_dcbts_l_v1 import plan_call_v1
from .dmpl_tensor_io_v1 import parse_tensor_q32_v1, require_shape
from .dmpl_types_v1 import (
    DMPLError,
    DMPL_E_DIM_MISMATCH,
    DMPL_E_DISABLED,
    DMPL_E_HASH_MISMATCH,
    DMPL_E_NONCANON_GCJ1,
    DMPL_E_OPSET_MISMATCH,
    DMPL_E_RETRIEVAL_DIGEST_MISMATCH,
    DMPL_E_TRACE_CHAIN_BREAK,
    _sha256_id_to_digest32,
)
from .eudrs_u_hash_v1 import gcj1_canon_bytes, gcj1_loads_and_verify_canonical
from .verify_dmpl_opset_v1 import verify_dmpl_opset_v1


_U32LE = struct.Struct("<I")
_CHUNK_SIZE_BYTES_V1 = 1048576
_TRACE_PREFIX = b"DMPL/TRACE/v1\x00"
_EMPTY_CHUNKS_DOMAIN = b"DMPL/CHUNKS/EMPTY/v1\x00"


def _sha25632(data: bytes) -> bytes:
    return hashlib.sha256(bytes(data)).digest()


def _sha256_id(data: bytes) -> str:
    return f"sha256:{_sha25632(data).hex()}"


def _hash_json_obj(obj: dict[str, Any], *, reason: str) -> str:
    try:
        raw = gcj1_canon_bytes(obj)
    except Exception:
        raise DMPLError(reason_code=reason, details={"hint": "gcj1_canon_bytes failed"})
    return _sha256_id(raw)


def _require_no_abs_paths(obj: Any) -> None:
    try:
        require_no_absolute_paths(obj)
    except OmegaV18Error:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "absolute path"})


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
    _require_no_abs_paths(obj)
    # Schema validation (when available).
    try:
        validate_schema(obj, str(artifact_type))
    except Exception:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"artifact_id": str(artifact_id), "artifact_type": str(artifact_type)})
    return dict(obj)


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


@dataclass(frozen=True, slots=True)
class _ParsedTrace:
    record_objs: list[dict[str, Any]]
    record_bytes: list[bytes]
    trace_chain_final_id: str
    chunks_merkle_root_id: str


def _parse_lenpref_canonjson_stream(*, stream_bytes: bytes, record_count_u64: int) -> tuple[list[dict[str, Any]], list[bytes]]:
    if not isinstance(stream_bytes, (bytes, bytearray, memoryview)):
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "stream type"})
    buf = bytes(stream_bytes)
    off = 0
    objs: list[dict[str, Any]] = []
    raws: list[bytes] = []
    while off < len(buf):
        if off + 4 > len(buf):
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "trailing bytes"})
        (n,) = _U32LE.unpack_from(buf, off)
        off += 4
        size = int(n)
        if size < 0 or off + size > len(buf):
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "lenpref out of range"})
        rec_bytes = bytes(buf[off : off + size])
        off += size
        try:
            rec_obj = gcj1_loads_and_verify_canonical(rec_bytes)
        except OmegaV18Error:
            raise DMPLError(reason_code=DMPL_E_NONCANON_GCJ1, details={"hint": "record noncanonical"})
        if not isinstance(rec_obj, dict):
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "record not dict"})
        _require_no_abs_paths(rec_obj)
        objs.append(dict(rec_obj))
        raws.append(rec_bytes)

    if off != len(buf):
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "stream parse mismatch"})
    if int(record_count_u64) != len(objs):
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "record_count mismatch", "expected": int(record_count_u64), "got": int(len(objs))})
    return objs, raws


def _recompute_trace_chain_final_id(*, plan_query_hash32: bytes, modelpack_hash32: bytes, opset_id: str, record_bytes: list[bytes]) -> str:
    if len(bytes(plan_query_hash32)) != 32 or len(bytes(modelpack_hash32)) != 32:
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "hash32 len"})
    h = _sha25632(_TRACE_PREFIX + bytes(plan_query_hash32) + bytes(modelpack_hash32) + str(opset_id).encode("utf-8", errors="strict"))
    for raw in record_bytes:
        ri_hash32 = _sha25632(bytes(raw))
        h = _sha25632(bytes(h) + bytes(ri_hash32))
    return f"sha256:{h.hex()}"


def _recompute_chunks_merkle_root_id(*, record_count_u64: int, chunk_hashes32: list[bytes]) -> str:
    if int(record_count_u64) == 0:
        root32 = _sha25632(_EMPTY_CHUNKS_DOMAIN)
    else:
        root32 = compute_chunk_merkle_root_v1([bytes(h) for h in chunk_hashes32])
    if not isinstance(root32, (bytes, bytearray, memoryview)) or len(bytes(root32)) != 32:
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "bad merkle root"})
    return f"sha256:{bytes(root32).hex()}"


def _load_trace_chunks_and_stream(
    *,
    resolver: Any,
    chunks: list[dict[str, Any]],
) -> tuple[list[bytes], bytes]:
    try:
        fn = getattr(resolver, "load_artifact_bytes")
    except Exception:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver missing load_artifact_bytes"})
    if not callable(fn):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver.load_artifact_bytes not callable"})

    chunk_bytes_list: list[bytes] = []
    for row in chunks:
        chunk_bin_id = str(row.get("chunk_bin_id", "")).strip()
        chunk_bytes_u32 = row.get("chunk_bytes_u32")
        if not isinstance(chunk_bytes_u32, int):
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "chunk_bytes_u32 type"})
        raw = fn(artifact_id=str(chunk_bin_id), artifact_type="dmpl_rollout_trace_chunk_v1", ext="bin")
        if not isinstance(raw, (bytes, bytearray, memoryview)):
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver returned non-bytes"})
        b = bytes(raw)
        if len(b) != int(chunk_bytes_u32):
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "chunk len mismatch"})
        if _sha256_id(b) != str(chunk_bin_id).strip():
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"artifact_id": str(chunk_bin_id), "artifact_type": "dmpl_rollout_trace_chunk_v1"})
        chunk_bytes_list.append(b)

    stream = b"".join(chunk_bytes_list)
    return chunk_bytes_list, stream


def _verify_stored_trace_internal_consistency(
    *,
    plan_query_obj: dict[str, Any],
    rollout_trace_obj: dict[str, Any],
    resolver: Any,
) -> _ParsedTrace:
    record_count_u64 = rollout_trace_obj.get("record_count_u64")
    if not isinstance(record_count_u64, int) or int(record_count_u64) < 0:
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "record_count_u64"})

    chunk_size = rollout_trace_obj.get("chunk_size_bytes_u32")
    if int(chunk_size) != int(_CHUNK_SIZE_BYTES_V1):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"field": "chunk_size_bytes_u32", "got": chunk_size})

    chunks = _require_sorted_contiguous_chunks(rollout_trace_obj.get("chunks"))
    if int(record_count_u64) == 0:
        if chunks:
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "record_count==0 but chunks nonempty"})
    else:
        if not chunks:
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "record_count>0 but chunks empty"})

    for i, row in enumerate(chunks):
        chunk_bytes_u32 = row.get("chunk_bytes_u32")
        if not isinstance(chunk_bytes_u32, int):
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "chunk_bytes_u32 type"})
        if i < len(chunks) - 1:
            if int(chunk_bytes_u32) != int(_CHUNK_SIZE_BYTES_V1):
                raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "non-final chunk size"})
        else:
            if int(chunk_bytes_u32) < 1 or int(chunk_bytes_u32) > int(_CHUNK_SIZE_BYTES_V1):
                raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "final chunk size"})

    # Load chunk bytes + parse records.
    chunk_bytes_list, stream_bytes = _load_trace_chunks_and_stream(resolver=resolver, chunks=chunks)
    record_objs, record_raws = _parse_lenpref_canonjson_stream(stream_bytes=stream_bytes, record_count_u64=int(record_count_u64))

    # Load droot/config to get modelpack hash32 for the trace chain H0.
    droot_id = str(plan_query_obj.get("dmpl_droot_id", "")).strip()
    if not droot_id.startswith("sha256:"):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "dmpl_droot_id"})
    droot_obj = _load_json_by_id_and_type(resolver=resolver, artifact_id=droot_id, artifact_type="dmpl_droot_v1")
    config_id = str(droot_obj.get("dmpl_config_id", "")).strip()
    config_obj = _load_json_by_id_and_type(resolver=resolver, artifact_id=config_id, artifact_type="dmpl_config_v1")
    modelpack_id = str(config_obj.get("active_modelpack_id", "")).strip()
    modelpack_hash32 = _sha256_id_to_digest32(modelpack_id, reason=DMPL_E_HASH_MISMATCH)

    # Recompute trace chain final using stored bytes.
    plan_query_id = _hash_json_obj(plan_query_obj, reason=DMPL_E_NONCANON_GCJ1)
    plan_query_hash32 = _sha256_id_to_digest32(plan_query_id, reason=DMPL_E_HASH_MISMATCH)
    opset_id = str(rollout_trace_obj.get("opset_id", "")).strip()
    trace_chain_final_exp = _recompute_trace_chain_final_id(
        plan_query_hash32=plan_query_hash32,
        modelpack_hash32=bytes(modelpack_hash32),
        opset_id=opset_id,
        record_bytes=record_raws,
    )
    if str(trace_chain_final_exp).strip() != str(rollout_trace_obj.get("trace_chain_final", "")).strip():
        raise DMPLError(reason_code=DMPL_E_TRACE_CHAIN_BREAK, details={})

    # Recompute chunks merkle root using stored chunk hashes.
    chunk_hashes32 = [_sha25632(cb) for cb in chunk_bytes_list]
    chunks_root_exp = _recompute_chunks_merkle_root_id(record_count_u64=int(record_count_u64), chunk_hashes32=chunk_hashes32)
    if str(chunks_root_exp).strip() != str(rollout_trace_obj.get("chunks_merkle_root", "")).strip():
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "chunks merkle root"})

    return _ParsedTrace(
        record_objs=record_objs,
        record_bytes=record_raws,
        trace_chain_final_id=str(trace_chain_final_exp),
        chunks_merkle_root_id=str(chunks_root_exp),
    )


class _MemArtifactWriterV1:
    def __init__(self) -> None:
        self._json: dict[tuple[str, str], bytes] = {}
        self._bin: dict[tuple[str, str], bytes] = {}

    def write_json_artifact(self, artifact_type: str, obj: Any) -> str:
        at = str(artifact_type).strip()
        if not at:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "empty artifact_type"})
        try:
            raw = gcj1_canon_bytes(obj)
        except OmegaV18Error:
            raise DMPLError(reason_code=DMPL_E_NONCANON_GCJ1, details={"artifact_type": at})
        out_id = _sha256_id(raw)
        key = (at, str(out_id))
        prev = self._json.get(key)
        if prev is not None and prev != raw:
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "json id collision", "artifact_type": at, "artifact_id": str(out_id)})
        self._json[key] = raw
        return str(out_id)

    def write_bin_artifact(self, artifact_type: str, raw: bytes) -> str:
        at = str(artifact_type).strip()
        if not at:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "empty artifact_type"})
        b = bytes(raw)
        out_id = _sha256_id(b)
        key = (at, str(out_id))
        prev = self._bin.get(key)
        if prev is not None and prev != b:
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "bin id collision", "artifact_type": at, "artifact_id": str(out_id)})
        self._bin[key] = b
        return str(out_id)

    def load_json_obj(self, artifact_type: str, artifact_id: str) -> dict[str, Any]:
        key = (str(artifact_type).strip(), str(artifact_id).strip())
        raw = self._json.get(key)
        if raw is None:
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "missing replay json", "artifact_type": key[0], "artifact_id": key[1]})
        try:
            obj = gcj1_loads_and_verify_canonical(raw)
        except OmegaV18Error:
            raise DMPLError(reason_code=DMPL_E_NONCANON_GCJ1, details={"artifact_type": key[0], "artifact_id": key[1]})
        if not isinstance(obj, dict):
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "replay json not dict"})
        _require_no_abs_paths(obj)
        return dict(obj)

    def load_bin(self, artifact_type: str, artifact_id: str) -> bytes:
        key = (str(artifact_type).strip(), str(artifact_id).strip())
        raw = self._bin.get(key)
        if raw is None:
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "missing replay bin", "artifact_type": key[0], "artifact_id": key[1]})
        return bytes(raw)


def _verify_action_receipt_struct(*, action_receipt_obj: dict[str, Any]) -> None:
    tie_break = action_receipt_obj.get("tie_break_proof")
    if not isinstance(tie_break, dict):
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "tie_break_proof"})
    proof_digest = str(tie_break.get("proof_digest", "")).strip()
    ordering_policy = tie_break.get("ordering_policy")
    ordering_keys = tie_break.get("ordering_keys")
    if not isinstance(ordering_policy, dict) or not isinstance(ordering_keys, list):
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "tie_break_proof fields"})
    core = {"ordering_policy": dict(ordering_policy), "ordering_keys": list(ordering_keys)}
    try:
        exp = _sha256_id(gcj1_canon_bytes(core))
    except OmegaV18Error:
        raise DMPLError(reason_code=DMPL_E_NONCANON_GCJ1, details={"hint": "tie_break_proof core noncanon"})
    if str(exp).strip() != proof_digest:
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "tie_break_proof digest"})


def _collect_action_record_ids(*, trace_records: list[dict[str, Any]], action_receipt_obj: dict[str, Any]) -> list[str]:
    ids: set[str] = set()
    for rec in trace_records:
        if not isinstance(rec, dict):
            continue
        arid = rec.get("action_record_id")
        if isinstance(arid, str) and arid.startswith("sha256:"):
            ids.add(str(arid).strip())
        # Enforce record-level binding when both fields exist.
        ah = rec.get("action_hash")
        if isinstance(arid, str) and isinstance(ah, str) and str(arid).strip() != str(ah).strip():
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "action_hash != action_record_id"})

    chosen = action_receipt_obj.get("chosen_action_record_id")
    if isinstance(chosen, str) and chosen.startswith("sha256:"):
        ids.add(str(chosen).strip())
    return sorted(ids)


def _classify_first_divergence(
    *,
    stored_records: list[dict[str, Any]],
    replay_records: list[dict[str, Any]],
    stored_trace_chain_final: str,
    replay_trace_chain_final: str,
) -> None:
    n = min(len(stored_records), len(replay_records))
    for i in range(n):
        s = stored_records[i]
        r = replay_records[i]
        if s == r:
            continue

        # Retrieval mismatch classification.
        for field in ("retrieval_query_digest", "retrieval_result_digest", "retrieval_trace_root"):
            if s.get(field) != r.get(field):
                raise DMPLError(
                    reason_code=DMPL_E_RETRIEVAL_DIGEST_MISMATCH,
                    details={"record_index_u64": int(i), "field": str(field), "stored": s.get(field), "replay": r.get(field)},
                )

        # Gate mismatch.
        if s.get("gate_digest") != r.get("gate_digest") or s.get("gate_active") != r.get("gate_active"):
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"record_index_u64": int(i), "field": "gate"})

        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"record_index_u64": int(i)})

    if len(stored_records) != len(replay_records):
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"stored_count": int(len(stored_records)), "replay_count": int(len(replay_records))})

    if str(stored_trace_chain_final).strip() != str(replay_trace_chain_final).strip():
        raise DMPLError(reason_code=DMPL_E_TRACE_CHAIN_BREAK, details={})

    raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "id mismatch but records match"})


def verify_dmpl_plan_replay_v1(
    plan_query_obj: dict,
    rollout_trace_obj: dict,
    action_receipt_obj: dict,
    resolver,
) -> None:
    if not isinstance(plan_query_obj, dict) or not isinstance(rollout_trace_obj, dict) or not isinstance(action_receipt_obj, dict):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "inputs must be dicts"})

    # Step A1-A3: validate stored artifacts against schemas (fail-closed).
    for obj, schema in (
        (plan_query_obj, "dmpl_plan_query_v1"),
        (rollout_trace_obj, "dmpl_rollout_trace_v1"),
        (action_receipt_obj, "dmpl_action_receipt_v1"),
    ):
        try:
            validate_schema(obj, schema)
        except Exception:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": f"schema {schema}"})
        if str(obj.get("schema_id", "")).strip() != schema:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "schema_id mismatch", "schema": schema})
        _require_no_abs_paths(obj)

    # Step A4: link consistency (ids computed from canonical bytes).
    plan_query_id = _hash_json_obj(plan_query_obj, reason=DMPL_E_NONCANON_GCJ1)
    rollout_trace_id = _hash_json_obj(rollout_trace_obj, reason=DMPL_E_NONCANON_GCJ1)
    if str(rollout_trace_obj.get("plan_query_id", "")).strip() != str(plan_query_id).strip():
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "trace.plan_query_id"})
    if str(action_receipt_obj.get("plan_query_id", "")).strip() != str(plan_query_id).strip():
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "receipt.plan_query_id"})
    if str(action_receipt_obj.get("rollout_trace_id", "")).strip() != str(rollout_trace_id).strip():
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "receipt.rollout_trace_id"})

    # Step A5-A7: validate stored trace + chunks using stored bytes.
    parsed = _verify_stored_trace_internal_consistency(
        plan_query_obj=dict(plan_query_obj),
        rollout_trace_obj=dict(rollout_trace_obj),
        resolver=resolver,
    )

    # Step B: load runtime inputs as planner would + opset compliance.
    droot_id = str(plan_query_obj.get("dmpl_droot_id", "")).strip()
    droot_obj = _load_json_by_id_and_type(resolver=resolver, artifact_id=droot_id, artifact_type="dmpl_droot_v1")
    runtime = load_runtime_from_droot_v1(droot_id=str(droot_id), resolver=resolver)
    verify_dmpl_opset_v1(droot_obj=dict(droot_obj), config_obj=dict(runtime.config), modelpack_obj=dict(runtime.modelpack))

    if not bool(runtime.config.get("enabled_b", False)):
        raise DMPLError(reason_code=DMPL_E_DISABLED, details={})

    # Load z0 tensor bin and verify shape [d] (planner will do this too; keep early + deterministic).
    z0_id = str(plan_query_obj.get("z0_tensor_bin_id", "")).strip()
    try:
        fn = getattr(resolver, "load_artifact_bytes")
    except Exception:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver missing load_artifact_bytes"})
    if not callable(fn):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver.load_artifact_bytes not callable"})
    z0_raw = fn(artifact_id=str(z0_id), artifact_type="dmpl_tensor_q32_v1", ext="bin")
    if not isinstance(z0_raw, (bytes, bytearray, memoryview)):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver returned non-bytes"})
    if _sha256_id(bytes(z0_raw)) != str(z0_id).strip():
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"artifact_id": str(z0_id), "artifact_type": "dmpl_tensor_q32_v1"})
    dims, vals = parse_tensor_q32_v1(bytes(z0_raw))
    require_shape(dims, [int(runtime.dims.d_u32)])
    if len(vals) != int(runtime.dims.d_u32):
        raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "z0 vals"})

    # Step C: replay planning with an in-memory writer.
    mem_writer = _MemArtifactWriterV1()
    replay_result = plan_call_v1(runtime=runtime, plan_query_obj=dict(plan_query_obj), resolver=resolver, artifact_writer=mem_writer)
    replay_rollout_trace_id = str(replay_result.rollout_trace_id)
    replay_action_receipt_id = str(replay_result.action_receipt_id)

    # Load replay artifacts.
    replay_rollout_trace_obj = mem_writer.load_json_obj("dmpl_rollout_trace_v1", replay_rollout_trace_id)
    replay_action_receipt_obj = mem_writer.load_json_obj("dmpl_action_receipt_v1", replay_action_receipt_id)

    # Compare ids (Step D1) and classify divergences deterministically (Step D2).
    stored_rollout_trace_id = str(rollout_trace_id).strip()
    stored_action_receipt_id = _hash_json_obj(action_receipt_obj, reason=DMPL_E_NONCANON_GCJ1)
    if replay_rollout_trace_id.strip() != stored_rollout_trace_id or replay_action_receipt_id.strip() != stored_action_receipt_id.strip():
        # Parse replay trace stream into record objs (do not attempt to load droot/config from replay outputs).
        replay_record_count = replay_rollout_trace_obj.get("record_count_u64")
        if not isinstance(replay_record_count, int) or int(replay_record_count) < 0:
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "replay record_count_u64"})
        replay_chunks = _require_sorted_contiguous_chunks(replay_rollout_trace_obj.get("chunks"))
        replay_chunk_bytes: list[bytes] = []
        for row in replay_chunks:
            cid = str(row.get("chunk_bin_id", "")).strip()
            csz = row.get("chunk_bytes_u32")
            if not isinstance(csz, int):
                raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "replay chunk_bytes_u32 type"})
            b = mem_writer.load_bin("dmpl_rollout_trace_chunk_v1", cid)
            if len(b) != int(csz):
                raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "replay chunk len mismatch"})
            if _sha256_id(b) != cid:
                raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "replay chunk hash mismatch"})
            replay_chunk_bytes.append(b)
        replay_stream = b"".join(replay_chunk_bytes)
        replay_records, _replay_raws = _parse_lenpref_canonjson_stream(stream_bytes=replay_stream, record_count_u64=int(replay_record_count))
        _classify_first_divergence(
            stored_records=parsed.record_objs,
            replay_records=replay_records,
            stored_trace_chain_final=str(rollout_trace_obj.get("trace_chain_final", "")).strip(),
            replay_trace_chain_final=str(replay_rollout_trace_obj.get("trace_chain_final", "")).strip(),
        )

    # Step D3: ActionReceipt structural correctness + chosen ids/hashes.
    _verify_action_receipt_struct(action_receipt_obj=dict(action_receipt_obj))
    _verify_action_receipt_struct(action_receipt_obj=dict(replay_action_receipt_obj))

    for field, expected in (
        ("chosen_action_record_id", str(replay_action_receipt_obj.get("chosen_action_record_id", "")).strip()),
        ("chosen_action_hash", str(replay_action_receipt_obj.get("chosen_action_hash", "")).strip()),
        ("chosen_node_id", str(replay_action_receipt_obj.get("chosen_node_id", "")).strip()),
    ):
        if str(action_receipt_obj.get(field, "")).strip() != expected:
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "receipt field mismatch", "field": str(field)})

    # Step D4: referenced action artifacts exist and match.
    action_ids = _collect_action_record_ids(trace_records=parsed.record_objs, action_receipt_obj=dict(action_receipt_obj))
    for action_id in action_ids:
        raw = fn(artifact_id=str(action_id), artifact_type="dmpl_action_v1", ext="json")
        if not isinstance(raw, (bytes, bytearray, memoryview)):
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver returned non-bytes"})
        b = bytes(raw)
        if _sha256_id(b) != str(action_id).strip():
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"artifact_id": str(action_id), "artifact_type": "dmpl_action_v1"})
        try:
            obj = gcj1_loads_and_verify_canonical(b)
        except OmegaV18Error:
            raise DMPLError(reason_code=DMPL_E_NONCANON_GCJ1, details={"artifact_id": str(action_id), "artifact_type": "dmpl_action_v1"})
        if not isinstance(obj, dict):
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "action not dict"})
        _require_no_abs_paths(obj)
        hashed_id, _hashed32 = hash_action_record_v1(dict(obj))
        if str(hashed_id).strip() != str(action_id).strip():
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "action hash mismatch"})


class _ReplayResolverV1:
    """Resolver adapter over the in-memory writer outputs (used for replay trace chunk loading)."""

    def __init__(self, writer: _MemArtifactWriterV1) -> None:
        self._w = writer

    def load_artifact_bytes(self, *, artifact_id: str, artifact_type: str, ext: str) -> bytes:
        if str(ext).strip() == "json":
            # Only needed for internal helpers; callers should prefer writer.load_json_obj.
            key = (str(artifact_type).strip(), str(artifact_id).strip())
            raw = self._w._json.get(key)  # noqa: SLF001 - deterministic test-only adapter
            if raw is None:
                raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "missing replay json", "artifact_type": key[0], "artifact_id": key[1]})
            return bytes(raw)
        if str(ext).strip() == "bin":
            return self._w.load_bin(str(artifact_type).strip(), str(artifact_id).strip())
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "bad ext"})


__all__ = [
    "verify_dmpl_plan_replay_v1",
]
