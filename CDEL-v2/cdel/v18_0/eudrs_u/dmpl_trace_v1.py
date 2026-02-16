"""DMPL rollout trace writer (v1).

Phase 2 contract:
  - Record encoding: lenpref_canonjson_v1 (u32le(len(bytes)) + GCJ-1 bytes).
  - Chunking: fixed 1MiB BIN chunks (`dmpl_rollout_trace_chunk_v1`).
  - Hash chain: DMPL/TRACE/v1.
  - Chunks merkle root: DMPL/MERKLE/LEAF|NODE v1 with leaf names = chunk_index decimal string.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import Any

from .dmpl_merkle_v1 import compute_chunk_merkle_root_v1
from .dmpl_types_v1 import (
    DMPLError,
    DMPL_E_BUDGET_EXCEEDED,
    DMPL_E_HASH_MISMATCH,
    DMPL_E_OPSET_MISMATCH,
    _sha25632_count,
    _sha256_id_from_hex_digest32,
    _sha256_id_to_digest32,
)
from .eudrs_u_hash_v1 import gcj1_canon_bytes

_TRACE_PREFIX = b"DMPL/TRACE/v1\x00"
_EMPTY_CHUNKS_DOMAIN = b"DMPL/CHUNKS/EMPTY/v1\x00"

_CHUNK_SIZE_BYTES_V1 = 1048576


def encode_record_lenpref_canonjson_v1(record_obj: dict) -> bytes:
    raw = gcj1_canon_bytes(record_obj)
    n = len(raw)
    if n < 0 or n > 0xFFFFFFFF:
        raise DMPLError(reason_code=DMPL_E_BUDGET_EXCEEDED, details={"hint": "record too large"})
    return struct.pack("<I", int(n) & 0xFFFFFFFF) + raw


def trace_h0_v1(plan_query_hash32: bytes, modelpack_hash32: bytes, opset_id: str) -> bytes:
    if not isinstance(plan_query_hash32, (bytes, bytearray, memoryview)) or len(bytes(plan_query_hash32)) != 32:
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "plan_query_hash32"})
    if not isinstance(modelpack_hash32, (bytes, bytearray, memoryview)) or len(bytes(modelpack_hash32)) != 32:
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "modelpack_hash32"})
    if not isinstance(opset_id, str):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "opset_id"})
    return _sha25632_count(_TRACE_PREFIX + bytes(plan_query_hash32) + bytes(modelpack_hash32) + opset_id.encode("utf-8", errors="strict"))


@dataclass(frozen=True, slots=True)
class _ChunkInfo:
    chunk_index_u32: int
    chunk_bin_id: str
    chunk_bytes_u32: int
    chunk_hash32: bytes
    chunk_bytes: bytes


class TraceWriterV1:
    def __init__(self, plan_query_id: str, modelpack_hash32: bytes, opset_id: str, chunk_size: int = _CHUNK_SIZE_BYTES_V1) -> None:
        if int(chunk_size) != int(_CHUNK_SIZE_BYTES_V1):
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "chunk_size"})
        self._plan_query_id = str(plan_query_id)
        self._plan_query_hash32 = _sha256_id_to_digest32(str(plan_query_id), reason=DMPL_E_HASH_MISMATCH)
        self._modelpack_hash32 = bytes(modelpack_hash32)
        if len(self._modelpack_hash32) != 32:
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "modelpack_hash32 len"})
        self._opset_id = str(opset_id)
        self._chunk_size = int(chunk_size)

        self._h_i = trace_h0_v1(self._plan_query_hash32, self._modelpack_hash32, self._opset_id)
        self._record_count_u64 = 0

        self._cur = bytearray()
        self._chunks: list[_ChunkInfo] = []

    def append_record(self, record_obj: dict) -> None:
        if not isinstance(record_obj, dict):
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "record type"})
        enc = encode_record_lenpref_canonjson_v1(record_obj)
        if len(enc) > int(self._chunk_size):
            raise DMPLError(reason_code=DMPL_E_BUDGET_EXCEEDED, details={"hint": "record exceeds chunk size"})
        # fixed_1MiB_v1: flush BIN chunks at exact 1MiB boundaries (except the final chunk).
        # This means record bytes may span chunks; the record stream is decoded from the
        # concatenation of all chunk bytes.
        off = 0
        while off < len(enc):
            space = int(self._chunk_size) - int(len(self._cur))
            if space < 0:
                raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "chunk overflow"})
            if space == 0:
                self._flush_chunk(allow_partial=False)
                continue
            take = min(int(space), int(len(enc) - off))
            self._cur += enc[off : off + take]
            off += take
            if len(self._cur) == int(self._chunk_size):
                self._flush_chunk(allow_partial=False)

        # Hash chain update:
        ri_hash32 = _sha25632_count(gcj1_canon_bytes(record_obj))
        self._h_i = _sha25632_count(bytes(self._h_i) + bytes(ri_hash32))
        self._record_count_u64 += 1

    def preview_append_op_delta_v1(self, record_obj: dict) -> int:
        """Return the deterministic sha256-op delta for append_record(record_obj).

        append_record always performs:
          - ri_hash32 = sha256(canon_json(record_obj))           (+1)
          - h_{i+1}   = sha256(h_i + ri_hash32)                 (+1)
        and may flush the current chunk first when it is non-empty and the next
        record would exceed the fixed chunk size:
          - chunk_hash32 = sha256(cur_chunk_bytes)              (+1)
        """

        if not isinstance(record_obj, dict):
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "record type"})
        enc = encode_record_lenpref_canonjson_v1(record_obj)
        if len(enc) > int(self._chunk_size):
            raise DMPLError(reason_code=DMPL_E_BUDGET_EXCEEDED, details={"hint": "record exceeds chunk size"})
        # Hash chain ops: ri_hash32 (+1) and h_{i+1} (+1).
        # Chunk ops: when record stream bytes would fill (or exceed) the current fixed chunk boundary, (+1).
        will_flush = (len(self._cur) + len(enc)) >= int(self._chunk_size)
        return 3 if will_flush else 2

    def _flush_chunk(self, *, allow_partial: bool) -> None:
        if not self._cur:
            return
        if not bool(allow_partial) and int(len(self._cur)) != int(self._chunk_size):
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "non-final chunk not full"})
        chunk_bytes = bytes(self._cur)
        chunk_hash32 = _sha25632_count(chunk_bytes)
        chunk_bin_id = _sha256_id_from_hex_digest32(chunk_hash32)
        idx = int(len(self._chunks))
        self._chunks.append(
            _ChunkInfo(
                chunk_index_u32=int(idx),
                chunk_bin_id=str(chunk_bin_id),
                chunk_bytes_u32=int(len(chunk_bytes)),
                chunk_hash32=bytes(chunk_hash32),
                chunk_bytes=chunk_bytes,
            )
        )
        self._cur = bytearray()

    def finalize(self, write_bin_artifact, write_json_artifact) -> tuple[str, str]:
        if not callable(write_bin_artifact) or not callable(write_json_artifact):
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "writer callbacks"})

        # Flush any tail chunk.
        self._flush_chunk(allow_partial=True)

        chunks_obj: list[dict[str, Any]] = []
        chunk_hashes32: list[bytes] = []
        for info in self._chunks:
            out_id = write_bin_artifact("dmpl_rollout_trace_chunk_v1", bytes(info.chunk_bytes))
            if str(out_id).strip() != str(info.chunk_bin_id).strip():
                raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "chunk id mismatch"})
            chunks_obj.append(
                {
                    "chunk_index_u32": int(info.chunk_index_u32),
                    "chunk_bin_id": str(info.chunk_bin_id),
                    "chunk_bytes_u32": int(info.chunk_bytes_u32),
                }
            )
            chunk_hashes32.append(_sha256_id_to_digest32(str(info.chunk_bin_id), reason=DMPL_E_HASH_MISMATCH))

        if int(self._record_count_u64) == 0:
            if chunks_obj:
                raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "record_count==0 but chunks nonempty"})
            chunks_merkle_root32 = _sha25632_count(_EMPTY_CHUNKS_DOMAIN)
        else:
            chunks_merkle_root32 = compute_chunk_merkle_root_v1(chunk_hashes32)

        trace_chain_final_id = _sha256_id_from_hex_digest32(bytes(self._h_i))
        chunks_merkle_root_id = _sha256_id_from_hex_digest32(bytes(chunks_merkle_root32))

        manifest_obj: dict[str, Any] = {
            "schema_id": "dmpl_rollout_trace_v1",
            "dc1_id": "dc1:q32_v1",
            "opset_id": str(self._opset_id),
            "plan_query_id": str(self._plan_query_id),
            "record_count_u64": int(self._record_count_u64),
            "chunk_size_bytes_u32": int(_CHUNK_SIZE_BYTES_V1),
            "chunks": chunks_obj,
            "trace_chain_final": str(trace_chain_final_id),
            "chunks_merkle_root": str(chunks_merkle_root_id),
        }

        rollout_trace_id = write_json_artifact("dmpl_rollout_trace_v1", manifest_obj)
        return str(rollout_trace_id), str(chunks_merkle_root_id)


__all__ = [
    "TraceWriterV1",
    "encode_record_lenpref_canonjson_v1",
    "trace_h0_v1",
]
