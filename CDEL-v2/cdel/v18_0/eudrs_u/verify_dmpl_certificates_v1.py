"""DMPL certificate verifiers (v1).

Phase 3 contract: certificate verifiers are structural-only (schema + canonical +
internal reference existence). Phase 4 makes them gating-critical.

This module is RE2: deterministic and fail-closed via DMPLError.
"""

from __future__ import annotations

import hashlib
import struct
from typing import Any

from ..omega_common_v1 import OmegaV18Error, require_no_absolute_paths, validate_schema
from .dmpl_config_load_v1 import load_runtime_from_droot_v1
from .dmpl_tensor_io_v1 import parse_tensor_q32_v1, require_shape
from .dmpl_train_sgd_v1 import (
    ConceptPatchEntryV1,
    TrainableStateV1,
    train_step_sgd_det_v1,
)
from .dmpl_train_trace_v1 import parse_lenpref_canonjson_stream_v1
from .dmpl_types_v1 import (
    DMPLError,
    DMPL_E_CAC_FAIL,
    DMPL_E_DIM_MISMATCH,
    DMPL_E_HASH_MISMATCH,
    DMPL_E_LASUM_BROKEN,
    DMPL_E_NONCANON_GCJ1,
    DMPL_E_OPSET_MISMATCH,
    DMPL_E_REDUCTION_ORDER_VIOLATION,
    DMPL_E_STAB_GATE_FAIL_G0,
    DMPL_E_STAB_GATE_FAIL_G1,
    DMPL_E_STAB_GATE_FAIL_G2,
    DMPL_E_STAB_GATE_FAIL_G3,
    DMPL_E_STAB_GATE_FAIL_G4,
    DMPL_E_STAB_GATE_FAIL_G5,
    DMPL_E_UFC_INVALID,
    DMPL_OK,
    Q32_ONE,
)
from .eudrs_u_hash_v1 import gcj1_loads_and_verify_canonical
from .eudrs_u_q32ops_v1 import add_sat, mul_q32
from .qxrl_opset_math_v1 import div_q32_pos_rne_v1


def _require_no_abs_paths(obj: Any) -> None:
    try:
        require_no_absolute_paths(obj)
    except OmegaV18Error:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "absolute path"})


def _load_canon_json_by_ref(*, resolver: Any, artifact_ref: dict[str, Any]) -> dict[str, Any]:
    # Phase 3: require resolver.load_artifact_ref_bytes(ArtifactRef)->bytes
    try:
        fn = getattr(resolver, "load_artifact_ref_bytes")
    except Exception:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver missing load_artifact_ref_bytes"})
    if not callable(fn):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver.load_artifact_ref_bytes not callable"})
    raw = fn(artifact_ref)
    if not isinstance(raw, (bytes, bytearray, memoryview)):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver returned non-bytes"})
    b = bytes(raw)
    try:
        obj = gcj1_loads_and_verify_canonical(b)
    except OmegaV18Error:
        raise DMPLError(reason_code=DMPL_E_NONCANON_GCJ1, details={"hint": "certificate noncanonical"})
    if not isinstance(obj, dict):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "certificate not dict"})
    _require_no_abs_paths(obj)
    return dict(obj)


def verify_dmpl_certificates_struct_v1(
    cert_refs_obj: dict,  # dmpl_evidence.certificate_refs
    resolver,
) -> None:
    if not isinstance(cert_refs_obj, dict):
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "certificate_refs not dict"})

    expected_keys = {
        "dmpl_cac_pack_ref",
        "dmpl_ufc_flow_ref",
        "dmpl_stab_report_ref",
        "dmpl_lasum_report_ref",
    }
    if set(cert_refs_obj.keys()) != expected_keys:
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "certificate_refs keys"})

    # Phase 3: schema + canonical only (schemas are intentionally minimal in this checkout).
    items = [
        ("dmpl_cac_pack_ref", "dmpl_cac_pack_v1"),
        ("dmpl_ufc_flow_ref", "dmpl_ufc_flow_v1"),
        ("dmpl_stab_report_ref", "dmpl_stab_report_v1"),
        ("dmpl_lasum_report_ref", "dmpl_lasum_report_v1"),
    ]
    for key, schema_name in items:
        ref = cert_refs_obj.get(key)
        if ref is None:
            continue
        if not isinstance(ref, dict):
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "bad certificate ref", "key": str(key)})
        obj = _load_canon_json_by_ref(resolver=resolver, artifact_ref=dict(ref))
        try:
            validate_schema(obj, schema_name)
        except Exception:
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "certificate schema", "schema": str(schema_name)})
        if str(obj.get("schema_id", "")).strip() != str(schema_name):
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "certificate schema_id", "schema": str(schema_name)})


__all__ = [
    "verify_dmpl_certificates_struct_v1",
    "verify_dmpl_certificates_gated_v1",
]


_U32LE = struct.Struct("<I")
_EMPTY_CHUNKS_DOMAIN = b"DMPL/CHUNKS/EMPTY/v1\x00"


def _sha25632(data: bytes) -> bytes:
    return hashlib.sha256(bytes(data)).digest()


def _sha256_id(data: bytes) -> str:
    return f"sha256:{_sha25632(data).hex()}"


def _require_sha256_id(value: Any, *, reason: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != (len("sha256:") + 64):
        raise DMPLError(reason_code=reason, details={"value": str(value)})
    try:
        bytes.fromhex(value.split(":", 1)[1])
    except Exception:
        raise DMPLError(reason_code=reason, details={"value": str(value)})
    return str(value)


def _load_json_by_id_and_type(*, resolver: Any, artifact_id: str, artifact_type: str, schema_validate: bool = True) -> dict[str, Any]:
    try:
        fn = getattr(resolver, "load_artifact_bytes")
    except Exception:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver missing load_artifact_bytes"})
    if not callable(fn):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver.load_artifact_bytes not callable"})
    raw = fn(artifact_id=str(artifact_id), artifact_type=str(artifact_type), ext="json")
    if not isinstance(raw, (bytes, bytearray, memoryview)):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver returned non-bytes"})
    b = bytes(raw)
    if _sha256_id(b) != str(artifact_id).strip():
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"artifact_id": str(artifact_id), "artifact_type": str(artifact_type)})
    try:
        obj = gcj1_loads_and_verify_canonical(b)
    except OmegaV18Error:
        raise DMPLError(reason_code=DMPL_E_NONCANON_GCJ1, details={"artifact_id": str(artifact_id), "artifact_type": str(artifact_type)})
    if not isinstance(obj, dict):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"artifact_type": str(artifact_type), "hint": "not dict"})
    _require_no_abs_paths(obj)
    if schema_validate:
        try:
            validate_schema(obj, str(artifact_type))
        except Exception:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"artifact_id": str(artifact_id), "artifact_type": str(artifact_type)})
        if str(obj.get("schema_id", "")).strip() != str(artifact_type):
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "schema_id mismatch", "artifact_type": str(artifact_type)})
    return dict(obj)


def _load_bin_by_id_and_type(*, resolver: Any, artifact_id: str, artifact_type: str, expected_len: int | None = None) -> bytes:
    try:
        fn = getattr(resolver, "load_artifact_bytes")
    except Exception:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver missing load_artifact_bytes"})
    if not callable(fn):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver.load_artifact_bytes not callable"})
    raw = fn(artifact_id=str(artifact_id), artifact_type=str(artifact_type), ext="bin")
    if not isinstance(raw, (bytes, bytearray, memoryview)):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver returned non-bytes"})
    b = bytes(raw)
    if expected_len is not None and int(len(b)) != int(expected_len):
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "bin len mismatch"})
    if _sha256_id(b) != str(artifact_id).strip():
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"artifact_id": str(artifact_id), "artifact_type": str(artifact_type)})
    return b


