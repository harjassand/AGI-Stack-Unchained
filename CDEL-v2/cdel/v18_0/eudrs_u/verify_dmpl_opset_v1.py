"""DMPL opset compliance verifier (v1).

Phase 3 contract: reject any semantic drift from pinned v1 IDs/behavior.

This module is RE2: deterministic and fail-closed via DMPLError reason codes.
"""

from __future__ import annotations

from typing import Any

from .dmpl_types_v1 import (
    DMPLError,
    DMPL_E_CONCEPT_PATCH_POLICY_VIOLATION,
    DMPL_E_OPSET_MISMATCH,
    DMPL_E_Q32_VIOLATION,
)


def _req_dict(obj: dict[str, Any], key: str) -> dict[str, Any]:
    value = obj.get(key)
    if not isinstance(value, dict):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": f"{key} not dict"})
    return dict(value)


def _req_bool(obj: dict[str, Any], key: str) -> bool:
    value = obj.get(key)
    if not isinstance(value, bool):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": f"{key} not bool"})
    return bool(value)


def _req_str(obj: dict[str, Any], key: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": f"{key} not str"})
    return str(value).strip()


def _req_i64(obj: dict[str, Any], key: str) -> int:
    value = obj.get(key)
    if not isinstance(value, int):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": f"{key} not int"})
    return int(value)


def _expect_eq(field: str, got: Any, expected: Any, *, reason: str = DMPL_E_OPSET_MISMATCH) -> None:
    if got != expected:
        raise DMPLError(reason_code=reason, details={"field": str(field), "expected": expected, "got": got})


def verify_dmpl_opset_v1(droot_obj: dict, config_obj: dict, modelpack_obj: dict) -> None:
    if not isinstance(droot_obj, dict) or not isinstance(config_obj, dict) or not isinstance(modelpack_obj, dict):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "inputs must be dicts"})

    droot_opset = _req_str(droot_obj, "opset_id")
    droot_dc1 = _req_str(droot_obj, "dc1_id")
    config_opset = _req_str(config_obj, "opset_id")
    config_dc1 = _req_str(config_obj, "dc1_id")
    modelpack_opset = _req_str(modelpack_obj, "opset_id")
    modelpack_dc1 = _req_str(modelpack_obj, "dc1_id")

    # Cross-field identity pins.
    _expect_eq("droot.opset_semantics_id", _req_str(droot_obj, "opset_semantics_id"), droot_opset)
    _expect_eq("config.opset_id", config_opset, droot_opset)
    _expect_eq("modelpack.opset_id", modelpack_opset, droot_opset)
    _expect_eq("config.dc1_id", config_dc1, droot_dc1)
    _expect_eq("modelpack.dc1_id", modelpack_dc1, droot_dc1)

    # Config pinned IDs.
    caps = _req_dict(config_obj, "caps")
    retrieval_spec = _req_dict(config_obj, "retrieval_spec")
    gating_spec = _req_dict(config_obj, "gating_spec")
    planner_spec = _req_dict(config_obj, "planner_spec")
    hash_layout_ids = _req_dict(config_obj, "hash_layout_ids")
    objective_spec = _req_dict(config_obj, "objective_spec")

    _expect_eq("retrieval_spec.key_fn_id", _req_str(retrieval_spec, "key_fn_id"), "dmpl_key_v1")
    _expect_eq("retrieval_spec.score_fn_id", _req_str(retrieval_spec, "score_fn_id"), "ml_index_v1_default")
    _expect_eq("retrieval_spec.tie_rule_id", _req_str(retrieval_spec, "tie_rule_id"), "score_desc_id_asc")
    _expect_eq(
        "retrieval_spec.K_ctx_u32",
        int(_req_i64(retrieval_spec, "K_ctx_u32")) & 0xFFFFFFFFFFFFFFFF,
        int(_req_i64(caps, "K_ctx_u32")) & 0xFFFFFFFFFFFFFFFF,
    )

    _expect_eq("gating_spec.pwl_pos_id", _req_str(gating_spec, "pwl_pos_id"), "pwl_pos_v1")
    normalize_weights_b = _req_bool(gating_spec, "normalize_weights_b")
    inv_q32_id = _req_str(gating_spec, "inv_q32_id")
    if normalize_weights_b:
        _expect_eq("gating_spec.inv_q32_id", inv_q32_id, "div_q32_pos_rne_v1")
        epsilon_q32 = _req_dict(gating_spec, "epsilon_q32")
        if set(epsilon_q32.keys()) != {"q"}:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "epsilon_q32 keys"})
        eps_q = int(_req_i64(epsilon_q32, "q"))
        if eps_q <= 0:
            raise DMPLError(reason_code=DMPL_E_Q32_VIOLATION, details={"field": "epsilon_q32.q", "q": int(eps_q)})
    else:
        _expect_eq("gating_spec.inv_q32_id", inv_q32_id, "")

    # Phase 3 restriction: inverse head is not supported in this checkout.
    if bool(gating_spec.get("inverse_head_enabled_b", False)):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "inverse head enabled"})

    _expect_eq("planner_spec.algorithm_id", _req_str(planner_spec, "algorithm_id"), "dcbts_l_v1")
    _expect_eq("planner_spec.action_source_id", _req_str(planner_spec, "action_source_id"), "dmpl_action_enum_v1")
    ordering_policy = _req_dict(planner_spec, "ordering_policy")
    _expect_eq("ordering_policy.primary_key_id", _req_str(ordering_policy, "primary_key_id"), "upper_bound_primary_score_desc")
    _expect_eq("ordering_policy.secondary_key_id", _req_str(ordering_policy, "secondary_key_id"), "depth_asc")
    _expect_eq("ordering_policy.tertiary_key_id", _req_str(ordering_policy, "tertiary_key_id"), "node_id_asc")
    aux_policy = _req_dict(planner_spec, "aux_tie_break_policy")
    _expect_eq(
        "aux_tie_break_policy.aux_allowed_only_on_exact_score_ties_b",
        bool(aux_policy.get("aux_allowed_only_on_exact_score_ties_b", False)),
        True,
    )

    _expect_eq("hash_layout_ids.record_encoding_id", _req_str(hash_layout_ids, "record_encoding_id"), "lenpref_canonjson_v1")
    _expect_eq("hash_layout_ids.chunking_rule_id", _req_str(hash_layout_ids, "chunking_rule_id"), "fixed_1MiB_v1")

    _expect_eq("objective_spec.reward_proxy_id", _req_str(objective_spec, "reward_proxy_id"), "ufc_proxy_v1")
    _expect_eq("objective_spec.ufc_objective_id", _req_str(objective_spec, "ufc_objective_id"), "ufc_v1_primary")

    # Modelpack pinned IDs + patch policy.
    _expect_eq("modelpack.forward_arch_id", _req_str(modelpack_obj, "forward_arch_id"), "dmpl_linear_pwl_v1")
    _expect_eq("modelpack.value_arch_id", _req_str(modelpack_obj, "value_arch_id"), "dmpl_linear_v1")
    _expect_eq("modelpack.activation_id", _req_str(modelpack_obj, "activation_id"), "hard_tanh_q32_v1")
    _expect_eq("modelpack.gating_arch_id", _req_str(modelpack_obj, "gating_arch_id"), "linear_gate_v1")

    patch_policy = _req_dict(modelpack_obj, "patch_policy")
    vm_patch_allowed = patch_policy.get("vm_patch_allowed_b")
    if vm_patch_allowed is not False:
        raise DMPLError(
            reason_code=DMPL_E_CONCEPT_PATCH_POLICY_VIOLATION,
            details={"field": "patch_policy.vm_patch_allowed_b", "got": vm_patch_allowed},
        )
    allowed_patch_types = patch_policy.get("allowed_patch_types")
    if allowed_patch_types != ["matrix_patch", "lowrank_patch"]:
        raise DMPLError(
            reason_code=DMPL_E_OPSET_MISMATCH,
            details={"field": "patch_policy.allowed_patch_types", "expected": ["matrix_patch", "lowrank_patch"], "got": allowed_patch_types},
        )


__all__ = [
    "verify_dmpl_opset_v1",
]

