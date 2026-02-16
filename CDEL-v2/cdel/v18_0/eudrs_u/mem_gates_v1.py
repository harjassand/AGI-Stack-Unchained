"""MEM gate recomputation for ML-Index v1 (Phase 3).

This module is RE2: deterministic and fail-closed.
"""

from __future__ import annotations

import hashlib
import heapq
from typing import Callable

from ..omega_common_v1 import fail
from .eudrs_u_artifact_refs_v1 import require_artifact_ref_v1
from .ml_index_v1 import (
    decode_ml_index_page_v1,
    require_ml_index_bucket_listing_v1,
    require_ml_index_manifest_v1,
    retrieve_topk_v1,
)


ANCHOR_SUITE_MAX_V1 = 256
ANCHOR_RECALL_K_V1 = 10


def _load_page_bytes_checked(*, page_ref: dict[str, str], load_page_bytes_by_ref: Callable[[dict[str, str]], bytes]) -> bytes:
    ref = require_artifact_ref_v1(page_ref)
    raw = load_page_bytes_by_ref(ref)
    if not isinstance(raw, (bytes, bytearray, memoryview)):
        fail("SCHEMA_FAIL")
    b = bytes(raw)
    digest = f"sha256:{hashlib.sha256(b).hexdigest()}"
    if digest != ref["artifact_id"]:
        fail("NONDETERMINISTIC")
    return b


def recompute_mem_g1_bucket_balance_metric_q32_v1(
    *,
    index_manifest_obj: dict,
    bucket_listing_obj: dict,
    load_page_bytes_by_ref: Callable[[dict[str, str]], bytes],
) -> tuple[int, int, int, int]:
    """Return (metric_q32, max_n, B, T) for MEM-G1."""

    if not isinstance(index_manifest_obj, dict) or not isinstance(bucket_listing_obj, dict) or not callable(load_page_bytes_by_ref):
        fail("SCHEMA_FAIL")

    manifest = require_ml_index_manifest_v1(index_manifest_obj)
    listing = require_ml_index_bucket_listing_v1(bucket_listing_obj)

    B = int(manifest.codebook_size_u32)
    if B <= 0:
        fail("SCHEMA_FAIL")

    counts = [0 for _ in range(B)]
    for bucket in listing.buckets:
        bucket_id = int(bucket.bucket_id_u32)
        if bucket_id < 0 or bucket_id >= B:
            fail("SCHEMA_FAIL")
        for entry in bucket.pages:
            page_bytes = _load_page_bytes_checked(page_ref=entry.page_ref, load_page_bytes_by_ref=load_page_bytes_by_ref)
            page = decode_ml_index_page_v1(page_bytes)
            if int(page.bucket_id_u32) != int(bucket_id):
                fail("SCHEMA_FAIL")
            if int(page.page_index_u32) != int(entry.page_index_u32):
                fail("SCHEMA_FAIL")
            if int(page.key_dim_u32) != int(manifest.key_dim_u32):
                fail("SCHEMA_FAIL")
            counts[bucket_id] += len(page.records)

    T = int(sum(int(v) for v in counts))
    max_n = int(max(int(v) for v in counts)) if counts else 0

    if T == 0:
        metric_q32 = (1 << 63) - 1
    else:
        metric_q32 = ((int(max_n) << 32) * int(B)) // int(T)
        if metric_q32 < 0 or metric_q32 > (1 << 63) - 1:
            fail("SCHEMA_FAIL")

    return int(metric_q32), int(max_n), int(B), int(T)


def verify_mem_g1_bucket_balance_v1(
    *,
    index_manifest_obj: dict,
    bucket_listing_obj: dict,
    load_page_bytes_by_ref: Callable[[dict[str, str]], bytes],
) -> int:
    """Fail-closed MEM-G1 verification.

    Returns metric_q32 on pass.
    """

    metric_q32, _max_n, _B, T = recompute_mem_g1_bucket_balance_metric_q32_v1(
        index_manifest_obj=index_manifest_obj,
        bucket_listing_obj=bucket_listing_obj,
        load_page_bytes_by_ref=load_page_bytes_by_ref,
    )
    if int(T) == 0:
        fail("MEM_G1_REJECT")

    manifest = require_ml_index_manifest_v1(index_manifest_obj)
    cap = int(manifest.mem_gates.mem_g1_bucket_balance_max_q32)
    if int(metric_q32) > cap:
        fail("MEM_G1_REJECT")
    return int(metric_q32)


