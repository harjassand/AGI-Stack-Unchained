from __future__ import annotations

import struct

import pytest

from cdel.v18_0.eudrs_u.ml_index_v1 import (
    MLIndexCodebookV1,
    MLIndexPageRecordV1,
    MLIndexPageV1,
    MLIndexRootV1,
    SCHEMA_ID_IDXP_U32,
    VERSION_U32_V1,
    decode_ml_index_codebook_v1,
    decode_ml_index_page_v1,
    encode_ml_index_codebook_v1,
    encode_ml_index_page_v1,
    encode_ml_index_root_v1,
    retrieve_topk_v1,
)
from cdel.v18_0.omega_common_v1 import OmegaV18Error, Q32_ONE, hash_bytes


def test_codebook_roundtrip() -> None:
    codebook = MLIndexCodebookV1(K_u32=2, d_u32=1, C_q32=[1 * Q32_ONE, -1 * Q32_ONE])
    raw = encode_ml_index_codebook_v1(codebook)
    dec = decode_ml_index_codebook_v1(raw)
    assert dec == codebook


def test_decode_page_rejects_unsorted_record_hashes() -> None:
    # Build a minimal page with 2 records; make record_hash32 descending to trigger reject.
    key_dim = 1
    rec_size = 64 + key_dim * 8

    header = struct.pack(
        "<IIIIIII",
        int(SCHEMA_ID_IDXP_U32) & 0xFFFFFFFF,
        int(VERSION_U32_V1) & 0xFFFFFFFF,
        0,  # bucket_id
        0,  # page_index
        2,  # record_count
        key_dim,
        0,
    )

    rec0 = (b"\x02" * 32) + (b"\x00" * 32) + struct.pack("<q", 0)
    rec1 = (b"\x01" * 32) + (b"\x00" * 32) + struct.pack("<q", 0)
    assert len(rec0) == rec_size
    assert len(rec1) == rec_size
    raw = header + rec0 + rec1
    with pytest.raises(OmegaV18Error):
        decode_ml_index_page_v1(raw)


def test_retrieve_topk_is_deterministic_and_emits_trace_root32() -> None:
    # Build a small index that forces output tie-breaks by record_hash32.
    codebook = MLIndexCodebookV1(K_u32=2, d_u32=1, C_q32=[0, 0])
    codebook_bytes = encode_ml_index_codebook_v1(codebook)

    index_root = MLIndexRootV1(K_u32=2, fanout_u32=2, bucket_root_hash32=[b"\x00" * 32, b"\x00" * 32])
    index_root_bytes = encode_ml_index_root_v1(index_root)

    rec_hi = MLIndexPageRecordV1(record_hash32=b"\x05" * 32, payload_hash32=b"\xa0" * 32, key_q32=[2 * Q32_ONE])
    rec_a = MLIndexPageRecordV1(record_hash32=b"\x10" * 32, payload_hash32=b"\xaa" * 32, key_q32=[1 * Q32_ONE])
    rec_b = MLIndexPageRecordV1(record_hash32=b"\x20" * 32, payload_hash32=b"\xbb" * 32, key_q32=[1 * Q32_ONE])
    page0 = MLIndexPageV1(bucket_id_u32=0, page_index_u32=0, key_dim_u32=1, records=[rec_hi, rec_a, rec_b])
    page0_bytes = encode_ml_index_page_v1(page0)
    page0_id = hash_bytes(page0_bytes)
    page0_ref = {"artifact_id": page0_id, "artifact_relpath": "p0.bin"}

    rec_c = MLIndexPageRecordV1(record_hash32=b"\x15" * 32, payload_hash32=b"\xcc" * 32, key_q32=[1 * Q32_ONE])
    page1 = MLIndexPageV1(bucket_id_u32=1, page_index_u32=0, key_dim_u32=1, records=[rec_c])
    page1_bytes = encode_ml_index_page_v1(page1)
    page1_id = hash_bytes(page1_bytes)
    page1_ref = {"artifact_id": page1_id, "artifact_relpath": "p1.bin"}

    page_bytes_by_id = {page0_id: page0_bytes, page1_id: page1_bytes}

    def _load_page_bytes_by_ref(ref: dict[str, str]) -> bytes:
        return page_bytes_by_id[ref["artifact_id"]]

    manifest_obj = {
        "schema_id": "ml_index_manifest_v1",
        "index_kind": "ML_INDEX_V1",
        "opset_id": "opset:eudrs_u_v1:sha256:" + ("00" * 32),
        "key_dim_u32": 1,
        "codebook_size_u32": 2,
        "bucket_visit_k_u32": 2,
        "scan_cap_per_bucket_u32": 10,
        "merkle_fanout_u32": 2,
        "sim_kind": "DOT_Q32_SHIFT_EACH_DIM_V1",
        "codebook_ref": {"artifact_id": hash_bytes(codebook_bytes), "artifact_relpath": "cbk.bin"},
        "index_root_ref": {"artifact_id": hash_bytes(index_root_bytes), "artifact_relpath": "idx.bin"},
        "bucket_listing_ref": {"artifact_id": "sha256:" + ("00" * 32), "artifact_relpath": "listing.json"},
        "mem_gates": {
            "mem_g1_bucket_balance_max_q32": {"q": (1 << 63) - 1},
            "mem_g2_anchor_recall_min_q32": {"q": 0},
        },
    }

    bucket_listing_obj = {
        "schema_id": "ml_index_bucket_listing_v1",
        "index_manifest_id": "sha256:" + ("11" * 32),
        "buckets": [
            {"bucket_id_u32": 0, "pages": [{"page_index_u32": 0, "page_ref": page0_ref}]},
            {"bucket_id_u32": 1, "pages": [{"page_index_u32": 0, "page_ref": page1_ref}]},
        ],
    }

    expected = [
        (rec_hi.record_hash32, rec_hi.payload_hash32, 2 * Q32_ONE),
        (rec_a.record_hash32, rec_a.payload_hash32, 1 * Q32_ONE),
        (rec_c.record_hash32, rec_c.payload_hash32, 1 * Q32_ONE),
    ]

    out1, trace1 = retrieve_topk_v1(
        index_manifest_obj=manifest_obj,
        codebook_bytes=codebook_bytes,
        index_root_bytes=index_root_bytes,
        bucket_listing_obj=bucket_listing_obj,
        load_page_bytes_by_ref=_load_page_bytes_by_ref,
        query_key_q32_s64=[1 * Q32_ONE],
        top_k_u32=3,
    )
    out2, trace2 = retrieve_topk_v1(
        index_manifest_obj=manifest_obj,
        codebook_bytes=codebook_bytes,
        index_root_bytes=index_root_bytes,
        bucket_listing_obj=bucket_listing_obj,
        load_page_bytes_by_ref=_load_page_bytes_by_ref,
        query_key_q32_s64=[1 * Q32_ONE],
        top_k_u32=3,
    )

    assert out1 == expected
    assert out1 == out2
    assert trace1 == trace2
    assert len(trace1) == 32

    # Pinned determinism check: update only with a spec change.
    assert trace1.hex() == "f0846cee26199dc83747d74d94615c7bd6731091ae67c99f118c40641829a39d"