def _require_sorted_contiguous_chunks(chunks_obj: Any) -> list[dict[str, Any]]:
    if not isinstance(chunks_obj, list):
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "chunks not list"})
    chunks: list[dict[str, Any]] = []
    for row in chunks_obj:
        if not isinstance(row, dict):
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "chunk row type"})
        chunks.append(dict(row))
    chunks.sort(key=lambda r: int(r.get("chunk_index_u32", -1)))
    for i, row in enumerate(chunks):
        idx = row.get("chunk_index_u32")
        if not isinstance(idx, int) or int(idx) != int(i):
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "chunk indices", "at": int(i), "got": idx})
    return chunks


def _load_chunks_stream(*, resolver: Any, chunks: list[dict[str, Any]], artifact_type: str) -> tuple[bytes, list[bytes]]:
    chunk_hashes32: list[bytes] = []
    out: list[bytes] = []
    for row in chunks:
        chunk_bin_id = str(row.get("chunk_bin_id", "")).strip()
        chunk_bytes_u32 = row.get("chunk_bytes_u32")
        if not isinstance(chunk_bytes_u32, int):
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "chunk_bytes_u32 type"})
        b = _load_bin_by_id_and_type(resolver=resolver, artifact_id=chunk_bin_id, artifact_type=str(artifact_type), expected_len=int(chunk_bytes_u32))
        out.append(b)
        chunk_hashes32.append(_sha25632(b))
    return b"".join(out), chunk_hashes32


def _recompute_chunks_merkle_root_id(*, record_count_u64: int, chunk_hashes32: list[bytes]) -> str:
    if int(record_count_u64) == 0:
        root32 = _sha25632(_EMPTY_CHUNKS_DOMAIN)
    else:
        from .dmpl_merkle_v1 import compute_chunk_merkle_root_v1

        root32 = compute_chunk_merkle_root_v1([bytes(h) for h in chunk_hashes32])
    return f"sha256:{bytes(root32).hex()}"


def _q32(obj: dict[str, Any], key: str, *, reason: str) -> int:
    v = obj.get(key)
    if not isinstance(v, dict) or set(v.keys()) != {"q"}:
        raise DMPLError(reason_code=reason, details={"hint": f"bad q32 {key}"})
    q = v.get("q")
    if not isinstance(q, int):
        raise DMPLError(reason_code=reason, details={"hint": f"bad q32 {key}"})
    return int(q)


def _bound_score_q32_from_action_receipt(action_receipt_obj: dict[str, Any], *, reason: str) -> int:
    t = action_receipt_obj.get("tie_break_proof")
    if not isinstance(t, dict):
        raise DMPLError(reason_code=reason, details={"hint": "tie_break_proof"})
    keys = t.get("ordering_keys")
    if not isinstance(keys, list) or len(keys) != 1 or not isinstance(keys[0], dict):
        raise DMPLError(reason_code=reason, details={"hint": "ordering_keys"})
    return int(_q32(keys[0], "bound_score_q32", reason=reason))


def _require_plan_evidence_triple_present(
    *,
    plan_evidence_obj: list[dict[str, Any]],
    plan_query_id: str,
    rollout_trace_id: str,
    action_receipt_id: str,
) -> None:
    pq = str(plan_query_id).strip()
    rt = str(rollout_trace_id).strip()
    ar = str(action_receipt_id).strip()
    for item in plan_evidence_obj:
        if not isinstance(item, dict):
            continue
        pq_ref = item.get("plan_query_ref")
        rt_ref = item.get("rollout_trace_ref")
        ar_ref = item.get("action_receipt_ref")
        if not isinstance(pq_ref, dict) or not isinstance(rt_ref, dict) or not isinstance(ar_ref, dict):
            continue
        if str(pq_ref.get("artifact_id", "")).strip() == pq and str(rt_ref.get("artifact_id", "")).strip() == rt and str(ar_ref.get("artifact_id", "")).strip() == ar:
            return
    raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "missing referenced plan evidence"})


def _reconstruct_chosen_path_from_trace(
    *,
    rollout_trace_obj: dict[str, Any],
    action_receipt_obj: dict[str, Any],
    resolver: Any,
) -> list[dict[str, Any]]:
    # Load + parse rollout trace records (EXPAND stream).
    record_count = rollout_trace_obj.get("record_count_u64")
    if not isinstance(record_count, int) or int(record_count) < 0:
        raise DMPLError(reason_code=DMPL_E_UFC_INVALID, details={"hint": "record_count_u64"})
    chunks = _require_sorted_contiguous_chunks(rollout_trace_obj.get("chunks"))
    stream, _chunk_hashes32 = _load_chunks_stream(resolver=resolver, chunks=chunks, artifact_type="dmpl_rollout_trace_chunk_v1")
    record_objs, _record_raws = parse_lenpref_canonjson_stream_v1(stream_bytes=stream, record_count_u64=int(record_count))

    nodes: dict[str, dict[str, Any]] = {}
    for rec in record_objs:
        if not isinstance(rec, dict):
            continue
        if str(rec.get("record_kind", "")).strip() != "EXPAND":
            continue
        node_id = str(rec.get("node_id", "")).strip()
        if node_id:
            nodes[node_id] = dict(rec)

    leaf_id = str(action_receipt_obj.get("chosen_node_id", "")).strip()
    if not leaf_id:
        raise DMPLError(reason_code=DMPL_E_UFC_INVALID, details={"hint": "chosen_node_id"})

    # Collect records from leaf->root (excluding root).
    rev: list[dict[str, Any]] = []
    cur = str(leaf_id)
    while cur in nodes:
        rec = nodes[cur]
        rev.append(rec)
        cur = str(rec.get("parent_id", "")).strip()
        if not cur:
            break
    rev.reverse()
    return rev


