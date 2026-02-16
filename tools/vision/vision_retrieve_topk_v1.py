"""Deterministic ML-index retrieval tool for Vision Stage 2 (v1).

This is a developer tool (NOT a verifier). It:
  - loads a vision_item_listing_v1 + ml_index_manifest_v1 bundle
  - computes a query key from a vision_item_descriptor_v1
  - runs RE2 retrieve_topk_v1 and prints resolved descriptor relpaths
  - optionally writes a GCJ-1 canonical retrieval report
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from cdel.v18_0.eudrs_u.eudrs_u_artifact_refs_v1 import require_artifact_ref_v1, require_safe_relpath_v1, verify_artifact_ref_v1
from cdel.v18_0.eudrs_u.eudrs_u_hash_v1 import gcj1_canon_bytes, gcj1_loads_and_verify_canonical, sha256_prefixed
from cdel.v18_0.eudrs_u.ml_index_v1 import retrieve_topk_v1
from cdel.v18_0.eudrs_u.vision_items_v1 import compute_item_embedding_key_q32_s64_v1, parse_vision_embedding_config_v1
from cdel.v18_0.omega_common_v1 import fail, require_no_absolute_paths, validate_schema


def _resolve_staged_root(state_dir: Path) -> Path:
    root = Path(state_dir).resolve()
    staged = root / "eudrs_u" / "staged_registry_tree"
    if staged.exists() and staged.is_dir():
        return staged.resolve()
    return root


def _load_canon_obj(path: Path, *, expected_schema_id: str) -> dict[str, Any]:
    raw = path.read_bytes()
    obj = gcj1_loads_and_verify_canonical(raw)
    if not isinstance(obj, dict):
        fail("SCHEMA_FAIL")
    require_no_absolute_paths(obj)
    if str(obj.get("schema_id", "")).strip() != expected_schema_id:
        fail("SCHEMA_FAIL")
    try:
        validate_schema(obj, expected_schema_id)
    except Exception:  # noqa: BLE001
        fail("SCHEMA_FAIL")
    return dict(obj)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vision_retrieve_topk_v1")
    parser.add_argument("--state_dir", required=True)
    parser.add_argument("--item_listing_relpath", required=True)
    parser.add_argument("--index_manifest_relpath", required=True)
    parser.add_argument("--query_descriptor_relpath", required=True)
    parser.add_argument("--top_k_u32", type=int, default=10)
    parser.add_argument("--out_report_path")
    args = parser.parse_args(argv)

    state_dir = Path(args.state_dir).resolve()
    staged_root = _resolve_staged_root(state_dir)

    listing_rel = require_safe_relpath_v1(str(args.item_listing_relpath), reason="SCHEMA_FAIL")
    index_rel = require_safe_relpath_v1(str(args.index_manifest_relpath), reason="SCHEMA_FAIL")
    query_rel = require_safe_relpath_v1(str(args.query_descriptor_relpath), reason="SCHEMA_FAIL")

    listing_path = (staged_root / listing_rel).resolve()
    index_path = (staged_root / index_rel).resolve()
    query_path = (staged_root / query_rel).resolve()
    for p in (listing_path, index_path, query_path):
        if not p.exists() or not p.is_file():
            fail("MISSING_STATE_INPUT")

    listing_obj = _load_canon_obj(listing_path, expected_schema_id="vision_item_listing_v1")
    index_obj = _load_canon_obj(index_path, expected_schema_id="ml_index_manifest_v1")

    # Build id -> relpath table for result resolution.
    id_to_rel: dict[str, str] = {}
    for row in list(listing_obj.get("items", [])):
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        ref = require_artifact_ref_v1(row.get("item_ref"), reason="SCHEMA_FAIL")
        id_to_rel[str(ref["artifact_id"])] = str(ref["artifact_relpath"])

    # Load query descriptor and compute query key deterministically.
    desc_obj = _load_canon_obj(query_path, expected_schema_id="vision_item_descriptor_v1")
    embed_ref = require_artifact_ref_v1(desc_obj.get("embedding_config_ref"), reason="SCHEMA_FAIL")
    embed_path = verify_artifact_ref_v1(
        artifact_ref=embed_ref,
        base_dir=staged_root,
        expected_relpath_prefix="polymath/registry/eudrs_u/vision/embed_configs/",
    )
    embed_obj = _load_canon_obj(embed_path, expected_schema_id="vision_embedding_config_v1")
    embed_cfg = parse_vision_embedding_config_v1(embed_obj)
    query_key = compute_item_embedding_key_q32_s64_v1(base_dir=staged_root, item_desc_obj=desc_obj, embed_cfg=embed_cfg)

    # Load ML-index bundle assets.
    codebook_ref = require_artifact_ref_v1(index_obj.get("codebook_ref"), reason="SCHEMA_FAIL")
    index_root_ref = require_artifact_ref_v1(index_obj.get("index_root_ref"), reason="SCHEMA_FAIL")
    bucket_listing_ref = require_artifact_ref_v1(index_obj.get("bucket_listing_ref"), reason="SCHEMA_FAIL")
    codebook_bytes = verify_artifact_ref_v1(artifact_ref=codebook_ref, base_dir=staged_root).read_bytes()
    index_root_bytes = verify_artifact_ref_v1(artifact_ref=index_root_ref, base_dir=staged_root).read_bytes()
    bucket_listing_obj = _load_canon_obj(
        verify_artifact_ref_v1(artifact_ref=bucket_listing_ref, base_dir=staged_root),
        expected_schema_id="ml_index_bucket_listing_v1",
    )

    def _load_page_bytes_by_ref(ref: dict[str, str]) -> bytes:
        # Retrieval is deterministic only if page bytes are content-addressed and stable.
        path = verify_artifact_ref_v1(artifact_ref=ref, base_dir=staged_root)
        return path.read_bytes()

    results, trace_root32 = retrieve_topk_v1(
        index_manifest_obj=index_obj,
        codebook_bytes=codebook_bytes,
        index_root_bytes=index_root_bytes,
        bucket_listing_obj=bucket_listing_obj,
        load_page_bytes_by_ref=_load_page_bytes_by_ref,
        query_key_q32_s64=list(query_key),
        top_k_u32=int(args.top_k_u32),
    )

    result_rows: list[dict[str, Any]] = []
    for rank, (rh32, ph32, score) in enumerate(results):
        rid = "sha256:" + bytes(rh32).hex()
        rel = id_to_rel.get(rid, "<missing from listing>")
        provenance: dict[str, Any] = {}
        if rel != "<missing from listing>":
            desc_path = (staged_root / rel).resolve()
            if desc_path.exists() and desc_path.is_file():
                desc_obj = _load_canon_obj(desc_path, expected_schema_id="vision_item_descriptor_v1")
                provenance = {
                    "session_manifest_id": str(desc_obj["session_manifest_ref"]["artifact_id"]),
                    "frame_manifest_id": str(desc_obj["frame_manifest_ref"]["artifact_id"]),
                    "frame_index_u32": int(desc_obj["frame_index_u32"]),
                    "perception_run_id": str(desc_obj["perception_run_ref"]["artifact_id"]),
                    "frame_report_id": str(desc_obj["frame_report_ref"]["artifact_id"]),
                    "qxwmr_state_id": str(desc_obj["qxwmr_state_ref"]["artifact_id"]),
                    "track_id_u32": int(desc_obj["track_id_u32"]),
                    "obj_local_id_u32": int(desc_obj["obj_local_id_u32"]),
                }

        if provenance:
            sys.stdout.write(
                f"{rank:03d} score_q32_s64={int(score)} record_id={rid} relpath={rel} "
                f"session_id={provenance['session_manifest_id']} frame={int(provenance['frame_index_u32'])} "
                f"track={int(provenance['track_id_u32'])} obj={int(provenance['obj_local_id_u32'])}\n"
            )
        else:
            sys.stdout.write(f"{rank:03d} score_q32_s64={int(score)} record_id={rid} relpath={rel}\n")

        result_rows.append(
            {
                "record_id": rid,
                "payload_id": "sha256:" + bytes(ph32).hex(),
                "score_q32_s64": int(score),
                "item_relpath": str(id_to_rel.get(rid, "")),
                "provenance": dict(provenance),
            }
        )

    out_report_path = str(args.out_report_path).strip() if args.out_report_path is not None else ""
    if out_report_path:
        report_path = Path(out_report_path).resolve()
        report_obj = {
            "schema_id": "vision_retrieval_report_v1",
            "state_dir_rel": require_safe_relpath_v1(report_path.relative_to(Path.cwd().resolve()).as_posix(), reason="SCHEMA_FAIL")
            if str(report_path).startswith(str(Path.cwd().resolve()))
            else report_path.name,
            "item_listing_ref": {"artifact_id": sha256_prefixed(listing_path.read_bytes()), "artifact_relpath": listing_rel},
            "index_manifest_ref": {"artifact_id": sha256_prefixed(index_path.read_bytes()), "artifact_relpath": index_rel},
            "query_descriptor_ref": {"artifact_id": sha256_prefixed(query_path.read_bytes()), "artifact_relpath": query_rel},
            "top_k_u32": int(args.top_k_u32),
            "retrieval_trace_root32": "sha256:" + bytes(trace_root32).hex(),
            "results": list(result_rows),
        }
        require_no_absolute_paths(report_obj)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_bytes(gcj1_canon_bytes(report_obj))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
