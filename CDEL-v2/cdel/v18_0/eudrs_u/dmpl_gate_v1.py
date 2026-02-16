"""DMPL deterministic gating (v1).

Phase 2 contract: see §5.7 (GateDet).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..omega_common_v1 import OmegaV18Error, require_no_absolute_paths, validate_schema
from .dmpl_config_load_v1 import DmplRuntime
from .dmpl_retrieve_v1 import RetrieveOutput
from .dmpl_tensor_io_v1 import parse_tensor_q32_v1, require_shape
from .dmpl_types_v1 import (
    DMPLError,
    DMPL_E_DIM_MISMATCH,
    DMPL_E_HASH_MISMATCH,
    DMPL_E_NONCANON_GCJ1,
    DMPL_E_OPSET_MISMATCH,
    Q32_ONE,
    _active_resolver,
    _add_sat_count,
    _div_q32_pos_rne_count,
    _mul_q32_count,
    _sha25632_count,
    _sha256_id_from_hex_digest32,
    _sha256_id_to_digest32,
)
from .eudrs_u_hash_v1 import gcj1_canon_bytes, gcj1_loads_and_verify_canonical
from .eudrs_u_q32ops_v1 import topk_det


@dataclass(frozen=True, slots=True)
class GateItem:
    concept_shard_id: str
    w_q32: int


@dataclass(frozen=True, slots=True)
class GateOutput:
    gate_active: list[GateItem]
    gate_digest: str


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


def _load_concept_shard_obj(concept_shard_id: str) -> dict[str, Any]:
    resolver = _active_resolver()
    if resolver is None:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "no active resolver"})
    raw = _resolver_load_bytes(resolver, artifact_id=str(concept_shard_id), artifact_type="dmpl_concept_shard_v1", ext="json")
    if _sha256_id_from_hex_digest32(_sha25632_count(raw)) != str(concept_shard_id).strip():
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"artifact_id": str(concept_shard_id), "artifact_type": "dmpl_concept_shard_v1"})
    try:
        obj = gcj1_loads_and_verify_canonical(raw)
    except OmegaV18Error:
        raise DMPLError(reason_code=DMPL_E_NONCANON_GCJ1, details={"artifact_id": str(concept_shard_id), "artifact_type": "dmpl_concept_shard_v1"})
    if not isinstance(obj, dict):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "concept shard not dict"})
    require_no_absolute_paths(obj)
    try:
        validate_schema(obj, "dmpl_concept_shard_v1")
    except Exception:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "concept shard schema"})
    return dict(obj)


def _load_embed_vec_q32(*, concept_shard_obj: dict[str, Any], embed_dim_u32: int) -> list[int]:
    resolver = _active_resolver()
    if resolver is None:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "no active resolver"})
    embed_bin_id = str(concept_shard_obj.get("embed_tensor_bin_id", "")).strip()
    if not embed_bin_id.startswith("sha256:"):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "embed_tensor_bin_id"})
    raw = _resolver_load_bytes(resolver, artifact_id=embed_bin_id, artifact_type="dmpl_tensor_q32_v1", ext="bin")
    if _sha256_id_from_hex_digest32(_sha25632_count(raw)) != embed_bin_id:
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"artifact_id": embed_bin_id, "artifact_type": "dmpl_tensor_q32_v1"})
    dims, vals = parse_tensor_q32_v1(raw)
    require_shape(dims, [int(embed_dim_u32)])
    if len(vals) != int(embed_dim_u32):
        raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "embed vals"})
    return [int(v) for v in vals]


def gate_det_v1(runtime: DmplRuntime, z_t: list[int], retrieved: RetrieveOutput) -> GateOutput:
    if not isinstance(runtime, DmplRuntime):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "runtime type"})
    if not isinstance(z_t, list) or len(z_t) != int(runtime.dims.d_u32):
        raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "z_t shape"})
    if not isinstance(retrieved, RetrieveOutput):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "retrieved type"})

    gating_spec = runtime.config.get("gating_spec")
    if not isinstance(gating_spec, dict):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "gating_spec"})
    if bool(gating_spec.get("inverse_head_enabled_b", False)):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "inverse head enabled"})

    normalize_weights_b = bool(gating_spec.get("normalize_weights_b", False))
    epsilon_q32 = gating_spec.get("epsilon_q32")
    if not isinstance(epsilon_q32, dict) or set(epsilon_q32.keys()) != {"q"}:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "epsilon_q32"})
    epsilon_q = int(epsilon_q32.get("q", 0))
    if normalize_weights_b and epsilon_q <= 0:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "epsilon must be >0"})

    K_g_u32 = int(runtime.caps.get("K_g_u32", 0))
    if K_g_u32 < 0:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "K_g"})

    # 1) q = Wg @ z
    (Wg_dims, Wg_vals) = runtime.base_forward.get("Wg", ([], []))
    require_shape(Wg_dims, [int(runtime.dims.embed_dim_u32), int(runtime.dims.d_u32)])
    embed_dim = int(runtime.dims.embed_dim_u32)
    d = int(runtime.dims.d_u32)

    q_vec: list[int] = []
    for i in range(embed_dim):
        acc = 0
        row_off = i * d
        for j in range(d):
            acc = _add_sat_count(acc, _mul_q32_count(int(Wg_vals[row_off + j]), int(z_t[j])))
        q_vec.append(int(acc))

    # 2) alpha for each retrieved concept (in retrieved.items order)
    alpha_by_id: dict[int, tuple[str, int]] = {}
    pairs: list[tuple[int, int]] = []
    for it in list(retrieved.items):
        concept_id = str(it.concept_shard_id)
        cid32 = _sha256_id_to_digest32(concept_id, reason=DMPL_E_HASH_MISMATCH)
        tie_id = int.from_bytes(cid32, byteorder="big", signed=False)

        concept_obj = _load_concept_shard_obj(concept_id)
        e_vec = _load_embed_vec_q32(concept_shard_obj=concept_obj, embed_dim_u32=embed_dim)

        g = 0
        for k in range(embed_dim):
            g = _add_sat_count(g, _mul_q32_count(int(q_vec[k]), int(e_vec[k])))
        alpha = int(g) if int(g) > 0 else 0
        alpha_by_id[int(tie_id)] = (concept_id, int(alpha))
        pairs.append((int(alpha), int(tie_id)))

    # 3) Select top K_g by (alpha desc, concept_id asc).
    selected_pairs = topk_det(pairs, int(K_g_u32)) if int(K_g_u32) > 0 else []

    selected_items: list[tuple[str, int]] = []
    for alpha, tie_id in selected_pairs:
        concept_id, alpha_q32 = alpha_by_id[int(tie_id)]
        selected_items.append((str(concept_id), int(alpha_q32)))

    # 4) Weight normalization (optional).
    gate_active: list[GateItem] = []
    if normalize_weights_b:
        Z = int(epsilon_q)
        for _cid, alpha_q32 in selected_items:
            Z = _add_sat_count(Z, int(alpha_q32))
        if int(Z) <= 0:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "Z<=0"})
        invZ = _div_q32_pos_rne_count(numer_q32_s64=int(Q32_ONE), denom_q32_pos_s64=int(Z))
        for cid, alpha_q32 in selected_items:
            w = _mul_q32_count(int(alpha_q32), int(invZ))
            gate_active.append(GateItem(concept_shard_id=str(cid), w_q32=int(w)))
    else:
        for cid, alpha_q32 in selected_items:
            gate_active.append(GateItem(concept_shard_id=str(cid), w_q32=int(alpha_q32)))

    gate_obj = {
        "schema_id": "dmpl_gate_out_v1",
        "retrieval_result_digest": str(retrieved.retrieval_result_digest),
        "gate_active": [{"concept_shard_id": str(g.concept_shard_id), "w_q32": {"q": int(g.w_q32)}} for g in gate_active],
    }
    gate_digest = _sha256_id_from_hex_digest32(_sha25632_count(gcj1_canon_bytes(gate_obj)))

    return GateOutput(gate_active=gate_active, gate_digest=str(gate_digest))


__all__ = [
    "GateItem",
    "GateOutput",
    "gate_det_v1",
]
