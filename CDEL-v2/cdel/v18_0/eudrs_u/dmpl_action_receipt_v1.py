"""DMPL ActionReceipt emission (v1).

Phase 2 contract: see §3.5 and §5.13.

This module relies on the active artifact writer context (set by the planner/VM).
"""

from __future__ import annotations

from typing import Any

from .dmpl_config_load_v1 import DmplRuntime
from .dmpl_types_v1 import (
    DMPLError,
    DMPL_E_HASH_MISMATCH,
    DMPL_E_OPSET_MISMATCH,
    Q32_ONE,
    _active_artifact_writer,
    _sha25632_count,
    _sha256_id_from_hex_digest32,
)
from .eudrs_u_hash_v1 import gcj1_canon_bytes


def _require_sha256_id(value: Any, *, reason: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != (len("sha256:") + 64):
        raise DMPLError(reason_code=reason, details={"value": str(value)})
    # hex validation
    try:
        bytes.fromhex(value.split(":", 1)[1])
    except Exception:
        raise DMPLError(reason_code=reason, details={"value": str(value)})
    return str(value)


def _write_json_artifact(artifact_type: str, obj: Any) -> str:
    writer = _active_artifact_writer()
    if writer is None:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "no active artifact writer"})
    try:
        fn = getattr(writer, "write_json_artifact")
    except Exception:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "writer missing write_json_artifact"})
    if not callable(fn):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "write_json_artifact not callable"})
    out_id = fn(str(artifact_type), obj)
    return _require_sha256_id(out_id, reason=DMPL_E_HASH_MISMATCH)


def emit_action_receipt_v1(
    runtime: DmplRuntime,
    plan_query_id: str,
    rollout_trace_id: str,
    chosen_action_record_id: str,
    chosen_action_hash_id: str,
    chosen_node_id: str,
    chosen_bound_score_q32: int,
    chosen_depth_u32: int,
    budget_summary: dict,
    status_obj: dict,
) -> str:
    if not isinstance(runtime, DmplRuntime):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "runtime type"})

    plan_query_id = _require_sha256_id(plan_query_id, reason=DMPL_E_OPSET_MISMATCH)
    rollout_trace_id = _require_sha256_id(rollout_trace_id, reason=DMPL_E_OPSET_MISMATCH)
    chosen_action_record_id = _require_sha256_id(chosen_action_record_id, reason=DMPL_E_OPSET_MISMATCH)
    chosen_action_hash_id = _require_sha256_id(chosen_action_hash_id, reason=DMPL_E_OPSET_MISMATCH)
    chosen_node_id = _require_sha256_id(chosen_node_id, reason=DMPL_E_OPSET_MISMATCH)

    if not isinstance(budget_summary, dict):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "budget_summary type"})
    if not isinstance(status_obj, dict):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "status_obj type"})

    ordering_policy = {
        "primary_key_id": "upper_bound_primary_score_desc",
        "secondary_key_id": "depth_asc",
        "tertiary_key_id": "node_id_asc",
    }
    ordering_keys = [
        {
            "candidate_rank_u32": 0,
            "node_id": str(chosen_node_id),
            "bound_score_q32": {"q": int(chosen_bound_score_q32)},
            "depth_u32": int(chosen_depth_u32) & 0xFFFFFFFF,
        }
    ]

    tie_break_core = {
        "ordering_policy": ordering_policy,
        "ordering_keys": ordering_keys,
    }
    proof_digest = _sha256_id_from_hex_digest32(_sha25632_count(gcj1_canon_bytes(tie_break_core)))
    tie_break_proof = dict(tie_break_core)
    tie_break_proof["proof_digest"] = str(proof_digest)

    caps = dict(runtime.caps)
    gating_spec = runtime.config.get("gating_spec")
    if not isinstance(gating_spec, dict):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "gating_spec"})

    gating_summary = {
        "caps_digest": str(runtime.caps_digest),
        "K_ctx_u32": int(caps.get("K_ctx_u32", 0)) & 0xFFFFFFFF,
        "K_g_u32": int(caps.get("K_g_u32", 0)) & 0xFFFFFFFF,
        "inverse_head_enabled_b": bool(gating_spec.get("inverse_head_enabled_b", False)),
        # Phase 2: inverse head not implemented => always 0.
        "rev_err_max_q32": {"q": 0},
        "planner_budget_summary": dict(budget_summary),
        "status": dict(status_obj),
    }

    receipt_obj = {
        "schema_id": "dmpl_action_receipt_v1",
        "dc1_id": str(runtime.dc1_id),
        "opset_id": str(runtime.opset_id),
        "plan_query_id": str(plan_query_id),
        "rollout_trace_id": str(rollout_trace_id),
        "chosen_action_record_id": str(chosen_action_record_id),
        "chosen_action_hash": str(chosen_action_hash_id),
        "chosen_node_id": str(chosen_node_id),
        "tie_break_proof": tie_break_proof,
        "ufc_decomposition": {"schema_id": "dmpl_ufc_decomposition_v1", "terms": {}},
        "gating_summary": gating_summary,
    }

    return _write_json_artifact("dmpl_action_receipt_v1", receipt_obj)


__all__ = [
    "emit_action_receipt_v1",
]