def _recompute_ufc_for_scenario(
    *,
    scenario_id: str,
    chosen_action_receipt_id: str,
    chosen_rollout_trace_id: str,
    rollout_trace_obj: dict[str, Any],
    action_receipt_obj: dict[str, Any],
    gamma_q32: int,
    resolver: Any,
) -> dict[str, Any]:
    path_recs = _reconstruct_chosen_path_from_trace(rollout_trace_obj=rollout_trace_obj, action_receipt_obj=action_receipt_obj, resolver=resolver)

    # Precompute gamma_pow up to max depth needed.
    max_depth = 0
    for rec in path_recs:
        depth_u32 = rec.get("depth_u32")
        if isinstance(depth_u32, int) and int(depth_u32) > max_depth:
            max_depth = int(depth_u32)
    # Need gamma_pow[max_depth] at least.
    gamma_pow: list[int] = [int(Q32_ONE)]
    for _t in range(int(max_depth) + 2):
        gamma_pow.append(int(mul_q32(int(gamma_pow[-1]), int(gamma_q32))))

    sum_discounted = 0
    path_out: list[dict[str, Any]] = []
    for rec in path_recs:
        depth_child = rec.get("depth_u32")
        if not isinstance(depth_child, int) or depth_child <= 0:
            raise DMPLError(reason_code=DMPL_E_UFC_INVALID, details={"hint": "depth_u32"})
        depth_parent = int(depth_child) - 1

        r_hat_obj = rec.get("r_hat_q32")
        if not isinstance(r_hat_obj, dict):
            raise DMPLError(reason_code=DMPL_E_UFC_INVALID, details={"hint": "r_hat_q32"})
        r_hat_q32 = int(r_hat_obj.get("q", 0))

        gp = int(gamma_pow[depth_parent])
        discounted_r = int(mul_q32(int(gp), int(r_hat_q32)))
        sum_discounted = add_sat(int(sum_discounted), int(discounted_r))

        gate_active = rec.get("gate_active")
        if not isinstance(gate_active, list):
            raise DMPLError(reason_code=DMPL_E_UFC_INVALID, details={"hint": "gate_active"})

        path_out.append(
            {
                "depth_u32": int(depth_parent) & 0xFFFFFFFF,
                "r_hat_q32": {"q": int(r_hat_q32)},
                "gamma_pow_q32": {"q": int(gp)},
                "discounted_r_q32": {"q": int(discounted_r)},
                "gate_active": list(gate_active),
            }
        )

    if path_recs:
        leaf_rec = path_recs[-1]
        leaf_depth = int(leaf_rec.get("depth_u32", 0))
        v_term_obj = leaf_rec.get("v_tp1_q32")
        if not isinstance(v_term_obj, dict):
            raise DMPLError(reason_code=DMPL_E_UFC_INVALID, details={"hint": "v_tp1_q32"})
        v_term_q32 = int(v_term_obj.get("q", 0))
        gp_term = int(gamma_pow[leaf_depth])
        discounted_v = int(mul_q32(int(gp_term), int(v_term_q32)))
        sum_discounted = add_sat(int(sum_discounted), int(discounted_v))
        terminal_obj = {
            "depth_u32": int(leaf_depth) & 0xFFFFFFFF,
            "v_term_q32": {"q": int(v_term_q32)},
            "gamma_pow_q32": {"q": int(gp_term)},
            "discounted_v_q32": {"q": int(discounted_v)},
        }
    else:
        terminal_obj = {
            "depth_u32": 0,
            "v_term_q32": {"q": 0},
            "gamma_pow_q32": {"q": int(Q32_ONE)},
            "discounted_v_q32": {"q": 0},
        }

    bound_score_q32 = _bound_score_q32_from_action_receipt(action_receipt_obj, reason=DMPL_E_UFC_INVALID)
    sum_check_b = bool(int(sum_discounted) == int(bound_score_q32))

    return {
        "scenario_id": str(scenario_id),
        "chosen_action_receipt_id": str(chosen_action_receipt_id),
        "chosen_rollout_trace_id": str(chosen_rollout_trace_id),
        "path": path_out,
        "terminal": terminal_obj,
        "sum_discounted_q32": {"q": int(sum_discounted)},
        "bound_score_q32": {"q": int(bound_score_q32)},
        "sum_check_b": bool(sum_check_b),
    }


def _load_train_evidence_from_resolver(resolver: Any) -> dict[str, Any]:
    ev = getattr(resolver, "_dmpl_train_evidence_v1", None)
    if not isinstance(ev, dict):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver missing train evidence"})
    return dict(ev)


def _load_training_triplet_from_resolver(*, resolver: Any) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    ev = _load_train_evidence_from_resolver(resolver)
    for k in ("dmpl_train_run_ref", "dmpl_train_trace_ref", "dmpl_train_receipt_ref"):
        if k not in ev:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "train_evidence keys"})
    run = _load_canon_json_by_ref(resolver=resolver, artifact_ref=dict(ev["dmpl_train_run_ref"]))
    trace = _load_canon_json_by_ref(resolver=resolver, artifact_ref=dict(ev["dmpl_train_trace_ref"]))
    receipt = _load_canon_json_by_ref(resolver=resolver, artifact_ref=dict(ev["dmpl_train_receipt_ref"]))
    # Schema validate now (fail-closed).
    try:
        validate_schema(run, "dmpl_train_run_v1")
        validate_schema(trace, "dmpl_train_trace_v1")
        validate_schema(receipt, "dmpl_train_receipt_v1")
    except Exception:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "train evidence schema"})
    return dict(run), dict(trace), dict(receipt)


