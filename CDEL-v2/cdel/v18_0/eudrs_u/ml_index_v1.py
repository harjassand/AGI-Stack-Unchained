"""ML-Index v1 (deterministic sublinear retrieval) for EUDRS-U.

Normative spec: user directive §11.

This module is RE2: deterministic, fail-closed.
"""

from __future__ import annotations

import hashlib
import heapq
import re
import struct
import sys
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Final, Iterable

from ..omega_common_v1 import ensure_sha256, fail, q32_int
from .eudrs_u_artifact_refs_v1 import require_artifact_ref_v1, verify_artifact_ref_v1
from .eudrs_u_hash_v1 import gcj1_loads_and_verify_canonical
from .eudrs_u_merkle_v1 import merkle_fanout_v1
from .eudrs_u_q32ops_v1 import dot_q32_shift_each_dim_v1, dot_q32_shift_end_v1, topk_det


def _fourcc_u32(tag4: str) -> int:
    if not isinstance(tag4, str) or len(tag4) != 4:
        fail("SCHEMA_FAIL")
    raw = tag4.encode("ascii", errors="strict")
    return int.from_bytes(raw, byteorder="big", signed=False)


SCHEMA_ID_CBK1_U32: Final[int] = _fourcc_u32("CBK1")
SCHEMA_ID_IDX1_U32: Final[int] = _fourcc_u32("IDX1")
SCHEMA_ID_IDXP_U32: Final[int] = _fourcc_u32("IDXP")

VERSION_U32_V1: Final[int] = 1

_CODEBOOK_HEADER = struct.Struct("<IIIII")  # schema_id, version, K, d, reserved
_INDEX_ROOT_HEADER = struct.Struct("<IIIII")  # schema_id, version, K, fanout, reserved
_PAGE_HEADER = struct.Struct("<IIIIIII")  # schema_id, version, bucket_id, page_index, record_count, key_dim, reserved

_OPSET_ID_RE = re.compile(r"^opset:eudrs_u_v1:sha256:[0-9a-f]{64}$")


def _require_bytes_like(data: object) -> memoryview:
    if not isinstance(data, (bytes, bytearray, memoryview)):
        fail("SCHEMA_FAIL")
    mv = memoryview(data)
    if mv.ndim != 1:
        fail("SCHEMA_FAIL")
    return mv


def _read_s64_array_le(mv: memoryview, off: int, count: int) -> tuple[list[int], int]:
    n = int(count)
    if n < 0:
        fail("SCHEMA_FAIL")
    nbytes = n * 8
    end = off + nbytes
    if end < off or end > len(mv):
        fail("SCHEMA_FAIL")
    arr = array("q")
    arr.frombytes(mv[off:end])
    if sys.byteorder != "little":
        arr.byteswap()
    return [int(v) for v in arr], end


def _pack_s64_array_le(values: Iterable[int]) -> bytes:
    arr = array("q", (int(v) for v in values))
    if sys.byteorder != "little":
        arr.byteswap()
    return arr.tobytes()


def _sha256_id_to_bytes32(value: str) -> bytes:
    """Convert a `sha256:<64hex>` string into 32 raw bytes."""

    sha = ensure_sha256(value)
    try:
        return bytes.fromhex(sha.split(":", 1)[1])
    except Exception:
        fail("SCHEMA_FAIL")
    return b""


@dataclass(frozen=True, slots=True)
class MLIndexMemGatesV1:
    mem_g1_bucket_balance_max_q32: int
    mem_g2_anchor_recall_min_q32: int


@dataclass(frozen=True, slots=True)
class MLIndexManifestV1:
    """ml_index_manifest_v1.json (Phase 3)."""

    opset_id: str
    key_dim_u32: int
    codebook_size_u32: int
    bucket_visit_k_u32: int
    scan_cap_per_bucket_u32: int
    merkle_fanout_u32: int
    sim_kind: str
    codebook_ref: dict[str, str]
    index_root_ref: dict[str, str]
    bucket_listing_ref: dict[str, str]
    mem_gates: MLIndexMemGatesV1


