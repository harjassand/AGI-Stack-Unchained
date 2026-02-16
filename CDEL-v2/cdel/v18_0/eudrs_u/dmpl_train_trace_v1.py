"""DMPL train trace writer/parser (v1).

Phase 4 contract:
  - Record encoding: lenpref_canonjson_v1 (u32le(len(bytes)) + GCJ-1 bytes).
  - Chunking: fixed 1MiB BIN chunks (`dmpl_train_trace_chunk_v1`).
  - Hash chain: DMPL/TRAIN_TRACE/v1.
  - Chunks merkle root: DMPL/MERKLE/LEAF|NODE v1 with leaf names = chunk_index decimal string.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import Any

from ..omega_common_v1 import OmegaV18Error, require_no_absolute_paths
from .dmpl_merkle_v1 import compute_chunk_merkle_root_v1
from .dmpl_types_v1 import (
    DMPLError,
    DMPL_E_BUDGET_EXCEEDED,
    DMPL_E_HASH_MISMATCH,
    DMPL_E_NONCANON_GCJ1,
    DMPL_E_OPSET_MISMATCH,
    _sha25632_count,
    _sha256_id_from_hex_digest32,
    _sha256_id_to_digest32,
)
from .eudrs_u_hash_v1 import gcj1_canon_bytes, gcj1_loads_and_verify_canonical


_U32LE = struct.Struct("<I")

_TRACE_PREFIX = b"DMPL/TRAIN_TRACE/v1\x00"
_EMPTY_CHUNKS_DOMAIN = b"DMPL/CHUNKS/EMPTY/v1\x00"

_CHUNK_SIZE_BYTES_V1 = 1048576


def encode_record_lenpref_canonjson_v1(record_obj: dict) -> bytes:
    raw = gcj1_canon_bytes(record_obj)
    n = len(raw)
    if n < 0 or n > 0xFFFFFFFF:
        raise DMPLError(reason_code=DMPL_E_BUDGET_EXCEEDED, details={"hint": "record too large"})
    return struct.pack("<I", int(n) & 0xFFFFFFFF) + raw


def train_trace_h0_v1(train_run_hash32: bytes, opset_id: str) -> bytes:
    if not isinstance(train_run_hash32, (bytes, bytearray, memoryview)) or len(bytes(train_run_hash32)) != 32:
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "train_run_hash32"})
    if not isinstance(opset_id, str):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "opset_id"})
    return _sha25632_count(_TRACE_PREFIX + bytes(train_run_hash32) + opset_id.encode("utf-8", errors="strict"))


@dataclass(frozen=True, slots=True)
class _ChunkInfo:
    chunk_index_u32: int
    chunk_bin_id: str
    chunk_bytes_u32: int
    chunk_hash32: bytes
    chunk_bytes: bytes


class TrainTraceWriterV1:
    def __init__(self, *, train_run_id: str, opset_id: str, chunk_size: int = _CHUNK_SIZE_BYTES_V1) -> None:
        if int(chunk_size) != int(_CHUNK_SIZE_BYTES_V1):
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "chunk_size"})
        self._train_run_id = str(train_run_id)
        train_run_hash32 = _sha256_id_to_digest32(str(train_run_id), reason=DMPL_E_HASH_MISMATCH)
        self._opset_id = str(opset_id)
        self._chunk_size = int(chunk_size)

        self._h_i = train_trace_h0_v1(bytes(train_run_hash32), self._opset_id)
        self._record_count_u64 = 0

        self._cur = bytearray()
        self._chunks: list[_ChunkInfo] = []

    def append_record(self, record_obj: dict[str, Any]) -> None:
        if not isinstance(record_obj, dict):
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "record type"})
        enc = encode_record_lenpref_canonjson_v1(record_obj)
        if len(enc) > int(self._chunk_size):
            raise DMPLError(reason_code=DMPL_E_BUDGET_EXCEEDED, details={"hint": "record exceeds chunk size"})

        # fixed_1MiB_v1 chunking (record stream may span chunks).
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

        # Hash chain update (ri_hash32 over canonical record bytes).
        ri_hash32 = _sha25632_count(gcj1_canon_bytes(record_obj))
        self._h_i = _sha25632_count(bytes(self._h_i) + bytes(ri_hash32))
        self._record_count_u64 += 1

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

        self._flush_chunk(allow_partial=True)

        chunks_obj: list[dict[str, Any]] = []
        chunk_hashes32: list[bytes] = []
        for info in self._chunks:
            out_id = write_bin_artifact("dmpl_train_trace_chunk_v1", bytes(info.chunk_bytes))
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
            chunks_merkle_root32 = compute_chunk_merkle_root_v1([bytes(h) for h in chunk_hashes32])

        trace_chain_final_id = _sha256_id_from_hex_digest32(bytes(self._h_i))
        chunks_merkle_root_id = _sha256_id_from_hex_digest32(bytes(chunks_merkle_root32))

        manifest_obj: dict[str, Any] = {
            "schema_id": "dmpl_train_trace_v1",
            "dc1_id": "dc1:q32_v1",
            "opset_id": str(self._opset_id),
            "train_run_id": str(self._train_run_id),
            "record_count_u64": int(self._record_count_u64),
            "chunk_size_bytes_u32": int(_CHUNK_SIZE_BYTES_V1),
            "chunks": chunks_obj,
            "trace_chain_final": str(trace_chain_final_id),
            "chunks_merkle_root": str(chunks_merkle_root_id),
        }

        train_trace_id = write_json_artifact("dmpl_train_trace_v1", manifest_obj)
        return str(train_trace_id), str(chunks_merkle_root_id)


def parse_lenpref_canonjson_stream_v1(*, stream_bytes: bytes, record_count_u64: int) -> tuple[list[dict[str, Any]], list[bytes]]:
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
        require_no_absolute_paths(rec_obj)
        objs.append(dict(rec_obj))
        raws.append(rec_bytes)

    if off != len(buf):
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "stream parse mismatch"})
    if int(record_count_u64) != len(objs):
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "record_count mismatch", "expected": int(record_count_u64), "got": int(len(objs))})
    return objs, raws


__all__ = [
    "TrainTraceWriterV1",
    "encode_record_lenpref_canonjson_v1",
    "parse_lenpref_canonjson_stream_v1",
    "train_trace_h0_v1",
]

