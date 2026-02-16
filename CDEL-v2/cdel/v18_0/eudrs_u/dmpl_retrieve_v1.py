"""DMPL deterministic retrieval wrapper over ML-Index v1.

Phase 2 contract:
  - Compute `key_bytes` exactly (DMPL/KEY/v1) and query ML-Index with K=K_ctx.
  - Return results in deterministic order and expose `retrieval_trace_root_id`.
  - Emit `retrieval_query_digest` and `retrieval_result_digest` as sha256 over GCJ-1 canonical JSON.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import Any

from ..omega_common_v1 import OmegaV18Error, require_no_absolute_paths, validate_schema
from .dmpl_config_load_v1 import DmplRuntime
from .dmpl_types_v1 import (
    DMPLError,
    DMPL_E_DIM_MISMATCH,
    DMPL_E_HASH_MISMATCH,
    DMPL_E_NONCANON_GCJ1,
    DMPL_E_OPSET_MISMATCH,
    _active_resolver,
    _sha25632_count,
    _sha256_id_from_hex_digest32,
    _sha256_id_to_digest32,
    _u32_le,
)
from .eudrs_u_artifact_refs_v1 import require_artifact_ref_v1
from .eudrs_u_hash_v1 import gcj1_canon_bytes, gcj1_loads_and_verify_canonical
from .ml_index_v1 import retrieve_topk_v1, require_ml_index_manifest_v1

_KEY_PREFIX = b"DMPL/KEY/v1\x00"


@dataclass(frozen=True, slots=True)
class RetrieveItem:
    concept_shard_id: str
    score_q32: int
    record_hash_u32: int


@dataclass(frozen=True, slots=True)
class RetrieveOutput:
    items: list[RetrieveItem]
    retrieval_trace_root_id: str
    retrieval_query_digest: str
    retrieval_result_digest: str


def _resolver_load_bytes(resolver: Any, *, artifact_id: str, artifact_type: str, ext: str) -> bytes:
    try:
        fn = getattr(resolver, "load_artifact_bytes")
    except Exception:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver missing load_artifact_bytes"})
    if not callable(fn):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver.load_artifact_bytes not callable"})
    raw = fn(artifact_id=str(artifact_id), artifact_type=str(artifact_type), ext=str(ext))
    if not isinstance(raw, (bytes, bytearray, memoryview)):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver returned non-bytes"})
    return bytes(raw)


def _load_json_by_id_and_type(*, artifact_id: str, artifact_type: str) -> dict[str, Any]:
    resolver = _active_resolver()
    if resolver is None:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "no active resolver"})
    raw = _resolver_load_bytes(resolver, artifact_id=str(artifact_id), artifact_type=str(artifact_type), ext="json")
    if _sha256_id_from_hex_digest32(_sha25632_count(raw)) != str(artifact_id).strip():
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"artifact_id": str(artifact_id), "artifact_type": str(artifact_type)})
    try:
        obj = gcj1_loads_and_verify_canonical(raw)
    except OmegaV18Error:
        raise DMPLError(reason_code=DMPL_E_NONCANON_GCJ1, details={"artifact_id": str(artifact_id), "artifact_type": str(artifact_type)})
    if not isinstance(obj, dict):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "not dict", "artifact_type": str(artifact_type)})
    require_no_absolute_paths(obj)
    # JSON schema validation (when schema exists).
    try:
        validate_schema(obj, str(artifact_type))
    except Exception:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"artifact_type": str(artifact_type), "artifact_id": str(artifact_id)})
    return dict(obj)


def _artifact_type_from_relpath(relpath: str, *, expected_ext: str) -> str:
    # sha256_<hex>.<artifact_type>.(json|bin)
    name = str(relpath).split("/")[-1]
    parts = name.split(".")
    if len(parts) < 3:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "bad relpath", "relpath": str(relpath)})
    if parts[-1] != expected_ext:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "bad ext", "relpath": str(relpath)})
    artifact_type = ".".join(parts[1:-1])
    if not artifact_type:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "missing artifact_type", "relpath": str(relpath)})
    return artifact_type


def retrieve_det_v1(runtime: DmplRuntime, state_hash32: bytes, z_hash32: bytes, a_hash32: bytes, ladder_level_u32: int) -> RetrieveOutput:
    if not isinstance(runtime, DmplRuntime):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "runtime type"})
    if not isinstance(state_hash32, (bytes, bytearray, memoryview)) or len(bytes(state_hash32)) != 32:
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "state_hash32"})
    if not isinstance(z_hash32, (bytes, bytearray, memoryview)) or len(bytes(z_hash32)) != 32:
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "z_hash32"})
    if not isinstance(a_hash32, (bytes, bytearray, memoryview)) or len(bytes(a_hash32)) != 32:
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "a_hash32"})

    caps = dict(runtime.caps)
    config = dict(runtime.config)
    retrieval_spec = config.get("retrieval_spec")
    if not isinstance(retrieval_spec, dict):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "retrieval_spec"})

    K_ctx_u32 = int(caps.get("K_ctx_u32", 0))
    if int(retrieval_spec.get("K_ctx_u32", -1)) != int(K_ctx_u32):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "K_ctx mismatch"})
    scan_cap_cfg = int(retrieval_spec.get("scan_cap_per_bucket_u32", 0))
    if scan_cap_cfg <= 0:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "scan cap"})

    ml_index_manifest_id = str(retrieval_spec.get("ml_index_manifest_id", "")).strip()
    if not ml_index_manifest_id.startswith("sha256:"):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "ml_index_manifest_id"})

    # DMPL key bytes: sha256(DMPL/KEY/v1 || state_hash32 || z_hash32 || a_hash32 || ladder_level_u32 || modelpack_hash32)
    key_bytes = _sha25632_count(
        _KEY_PREFIX
        + bytes(state_hash32)
        + bytes(z_hash32)
        + bytes(a_hash32)
        + _u32_le(int(ladder_level_u32))
        + bytes(runtime.modelpack_hash32)
    )
    key_id = _sha256_id_from_hex_digest32(_sha25632_count(bytes(key_bytes)))

    query_obj = {
        "schema_id": "dmpl_retrieval_query_v1",
        "dc1_id": str(runtime.dc1_id),
        "opset_id": str(runtime.opset_id),
        "ml_index_manifest_id": str(ml_index_manifest_id),
        "key_id": str(key_id),
        "K_u32": int(K_ctx_u32),
        "scan_cap_per_bucket_u32": int(scan_cap_cfg),
        "score_fn_id": "ml_index_v1_default",
        "tie_rule_id": "score_desc_id_asc",
    }
    retrieval_query_digest = _sha256_id_from_hex_digest32(_sha25632_count(gcj1_canon_bytes(query_obj)))

    manifest_obj = _load_json_by_id_and_type(artifact_id=ml_index_manifest_id, artifact_type="ml_index_manifest_v1")
    manifest = require_ml_index_manifest_v1(manifest_obj)
    if int(manifest.scan_cap_per_bucket_u32) != int(scan_cap_cfg):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "scan cap mismatch"})

    # Load referenced ML-index artifacts via their ArtifactRefs.
    resolver = _active_resolver()
    if resolver is None:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "no active resolver"})

    def _load_ref_bytes(ref: dict[str, str], *, ext: str) -> bytes:
        aref = require_artifact_ref_v1(ref)
        relpath = str(aref.get("artifact_relpath", ""))
        atype = _artifact_type_from_relpath(relpath, expected_ext=ext)
        raw = _resolver_load_bytes(resolver, artifact_id=str(aref["artifact_id"]), artifact_type=str(atype), ext=str(ext))
        # Hash check (fail-closed).
        if _sha256_id_from_hex_digest32(_sha25632_count(raw)) != str(aref["artifact_id"]).strip():
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"artifact_id": str(aref["artifact_id"]), "artifact_type": str(atype)})
        return raw

    codebook_bytes = _load_ref_bytes(manifest.codebook_ref, ext="bin")
    index_root_bytes = _load_ref_bytes(manifest.index_root_ref, ext="bin")
    bucket_listing_bytes = _load_ref_bytes(manifest.bucket_listing_ref, ext="json")
    try:
        bucket_listing_obj = gcj1_loads_and_verify_canonical(bucket_listing_bytes)
    except OmegaV18Error:
        raise DMPLError(reason_code=DMPL_E_NONCANON_GCJ1, details={"hint": "bucket listing noncanon"})
    if not isinstance(bucket_listing_obj, dict):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "bucket listing not dict"})

    # Query key is the 32 key_bytes interpreted as key_dim_u32 signed i64 values (little-endian).
    key_dim_u32 = int(manifest.key_dim_u32)
    if int(key_dim_u32) < 0 or (8 * int(key_dim_u32)) != len(key_bytes):
        raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "key_dim vs sha256"})
    query_key_q32_s64: list[int] = []
    for i in range(int(key_dim_u32)):
        (v,) = struct.unpack_from("<q", key_bytes, i * 8)
        query_key_q32_s64.append(int(v))

    def _load_page_bytes_by_ref(ref: dict[str, str]) -> bytes:
        aref = require_artifact_ref_v1(ref)
        relpath = str(aref.get("artifact_relpath", ""))
        atype = _artifact_type_from_relpath(relpath, expected_ext="bin")
        return _resolver_load_bytes(resolver, artifact_id=str(aref["artifact_id"]), artifact_type=str(atype), ext="bin")

    results, retrieval_trace_root32 = retrieve_topk_v1(
        index_manifest_obj=manifest_obj,
        codebook_bytes=codebook_bytes,
        index_root_bytes=index_root_bytes,
        bucket_listing_obj=bucket_listing_obj,
        load_page_bytes_by_ref=_load_page_bytes_by_ref,
        query_key_q32_s64=query_key_q32_s64,
        top_k_u32=int(K_ctx_u32) if int(K_ctx_u32) > 0 else 1,
    )

    # Convert + enforce DMPL tie rule: (score desc, concept_shard_id asc).
    items: list[RetrieveItem] = []
    for _rh32, payload_hash32, score in results:
        concept_id = _sha256_id_from_hex_digest32(bytes(payload_hash32))
        items.append(RetrieveItem(concept_shard_id=str(concept_id), score_q32=int(score), record_hash_u32=0))
    items.sort(key=lambda r: (-int(r.score_q32), str(r.concept_shard_id)))
    if int(K_ctx_u32) >= 0:
        items = items[: int(K_ctx_u32)]

    results_list_obj: list[dict[str, Any]] = [
        {"concept_shard_id": str(it.concept_shard_id), "score_q32": {"q": int(it.score_q32)}, "record_hash_u32": int(it.record_hash_u32)}
        for it in items
    ]
    retrieval_result_digest = _sha256_id_from_hex_digest32(_sha25632_count(gcj1_canon_bytes(results_list_obj)))

    return RetrieveOutput(
        items=items,
        retrieval_trace_root_id=_sha256_id_from_hex_digest32(bytes(retrieval_trace_root32)),
        retrieval_query_digest=str(retrieval_query_digest),
        retrieval_result_digest=str(retrieval_result_digest),
    )


__all__ = [
    "RetrieveItem",
    "RetrieveOutput",
    "retrieve_det_v1",
]