def require_ml_index_manifest_v1(obj: Any) -> MLIndexManifestV1:
    if not isinstance(obj, dict):
        fail("SCHEMA_FAIL")
    expected_keys = {
        "schema_id",
        "index_kind",
        "opset_id",
        "key_dim_u32",
        "codebook_size_u32",
        "bucket_visit_k_u32",
        "scan_cap_per_bucket_u32",
        "merkle_fanout_u32",
        "sim_kind",
        "codebook_ref",
        "index_root_ref",
        "bucket_listing_ref",
        "mem_gates",
    }
    if set(obj.keys()) != expected_keys:
        fail("SCHEMA_FAIL")
    if str(obj.get("schema_id", "")).strip() != "ml_index_manifest_v1":
        fail("SCHEMA_FAIL")
    if str(obj.get("index_kind", "")).strip() != "ML_INDEX_V1":
        fail("SCHEMA_FAIL")

    opset_id = str(obj.get("opset_id", "")).strip()
    if _OPSET_ID_RE.fullmatch(opset_id) is None:
        fail("SCHEMA_FAIL")

    key_dim_u32 = obj.get("key_dim_u32")
    codebook_size_u32 = obj.get("codebook_size_u32")
    bucket_visit_k_u32 = obj.get("bucket_visit_k_u32")
    scan_cap_per_bucket_u32 = obj.get("scan_cap_per_bucket_u32")
    merkle_fanout_u32 = obj.get("merkle_fanout_u32")
    if not isinstance(key_dim_u32, int) or key_dim_u32 < 0:
        fail("SCHEMA_FAIL")
    if not isinstance(codebook_size_u32, int) or codebook_size_u32 < 0:
        fail("SCHEMA_FAIL")
    if not isinstance(bucket_visit_k_u32, int) or bucket_visit_k_u32 <= 0:
        fail("SCHEMA_FAIL")
    if not isinstance(scan_cap_per_bucket_u32, int) or scan_cap_per_bucket_u32 <= 0:
        fail("SCHEMA_FAIL")
    if not isinstance(merkle_fanout_u32, int) or merkle_fanout_u32 <= 0:
        fail("SCHEMA_FAIL")

    sim_kind = str(obj.get("sim_kind", "")).strip()
    if sim_kind not in {"DOT_Q32_SHIFT_EACH_DIM_V1", "DOT_Q32_SHIFT_END_V1"}:
        fail("SCHEMA_FAIL")

    codebook_ref = require_artifact_ref_v1(obj.get("codebook_ref"))
    index_root_ref = require_artifact_ref_v1(obj.get("index_root_ref"))
    bucket_listing_ref = require_artifact_ref_v1(obj.get("bucket_listing_ref"))

    mem_gates_raw = obj.get("mem_gates")
    if not isinstance(mem_gates_raw, dict) or set(mem_gates_raw.keys()) != {
        "mem_g1_bucket_balance_max_q32",
        "mem_g2_anchor_recall_min_q32",
    }:
        fail("SCHEMA_FAIL")
    mem_gates = MLIndexMemGatesV1(
        mem_g1_bucket_balance_max_q32=int(q32_int(mem_gates_raw.get("mem_g1_bucket_balance_max_q32"))),
        mem_g2_anchor_recall_min_q32=int(q32_int(mem_gates_raw.get("mem_g2_anchor_recall_min_q32"))),
    )

    return MLIndexManifestV1(
        opset_id=opset_id,
        key_dim_u32=int(key_dim_u32),
        codebook_size_u32=int(codebook_size_u32),
        bucket_visit_k_u32=int(bucket_visit_k_u32),
        scan_cap_per_bucket_u32=int(scan_cap_per_bucket_u32),
        merkle_fanout_u32=int(merkle_fanout_u32),
        sim_kind=sim_kind,
        codebook_ref=codebook_ref,
        index_root_ref=index_root_ref,
        bucket_listing_ref=bucket_listing_ref,
        mem_gates=mem_gates,
    )


@dataclass(frozen=True, slots=True)
class MLIndexBucketListingPageV1:
    page_index_u32: int
    page_ref: dict[str, str]


@dataclass(frozen=True, slots=True)
class MLIndexBucketListingBucketV1:
    bucket_id_u32: int
    pages: list[MLIndexBucketListingPageV1]


@dataclass(frozen=True, slots=True)
class MLIndexBucketListingV1:
    """ml_index_bucket_listing_v1.json (Phase 3)."""

    index_manifest_id: str
    buckets: list[MLIndexBucketListingBucketV1]


