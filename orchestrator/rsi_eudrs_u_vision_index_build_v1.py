"""Omega-dispatchable EUDRS-U producer: vision index build (Stage 2) v1.

This producer is untrusted (RE3). It MUST only emit content-addressed artifacts
under a staged registry tree and rely on RE2 fail-closed verification.

Authoritative Stage-2 verification lives in RE2:
  cdel.v18_0.eudrs_u.verify_vision_stage2_v1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from cdel.v18_0.eudrs_u.eudrs_u_hash_v1 import gcj1_canon_bytes, gcj1_loads_strict, sha256_prefixed
from cdel.v18_0.eudrs_u.eudrs_u_merkle_v1 import merkle_fanout_v1
from cdel.v18_0.eudrs_u.ml_index_v1 import (
    MLIndexCodebookV1,
    MLIndexPageRecordV1,
    MLIndexPageV1,
    MLIndexRootV1,
    encode_ml_index_codebook_v1,
    encode_ml_index_page_v1,
    encode_ml_index_root_v1,
)
from cdel.v18_0.eudrs_u.verify_vision_stage2_v1 import verify as verify_stage2
from cdel.v18_0.eudrs_u.vision_items_v1 import compute_item_embedding_key_q32_s64_v1, parse_vision_embedding_config_v1
from cdel.v18_0.omega_common_v1 import fail, require_no_absolute_paths, validate_schema

from cdel.v18_0.eudrs_u.eudrs_u_artifact_refs_v1 import require_safe_relpath_v1


_CAMPAIGN_ID = "rsi_eudrs_u_vision_index_build_v1"


def _write_hashed_json(*, root: Path, rel_dir: str, artifact_type: str, payload: dict[str, Any]) -> dict[str, str]:
    require_no_absolute_paths(payload)
    raw = gcj1_canon_bytes(payload)
    digest = sha256_prefixed(raw)
    hex64 = digest.split(":", 1)[1]
    name = f"sha256_{hex64}.{artifact_type}.json"
    out_path = (Path(root) / rel_dir / name)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(raw)
    return {"artifact_id": digest, "artifact_relpath": out_path.relative_to(Path(root)).as_posix()}


def _write_hashed_bin(*, root: Path, rel_dir: str, artifact_type: str, data: bytes) -> dict[str, str]:
    digest = sha256_prefixed(bytes(data))
    hex64 = digest.split(":", 1)[1]
    name = f"sha256_{hex64}.{artifact_type}.bin"
    out_path = (Path(root) / rel_dir / name)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(bytes(data))
    return {"artifact_id": digest, "artifact_relpath": out_path.relative_to(Path(root)).as_posix()}


def _load_embedding_config(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        fail("MISSING_STATE_INPUT")
    obj = gcj1_loads_strict(path.read_bytes())
    if not isinstance(obj, dict):
        fail("SCHEMA_FAIL")
    require_no_absolute_paths(obj)
    if str(obj.get("schema_id", "")).strip() != "vision_embedding_config_v1":
        fail("SCHEMA_FAIL")
    try:
        validate_schema(obj, "vision_embedding_config_v1")
    except Exception:  # noqa: BLE001
        fail("SCHEMA_FAIL")
    return dict(obj)


def _normalize_relpath_under_staged(rel: str) -> str:
    s = str(rel).strip()
    if not s:
        fail("SCHEMA_FAIL")
    prefix = "eudrs_u/staged_registry_tree/"
    if s.startswith(prefix):
        s = s[len(prefix) :]
    return require_safe_relpath_v1(s, reason="SCHEMA_FAIL")


def _load_run_relpaths(
    stage_root: Path,
    *,
    relpaths_file: Path | None,
    discover_under: str | None,
) -> list[str]:
    if (relpaths_file is None) == (discover_under is None):
        fail("SCHEMA_FAIL")

    if relpaths_file is not None:
        if not relpaths_file.exists() or not relpaths_file.is_file():
            fail("MISSING_STATE_INPUT")
        out: list[str] = []
        for line in relpaths_file.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s:
                continue
            out.append(_normalize_relpath_under_staged(s))
        # Deterministic: sort, de-dup.
        out = sorted(set(out))
        if not out:
            fail("MISSING_STATE_INPUT")
        return out

    assert discover_under is not None
    root_rel = _normalize_relpath_under_staged(discover_under)
    root_abs = (stage_root / root_rel).resolve()
    if not root_abs.exists() or not root_abs.is_dir():
        fail("MISSING_STATE_INPUT")
    matches = sorted(root_abs.rglob("*.vision_perception_run_manifest_v1.json"), key=lambda p: p.as_posix())
    rels: list[str] = []
    for p in matches:
        rels.append(p.relative_to(stage_root).as_posix())
    rels = sorted(set(rels))
    if not rels:
        fail("MISSING_STATE_INPUT")
    return rels


def _emit(
    state_dir: Path,
    *,
    embedding_config_path: Path,
    perception_run_manifest_relpaths_file: Path | None,
    discover_runs_under: str | None,
    page_record_cap_u32: int,
    codebook_size_u32: int,
    bucket_visit_k_u32: int,
    scan_cap_per_bucket_u32: int,
    merkle_fanout_u32: int,
    sim_kind: str,
) -> dict[str, Any]:
    state_dir = Path(state_dir).resolve()
    state_dir.mkdir(parents=True, exist_ok=True)

    stage_root = state_dir / "eudrs_u" / "staged_registry_tree"
    stage_root.mkdir(parents=True, exist_ok=True)

    # 1) Embedding config (CAS under staged tree).
    embed_cfg_obj = _load_embedding_config(Path(embedding_config_path).resolve())
    embed_cfg_ref = _write_hashed_json(
        root=stage_root,
        rel_dir="polymath/registry/eudrs_u/vision/embed_configs",
        artifact_type="vision_embedding_config_v1",
        payload=embed_cfg_obj,
    )
    embed_cfg = parse_vision_embedding_config_v1(dict(embed_cfg_obj))
    if str(embed_cfg.embedding_kind).strip() != "VISION_EMBED_BASE_V1":
        # RE2 Stage2 verifier currently rejects non-base embedding kinds.
        fail("SCHEMA_FAIL")
    if str(embed_cfg.item_kind).strip() != "OBJECT_CROP_V1":
        fail("SCHEMA_FAIL")

    # 2) Load Stage1 run manifests (inputs must already exist under staged tree).
    run_relpaths = _load_run_relpaths(
        stage_root,
        relpaths_file=None if perception_run_manifest_relpaths_file is None else Path(perception_run_manifest_relpaths_file).resolve(),
        discover_under=None if discover_runs_under is None else str(discover_runs_under),
    )

    # 3) Build descriptors for every Stage1 object.
    descriptor_refs: list[dict[str, str]] = []
    descriptor_objs_by_id: dict[str, dict[str, Any]] = {}

    for run_rel in run_relpaths:
        run_path = (stage_root / run_rel).resolve()
        if not run_path.exists() or not run_path.is_file():
            fail("MISSING_STATE_INPUT")
        run_bytes = run_path.read_bytes()
        run_obj = gcj1_loads_strict(run_bytes)
        if not isinstance(run_obj, dict):
            fail("SCHEMA_FAIL")
        require_no_absolute_paths(run_obj)
        try:
            validate_schema(run_obj, "vision_perception_run_manifest_v1")
        except Exception:  # noqa: BLE001
            fail("SCHEMA_FAIL")

        session_ref = dict(run_obj["session_manifest_ref"])
        session_path = stage_root / session_ref["artifact_relpath"]
        session_obj = gcj1_loads_strict(session_path.read_bytes())
        if not isinstance(session_obj, dict):
            fail("SCHEMA_FAIL")
        require_no_absolute_paths(session_obj)
        session_schema = str(session_obj.get("schema_id", "")).strip()
        if session_schema not in {"vision_session_manifest_v1", "vision_session_manifest_v2"}:
            fail("SCHEMA_FAIL")
        try:
            validate_schema(session_obj, session_schema)
        except Exception:  # noqa: BLE001
            fail("SCHEMA_FAIL")

        frame_manifest_ref_by_idx = {int(r["frame_index_u32"]): dict(r["frame_manifest_ref"]) for r in session_obj["frames"]}
        qxwmr_state_ref_by_idx = {int(r["frame_index_u32"]): dict(r["state_ref"]) for r in run_obj["qxwmr_states"]}

        perception_run_ref = {"artifact_id": sha256_prefixed(run_bytes), "artifact_relpath": run_rel}

        for row in list(run_obj.get("frame_reports", [])):
            idx = int(row["frame_index_u32"])
            report_ref = dict(row["report_ref"])
            report_path = stage_root / report_ref["artifact_relpath"]
            report_obj = gcj1_loads_strict(report_path.read_bytes())
            if not isinstance(report_obj, dict):
                fail("SCHEMA_FAIL")
            require_no_absolute_paths(report_obj)
            try:
                validate_schema(report_obj, "vision_perception_frame_report_v1")
            except Exception:  # noqa: BLE001
                fail("SCHEMA_FAIL")

            for o in list(report_obj.get("objects", [])):
                desc = {
                    "schema_id": "vision_item_descriptor_v1",
                    "item_kind": "OBJECT_CROP_V1",
                    "session_manifest_ref": dict(session_ref),
                    "frame_manifest_ref": dict(frame_manifest_ref_by_idx[idx]),
                    "frame_index_u32": int(idx),
                    "perception_run_ref": dict(perception_run_ref),
                    "frame_report_ref": dict(report_ref),
                    "qxwmr_state_ref": dict(qxwmr_state_ref_by_idx[idx]),
                    "track_id_u32": int(o["track_id_u32"]),
                    "obj_local_id_u32": int(o["obj_local_id_u32"]),
                    "bbox": dict(o["bbox"]),
                    "mask_ref": dict(o["mask_ref"]),
                    "embedding_config_ref": dict(embed_cfg_ref),
                }
                try:
                    validate_schema(desc, "vision_item_descriptor_v1")
                except Exception:  # noqa: BLE001
                    fail("SCHEMA_FAIL")
                dref = _write_hashed_json(
                    root=stage_root,
                    rel_dir="polymath/registry/eudrs_u/vision/items",
                    artifact_type="vision_item_descriptor_v1",
                    payload=desc,
                )
                descriptor_refs.append(dict(dref))
                descriptor_objs_by_id[str(dref["artifact_id"])] = dict(desc)

    # 4) Listing: sort by artifact_id ascending, strictly increasing (verifier enforces).
    descriptor_refs.sort(key=lambda r: str(r["artifact_id"]))
    prev_id: str | None = None
    for r in descriptor_refs:
        aid = str(r.get("artifact_id", "")).strip()
        if not aid:
            fail("SCHEMA_FAIL")
        if prev_id is not None and aid <= prev_id:
            fail("SCHEMA_FAIL")
        prev_id = aid
    listing_ref = _write_hashed_json(
        root=stage_root,
        rel_dir="polymath/registry/eudrs_u/vision/listings",
        artifact_type="vision_item_listing_v1",
        payload={
            "schema_id": "vision_item_listing_v1",
            "embedding_config_id": str(embed_cfg_ref["artifact_id"]),
            "items": [{"item_ref": dict(r)} for r in descriptor_refs],
        },
    )

    # 5) Compute embedding keys and build ML-index records (deterministic).
    key_dim = int(embed_cfg.key_dim_u32)
    records: list[MLIndexPageRecordV1] = []
    for dref in descriptor_refs:
        did = str(dref["artifact_id"])
        dobj = descriptor_objs_by_id[did]
        key = compute_item_embedding_key_q32_s64_v1(base_dir=stage_root, item_desc_obj=dobj, embed_cfg=embed_cfg)
        rh32 = bytes.fromhex(did.split(":", 1)[1])
        records.append(MLIndexPageRecordV1(record_hash32=rh32, payload_hash32=rh32, key_q32=key))

    # 6) Build a deterministic ML-index bundle.
    if int(page_record_cap_u32) <= 0:
        fail("SCHEMA_FAIL")
    K = int(codebook_size_u32)
    if K <= 0:
        fail("SCHEMA_FAIL")
    if int(bucket_visit_k_u32) <= 0 or int(bucket_visit_k_u32) > K:
        fail("SCHEMA_FAIL")
    if int(scan_cap_per_bucket_u32) <= 0:
        fail("SCHEMA_FAIL")
    if int(merkle_fanout_u32) <= 0:
        fail("SCHEMA_FAIL")
    sim_kind_s = str(sim_kind).strip()
    if sim_kind_s not in {"DOT_Q32_SHIFT_END_V1", "DOT_Q32_SHIFT_EACH_DIM_V1"}:
        fail("SCHEMA_FAIL")

    codebook = MLIndexCodebookV1(K_u32=K, d_u32=key_dim, C_q32=[0 for _ in range(K * key_dim)])
    codebook_ref = _write_hashed_bin(
        root=stage_root,
        rel_dir="polymath/registry/eudrs_u/indices",
        artifact_type="ml_index_codebook_v1",
        data=encode_ml_index_codebook_v1(codebook),
    )

    # Canonical page ordering: record_hash32 strictly increasing.
    records.sort(key=lambda r: bytes(r.record_hash32))

    # v1 producer: assign all records to bucket 0.
    pages: list[dict[str, Any]] = []
    page_refs_bucket0: list[dict[str, str]] = []
    for page_index, off in enumerate(range(0, len(records), int(page_record_cap_u32))):
        chunk = records[off : off + int(page_record_cap_u32)]
        page = MLIndexPageV1(bucket_id_u32=0, page_index_u32=int(page_index), key_dim_u32=key_dim, records=list(chunk))
        pref = _write_hashed_bin(
            root=stage_root,
            rel_dir="polymath/registry/eudrs_u/indices/buckets/0/pages",
            artifact_type="ml_index_page_v1",
            data=encode_ml_index_page_v1(page),
        )
        page_refs_bucket0.append(dict(pref))
        pages.append({"page_index_u32": int(page_index), "page_ref": dict(pref)})

    bucket_listing_ref = _write_hashed_json(
        root=stage_root,
        rel_dir="polymath/registry/eudrs_u/indices",
        artifact_type="ml_index_bucket_listing_v1",
        payload={
            "schema_id": "ml_index_bucket_listing_v1",
            "index_manifest_id": "sha256:" + ("00" * 32),
            "buckets": [{"bucket_id_u32": 0, "pages": list(pages)}],
        },
    )

    # Index root: per-bucket Merkle roots over page artifact ids (bytes32).
    bucket_roots: list[bytes] = []
    leafs0 = [bytes.fromhex(ref["artifact_id"].split(":", 1)[1]) for ref in page_refs_bucket0]
    root0 = merkle_fanout_v1(leaf_hash32=leafs0, fanout_u32=int(merkle_fanout_u32))
    for bucket_id in range(K):
        if bucket_id == 0:
            bucket_roots.append(bytes(root0))
        else:
            bucket_roots.append(b"\x00" * 32)
    index_root = MLIndexRootV1(K_u32=K, fanout_u32=int(merkle_fanout_u32), bucket_root_hash32=bucket_roots)
    index_root_ref = _write_hashed_bin(
        root=stage_root,
        rel_dir="polymath/registry/eudrs_u/indices",
        artifact_type="ml_index_root_v1",
        data=encode_ml_index_root_v1(index_root),
    )

    # ML-index manifest (CAS JSON under staged tree).
    opset_digest = sha256_prefixed(gcj1_canon_bytes({"schema_id": "eudrs_u_opset_stub_v1", "version_u64": 1}))
    opset_id = f"opset:eudrs_u_v1:{opset_digest}"
    index_manifest_obj = {
        "schema_id": "ml_index_manifest_v1",
        "index_kind": "ML_INDEX_V1",
        "opset_id": opset_id,
        "key_dim_u32": int(key_dim),
        "codebook_size_u32": int(K),
        "bucket_visit_k_u32": int(bucket_visit_k_u32),
        "scan_cap_per_bucket_u32": int(scan_cap_per_bucket_u32),
        "merkle_fanout_u32": int(merkle_fanout_u32),
        "sim_kind": sim_kind_s,
        "codebook_ref": dict(codebook_ref),
        "index_root_ref": dict(index_root_ref),
        "bucket_listing_ref": dict(bucket_listing_ref),
        "mem_gates": {"mem_g1_bucket_balance_max_q32": {"q": 1 << 32}, "mem_g2_anchor_recall_min_q32": {"q": 0}},
    }
    index_manifest_ref = _write_hashed_json(
        root=stage_root,
        rel_dir="polymath/registry/eudrs_u/indices",
        artifact_type="ml_index_manifest_v1",
        payload=dict(index_manifest_obj),
    )

    listing_abs = stage_root / listing_ref["artifact_relpath"]
    index_abs = stage_root / index_manifest_ref["artifact_relpath"]

    # 7) Stage-2 authoritative verification (fail-closed).
    receipt_obj = verify_stage2(state_dir, item_listing_path=listing_abs, index_manifest_path=index_abs)
    receipt_bytes = gcj1_canon_bytes(receipt_obj)

    evidence_dir = state_dir / "eudrs_u" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "vision_stage2_verify_receipt_v1.json").write_bytes(receipt_bytes)

    # Also store a content-addressed copy under staged tree.
    _ = _write_hashed_json(
        root=stage_root,
        rel_dir="polymath/registry/eudrs_u/indices/receipts",
        artifact_type="vision_stage2_verify_receipt_v1",
        payload=dict(receipt_obj),
    )

    # Run-local evidence stubs required by the promotion summary schema.
    evidence_dir_rel = "eudrs_u/evidence"
    producer_kind = "vision_index_build"
    weights_ref = _write_hashed_json(root=state_dir, rel_dir=evidence_dir_rel, artifact_type="weights_manifest_v1", payload={"schema_id": "weights_manifest_v1", "producer_kind": producer_kind})
    # Evidence copy of the ML-index manifest produced under the staged tree.
    ml_index_ref = _write_hashed_json(root=state_dir, rel_dir=evidence_dir_rel, artifact_type="ml_index_manifest_v1", payload=dict(index_manifest_obj))
    cac_ref = _write_hashed_json(root=state_dir, rel_dir=evidence_dir_rel, artifact_type="cac_v1", payload={"schema_id": "cac_v1", "producer_kind": producer_kind})
    ufc_ref = _write_hashed_json(root=state_dir, rel_dir=evidence_dir_rel, artifact_type="ufc_v1", payload={"schema_id": "ufc_v1", "producer_kind": producer_kind})
    cooldown_ref = _write_hashed_json(root=state_dir, rel_dir=evidence_dir_rel, artifact_type="cooldown_ledger_v1", payload={"schema_id": "cooldown_ledger_v1", "producer_kind": producer_kind})
    stability_ref = _write_hashed_json(root=state_dir, rel_dir=evidence_dir_rel, artifact_type="stability_metrics_v1", payload={"schema_id": "stability_metrics_v1", "producer_kind": producer_kind})
    det_cert_ref = _write_hashed_json(root=state_dir, rel_dir=evidence_dir_rel, artifact_type="determinism_cert_v1", payload={"schema_id": "determinism_cert_v1", "producer_kind": producer_kind})
    uni_cert_ref = _write_hashed_json(root=state_dir, rel_dir=evidence_dir_rel, artifact_type="universality_cert_v1", payload={"schema_id": "universality_cert_v1", "producer_kind": producer_kind})

    # Minimal staged root tuple + active pointer (schema-only; promotion verification is out of scope).
    epoch_u64 = 0

    def _manifest(schema_id: str) -> dict[str, Any]:
        return {"schema_id": schema_id, "epoch_u64": int(epoch_u64), "dc1_id": "dc1:q32_v1", "opset_id": opset_id}

    registry_prefix = "polymath/registry/eudrs_u"
    sroot = _write_hashed_json(root=stage_root, rel_dir=f"{registry_prefix}/manifests", artifact_type="qxwmr_world_model_manifest_v1", payload=_manifest("qxwmr_world_model_manifest_v1"))
    oroot = _write_hashed_json(root=stage_root, rel_dir=f"{registry_prefix}/ontology/concepts", artifact_type="concept_def_v1", payload=_manifest("concept_def_v1"))
    kroot = _write_hashed_json(root=stage_root, rel_dir=f"{registry_prefix}/manifests", artifact_type="strategy_vm_manifest_v1", payload=_manifest("strategy_vm_manifest_v1"))
    croot = _write_hashed_bin(root=stage_root, rel_dir=f"{registry_prefix}/capsules", artifact_type="urc_capsule_v1", data=b"\x00" * 16)
    mroot = _write_hashed_json(root=stage_root, rel_dir=f"{registry_prefix}/memory/compaction", artifact_type="memory_compaction_receipt_v1", payload=_manifest("memory_compaction_receipt_v1"))
    wroot = _write_hashed_json(root=stage_root, rel_dir=f"{registry_prefix}/weights", artifact_type="weights_manifest_v1", payload=_manifest("weights_manifest_v1"))
    stability_gate_bundle = _write_hashed_json(root=stage_root, rel_dir=f"{registry_prefix}/gates", artifact_type="stability_metrics_v1", payload=_manifest("stability_metrics_v1"))
    determinism_cert = _write_hashed_json(root=stage_root, rel_dir=f"{registry_prefix}/certs", artifact_type="determinism_cert_v1", payload=_manifest("determinism_cert_v1"))
    universality_cert = _write_hashed_json(root=stage_root, rel_dir=f"{registry_prefix}/certs", artifact_type="universality_cert_v1", payload=_manifest("universality_cert_v1"))

    # Root tuple requires a DMPL droot reference. Stage-2 campaigns do not run
    # DMPL replay, so we emit a minimal schema-valid stub.
    opset_id_for_root_tuple = opset_id
    zero_sha = "sha256:" + ("00" * 32)
    droot_payload = {
        "schema_id": "dmpl_droot_v1",
        "dc1_id": "dc1:q32_v1",
        "opset_id": opset_id_for_root_tuple,
        "dmpl_config_id": zero_sha,
        "froot": zero_sha,
        "vroot": zero_sha,
        "caps_digest": zero_sha,
        "opset_semantics_id": opset_id_for_root_tuple,
    }
    try:
        validate_schema(droot_payload, "dmpl_droot_v1")
    except Exception:  # noqa: BLE001
        fail("SCHEMA_FAIL")
    droot = _write_hashed_json(root=stage_root, rel_dir=f"{registry_prefix}/dmpl/roots", artifact_type="dmpl_droot_v1", payload=droot_payload)

    root_tuple_payload = {
        "schema_id": "eudrs_u_root_tuple_v1",
        "epoch_u64": int(epoch_u64),
        "dc1_id": "dc1:q32_v1",
        "opset_id": opset_id,
        "sroot": sroot,
        "oroot": oroot,
        "kroot": kroot,
        "croot": croot,
        "droot": droot,
        "mroot": mroot,
        # Semantically iroot is the activated index root; keep it aligned with the manifest.
        "iroot": dict(index_root_ref),
        "wroot": wroot,
        "stability_gate_bundle": stability_gate_bundle,
        "determinism_cert": determinism_cert,
        "universality_cert": universality_cert,
    }
    try:
        validate_schema(root_tuple_payload, "eudrs_u_root_tuple_v1")
    except Exception:  # noqa: BLE001
        fail("SCHEMA_FAIL")
    root_tuple_ref = _write_hashed_json(root=stage_root, rel_dir=f"{registry_prefix}/roots", artifact_type="eudrs_u_root_tuple_v1", payload=root_tuple_payload)

    active_pointer_payload = {
        "schema_id": "active_root_tuple_ref_v1",
        "active_root_tuple": {"artifact_id": root_tuple_ref["artifact_id"], "artifact_relpath": root_tuple_ref["artifact_relpath"]},
    }
    active_pointer_path = stage_root / f"{registry_prefix}/active/active_root_tuple_ref_v1.json"
    active_pointer_path.parent.mkdir(parents=True, exist_ok=True)
    active_pointer_path.write_bytes(gcj1_canon_bytes(active_pointer_payload))

    summary_payload = {
        "schema_id": "eudrs_u_promotion_summary_v1",
        "proposed_root_tuple_ref": {
            "artifact_id": root_tuple_ref["artifact_id"],
            "artifact_relpath": f"eudrs_u/staged_registry_tree/{root_tuple_ref['artifact_relpath']}",
        },
        "staged_registry_tree_relpath": "eudrs_u/staged_registry_tree",
        "evidence": {
            "weights_manifest_ref": weights_ref,
            # Promotion verifier expects evidence artifacts under eudrs_u/evidence/.
            "ml_index_manifest_ref": ml_index_ref,
            "cac_ref": cac_ref,
            "ufc_ref": ufc_ref,
            "cooldown_ledger_ref": cooldown_ref,
            "stability_metrics_ref": stability_ref,
            "determinism_cert_ref": det_cert_ref,
            "universality_cert_ref": uni_cert_ref,
        },
    }
    require_no_absolute_paths(summary_payload)
    (state_dir / evidence_dir_rel).mkdir(parents=True, exist_ok=True)
    (state_dir / evidence_dir_rel / "eudrs_u_promotion_summary_v1.json").write_bytes(gcj1_canon_bytes(summary_payload))

    return {
        "status": "OK",
        "vision_item_listing_id": listing_ref["artifact_id"],
        "ml_index_manifest_id": index_manifest_ref["artifact_id"],
        "vision_stage2_receipt_sha256": sha256_prefixed(receipt_bytes),
    }


def _load_pack(path: Path) -> dict[str, Any]:
    obj = gcj1_loads_strict(path.read_bytes())
    if not isinstance(obj, dict):
        fail("SCHEMA_FAIL")
    require_no_absolute_paths(obj)
    return dict(obj)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=_CAMPAIGN_ID)
    parser.add_argument("--campaign_pack", required=True)
    parser.add_argument("--out_dir", required=True)
    parser.add_argument("--embedding_config_path", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--perception_run_manifest_relpaths_file")
    group.add_argument("--discover_runs_under")
    parser.add_argument("--page_record_cap_u32", required=True, type=int)
    parser.add_argument("--codebook_size_u32", required=True, type=int)
    parser.add_argument("--bucket_visit_k_u32", required=True, type=int)
    parser.add_argument("--scan_cap_per_bucket_u32", required=True, type=int)
    parser.add_argument("--merkle_fanout_u32", required=True, type=int)
    parser.add_argument("--sim_kind", required=True)
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir).resolve()
    _load_pack(Path(args.campaign_pack).resolve())

    state_dir = (out_dir / "daemon" / _CAMPAIGN_ID / "state").resolve()
    _emit(
        state_dir,
        embedding_config_path=Path(args.embedding_config_path),
        perception_run_manifest_relpaths_file=None if args.perception_run_manifest_relpaths_file is None else Path(args.perception_run_manifest_relpaths_file),
        discover_runs_under=None if args.discover_runs_under is None else str(args.discover_runs_under),
        page_record_cap_u32=int(args.page_record_cap_u32),
        codebook_size_u32=int(args.codebook_size_u32),
        bucket_visit_k_u32=int(args.bucket_visit_k_u32),
        scan_cap_per_bucket_u32=int(args.scan_cap_per_bucket_u32),
        merkle_fanout_u32=int(args.merkle_fanout_u32),
        sim_kind=str(args.sim_kind),
    )
    sys.stdout.write("OK\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