def _compute_holdout_mean_L1_pred_q32(
    *,
    candidate_droot_id: str,
    dataset_pack_obj: dict[str, Any],
    config_obj: dict[str, Any],
    resolver: Any,
) -> int:
    # Parse dataset samples.
    sample_count = dataset_pack_obj.get("sample_count_u64")
    if not isinstance(sample_count, int) or int(sample_count) < 0:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "sample_count_u64"})
    chunks = _require_sorted_contiguous_chunks(dataset_pack_obj.get("chunks"))
    stream, _chunk_hashes32 = _load_chunks_stream(resolver=resolver, chunks=chunks, artifact_type="dmpl_dataset_chunk_v1")
    sample_objs, _raws = parse_lenpref_canonjson_stream_v1(stream_bytes=stream, record_count_u64=int(sample_count))

    # Deterministic filter: episode_id sha256 last-bit == 1, take first up to min(256, sample_count).
    limit = min(256, int(sample_count))
    selected: list[dict[str, Any]] = []
    for rec in sample_objs:
        if len(selected) >= limit:
            break
        if not isinstance(rec, dict):
            continue
        episode_id = rec.get("episode_id")
        if not isinstance(episode_id, str) or not episode_id:
            continue
        h = hashlib.sha256(episode_id.encode("utf-8", errors="strict")).digest()
        if (h[-1] & 1) == 1:
            selected.append(dict(rec))
    if not selected:
        return 0

    # Load candidate runtime params.
    runtime = load_runtime_from_droot_v1(str(candidate_droot_id), resolver)
    d = int(runtime.dims.d_u32)
    p = int(runtime.dims.p_u32)
    embed_dim = int(runtime.dims.embed_dim_u32)

    (A0_dims, A0_vals) = runtime.base_forward["A0"]
    (B0_dims, B0_vals) = runtime.base_forward["B0"]
    (b0_dims, b0_vals) = runtime.base_forward["b0"]
    (Wg_dims, Wg_vals) = runtime.base_forward["Wg"]
    (w0_dims, w0_vals) = runtime.base_value["w0"]
    (v0_dims, v0_vals) = runtime.base_value["v0"]
    require_shape(A0_dims, [d, d])
    require_shape(B0_dims, [d, p])
    require_shape(b0_dims, [d])
    require_shape(Wg_dims, [embed_dim, d])
    require_shape(w0_dims, [d])
    require_shape(v0_dims, [1])
    if len(v0_vals) != 1:
        raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "v0 len"})

    state = TrainableStateV1(
        A0_q32=[int(v) for v in A0_vals],
        B0_q32=[int(v) for v in B0_vals],
        b0_q32=[int(v) for v in b0_vals],
        Wg_q32=[int(v) for v in Wg_vals],
        w0_q32=[int(v) for v in w0_vals],
        v0_q32=int(v0_vals[0]),
    )

    gating_spec = config_obj.get("gating_spec")
    if not isinstance(gating_spec, dict):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "gating_spec"})
    normalize_weights_b = bool(gating_spec.get("normalize_weights_b", False))
    epsilon_q32_obj = gating_spec.get("epsilon_q32")
    if not isinstance(epsilon_q32_obj, dict) or set(epsilon_q32_obj.keys()) != {"q"}:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "epsilon_q32"})
    epsilon_q32 = int(epsilon_q32_obj.get("q", 0))

    objective_spec = config_obj.get("objective_spec")
    if not isinstance(objective_spec, dict):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "objective_spec"})
    gamma_q32_obj = objective_spec.get("gamma_q32")
    if not isinstance(gamma_q32_obj, dict) or set(gamma_q32_obj.keys()) != {"q"}:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "gamma_q32"})
    gamma_q32 = int(gamma_q32_obj.get("q", 0))

    # Concept patch cache (concept_id, ladder_level_u32) -> entry.
    concept_cache: dict[tuple[str, int], ConceptPatchEntryV1] = {}

    def _load_concept_patch_entry(concept_id: str, ladder_level_u32: int) -> ConceptPatchEntryV1:
        key = (str(concept_id), int(ladder_level_u32))
        hit = concept_cache.get(key)
        if hit is not None:
            return hit
        concept_obj = _load_json_by_id_and_type(resolver=resolver, artifact_id=str(concept_id), artifact_type="dmpl_concept_shard_v1")
        embed_bin_id = str(concept_obj.get("embed_tensor_bin_id", "")).strip()
        embed_raw = _load_bin_by_id_and_type(resolver=resolver, artifact_id=embed_bin_id, artifact_type="dmpl_tensor_q32_v1")
        embed_dims, embed_vals = parse_tensor_q32_v1(embed_raw)
        require_shape(embed_dims, [embed_dim])

        patches = concept_obj.get("patches_by_level")
        if not isinstance(patches, list) or not patches:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "patches_by_level"})
        patch_row: dict[str, Any] | None = None
        for row in patches:
            if not isinstance(row, dict):
                continue
            if int(row.get("ladder_level_u32", -1)) == int(ladder_level_u32):
                patch_row = dict(row)
                break
        if patch_row is None:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "missing ladder level"})

        patch_kind = str(patch_row.get("patch_kind", "")).strip()
        v_c0_q32 = int((patch_row.get("v_c0_q32") or {}).get("q", 0))
        w_vec: list[int] | None = None
        w_bin_id = str(patch_row.get("w_bin_id", "")).strip()
        if w_bin_id != "sha256:" + ("0" * 64):
            w_raw = _load_bin_by_id_and_type(resolver=resolver, artifact_id=w_bin_id, artifact_type="dmpl_tensor_q32_v1")
            w_dims, w_vals = parse_tensor_q32_v1(w_raw)
            require_shape(w_dims, [d])
            w_vec = [int(v) for v in w_vals]

        # Only load forward patch tensors when needed.
        A_vals = B_vals = b_vals = None
        rank_u32 = None
        A_u_vals = A_v_vals = B_u_vals = B_v_vals = None
        if patch_kind == "matrix_patch":
            A_id = str(patch_row.get("A_bin_id", "")).strip()
            B_id = str(patch_row.get("B_bin_id", "")).strip()
            b_id = str(patch_row.get("b_bin_id", "")).strip()
            A_raw = _load_bin_by_id_and_type(resolver=resolver, artifact_id=A_id, artifact_type="dmpl_tensor_q32_v1")
            B_raw = _load_bin_by_id_and_type(resolver=resolver, artifact_id=B_id, artifact_type="dmpl_tensor_q32_v1")
            b_raw = _load_bin_by_id_and_type(resolver=resolver, artifact_id=b_id, artifact_type="dmpl_tensor_q32_v1")
            A_dims, A_vals2 = parse_tensor_q32_v1(A_raw)
            B_dims, B_vals2 = parse_tensor_q32_v1(B_raw)
            b_dims, b_vals2 = parse_tensor_q32_v1(b_raw)
            require_shape(A_dims, [d, d])
            require_shape(B_dims, [d, p])
            require_shape(b_dims, [d])
            A_vals = [int(v) for v in A_vals2]
            B_vals = [int(v) for v in B_vals2]
            b_vals = [int(v) for v in b_vals2]
        elif patch_kind == "lowrank_patch":
            rank_u32 = int(patch_row.get("rank_u32", 0))
            A_u_id = str(patch_row.get("A_u_bin_id", "")).strip()
            A_v_id = str(patch_row.get("A_v_bin_id", "")).strip()
            B_u_id = str(patch_row.get("B_u_bin_id", "")).strip()
            B_v_id = str(patch_row.get("B_v_bin_id", "")).strip()
            b_id = str(patch_row.get("b_bin_id", "")).strip()
            A_u_raw = _load_bin_by_id_and_type(resolver=resolver, artifact_id=A_u_id, artifact_type="dmpl_tensor_q32_v1")
            A_v_raw = _load_bin_by_id_and_type(resolver=resolver, artifact_id=A_v_id, artifact_type="dmpl_tensor_q32_v1")
            B_u_raw = _load_bin_by_id_and_type(resolver=resolver, artifact_id=B_u_id, artifact_type="dmpl_tensor_q32_v1")
            B_v_raw = _load_bin_by_id_and_type(resolver=resolver, artifact_id=B_v_id, artifact_type="dmpl_tensor_q32_v1")
            b_raw = _load_bin_by_id_and_type(resolver=resolver, artifact_id=b_id, artifact_type="dmpl_tensor_q32_v1")
            A_u_dims, A_u_vals2 = parse_tensor_q32_v1(A_u_raw)
            A_v_dims, A_v_vals2 = parse_tensor_q32_v1(A_v_raw)
            B_u_dims, B_u_vals2 = parse_tensor_q32_v1(B_u_raw)
            B_v_dims, B_v_vals2 = parse_tensor_q32_v1(B_v_raw)
            b_dims, b_vals2 = parse_tensor_q32_v1(b_raw)
            require_shape(A_u_dims, [d, rank_u32])
            require_shape(A_v_dims, [rank_u32, d])
            require_shape(B_u_dims, [d, rank_u32])
            require_shape(B_v_dims, [rank_u32, p])
            require_shape(b_dims, [d])
            A_u_vals = [int(v) for v in A_u_vals2]
            A_v_vals = [int(v) for v in A_v_vals2]
            B_u_vals = [int(v) for v in B_u_vals2]
            B_v_vals = [int(v) for v in B_v_vals2]
            b_vals = [int(v) for v in b_vals2]

        entry = ConceptPatchEntryV1(
            concept_shard_id=str(concept_id),
            embed_vec_q32=[int(v) for v in embed_vals],
            patch_kind=str(patch_kind),
            A_vals_q32=A_vals,
            B_vals_q32=B_vals,
            b_vals_q32=b_vals,
            rank_u32=rank_u32,
            A_u_vals_q32=A_u_vals,
            A_v_vals_q32=A_v_vals,
            B_u_vals_q32=B_u_vals,
            B_v_vals_q32=B_v_vals,
            v_c0_q32=int(v_c0_q32),
            w_vec_q32=w_vec,
        )
        concept_cache[key] = entry
        return entry

    sum_L_pred = 0
    for rec in selected:
        z_t_bin_id = _require_sha256_id(rec.get("z_t_bin_id"), reason=DMPL_E_HASH_MISMATCH)
        z_true_bin_id = _require_sha256_id(rec.get("z_tp1_true_bin_id"), reason=DMPL_E_HASH_MISMATCH)
        z_t_raw = _load_bin_by_id_and_type(resolver=resolver, artifact_id=z_t_bin_id, artifact_type="dmpl_tensor_q32_v1")
        z_true_raw = _load_bin_by_id_and_type(resolver=resolver, artifact_id=z_true_bin_id, artifact_type="dmpl_tensor_q32_v1")
        z_t_dims, z_t_vals = parse_tensor_q32_v1(z_t_raw)
        z_true_dims, z_true_vals = parse_tensor_q32_v1(z_true_raw)
        require_shape(z_t_dims, [d])
        require_shape(z_true_dims, [d])

        action_record_id = _require_sha256_id(rec.get("action_record_id"), reason=DMPL_E_HASH_MISMATCH)
        action_obj = _load_json_by_id_and_type(resolver=resolver, artifact_id=action_record_id, artifact_type="dmpl_action_v1", schema_validate=False)

        ladder_level_u32 = rec.get("ladder_level_u32")
        if not isinstance(ladder_level_u32, int):
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "ladder_level_u32"})

        active_concepts = rec.get("active_concepts")
        if not isinstance(active_concepts, list):
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "active_concepts"})
        concept_ids: list[str] = []
        prev: str | None = None
        for cid in active_concepts:
            c = _require_sha256_id(cid, reason=DMPL_E_HASH_MISMATCH)
            if prev is not None and c <= prev:
                raise DMPLError(reason_code=DMPL_E_REDUCTION_ORDER_VIOLATION, details={"hint": "active_concepts order"})
            prev = c
            concept_ids.append(c)

        concept_entries = [_load_concept_patch_entry(c, int(ladder_level_u32)) for c in concept_ids]

        # Use lr=0 to prevent mutation; copy state for safety.
        tmp_state = TrainableStateV1(
            A0_q32=list(state.A0_q32),
            B0_q32=list(state.B0_q32),
            b0_q32=list(state.b0_q32),
            Wg_q32=list(state.Wg_q32),
            w0_q32=list(state.w0_q32),
            v0_q32=int(state.v0_q32),
        )
        step_res = train_step_sgd_det_v1(
            d_u32=int(d),
            p_u32=int(p),
            embed_dim_u32=int(embed_dim),
            gamma_q32=int(gamma_q32),
            normalize_weights_b=bool(normalize_weights_b),
            epsilon_q32=int(epsilon_q32),
            max_grad_norm_q32=0,
            lr_q32=0,
            state=tmp_state,
            batch=[rec],
            concept_patches_by_sample=[concept_entries],
            action_objs=[dict(action_obj)],
            z_t_vecs_q32=[[int(v) for v in z_t_vals]],
            z_tp1_true_vecs_q32=[[int(v) for v in z_true_vals]],
        )
        sum_L_pred = add_sat(int(sum_L_pred), int(step_res.loss_pred_q32))

    denom = int(len(selected)) << 32
    if denom <= 0:
        return 0
    try:
        mean = int(div_q32_pos_rne_v1(numer_q32_s64=int(sum_L_pred), denom_q32_pos_s64=int(denom), ctr=None))
    except Exception:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "holdout div failed"})
    return int(mean)