def require_ml_index_bucket_listing_v1(obj: Any) -> MLIndexBucketListingV1:
    if not isinstance(obj, dict):
        fail("SCHEMA_FAIL")
    if set(obj.keys()) != {"schema_id", "index_manifest_id", "buckets"}:
        fail("SCHEMA_FAIL")
    if str(obj.get("schema_id", "")).strip() != "ml_index_bucket_listing_v1":
        fail("SCHEMA_FAIL")

    index_manifest_id = ensure_sha256(obj.get("index_manifest_id"))

    buckets_raw = obj.get("buckets")
    if not isinstance(buckets_raw, list):
        fail("SCHEMA_FAIL")

    buckets: list[MLIndexBucketListingBucketV1] = []
    prev_bucket_id: int | None = None
    for item in buckets_raw:
        if not isinstance(item, dict) or set(item.keys()) != {"bucket_id_u32", "pages"}:
            fail("SCHEMA_FAIL")
        bucket_id_u32 = item.get("bucket_id_u32")
        if not isinstance(bucket_id_u32, int) or bucket_id_u32 < 0 or bucket_id_u32 > 0xFFFFFFFF:
            fail("SCHEMA_FAIL")
        if prev_bucket_id is not None and int(bucket_id_u32) <= int(prev_bucket_id):
            # Strictly increasing: sorted ascending, no duplicates.
            fail("SCHEMA_FAIL")
        prev_bucket_id = int(bucket_id_u32)

        pages_raw = item.get("pages")
        if not isinstance(pages_raw, list):
            fail("SCHEMA_FAIL")
        pages: list[MLIndexBucketListingPageV1] = []
        prev_page_index: int | None = None
        for page_item in pages_raw:
            if not isinstance(page_item, dict) or set(page_item.keys()) != {"page_index_u32", "page_ref"}:
                fail("SCHEMA_FAIL")
            page_index_u32 = page_item.get("page_index_u32")
            if not isinstance(page_index_u32, int) or page_index_u32 < 0 or page_index_u32 > 0xFFFFFFFF:
                fail("SCHEMA_FAIL")
            if prev_page_index is not None and int(page_index_u32) <= int(prev_page_index):
                # Strictly increasing: sorted ascending, no duplicates.
                fail("SCHEMA_FAIL")
            prev_page_index = int(page_index_u32)
            page_ref = require_artifact_ref_v1(page_item.get("page_ref"))
            pages.append(MLIndexBucketListingPageV1(page_index_u32=int(page_index_u32), page_ref=page_ref))

        buckets.append(MLIndexBucketListingBucketV1(bucket_id_u32=int(bucket_id_u32), pages=pages))

    return MLIndexBucketListingV1(index_manifest_id=index_manifest_id, buckets=buckets)


@dataclass(frozen=True, slots=True)
class MLIndexCodebookV1:
    K_u32: int
    d_u32: int
    # Flattened row-major: C[k*d + i] are Q32 s64 integers.
    C_q32: list[int]

    def vec(self, k: int) -> list[int]:
        kk = int(k)
        if kk < 0 or kk >= int(self.K_u32):
            fail("SCHEMA_FAIL")
        d = int(self.d_u32)
        off = kk * d
        return [int(v) for v in self.C_q32[off : off + d]]


def decode_ml_index_codebook_v1(data: bytes | bytearray | memoryview) -> MLIndexCodebookV1:
    mv = _require_bytes_like(data)
    if len(mv) < _CODEBOOK_HEADER.size:
        fail("SCHEMA_FAIL")
    schema_id, version, K_u32, d_u32, reserved = _CODEBOOK_HEADER.unpack_from(mv, 0)
    if int(schema_id) != SCHEMA_ID_CBK1_U32 or int(version) != VERSION_U32_V1 or int(reserved) != 0:
        fail("SCHEMA_FAIL")
    K = int(K_u32)
    d = int(d_u32)
    if K < 0 or d < 0:
        fail("SCHEMA_FAIL")
    expected = _CODEBOOK_HEADER.size + (K * d * 8)
    if expected != len(mv):
        fail("SCHEMA_FAIL")
    C_q32, off = _read_s64_array_le(mv, _CODEBOOK_HEADER.size, K * d)
    if off != len(mv):
        fail("SCHEMA_FAIL")
    return MLIndexCodebookV1(K_u32=K, d_u32=d, C_q32=C_q32)


