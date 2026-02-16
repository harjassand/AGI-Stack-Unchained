from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v18_0.eudrs_u.eudrs_u_hash_v1 import gcj1_canon_bytes, sha256_prefixed
from cdel.v18_0.eudrs_u.eudrs_u_merkle_v1 import merkle_fanout_v1
from cdel.v18_0.eudrs_u.mem_gates_v1 import (
    recompute_mem_g1_bucket_balance_metric_q32_v1,
    recompute_mem_g2_anchor_recall_q32_v1,
    verify_mem_gates_v1,
)
from cdel.v18_0.eudrs_u.ml_index_v1 import (
    MLIndexCodebookV1,
    MLIndexPageRecordV1,
    MLIndexPageV1,
    MLIndexRootV1,
    encode_ml_index_codebook_v1,
    encode_ml_index_page_v1,
    load_ml_index_pages_by_bucket_v1,
    require_ml_index_manifest_v1,
    verify_ml_index_merkle_roots_v1,
)
from cdel.v18_0.omega_common_v1 import OmegaV18Error, Q32_ONE, hash_bytes


def _write_hashed_json_v1(*, out_dir: Path, suffix: str, payload: dict) -> tuple[Path, str]:
    raw = gcj1_canon_bytes(payload)
    digest = sha256_prefixed(raw)
    hex64 = digest.split(":", 1)[1]
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"sha256_{hex64}.{suffix}"
    path.write_bytes(raw)
    return path, digest


def _write_bin_artifact(*, base_dir: Path, rel_dir: str, suffix: str, data: bytes) -> dict[str, str]:
    out_dir = base_dir / rel_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    digest = hash_bytes(bytes(data))
    hex64 = digest.split(":", 1)[1]
    name = f"sha256_{hex64}.{suffix}"
    path = out_dir / name
    path.write_bytes(bytes(data))
    relpath = path.relative_to(base_dir).as_posix()
    return {"artifact_id": digest, "artifact_relpath": relpath}


def test_bucket_listing_root_mismatch_rejects(tmp_path: Path) -> None:
    base_dir = tmp_path / "staged_registry_tree"
    base_dir.mkdir(parents=True, exist_ok=True)

    # Two buckets, one page each.
    rec0 = MLIndexPageRecordV1(record_hash32=b"\x01" * 32, payload_hash32=b"\xaa" * 32, key_q32=[0, 0])
    page0 = MLIndexPageV1(bucket_id_u32=0, page_index_u32=0, key_dim_u32=2, records=[rec0])
    page0_ref = _write_bin_artifact(
        base_dir=base_dir,
        rel_dir="polymath/registry/eudrs_u/indices/buckets/0/pages",
        suffix="ml_index_page_v1.bin",
        data=encode_ml_index_page_v1(page0),
    )

    rec1 = MLIndexPageRecordV1(record_hash32=b"\x02" * 32, payload_hash32=b"\xbb" * 32, key_q32=[0, 0])
    page1 = MLIndexPageV1(bucket_id_u32=1, page_index_u32=0, key_dim_u32=2, records=[rec1])
    page1_ref = _write_bin_artifact(
        base_dir=base_dir,
        rel_dir="polymath/registry/eudrs_u/indices/buckets/1/pages",
        suffix="ml_index_page_v1.bin",
        data=encode_ml_index_page_v1(page1),
    )

    bucket_listing_payload = {
        "schema_id": "ml_index_bucket_listing_v1",
        "index_manifest_id": "sha256:" + ("11" * 32),
        "buckets": [
            {"bucket_id_u32": 0, "pages": [{"page_index_u32": 0, "page_ref": page0_ref}]},
            {"bucket_id_u32": 1, "pages": [{"page_index_u32": 0, "page_ref": page1_ref}]},
        ],
    }
    listing_path, listing_digest = _write_hashed_json_v1(
        out_dir=base_dir / "polymath/registry/eudrs_u/indices",
        suffix="ml_index_bucket_listing_v1.json",
        payload=bucket_listing_payload,
    )
    listing_ref = {"artifact_id": listing_digest, "artifact_relpath": listing_path.relative_to(base_dir).as_posix()}

    manifest_payload = {
        "schema_id": "ml_index_manifest_v1",
        "index_kind": "ML_INDEX_V1",
        "opset_id": "opset:eudrs_u_v1:sha256:" + ("00" * 32),
        "key_dim_u32": 2,
        "codebook_size_u32": 2,
        "bucket_visit_k_u32": 1,
        "scan_cap_per_bucket_u32": 1,
        "merkle_fanout_u32": 2,
        "sim_kind": "DOT_Q32_SHIFT_END_V1",
        "codebook_ref": {"artifact_id": "sha256:" + ("00" * 32), "artifact_relpath": "x.bin"},
        "index_root_ref": {"artifact_id": "sha256:" + ("00" * 32), "artifact_relpath": "y.bin"},
        "bucket_listing_ref": listing_ref,
        "mem_gates": {
            "mem_g1_bucket_balance_max_q32": {"q": (1 << 63) - 1},
            "mem_g2_anchor_recall_min_q32": {"q": 0},
        },
    }
    manifest = require_ml_index_manifest_v1(manifest_payload)

    _pages_by_bucket, leaf_hashes_by_bucket = load_ml_index_pages_by_bucket_v1(base_dir=base_dir, manifest=manifest)

    # Compute correct roots, then corrupt bucket 1 expected root.
    root0 = merkle_fanout_v1(leaf_hash32=leaf_hashes_by_bucket.get(0, []), fanout_u32=2)
    root1_good = merkle_fanout_v1(leaf_hash32=leaf_hashes_by_bucket.get(1, []), fanout_u32=2)
    assert root1_good != (b"\x99" * 32)
    index_root = MLIndexRootV1(K_u32=2, fanout_u32=2, bucket_root_hash32=[root0, b"\x99" * 32])

    with pytest.raises(OmegaV18Error):
        verify_ml_index_merkle_roots_v1(manifest=manifest, index_root=index_root, leaf_hashes_by_bucket=leaf_hashes_by_bucket)