def verify_dmpl_certificates_gated_v1(
    *,
    cert_refs_obj: dict,
    plan_evidence_obj: list[dict],
    config_obj: dict,
    resolver: Any,
) -> None:
    # DMPL enabled path only.
    if not isinstance(config_obj, dict):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "config_obj type"})
    if not bool(config_obj.get("enabled_b", False)):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "DMPL disabled in gated verifier"})

    if not isinstance(plan_evidence_obj, list) or not plan_evidence_obj:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "plan_evidence empty"})

    if not isinstance(cert_refs_obj, dict):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "certificate_refs not dict"})
    expected_keys = {
        "dmpl_cac_pack_ref",
        "dmpl_ufc_flow_ref",
        "dmpl_stab_report_ref",
        "dmpl_lasum_report_ref",
    }
    if set(cert_refs_obj.keys()) != expected_keys:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "certificate_refs keys"})

    # Require all cert refs are non-null.
    for k in sorted(expected_keys):
        if cert_refs_obj.get(k) is None:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "missing certificate ref", "key": str(k)})
        if not isinstance(cert_refs_obj.get(k), dict):
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "bad certificate ref", "key": str(k)})

    # Load cert objects by ArtifactRef and schema validate.
    cac_obj = _load_canon_json_by_ref(resolver=resolver, artifact_ref=dict(cert_refs_obj["dmpl_cac_pack_ref"]))
    ufc_obj = _load_canon_json_by_ref(resolver=resolver, artifact_ref=dict(cert_refs_obj["dmpl_ufc_flow_ref"]))
    stab_obj = _load_canon_json_by_ref(resolver=resolver, artifact_ref=dict(cert_refs_obj["dmpl_stab_report_ref"]))
    lasum_obj = _load_canon_json_by_ref(resolver=resolver, artifact_ref=dict(cert_refs_obj["dmpl_lasum_report_ref"]))
    try:
        validate_schema(cac_obj, "dmpl_cac_pack_v1")
        validate_schema(ufc_obj, "dmpl_ufc_flow_v1")
        validate_schema(stab_obj, "dmpl_stab_report_v1")
        validate_schema(lasum_obj, "dmpl_lasum_report_v1")
    except Exception:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "certificate schema"})

    # Load train evidence (needed for baseline/candidate droot IDs and dataset).
    train_run_obj, train_trace_obj, train_receipt_obj = _load_training_triplet_from_resolver(resolver=resolver)
    baseline_droot_id = _require_sha256_id(train_receipt_obj.get("baseline_droot_id"), reason=DMPL_E_HASH_MISMATCH)
    candidate_droot_id = _require_sha256_id(train_receipt_obj.get("candidate_droot_id"), reason=DMPL_E_HASH_MISMATCH)

    # Enforce eval_suite_id equality across certs.
    eval_suite_id = _require_sha256_id(cac_obj.get("eval_suite_id"), reason=DMPL_E_OPSET_MISMATCH)
    if _require_sha256_id(ufc_obj.get("eval_suite_id"), reason=DMPL_E_OPSET_MISMATCH) != eval_suite_id:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "eval_suite_id mismatch (ufc)"})
    if _require_sha256_id(stab_obj.get("eval_suite_id"), reason=DMPL_E_OPSET_MISMATCH) != eval_suite_id:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "eval_suite_id mismatch (stab)"})
    if _require_sha256_id(lasum_obj.get("eval_suite_id"), reason=DMPL_E_OPSET_MISMATCH) != eval_suite_id:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "eval_suite_id mismatch (lasum)"})

    # CAC verification.
    if str(cac_obj.get("baseline_droot_id", "")).strip() != str(baseline_droot_id).strip():
        raise DMPLError(reason_code=DMPL_E_CAC_FAIL, details={"hint": "baseline_droot_id mismatch"})
    if str(cac_obj.get("candidate_droot_id", "")).strip() != str(candidate_droot_id).strip():
        raise DMPLError(reason_code=DMPL_E_CAC_FAIL, details={"hint": "candidate_droot_id mismatch"})

    gating_spec = config_obj.get("gating_spec")
    if not isinstance(gating_spec, dict):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "gating_spec"})
    theta_obj = gating_spec.get("theta_cac_lb_q32")
    if not isinstance(theta_obj, dict) or set(theta_obj.keys()) != {"q"}:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "theta_cac_lb_q32"})
    theta_cac = int(theta_obj.get("q", 0))

    per_scenario = cac_obj.get("per_scenario")
    if not isinstance(per_scenario, list) or not per_scenario:
        raise DMPLError(reason_code=DMPL_E_CAC_FAIL, details={"hint": "per_scenario"})
    prev_sid: str | None = None
    deltas: list[int] = []
    for row in per_scenario:
        if not isinstance(row, dict):
            raise DMPLError(reason_code=DMPL_E_CAC_FAIL, details={"hint": "scenario row type"})
        sid = str(row.get("scenario_id", "")).strip()
        if not sid:
            raise DMPLError(reason_code=DMPL_E_CAC_FAIL, details={"hint": "scenario_id"})
        if prev_sid is not None and sid <= prev_sid:
            raise DMPLError(reason_code=DMPL_E_CAC_FAIL, details={"hint": "scenario_id order"})
        prev_sid = sid

        base_ev = row.get("baseline_plan_evidence")
        cand_ev = row.get("candidate_plan_evidence")
        if not isinstance(base_ev, dict) or not isinstance(cand_ev, dict):
            raise DMPLError(reason_code=DMPL_E_CAC_FAIL, details={"hint": "plan evidence ids"})
        base_pq = _require_sha256_id(base_ev.get("plan_query_id"), reason=DMPL_E_HASH_MISMATCH)
        base_rt = _require_sha256_id(base_ev.get("rollout_trace_id"), reason=DMPL_E_HASH_MISMATCH)
        base_ar = _require_sha256_id(base_ev.get("action_receipt_id"), reason=DMPL_E_HASH_MISMATCH)
        cand_pq = _require_sha256_id(cand_ev.get("plan_query_id"), reason=DMPL_E_HASH_MISMATCH)
        cand_rt = _require_sha256_id(cand_ev.get("rollout_trace_id"), reason=DMPL_E_HASH_MISMATCH)
        cand_ar = _require_sha256_id(cand_ev.get("action_receipt_id"), reason=DMPL_E_HASH_MISMATCH)

        _require_plan_evidence_triple_present(plan_evidence_obj=plan_evidence_obj, plan_query_id=base_pq, rollout_trace_id=base_rt, action_receipt_id=base_ar)
        _require_plan_evidence_triple_present(plan_evidence_obj=plan_evidence_obj, plan_query_id=cand_pq, rollout_trace_id=cand_rt, action_receipt_id=cand_ar)

        base_pq_obj = _load_json_by_id_and_type(resolver=resolver, artifact_id=base_pq, artifact_type="dmpl_plan_query_v1")
        cand_pq_obj = _load_json_by_id_and_type(resolver=resolver, artifact_id=cand_pq, artifact_type="dmpl_plan_query_v1")
        if str(base_pq_obj.get("dmpl_droot_id", "")).strip() != str(baseline_droot_id).strip():
            raise DMPLError(reason_code=DMPL_E_CAC_FAIL, details={"hint": "baseline plan_query droot mismatch"})
        if str(cand_pq_obj.get("dmpl_droot_id", "")).strip() != str(candidate_droot_id).strip():
            raise DMPLError(reason_code=DMPL_E_CAC_FAIL, details={"hint": "candidate plan_query droot mismatch"})
        if str((base_pq_obj.get("call_context") or {}).get("scenario_id", "")).strip() != sid:
            raise DMPLError(reason_code=DMPL_E_CAC_FAIL, details={"hint": "baseline scenario_id mismatch"})
        if str((cand_pq_obj.get("call_context") or {}).get("scenario_id", "")).strip() != sid:
            raise DMPLError(reason_code=DMPL_E_CAC_FAIL, details={"hint": "candidate scenario_id mismatch"})

        base_ar_obj = _load_json_by_id_and_type(resolver=resolver, artifact_id=base_ar, artifact_type="dmpl_action_receipt_v1")
        cand_ar_obj = _load_json_by_id_and_type(resolver=resolver, artifact_id=cand_ar, artifact_type="dmpl_action_receipt_v1")
        J_base = _bound_score_q32_from_action_receipt(base_ar_obj, reason=DMPL_E_CAC_FAIL)
        J_cand = _bound_score_q32_from_action_receipt(cand_ar_obj, reason=DMPL_E_CAC_FAIL)
        delta = add_sat(int(J_cand), int(-int(J_base)))
        if int(_q32(row, "J_base_q32", reason=DMPL_E_CAC_FAIL)) != int(J_base):
            raise DMPLError(reason_code=DMPL_E_CAC_FAIL, details={"hint": "J_base mismatch"})
        if int(_q32(row, "J_cand_q32", reason=DMPL_E_CAC_FAIL)) != int(J_cand):
            raise DMPLError(reason_code=DMPL_E_CAC_FAIL, details={"hint": "J_cand mismatch"})
        if int(_q32(row, "delta_q32", reason=DMPL_E_CAC_FAIL)) != int(delta):
            raise DMPLError(reason_code=DMPL_E_CAC_FAIL, details={"hint": "delta mismatch"})
        deltas.append(int(delta))

    cac_lb = min(deltas)
    if int(_q32(cac_obj, "cac_lb_q32", reason=DMPL_E_CAC_FAIL)) != int(cac_lb):
        raise DMPLError(reason_code=DMPL_E_CAC_FAIL, details={"hint": "cac_lb mismatch"})

    ok_cac = bool(int(cac_lb) >= int(theta_cac))
    status = cac_obj.get("status")
    if not isinstance(status, dict):
        raise DMPLError(reason_code=DMPL_E_CAC_FAIL, details={"hint": "status"})
    if bool(status.get("ok_b", False)) != bool(ok_cac):
        raise DMPLError(reason_code=DMPL_E_CAC_FAIL, details={"hint": "status.ok_b mismatch"})
    if ok_cac:
        if str(status.get("reason_code", "")).strip() != DMPL_OK:
            raise DMPLError(reason_code=DMPL_E_CAC_FAIL, details={"hint": "status.reason_code mismatch"})
    else:
        raise DMPLError(reason_code=DMPL_E_CAC_FAIL, details={"hint": "CAC threshold fail"})

    # UFC verification.
    if str(ufc_obj.get("candidate_droot_id", "")).strip() != str(candidate_droot_id).strip():
        raise DMPLError(reason_code=DMPL_E_UFC_INVALID, details={"hint": "candidate_droot_id mismatch"})
    gamma_obj = (config_obj.get("objective_spec") or {}).get("gamma_q32")
    if not isinstance(gamma_obj, dict) or set(gamma_obj.keys()) != {"q"}:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "gamma_q32"})
    gamma_q32 = int(gamma_obj.get("q", 0))

    ufc_per = ufc_obj.get("per_scenario")
    if not isinstance(ufc_per, list) or not ufc_per:
        raise DMPLError(reason_code=DMPL_E_UFC_INVALID, details={"hint": "per_scenario"})
    prev_sid = None
    for row in ufc_per:
        if not isinstance(row, dict):
            raise DMPLError(reason_code=DMPL_E_UFC_INVALID, details={"hint": "scenario row type"})
        sid = str(row.get("scenario_id", "")).strip()
        if not sid:
            raise DMPLError(reason_code=DMPL_E_UFC_INVALID, details={"hint": "scenario_id"})
        if prev_sid is not None and sid <= prev_sid:
            raise DMPLError(reason_code=DMPL_E_UFC_INVALID, details={"hint": "scenario_id order"})
        prev_sid = sid

        chosen_ar = _require_sha256_id(row.get("chosen_action_receipt_id"), reason=DMPL_E_HASH_MISMATCH)
        chosen_rt = _require_sha256_id(row.get("chosen_rollout_trace_id"), reason=DMPL_E_HASH_MISMATCH)
        # Require referenced evidence is present in plan evidence list.
        found = False
        for it in plan_evidence_obj:
            if not isinstance(it, dict):
                continue
            ar_ref = it.get("action_receipt_ref")
            rt_ref = it.get("rollout_trace_ref")
            if isinstance(ar_ref, dict) and isinstance(rt_ref, dict):
                if str(ar_ref.get("artifact_id", "")).strip() == chosen_ar and str(rt_ref.get("artifact_id", "")).strip() == chosen_rt:
                    found = True
                    break
        if not found:
            raise DMPLError(reason_code=DMPL_E_UFC_INVALID, details={"hint": "missing chosen plan evidence"})

        ar_obj = _load_json_by_id_and_type(resolver=resolver, artifact_id=chosen_ar, artifact_type="dmpl_action_receipt_v1")
        rt_obj = _load_json_by_id_and_type(resolver=resolver, artifact_id=chosen_rt, artifact_type="dmpl_rollout_trace_v1")

        pq_id = _require_sha256_id(ar_obj.get("plan_query_id"), reason=DMPL_E_HASH_MISMATCH)
        pq_obj = _load_json_by_id_and_type(resolver=resolver, artifact_id=pq_id, artifact_type="dmpl_plan_query_v1")
        if str(pq_obj.get("dmpl_droot_id", "")).strip() != str(candidate_droot_id).strip():
            raise DMPLError(reason_code=DMPL_E_UFC_INVALID, details={"hint": "plan_query droot mismatch"})

        exp = _recompute_ufc_for_scenario(
            scenario_id=sid,
            chosen_action_receipt_id=str(chosen_ar),
            chosen_rollout_trace_id=str(chosen_rt),
            rollout_trace_obj=rt_obj,
            action_receipt_obj=ar_obj,
            gamma_q32=int(gamma_q32),
            resolver=resolver,
        )

        if exp["sum_check_b"] is not True:
            raise DMPLError(reason_code=DMPL_E_UFC_INVALID, details={"hint": "sum_check_b false"})

        # Compare stored fields.
        if row != exp:
            raise DMPLError(reason_code=DMPL_E_UFC_INVALID, details={"hint": "ufc flow mismatch"})

    # STAB verification (recompute metrics and require pass).
    if str(stab_obj.get("candidate_droot_id", "")).strip() != str(candidate_droot_id).strip():
        raise DMPLError(reason_code=DMPL_E_STAB_GATE_FAIL_G0, details={"hint": "candidate_droot_id mismatch"})

    stab_thresholds = ((config_obj.get("gating_spec") or {}).get("stab_thresholds") or {})
    if not isinstance(stab_thresholds, dict):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "stab_thresholds"})

    # G0: determinism (metric 0, threshold must be 0).
    thr_G0 = int(((stab_thresholds.get("G0") or {}).get("q", 0)))
    if int(thr_G0) != 0:
        raise DMPLError(reason_code=DMPL_E_STAB_GATE_FAIL_G0, details={"hint": "G0 threshold != 0"})

    # G1: max grad_norm seen from train trace.
    if str(train_trace_obj.get("schema_id", "")).strip() != "dmpl_train_trace_v1":
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "train_trace schema"})
    record_count = train_trace_obj.get("record_count_u64")
    if not isinstance(record_count, int) or int(record_count) < 0:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "train_trace record_count"})
    trace_chunks = _require_sorted_contiguous_chunks(train_trace_obj.get("chunks"))
    trace_stream, _trace_hashes = _load_chunks_stream(resolver=resolver, chunks=trace_chunks, artifact_type="dmpl_train_trace_chunk_v1")
    step_objs, _raws = parse_lenpref_canonjson_stream_v1(stream_bytes=trace_stream, record_count_u64=int(record_count))
    max_grad_seen = 0
    for rec in step_objs:
        if not isinstance(rec, dict):
            continue
        if str(rec.get("record_kind", "")).strip() != "TRAIN_STEP":
            continue
        gn = int((rec.get("grad_norm_q32") or {}).get("q", 0))
        if gn > max_grad_seen:
            max_grad_seen = int(gn)

    thr_G1 = int(((stab_thresholds.get("G1") or {}).get("q", 0)))
    pass_G1 = bool(int(max_grad_seen) <= int(thr_G1))

    # G2: planning budget failures.
    thr_G2 = int(((stab_thresholds.get("G2") or {}).get("q", 0)))
    if int(thr_G2) != 0:
        # v1: threshold pinned to 0.
        raise DMPLError(reason_code=DMPL_E_STAB_GATE_FAIL_G2, details={"hint": "G2 threshold != 0"})
    fail_count = 0
    for item in plan_evidence_obj:
        if not isinstance(item, dict):
            continue
        ar_ref = item.get("action_receipt_ref")
        if not isinstance(ar_ref, dict):
            continue
        ar_id = _require_sha256_id(ar_ref.get("artifact_id"), reason=DMPL_E_HASH_MISMATCH)
        ar_obj = _load_json_by_id_and_type(resolver=resolver, artifact_id=ar_id, artifact_type="dmpl_action_receipt_v1")
        gating_summary = ar_obj.get("gating_summary")
        if not isinstance(gating_summary, dict):
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "gating_summary"})
        status = gating_summary.get("status")
        if not isinstance(status, dict):
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "gating_summary.status"})
        if bool(status.get("ok_b", False)) is not True:
            fail_count += 1
    pass_G2 = bool(fail_count == 0)

    # G3: predictive sanity holdout.
    thr_G3 = int(((stab_thresholds.get("G3") or {}).get("q", 0)))
    dataset_pack_id = _require_sha256_id(train_run_obj.get("dataset_pack_id"), reason=DMPL_E_HASH_MISMATCH)
    dataset_pack_obj = _load_json_by_id_and_type(resolver=resolver, artifact_id=dataset_pack_id, artifact_type="dmpl_dataset_pack_v1")
    mean_L1_pred_q32 = _compute_holdout_mean_L1_pred_q32(candidate_droot_id=candidate_droot_id, dataset_pack_obj=dataset_pack_obj, config_obj=config_obj, resolver=resolver)
    pass_G3 = bool(int(mean_L1_pred_q32) <= int(thr_G3))

    # G4: retrieval stability (plan replay already enforced) => metric 0, threshold pinned to 0.
    thr_G4 = int(((stab_thresholds.get("G4") or {}).get("q", 0)))
    if int(thr_G4) != 0:
        raise DMPLError(reason_code=DMPL_E_STAB_GATE_FAIL_G4, details={"hint": "G4 threshold != 0"})
    retrieval_mismatch_count = 0
    pass_G4 = True

    # G5: reverse consistency (inverse disabled) => metric 0, require threshold >=0.
    thr_G5 = int(((stab_thresholds.get("G5") or {}).get("q", 0)))
    if int(thr_G5) < 0:
        raise DMPLError(reason_code=DMPL_E_STAB_GATE_FAIL_G5, details={"hint": "G5 threshold < 0"})
    pass_G5 = True

    gate_results_exp = {
        "G0": {
            "pass_b": True,
            "metrics": {"metric_q32": {"q": 0}},
            "thresholds": {"threshold_q32": {"q": int(thr_G0)}},
            "reason_code": DMPL_OK,
        },
        "G1": {
            "pass_b": bool(pass_G1),
            "metrics": {"max_grad_norm_seen_q32": {"q": int(max_grad_seen)}},
            "thresholds": {"threshold_q32": {"q": int(thr_G1)}},
            "reason_code": DMPL_OK if pass_G1 else DMPL_E_STAB_GATE_FAIL_G1,
        },
        "G2": {
            "pass_b": bool(pass_G2),
            "metrics": {"planner_budget_fail_count_q32": {"q": int(fail_count)}},
            "thresholds": {"threshold_q32": {"q": int(thr_G2)}},
            "reason_code": DMPL_OK if pass_G2 else DMPL_E_STAB_GATE_FAIL_G2,
        },
        "G3": {
            "pass_b": bool(pass_G3),
            "metrics": {"mean_L1_pred_q32": {"q": int(mean_L1_pred_q32)}},
            "thresholds": {"threshold_q32": {"q": int(thr_G3)}},
            "reason_code": DMPL_OK if pass_G3 else DMPL_E_STAB_GATE_FAIL_G3,
        },
        "G4": {
            "pass_b": bool(pass_G4),
            "metrics": {"retrieval_mismatch_count_q32": {"q": int(retrieval_mismatch_count)}},
            "thresholds": {"threshold_q32": {"q": int(thr_G4)}},
            "reason_code": DMPL_OK,
        },
        "G5": {
            "pass_b": bool(pass_G5),
            "metrics": {"metric_q32": {"q": 0}},
            "thresholds": {"threshold_q32": {"q": int(thr_G5)}},
            "reason_code": DMPL_OK,
        },
    }

    stored_gate_results = stab_obj.get("gate_results")
    if stored_gate_results != gate_results_exp:
        # Deterministic mismatch reporting: first gate that differs (G0..G5).
        for k, code in [
            ("G0", DMPL_E_STAB_GATE_FAIL_G0),
            ("G1", DMPL_E_STAB_GATE_FAIL_G1),
            ("G2", DMPL_E_STAB_GATE_FAIL_G2),
            ("G3", DMPL_E_STAB_GATE_FAIL_G3),
            ("G4", DMPL_E_STAB_GATE_FAIL_G4),
            ("G5", DMPL_E_STAB_GATE_FAIL_G5),
        ]:
            if not (isinstance(stored_gate_results, dict) and stored_gate_results.get(k) == gate_results_exp.get(k)):
                raise DMPLError(reason_code=code, details={"hint": "stab report mismatch", "gate": str(k)})
        raise DMPLError(reason_code=DMPL_E_STAB_GATE_FAIL_G0, details={"hint": "stab report mismatch"})
    if not all(bool(gate_results_exp[k]["pass_b"]) for k in ["G0", "G1", "G2", "G3", "G4", "G5"]):
        # Fail-closed with the first failing gate's code (deterministic order G0..G5).
        for k, code in [
            ("G0", DMPL_E_STAB_GATE_FAIL_G0),
            ("G1", DMPL_E_STAB_GATE_FAIL_G1),
            ("G2", DMPL_E_STAB_GATE_FAIL_G2),
            ("G3", DMPL_E_STAB_GATE_FAIL_G3),
            ("G4", DMPL_E_STAB_GATE_FAIL_G4),
            ("G5", DMPL_E_STAB_GATE_FAIL_G5),
        ]:
            if not bool(gate_results_exp[k]["pass_b"]):
                raise DMPLError(reason_code=code, details={"hint": "stab gate fail"})

    # LA-SUM verification (conservation + exact report match).
    if str(lasum_obj.get("candidate_droot_id", "")).strip() != str(candidate_droot_id).strip():
        raise DMPLError(reason_code=DMPL_E_LASUM_BROKEN, details={"hint": "candidate_droot_id mismatch"})

    normalize_weights_b = bool((config_obj.get("gating_spec") or {}).get("normalize_weights_b", False))

    # Accumulate credits from UFC path reconstructions.
    credit_by_level: dict[int, int] = {}
    credit_by_concept: dict[str, int] = {}
    credit_by_concept["RESIDUAL"] = 0
    total_ufc = 0

    for row in ufc_per:
        sid = str(row.get("scenario_id", "")).strip()
        chosen_ar = _require_sha256_id(row.get("chosen_action_receipt_id"), reason=DMPL_E_HASH_MISMATCH)
        chosen_rt = _require_sha256_id(row.get("chosen_rollout_trace_id"), reason=DMPL_E_HASH_MISMATCH)
        ar_obj = _load_json_by_id_and_type(resolver=resolver, artifact_id=chosen_ar, artifact_type="dmpl_action_receipt_v1")
        rt_obj = _load_json_by_id_and_type(resolver=resolver, artifact_id=chosen_rt, artifact_type="dmpl_rollout_trace_v1")
        path_recs = _reconstruct_chosen_path_from_trace(rollout_trace_obj=rt_obj, action_receipt_obj=ar_obj, resolver=resolver)

        for rec in path_recs:
            ladder_level = int(rec.get("ladder_level_u32", 0))
            r_hat_q32 = int((rec.get("r_hat_q32") or {}).get("q", 0))
            credit_by_level[ladder_level] = add_sat(int(credit_by_level.get(ladder_level, 0)), int(r_hat_q32))

            delta_u = int(r_hat_q32)
            if normalize_weights_b:
                alloc_sum = 0
                gate_active = rec.get("gate_active")
                if not isinstance(gate_active, list):
                    raise DMPLError(reason_code=DMPL_E_LASUM_BROKEN, details={"hint": "gate_active"})
                for g in gate_active:
                    if not isinstance(g, dict):
                        continue
                    cid = str(g.get("concept_shard_id", "")).strip()
                    w_q32 = int((g.get("w_q32") or {}).get("q", 0))
                    alloc = int(mul_q32(int(w_q32), int(delta_u)))
                    credit_by_concept[cid] = add_sat(int(credit_by_concept.get(cid, 0)), int(alloc))
                    alloc_sum = add_sat(int(alloc_sum), int(alloc))
                residual = add_sat(int(delta_u), int(-int(alloc_sum)))
                credit_by_concept["RESIDUAL"] = add_sat(int(credit_by_concept["RESIDUAL"]), int(residual))
            else:
                credit_by_concept["RESIDUAL"] = add_sat(int(credit_by_concept["RESIDUAL"]), int(delta_u))

            total_ufc = add_sat(int(total_ufc), int(delta_u))

        # Terminal: allocate v_term to residual and to leaf ladder level.
        if path_recs:
            leaf = path_recs[-1]
            ladder_level = int(leaf.get("ladder_level_u32", 0))
            v_term_q32 = int((leaf.get("v_tp1_q32") or {}).get("q", 0))
            credit_by_level[ladder_level] = add_sat(int(credit_by_level.get(ladder_level, 0)), int(v_term_q32))
            credit_by_concept["RESIDUAL"] = add_sat(int(credit_by_concept["RESIDUAL"]), int(v_term_q32))
            total_ufc = add_sat(int(total_ufc), int(v_term_q32))

    # Totals + conservation check.
    total_credit = 0
    for v in credit_by_concept.values():
        total_credit = add_sat(int(total_credit), int(v))
    ok_b = bool(int(total_credit) == int(total_ufc))

    # Build canonical arrays.
    credit_by_level_arr = [{"ladder_level_u32": int(k) & 0xFFFFFFFF, "credit_q32": {"q": int(credit_by_level[k])}} for k in sorted(credit_by_level.keys())]
    credit_by_concept_items = []
    for cid in sorted([k for k in credit_by_concept.keys() if k != "RESIDUAL"]):
        credit_by_concept_items.append({"concept_shard_id": str(cid), "credit_q32": {"q": int(credit_by_concept[cid])}})
    credit_by_concept_items.append({"concept_shard_id": "RESIDUAL", "credit_q32": {"q": int(credit_by_concept["RESIDUAL"])}})

    totals_obj = {"total_credit_q32": {"q": int(total_credit)}, "total_ufc_q32": {"q": int(total_ufc)}, "ok_b": bool(ok_b)}
    status_obj = {"ok_b": bool(ok_b), "reason_code": DMPL_OK if ok_b else DMPL_E_LASUM_BROKEN}
    exp_lasum = {
        "schema_id": "dmpl_lasum_report_v1",
        "dc1_id": str(lasum_obj.get("dc1_id", "")).strip(),
        "opset_id": str(lasum_obj.get("opset_id", "")).strip(),
        "candidate_droot_id": str(candidate_droot_id),
        "eval_suite_id": str(eval_suite_id),
        "credit_by_level": credit_by_level_arr,
        "credit_by_concept": credit_by_concept_items,
        "totals": totals_obj,
        "status": status_obj,
    }

    if lasum_obj != exp_lasum:
        raise DMPLError(reason_code=DMPL_E_LASUM_BROKEN, details={"hint": "lasum report mismatch"})
    if not ok_b:
        raise DMPLError(reason_code=DMPL_E_LASUM_BROKEN, details={"hint": "lasum conservation fail"})