def encode_ml_index_codebook_v1(codebook: MLIndexCodebookV1) -> bytes:
    if not isinstance(codebook, MLIndexCodebookV1):
        fail("SCHEMA_FAIL")
    K = int(codebook.K_u32)
    d = int(codebook.d_u32)
    if K < 0 or d < 0:
        fail("SCHEMA_FAIL")
    if not isinstance(codebook.C_q32, list) or len(codebook.C_q32) != K * d:
        fail("SCHEMA_FAIL")
    header = _CODEBOOK_HEADER.pack(
        int(SCHEMA_ID_CBK1_U32) & 0xFFFFFFFF,
        int(VERSION_U32_V1) & 0xFFFFFFFF,
        int(K) & 0xFFFFFFFF,
        int(d) & 0xFFFFFFFF,
        0,
    )
    return header + _pack_s64_array_le(codebook.C_q32)


@dataclass(frozen=True, slots=True)
class MLIndexRootV1:
    K_u32: int
    fanout_u32: int
    bucket_root_hash32: list[bytes]  # length K, each 32 bytes


def decode_ml_index_root_v1(data: bytes | bytearray | memoryview) -> MLIndexRootV1:
    mv = _require_bytes_like(data)
    if len(mv) < _INDEX_ROOT_HEADER.size:
        fail("SCHEMA_FAIL")
    schema_id, version, K_u32, fanout_u32, reserved = _INDEX_ROOT_HEADER.unpack_from(mv, 0)
    if int(schema_id) != SCHEMA_ID_IDX1_U32 or int(version) != VERSION_U32_V1 or int(reserved) != 0:
        fail("SCHEMA_FAIL")
    K = int(K_u32)
    F = int(fanout_u32)
    if K < 0 or F <= 0:
        fail("SCHEMA_FAIL")
    expected = _INDEX_ROOT_HEADER.size + (K * 32)
    if expected != len(mv):
        fail("SCHEMA_FAIL")
    roots: list[bytes] = []
    off = _INDEX_ROOT_HEADER.size
    for _ in range(K):
        roots.append(bytes(mv[off : off + 32]))
        off += 32
    if off != len(mv):
        fail("SCHEMA_FAIL")
    return MLIndexRootV1(K_u32=K, fanout_u32=F, bucket_root_hash32=roots)


def encode_ml_index_root_v1(root: MLIndexRootV1) -> bytes:
    if not isinstance(root, MLIndexRootV1):
        fail("SCHEMA_FAIL")
    K = int(root.K_u32)
    F = int(root.fanout_u32)
    if K < 0 or F <= 0:
        fail("SCHEMA_FAIL")
    if not isinstance(root.bucket_root_hash32, list) or len(root.bucket_root_hash32) != K:
        fail("SCHEMA_FAIL")
    body = bytearray()
    for h in root.bucket_root_hash32:
        if not isinstance(h, (bytes, bytearray, memoryview)):
            fail("SCHEMA_FAIL")
        hb = bytes(h)
        if len(hb) != 32:
            fail("SCHEMA_FAIL")
        body += hb
    header = _INDEX_ROOT_HEADER.pack(
        int(SCHEMA_ID_IDX1_U32) & 0xFFFFFFFF,
        int(VERSION_U32_V1) & 0xFFFFFFFF,
        int(K) & 0xFFFFFFFF,
        int(F) & 0xFFFFFFFF,
        0,
    )
    return header + bytes(body)


@dataclass(frozen=True, slots=True)
class MLIndexPageRecordV1:
    record_hash32: bytes
    payload_hash32: bytes
    key_q32: list[int]


@dataclass(frozen=True, slots=True)
class MLIndexPageV1:
    bucket_id_u32: int
    page_index_u32: int
    key_dim_u32: int
    records: list[MLIndexPageRecordV1]