def test_mem_g1_and_mem_g2_golden_fixtures() -> None:
    # Synthetic 2-bucket index with known record distribution:
    # bucket0 has 3 records, bucket1 has 1 record => T=4, max_n=3, B=2
    # MEM-G1 metric = floor((max_n<<32)*B/T) = floor((3<<32)*2/4) = 1.5 in Q32.
    codebook = MLIndexCodebookV1(K_u32=2, d_u32=1, C_q32=[0, 0])
    codebook_bytes = encode_ml_index_codebook_v1(codebook)

    index_root = MLIndexRootV1(K_u32=2, fanout_u32=2, bucket_root_hash32=[b"\x00" * 32, b"\x00" * 32])
    # Index root bytes are only used for format + header consistency checks in retrieval/gates.
    from cdel.v18_0.eudrs_u.ml_index_v1 import encode_ml_index_root_v1

    index_root_bytes = encode_ml_index_root_v1(index_root)

    r0 = MLIndexPageRecordV1(record_hash32=b"\x01" * 32, payload_hash32=b"\xa1" * 32, key_q32=[0])
    r1 = MLIndexPageRecordV1(record_hash32=b"\x02" * 32, payload_hash32=b"\xa2" * 32, key_q32=[0])
    r2 = MLIndexPageRecordV1(record_hash32=b"\x03" * 32, payload_hash32=b"\xa3" * 32, key_q32=[0])
    page0 = MLIndexPageV1(bucket_id_u32=0, page_index_u32=0, key_dim_u32=1, records=[r0, r1, r2])
    page0_bytes = encode_ml_index_page_v1(page0)
    page0_id = hash_bytes(page0_bytes)

    r3 = MLIndexPageRecordV1(record_hash32=b"\x10" * 32, payload_hash32=b"\xb0" * 32, key_q32=[0])
    page1 = MLIndexPageV1(bucket_id_u32=1, page_index_u32=0, key_dim_u32=1, records=[r3])
    page1_bytes = encode_ml_index_page_v1(page1)
    page1_id = hash_bytes(page1_bytes)

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
        "scan_cap_per_bucket_u32": 100,
        "merkle_fanout_u32": 2,
        "sim_kind": "DOT_Q32_SHIFT_END_V1",
        "codebook_ref": {"artifact_id": hash_bytes(codebook_bytes), "artifact_relpath": "cbk.bin"},
        "index_root_ref": {"artifact_id": hash_bytes(index_root_bytes), "artifact_relpath": "idx.bin"},
        "bucket_listing_ref": {"artifact_id": "sha256:" + ("00" * 32), "artifact_relpath": "listing.json"},
        "mem_gates": {
            "mem_g1_bucket_balance_max_q32": {"q": 6442450944},  # exactly 1.5 in Q32
            "mem_g2_anchor_recall_min_q32": {"q": 1 * Q32_ONE},  # require perfect recall in this tiny index
        },
    }

    listing_obj = {
        "schema_id": "ml_index_bucket_listing_v1",
        "index_manifest_id": "sha256:" + ("11" * 32),
        "buckets": [
            {"bucket_id_u32": 0, "pages": [{"page_index_u32": 0, "page_ref": {"artifact_id": page0_id, "artifact_relpath": "p0.bin"}}]},
            {"bucket_id_u32": 1, "pages": [{"page_index_u32": 0, "page_ref": {"artifact_id": page1_id, "artifact_relpath": "p1.bin"}}]},
        ],
    }

    metric_q32, max_n, B, T = recompute_mem_g1_bucket_balance_metric_q32_v1(
        index_manifest_obj=manifest_obj,
        bucket_listing_obj=listing_obj,
        load_page_bytes_by_ref=_load_page_bytes_by_ref,
    )
    assert (metric_q32, max_n, B, T) == (6442450944, 3, 2, 4)

    recall_q32, hits, A = recompute_mem_g2_anchor_recall_q32_v1(
        index_manifest_obj=manifest_obj,
        codebook_bytes=codebook_bytes,
        index_root_bytes=index_root_bytes,
        bucket_listing_obj=listing_obj,
        load_page_bytes_by_ref=_load_page_bytes_by_ref,
    )
    assert (recall_q32, hits, A) == (1 * Q32_ONE, 4, 4)

    g1_q32, g2_q32 = verify_mem_gates_v1(
        index_manifest_obj=manifest_obj,
        codebook_bytes=codebook_bytes,
        index_root_bytes=index_root_bytes,
        bucket_listing_obj=listing_obj,
        load_page_bytes_by_ref=_load_page_bytes_by_ref,
    )
    assert (g1_q32, g2_q32) == (6442450944, 1 * Q32_ONE)

    # MEM-G1 fail (tighten cap by 1).
    bad_g1 = dict(manifest_obj)
    bad_g1["mem_gates"] = {
        "mem_g1_bucket_balance_max_q32": {"q": 6442450943},
        "mem_g2_anchor_recall_min_q32": {"q": 0},
    }
    with pytest.raises(OmegaV18Error):
        verify_mem_gates_v1(
            index_manifest_obj=bad_g1,
            codebook_bytes=codebook_bytes,
            index_root_bytes=index_root_bytes,
            bucket_listing_obj=listing_obj,
            load_page_bytes_by_ref=_load_page_bytes_by_ref,
        )

    # MEM-G2 fail (require > 1.0 recall).
    bad_g2 = dict(manifest_obj)
    bad_g2["mem_gates"] = {
        "mem_g1_bucket_balance_max_q32": {"q": (1 << 63) - 1},
        "mem_g2_anchor_recall_min_q32": {"q": (1 * Q32_ONE) + 1},
    }
    with pytest.raises(OmegaV18Error):
        verify_mem_gates_v1(
            index_manifest_obj=bad_g2,
            codebook_bytes=codebook_bytes,
            index_root_bytes=index_root_bytes,
            bucket_listing_obj=listing_obj,
            load_page_bytes_by_ref=_load_page_bytes_by_ref,
        )