def recompute_mem_g2_anchor_recall_q32_v1(
    *,
    index_manifest_obj: dict,
    codebook_bytes: bytes,
    index_root_bytes: bytes,
    bucket_listing_obj: dict,
    load_page_bytes_by_ref: Callable[[dict[str, str]], bytes],
) -> tuple[int, int, int]:
    """Return (recall_q32, hits, A) for MEM-G2."""

    if (
        not isinstance(index_manifest_obj, dict)
        or not isinstance(bucket_listing_obj, dict)
        or not callable(load_page_bytes_by_ref)
    ):
        fail("SCHEMA_FAIL")

    manifest = require_ml_index_manifest_v1(index_manifest_obj)
    listing = require_ml_index_bucket_listing_v1(bucket_listing_obj)

    B = int(manifest.codebook_size_u32)
    if B <= 0:
        fail("SCHEMA_FAIL")

    # Cache page bytes so anchor suite construction + repeated retrievals are deterministic and efficient.
    cache: dict[str, bytes] = {}

    def _load_cached(ref: dict[str, str]) -> bytes:
        rid = str(ref.get("artifact_id", "")).strip()
        if not rid:
            fail("SCHEMA_FAIL")
        hit = cache.get(rid)
        if hit is not None:
            return hit
        b = _load_page_bytes_checked(page_ref=ref, load_page_bytes_by_ref=load_page_bytes_by_ref)
        cache[rid] = b
        return b

    # Collect smallest record_hash32 anchors (A_MAX=256) from the index content.
    T = 0
    anchors_heap: list[tuple[bytes, bytes, list[int]]] = []  # max-heap via inverted record_hash

    for bucket in listing.buckets:
        bucket_id = int(bucket.bucket_id_u32)
        if bucket_id < 0 or bucket_id >= B:
            fail("SCHEMA_FAIL")
        for entry in bucket.pages:
            page = decode_ml_index_page_v1(_load_cached(entry.page_ref))
            if int(page.bucket_id_u32) != int(bucket_id):
                fail("SCHEMA_FAIL")
            if int(page.page_index_u32) != int(entry.page_index_u32):
                fail("SCHEMA_FAIL")
            if int(page.key_dim_u32) != int(manifest.key_dim_u32):
                fail("SCHEMA_FAIL")
            for rec in page.records:
                T += 1
                rh = bytes(rec.record_hash32)
                ph = bytes(rec.payload_hash32)
                key = [int(v) for v in rec.key_q32]
                if len(rh) != 32 or len(ph) != 32:
                    fail("SCHEMA_FAIL")
                # Maintain the A_MAX smallest record_hash32 values deterministically.
                inv = bytes((b ^ 0xFF) for b in rh)  # order-reversing
                item = (inv, rh, ph, key)
                if len(anchors_heap) < ANCHOR_SUITE_MAX_V1:
                    heapq.heappush(anchors_heap, item)
                else:
                    # anchors_heap is a min-heap on `inv` -> keeps largest original rh at [0].
                    if item > anchors_heap[0]:
                        heapq.heapreplace(anchors_heap, item)

    A = min(int(ANCHOR_SUITE_MAX_V1), int(T))
    if A <= 0:
        return 0, 0, 0

    anchors = [(rh, ph, key) for _inv, rh, ph, key in anchors_heap]
    anchors.sort(key=lambda row: row[0])
    anchors = anchors[:A]

    hits = 0
    for rh, _ph, key in anchors:
        results, _trace_root32 = retrieve_topk_v1(
            index_manifest_obj=index_manifest_obj,
            codebook_bytes=codebook_bytes,
            index_root_bytes=index_root_bytes,
            bucket_listing_obj=bucket_listing_obj,
            load_page_bytes_by_ref=_load_cached,
            query_key_q32_s64=key,
            top_k_u32=int(ANCHOR_RECALL_K_V1),
        )
        if any(bytes(out_rh) == bytes(rh) for out_rh, _out_ph, _score in results):
            hits += 1

    recall_q32 = (int(hits) << 32) // int(A)
    return int(recall_q32), int(hits), int(A)


def verify_mem_g2_anchor_recall_v1(
    *,
    index_manifest_obj: dict,
    codebook_bytes: bytes,
    index_root_bytes: bytes,
    bucket_listing_obj: dict,
    load_page_bytes_by_ref: Callable[[dict[str, str]], bytes],
) -> int:
    """Fail-closed MEM-G2 verification.

    Returns recall_q32 on pass.
    """

    recall_q32, _hits, _A = recompute_mem_g2_anchor_recall_q32_v1(
        index_manifest_obj=index_manifest_obj,
        codebook_bytes=codebook_bytes,
        index_root_bytes=index_root_bytes,
        bucket_listing_obj=bucket_listing_obj,
        load_page_bytes_by_ref=load_page_bytes_by_ref,
    )
    manifest = require_ml_index_manifest_v1(index_manifest_obj)
    floor_q32 = int(manifest.mem_gates.mem_g2_anchor_recall_min_q32)
    if int(recall_q32) < floor_q32:
        fail("MEM_G2_REJECT")
    return int(recall_q32)


def verify_mem_gates_v1(
    *,
    index_manifest_obj: dict,
    codebook_bytes: bytes,
    index_root_bytes: bytes,
    bucket_listing_obj: dict,
    load_page_bytes_by_ref: Callable[[dict[str, str]], bytes],
) -> tuple[int, int]:
    """Verify MEM-G1 and MEM-G2; returns (mem_g1_metric_q32, mem_g2_recall_q32)."""

    g1 = verify_mem_g1_bucket_balance_v1(
        index_manifest_obj=index_manifest_obj,
        bucket_listing_obj=bucket_listing_obj,
        load_page_bytes_by_ref=load_page_bytes_by_ref,
    )
    g2 = verify_mem_g2_anchor_recall_v1(
        index_manifest_obj=index_manifest_obj,
        codebook_bytes=codebook_bytes,
        index_root_bytes=index_root_bytes,
        bucket_listing_obj=bucket_listing_obj,
        load_page_bytes_by_ref=load_page_bytes_by_ref,
    )
    return int(g1), int(g2)


__all__ = [
    "ANCHOR_RECALL_K_V1",
    "ANCHOR_SUITE_MAX_V1",
    "recompute_mem_g1_bucket_balance_metric_q32_v1",
    "recompute_mem_g2_anchor_recall_q32_v1",
    "verify_mem_g1_bucket_balance_v1",
    "verify_mem_g2_anchor_recall_v1",
    "verify_mem_gates_v1",
]