def decode_ml_index_page_v1(data: bytes | bytearray | memoryview) -> MLIndexPageV1:
    mv = _require_bytes_like(data)
    if len(mv) < _PAGE_HEADER.size:
        fail("SCHEMA_FAIL")
    schema_id, version, bucket_id, page_index, record_count, key_dim, reserved = _PAGE_HEADER.unpack_from(mv, 0)
    if int(schema_id) != SCHEMA_ID_IDXP_U32 or int(version) != VERSION_U32_V1 or int(reserved) != 0:
        fail("SCHEMA_FAIL")

    bucket_id_u32 = int(bucket_id)
    page_index_u32 = int(page_index)
    record_count_u32 = int(record_count)
    key_dim_u32 = int(key_dim)
    if bucket_id_u32 < 0 or page_index_u32 < 0 or record_count_u32 < 0 or key_dim_u32 < 0:
        fail("SCHEMA_FAIL")

    rec_size = 64 + (key_dim_u32 * 8)
    expected = _PAGE_HEADER.size + (record_count_u32 * rec_size)
    if expected != len(mv):
        fail("SCHEMA_FAIL")

    off = _PAGE_HEADER.size
    records: list[MLIndexPageRecordV1] = []
    prev_hash: bytes | None = None
    for _ in range(record_count_u32):
        record_hash32 = bytes(mv[off : off + 32])
        payload_hash32 = bytes(mv[off + 32 : off + 64])
        off += 64
        key_q32, off = _read_s64_array_le(mv, off, key_dim_u32)
        if prev_hash is not None:
            if record_hash32 <= prev_hash:
                # Must be strictly increasing: sorted ascending, no duplicates.
                fail("SCHEMA_FAIL")
        prev_hash = record_hash32
        records.append(MLIndexPageRecordV1(record_hash32=record_hash32, payload_hash32=payload_hash32, key_q32=key_q32))
    if off != len(mv):
        fail("SCHEMA_FAIL")
    return MLIndexPageV1(
        bucket_id_u32=bucket_id_u32,
        page_index_u32=page_index_u32,
        key_dim_u32=key_dim_u32,
        records=records,
    )


def encode_ml_index_page_v1(page: MLIndexPageV1) -> bytes:
    if not isinstance(page, MLIndexPageV1):
        fail("SCHEMA_FAIL")
    bucket_id_u32 = int(page.bucket_id_u32)
    page_index_u32 = int(page.page_index_u32)
    key_dim_u32 = int(page.key_dim_u32)
    if bucket_id_u32 < 0 or page_index_u32 < 0 or key_dim_u32 < 0:
        fail("SCHEMA_FAIL")
    if not isinstance(page.records, list):
        fail("SCHEMA_FAIL")

    # Enforce canonical ordering: record_hash32 strictly increasing.
    prev: bytes | None = None
    for rec in page.records:
        if not isinstance(rec, MLIndexPageRecordV1):
            fail("SCHEMA_FAIL")
        if not isinstance(rec.record_hash32, (bytes, bytearray, memoryview)):
            fail("SCHEMA_FAIL")
        if not isinstance(rec.payload_hash32, (bytes, bytearray, memoryview)):
            fail("SCHEMA_FAIL")
        rh = bytes(rec.record_hash32)
        ph = bytes(rec.payload_hash32)
        if len(rh) != 32 or len(ph) != 32:
            fail("SCHEMA_FAIL")
        if not isinstance(rec.key_q32, list) or len(rec.key_q32) != key_dim_u32:
            fail("SCHEMA_FAIL")
        if prev is not None and rh <= prev:
            fail("SCHEMA_FAIL")
        prev = rh

    header = _PAGE_HEADER.pack(
        int(SCHEMA_ID_IDXP_U32) & 0xFFFFFFFF,
        int(VERSION_U32_V1) & 0xFFFFFFFF,
        int(bucket_id_u32) & 0xFFFFFFFF,
        int(page_index_u32) & 0xFFFFFFFF,
        int(len(page.records)) & 0xFFFFFFFF,
        int(key_dim_u32) & 0xFFFFFFFF,
        0,
    )
    out = bytearray()
    out += header
    for rec in page.records:
        out += bytes(rec.record_hash32)
        out += bytes(rec.payload_hash32)
        out += _pack_s64_array_le(rec.key_q32)
    return bytes(out)
def load_ml_index_pages_by_bucket_v1(
    *,
    base_dir: Path,
    manifest: MLIndexManifestV1,
) -> tuple[dict[int, list[MLIndexPageV1]], dict[int, list[bytes]]]:
    """Deterministically load bucket pages using the bucket listing manifest (Phase 3).

    Returns:
      pages_by_bucket: {bucket_id: [page0, page1, ...]} where page_index is strictly increasing.
      leaf_hashes_by_bucket: {bucket_id: [sha256(page_bytes), ...]} in the same order.

    Bucket discovery is driven only by `manifest.bucket_listing_ref` (no filesystem enumeration).
    """

    if not isinstance(manifest, MLIndexManifestV1):
        fail("SCHEMA_FAIL")
    if not isinstance(base_dir, Path):
        base_dir = Path(base_dir)

    K = int(manifest.codebook_size_u32)
    if K < 0:
        fail("SCHEMA_FAIL")

    listing_path = verify_artifact_ref_v1(
        artifact_ref=manifest.bucket_listing_ref,
        base_dir=base_dir,
        expected_relpath_prefix="polymath/registry/eudrs_u/",
    )
    listing_payload = gcj1_loads_and_verify_canonical(listing_path.read_bytes())
    if not isinstance(listing_payload, dict):
        fail("SCHEMA_FAIL")
    listing = require_ml_index_bucket_listing_v1(listing_payload)

    pages_by_bucket: dict[int, list[MLIndexPageV1]] = {}
    leaf_hashes_by_bucket: dict[int, list[bytes]] = {}
    for bucket in listing.buckets:
        bucket_id_u32 = int(bucket.bucket_id_u32)
        if bucket_id_u32 < 0 or bucket_id_u32 >= K:
            fail("SCHEMA_FAIL")

        pages: list[MLIndexPageV1] = []
        leafs: list[bytes] = []
        for entry in bucket.pages:
            page_ref = entry.page_ref
            page_path = verify_artifact_ref_v1(
                artifact_ref=page_ref,
                base_dir=base_dir,
                expected_relpath_prefix="polymath/registry/eudrs_u/",
            )
            page_bytes = page_path.read_bytes()
            page = decode_ml_index_page_v1(page_bytes)
            if int(page.bucket_id_u32) != int(bucket_id_u32):
                fail("SCHEMA_FAIL")
            if int(page.page_index_u32) != int(entry.page_index_u32):
                fail("SCHEMA_FAIL")
            if int(page.key_dim_u32) != int(manifest.key_dim_u32):
                fail("SCHEMA_FAIL")
            pages.append(page)
            leafs.append(_sha256_id_to_bytes32(page_ref["artifact_id"]))

        pages_by_bucket[int(bucket_id_u32)] = pages
        leaf_hashes_by_bucket[int(bucket_id_u32)] = leafs

    return pages_by_bucket, leaf_hashes_by_bucket


def verify_ml_index_merkle_roots_v1(
    *,
    manifest: MLIndexManifestV1,
    index_root: MLIndexRootV1,
    leaf_hashes_by_bucket: dict[int, list[bytes]],
) -> None:
    if not isinstance(manifest, MLIndexManifestV1) or not isinstance(index_root, MLIndexRootV1):
        fail("SCHEMA_FAIL")
    K = int(manifest.codebook_size_u32)
    if int(index_root.K_u32) != K:
        fail("SCHEMA_FAIL")
    if int(index_root.fanout_u32) != int(manifest.merkle_fanout_u32):
        fail("SCHEMA_FAIL")
    if not isinstance(leaf_hashes_by_bucket, dict):
        fail("SCHEMA_FAIL")

    for bucket_id in range(K):
        leafs = leaf_hashes_by_bucket.get(int(bucket_id), [])
        if not isinstance(leafs, list):
            fail("SCHEMA_FAIL")
        root = merkle_fanout_v1(leaf_hash32=leafs, fanout_u32=int(manifest.merkle_fanout_u32))
        expected = index_root.bucket_root_hash32[bucket_id]
        if root != expected:
            fail("NONDETERMINISTIC")

def _dot_fn_from_sim_kind(sim_kind: str) -> Callable[[list[int], list[int]], int]:
    sk = str(sim_kind).strip()
    if sk == "DOT_Q32_SHIFT_EACH_DIM_V1":
        return dot_q32_shift_each_dim_v1
    if sk == "DOT_Q32_SHIFT_END_V1":
        return dot_q32_shift_end_v1
    fail("SCHEMA_FAIL")
    return dot_q32_shift_each_dim_v1


def _u32_le(value: int) -> bytes:
    v = int(value)
    if v < 0 or v > 0xFFFFFFFF:
        fail("SCHEMA_FAIL")
    return struct.pack("<I", v & 0xFFFFFFFF)


def _s64_le(value: int) -> bytes:
    try:
        return struct.pack("<q", int(value))
    except Exception:
        fail("SCHEMA_FAIL")
    return b""


def _inv_bytes_for_desc_lex(raw: bytes) -> bytes:
    if not isinstance(raw, (bytes, bytearray, memoryview)):
        fail("SCHEMA_FAIL")
    b = bytes(raw)
    if len(b) != 32:
        fail("SCHEMA_FAIL")
    # Order-reversing mapping for bytes: enables deterministic "desc" via "asc".
    return bytes((x ^ 0xFF) for x in b)


def retrieve_topk_v1(
    *,
    index_manifest_obj: dict,
    codebook_bytes: bytes,
    index_root_bytes: bytes,
    bucket_listing_obj: dict,
    load_page_bytes_by_ref: Callable[[dict[str, str]], bytes],  # (ArtifactRefV1)->bytes
    query_key_q32_s64: list[int],
    top_k_u32: int,
) -> tuple[list[tuple[bytes, bytes, int]], bytes]:
    """Phase 3 deterministic retrieval over listing-addressed pages.

    Returns:
      results: list of (record_hash32, payload_hash32, score_q32_s64)
      retrieval_trace_root32: 32 bytes (SHA256 over canonical retrieval_trace_bytes)
    """

    if not isinstance(index_manifest_obj, dict):
        fail("SCHEMA_FAIL")
    if not isinstance(bucket_listing_obj, dict):
        fail("SCHEMA_FAIL")
    if not callable(load_page_bytes_by_ref):
        fail("SCHEMA_FAIL")
    if not isinstance(query_key_q32_s64, list):
        fail("SCHEMA_FAIL")

    top_k = int(top_k_u32)
    if top_k <= 0:
        fail("SCHEMA_FAIL")

    manifest = require_ml_index_manifest_v1(index_manifest_obj)
    listing = require_ml_index_bucket_listing_v1(bucket_listing_obj)

    # Decode binaries + cross-artifact consistency checks.
    codebook = decode_ml_index_codebook_v1(codebook_bytes)
    if int(codebook.K_u32) != int(manifest.codebook_size_u32):
        fail("SCHEMA_FAIL")
    if int(codebook.d_u32) != int(manifest.key_dim_u32):
        fail("SCHEMA_FAIL")

    index_root = decode_ml_index_root_v1(index_root_bytes)
    if int(index_root.K_u32) != int(manifest.codebook_size_u32):
        fail("SCHEMA_FAIL")
    if int(index_root.fanout_u32) != int(manifest.merkle_fanout_u32):
        fail("SCHEMA_FAIL")

    B = int(manifest.codebook_size_u32)
    if B <= 0:
        fail("SCHEMA_FAIL")

    d = int(manifest.key_dim_u32)
    if len(query_key_q32_s64) != d:
        fail("SCHEMA_FAIL")

    dot_fn = _dot_fn_from_sim_kind(manifest.sim_kind)

    # Materialize bucket->pages mapping (listing already enforces sorted order).
    pages_by_bucket: dict[int, list[MLIndexBucketListingPageV1]] = {}
    for bucket in listing.buckets:
        bucket_id = int(bucket.bucket_id_u32)
        if bucket_id < 0 or bucket_id >= B:
            fail("SCHEMA_FAIL")
        pages_by_bucket[int(bucket_id)] = list(bucket.pages)

    # Bucket selection (TopKDet: score desc, bucket_id asc), then visit in ascending bucket_id.
    V = min(int(manifest.bucket_visit_k_u32), B)
    bucket_scores = [(int(dot_fn(query_key_q32_s64, codebook.vec(bucket_id))), int(bucket_id)) for bucket_id in range(B)]
    selected = topk_det(bucket_scores, V)
    selected_bucket_ids = sorted(int(bucket_id) for _score, bucket_id in selected)

    scan_cap = int(manifest.scan_cap_per_bucket_u32)
    if scan_cap <= 0:
        fail("SCHEMA_FAIL")

    # Scan + maintain global TopK (score desc, record_hash asc).
    # Heap keeps the current "worst" of the kept set at heap[0] via (score asc, record_hash desc).
    heap: list[tuple[int, bytes, bytes, bytes]] = []  # (score, record_hash_inv, record_hash32, payload_hash32)
    scanned_hashes_by_bucket: dict[int, list[bytes]] = {}

    for bucket_id in selected_bucket_ids:
        pages = pages_by_bucket.get(int(bucket_id), [])
        if not isinstance(pages, list):
            fail("SCHEMA_FAIL")

        scanned = 0
        scanned_hashes: list[bytes] = []
        for entry in pages:
            if scanned >= scan_cap:
                break
            if not isinstance(entry, MLIndexBucketListingPageV1):
                fail("SCHEMA_FAIL")

            ref = require_artifact_ref_v1(entry.page_ref)
            page_bytes = load_page_bytes_by_ref(ref)
            mv = _require_bytes_like(page_bytes)

            # Enforce content-addressing: sha256(page_bytes) must match artifact_id.
            actual = f"sha256:{hashlib.sha256(mv.tobytes()).hexdigest()}"
            if actual != ref["artifact_id"]:
                fail("NONDETERMINISTIC")

            page = decode_ml_index_page_v1(mv)
            if int(page.bucket_id_u32) != int(bucket_id):
                fail("SCHEMA_FAIL")
            if int(page.page_index_u32) != int(entry.page_index_u32):
                fail("SCHEMA_FAIL")
            if int(page.key_dim_u32) != d:
                fail("SCHEMA_FAIL")

            for rec in page.records:
                if scanned >= scan_cap:
                    break
                if not isinstance(rec, MLIndexPageRecordV1):
                    fail("SCHEMA_FAIL")
                rh = bytes(rec.record_hash32)
                ph = bytes(rec.payload_hash32)
                if len(rh) != 32 or len(ph) != 32:
                    fail("SCHEMA_FAIL")

                scanned_hashes.append(rh)
                scanned += 1

                score = int(dot_fn(query_key_q32_s64, rec.key_q32))
                item = (int(score), _inv_bytes_for_desc_lex(rh), rh, ph)
                if len(heap) < top_k:
                    heapq.heappush(heap, item)
                else:
                    if item > heap[0]:
                        heapq.heapreplace(heap, item)

        scanned_hashes_by_bucket[int(bucket_id)] = scanned_hashes

    # Final output order: (score desc, record_hash32 asc)
    results: list[tuple[bytes, bytes, int]] = [(rh, ph, int(score)) for score, _rh_inv, rh, ph in heap]
    results.sort(key=lambda row: (-int(row[2]), row[0]))

    # Canonical retrieval trace root (Phase 3).
    query_key_bytes = b"".join(_s64_le(int(v)) for v in query_key_q32_s64)
    query_key_hash32 = hashlib.sha256(query_key_bytes).digest()

    trace = bytearray()
    trace += query_key_hash32

    trace += _u32_le(len(selected_bucket_ids))
    for bid in selected_bucket_ids:
        trace += _u32_le(int(bid))

    for bid in selected_bucket_ids:
        scanned_hashes = scanned_hashes_by_bucket.get(int(bid), [])
        if not isinstance(scanned_hashes, list):
            fail("SCHEMA_FAIL")
        trace += _u32_le(int(bid))
        trace += _u32_le(len(scanned_hashes))
        for rh in scanned_hashes:
            if not isinstance(rh, (bytes, bytearray, memoryview)):
                fail("SCHEMA_FAIL")
            rhb = bytes(rh)
            if len(rhb) != 32:
                fail("SCHEMA_FAIL")
            trace += rhb

    trace += _u32_le(len(results))
    for rh, ph, score in results:
        if not isinstance(rh, (bytes, bytearray, memoryview)) or not isinstance(ph, (bytes, bytearray, memoryview)):
            fail("SCHEMA_FAIL")
        rhb = bytes(rh)
        phb = bytes(ph)
        if len(rhb) != 32 or len(phb) != 32:
            fail("SCHEMA_FAIL")
        trace += rhb
        trace += phb
        trace += _s64_le(int(score))

    retrieval_trace_root32 = hashlib.sha256(bytes(trace)).digest()
    if len(retrieval_trace_root32) != 32:
        fail("SCHEMA_FAIL")
    return results, retrieval_trace_root32


__all__ = [
    "MLIndexBucketListingBucketV1",
    "MLIndexBucketListingPageV1",
    "MLIndexBucketListingV1",
    "MLIndexCodebookV1",
    "MLIndexManifestV1",
    "MLIndexMemGatesV1",
    "MLIndexPageRecordV1",
    "MLIndexPageV1",
    "MLIndexRootV1",
    "SCHEMA_ID_CBK1_U32",
    "SCHEMA_ID_IDXP_U32",
    "SCHEMA_ID_IDX1_U32",
    "VERSION_U32_V1",
    "decode_ml_index_codebook_v1",
    "decode_ml_index_page_v1",
    "decode_ml_index_root_v1",
    "encode_ml_index_codebook_v1",
    "encode_ml_index_page_v1",
    "encode_ml_index_root_v1",
    "load_ml_index_pages_by_bucket_v1",
    "require_ml_index_bucket_listing_v1",
    "require_ml_index_manifest_v1",
    "retrieve_topk_v1",
    "verify_ml_index_merkle_roots_v1",
]
