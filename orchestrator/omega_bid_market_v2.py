"""Deterministic policy proposal arbiter for Omega v19 policy market."""

from __future__ import annotations

import re
from typing import Any

from cdel.v18_0.omega_common_v1 import canon_hash_obj, fail, q32_mul, validate_schema

_BRANCH_ID_RE = re.compile(r"^b[0-9]{2}$")


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("sha256:") and len(value.split(":", 1)[1]) == 64


def _require_sha256(value: Any, *, reason: str = "SCHEMA_FAIL") -> str:
    if not _is_sha256(value):
        fail(reason)
    return str(value)


def _require_branch_id(value: Any, *, reason: str = "SCHEMA_FAIL") -> str:
    if not isinstance(value, str) or _BRANCH_ID_RE.fullmatch(value) is None:
        fail(reason)
    return value


def _require_int(value: Any, *, minimum: int | None = None, reason: str = "SCHEMA_FAIL") -> int:
    if not isinstance(value, int):
        fail(reason)
    ivalue = int(value)
    if minimum is not None and ivalue < minimum:
        fail(reason)
    return ivalue


def _validate_inputs_descriptor(payload: Any) -> None:
    if not isinstance(payload, dict):
        fail("SCHEMA_FAIL")
    if payload.get("schema_version") != "inputs_descriptor_v1":
        fail("SCHEMA_FAIL")
    _require_int(payload.get("tick_u64"), minimum=0)
    if "descriptor_id" in payload or "observation_report_hash" in payload or "issue_bundle_hash" in payload:
        _require_sha256(payload.get("descriptor_id"))
        _require_sha256(payload.get("state_hash"))
        _require_sha256(payload.get("observation_report_hash"))
        _require_sha256(payload.get("issue_bundle_hash"))
        return
    _require_sha256(payload.get("state_hash"))
    _require_sha256(payload.get("repo_tree_id"))
    _require_sha256(payload.get("observation_hash"))
    _require_sha256(payload.get("issues_hash"))
    _require_sha256(payload.get("registry_hash"))
    policy_program_ids = payload.get("policy_program_ids")
    if not isinstance(policy_program_ids, list) or not policy_program_ids or len(policy_program_ids) > 100:
        fail("SCHEMA_FAIL")
    for row in policy_program_ids:
        _require_sha256(row)
    _require_sha256(payload.get("predictor_id"))
    _require_sha256(payload.get("j_profile_id"))
    _require_sha256(payload.get("opcode_table_id"))
    _require_sha256(payload.get("budget_spec_id"))
    _require_sha256(payload.get("determinism_contract_id"))


def _validate_selection_policy(payload: Any) -> None:
    if not isinstance(payload, dict):
        fail("SCHEMA_FAIL")
    if payload.get("schema_version") != "policy_selection_policy_v1":
        fail("SCHEMA_FAIL")
    _require_sha256(payload.get("selection_policy_id"))
    model = payload.get("cost_model")
    if not isinstance(model, dict):
        fail("SCHEMA_FAIL")
    for key in ("base_cost_q32", "per_step_q32", "per_item_q32", "per_byte_read_q32", "per_byte_written_q32"):
        _require_int(model.get(key), minimum=0)
    target = payload.get("counterfactual_target")
    if target is not None:
        if not isinstance(target, dict):
            fail("SCHEMA_FAIL")
        _require_int(target.get("temperature_q32"), minimum=1)
        _require_int(target.get("margin_q32"))


def _validate_proposal(payload: Any) -> None:
    if not isinstance(payload, dict):
        fail("SCHEMA_FAIL")
    if payload.get("schema_version") != "policy_trace_proposal_v1":
        fail("SCHEMA_FAIL")
    _require_sha256(payload.get("inputs_descriptor_hash"))
    _require_sha256(payload.get("policy_program_id"))
    _require_branch_id(payload.get("branch_id"))
    _require_sha256(payload.get("vm_trace_hash"))
    _require_sha256(payload.get("decision_plan_hash"))
    summary = payload.get("plan_summary")
    if not isinstance(summary, dict):
        fail("SCHEMA_FAIL")
    action_kind = summary.get("action_kind")
    if not isinstance(action_kind, str) or not action_kind.strip():
        fail("SCHEMA_FAIL")
    budget_hint = summary.get("budget_hint_q32")
    if budget_hint is not None:
        _require_int(budget_hint)
    _require_int(payload.get("expected_J_new_q32"))
    _require_int(payload.get("expected_delta_J_q32"))
    _require_int(payload.get("compute_cost_q32"), minimum=0)
    _require_sha256(payload.get("proposal_commitment_hash"))


def _validate_vm_trace(payload: Any) -> None:
    if not isinstance(payload, dict):
        fail("SCHEMA_FAIL")
    if payload.get("schema_version") != "policy_vm_trace_v1":
        fail("SCHEMA_FAIL")
    _require_sha256(payload.get("inputs_descriptor_hash"))
    _require_sha256(payload.get("policy_program_id"))
    _require_branch_id(payload.get("branch_id"))
    _require_int(payload.get("round_u32"), minimum=0)
    halt_reason = payload.get("halt_reason")
    if not isinstance(halt_reason, str) or not halt_reason:
        fail("SCHEMA_FAIL")
    _require_int(payload.get("steps_executed_u64"), minimum=0)
    budget_outcome = payload.get("budget_outcome")
    if not isinstance(budget_outcome, dict):
        fail("SCHEMA_FAIL")
    _require_int(budget_outcome.get("items_used_u64"), minimum=0)
    _require_int(budget_outcome.get("bytes_read_u64"), minimum=0)
    _require_int(budget_outcome.get("bytes_written_u64"), minimum=0)
    _require_sha256(payload.get("trace_hash_chain_hash"))
    _require_sha256(payload.get("final_stack_commitment_hash"))


def _validate_selection_receipt(payload: Any) -> None:
    if not isinstance(payload, dict):
        fail("SCHEMA_FAIL")
    if payload.get("schema_version") != "policy_market_selection_v1":
        fail("SCHEMA_FAIL")
    _require_sha256(payload.get("inputs_descriptor_hash"))
    hashes = payload.get("proposal_hashes")
    if not isinstance(hashes, list) or not hashes:
        fail("SCHEMA_FAIL")
    normalized = [_require_sha256(row) for row in hashes]
    if normalized != sorted(normalized):
        fail("NONDETERMINISTIC")
    _require_branch_id(payload.get("winner_branch_id"))
    _require_sha256(payload.get("winner_proposal_hash"))
    _require_sha256(payload.get("selection_commitment_hash"))
    ranking = payload.get("ranking")
    if not isinstance(ranking, list) or not ranking:
        fail("SCHEMA_FAIL")
    for row in ranking:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        _require_branch_id(row.get("branch_id"))
        _require_sha256(row.get("proposal_hash"))
        _require_int(row.get("expected_J_new_q32"))
        _require_int(row.get("expected_delta_J_q32"))
        _require_int(row.get("compute_cost_q32"), minimum=0)
        _require_sha256(row.get("program_id"))
        _require_sha256(row.get("vm_trace_hash"))
        _require_sha256(row.get("decision_plan_hash"))
        _require_sha256(row.get("authoritative_binding_hash"))

def _as_q32_metric(metric: Any) -> int:
    if isinstance(metric, dict) and set(metric.keys()) == {"q"} and isinstance(metric.get("q"), int):
        return int(metric.get("q"))
    if isinstance(metric, int):
        return int(metric)
    fail("METRIC_TYPE_FAIL")
    return 0


def _compute_j_old_q32(*, observation_report: dict[str, Any] | None, j_profile: dict[str, Any] | None) -> int:
    if not isinstance(observation_report, dict) or not isinstance(j_profile, dict):
        return 0
    metrics = observation_report.get("metrics")
    weights = j_profile.get("metric_weights")
    if not isinstance(metrics, dict) or not isinstance(weights, list):
        return 0
    total_q32 = 0
    bias_obj = j_profile.get("bias_q32")
    if isinstance(bias_obj, dict) and set(bias_obj.keys()) == {"q"} and isinstance(bias_obj.get("q"), int):
        total_q32 = int(bias_obj.get("q"))
    for row in weights:
        if not isinstance(row, dict):
            fail("J_COMPUTE_FAIL")
        metric_id = str(row.get("metric_id", "")).strip()
        if not metric_id:
            fail("J_COMPUTE_FAIL")
        if metric_id not in metrics:
            fail("METRIC_MISSING")
        weight = row.get("weight_q32")
        if not (isinstance(weight, dict) and set(weight.keys()) == {"q"} and isinstance(weight.get("q"), int)):
            fail("J_COMPUTE_FAIL")
        total_q32 += q32_mul(_as_q32_metric(metrics.get(metric_id)), int(weight.get("q")))
    return int(total_q32)


def _predict_delta_q32(
    *,
    decision_plan_hash: str,
    observation_hash: str | None,
    predictor: dict[str, Any] | None,
) -> int:
    if not isinstance(predictor, dict):
        return 0
    if not isinstance(observation_hash, str) or not _is_sha256(observation_hash):
        return 0
    bias_obj = predictor.get("bias_q32", {"q": 0})
    w_plan_obj = predictor.get("w_plan_q32", {"q": 0})
    w_obs_obj = predictor.get("w_obs_q32", {"q": 0})
    if not all(
        isinstance(row, dict) and set(row.keys()) == {"q"} and isinstance(row.get("q"), int)
        for row in [bias_obj, w_plan_obj, w_obs_obj]
    ):
        fail("PREDICT_FAIL")
    try:
        plan_head = int(str(decision_plan_hash).split(":", 1)[1][:8], 16)
        obs_head = int(str(observation_hash).split(":", 1)[1][:8], 16)
    except Exception:
        fail("PREDICT_FAIL")
        return 0
    return int(bias_obj.get("q")) + q32_mul(int(w_plan_obj.get("q")), int(plan_head)) + q32_mul(
        int(w_obs_obj.get("q")), int(obs_head)
    )


def _cost_from_trace(*, trace: dict[str, Any], selection_policy: dict[str, Any]) -> int:
    model = selection_policy.get("cost_model")
    if not isinstance(model, dict):
        fail("SCHEMA_FAIL")
    for key in ("base_cost_q32", "per_step_q32", "per_item_q32", "per_byte_read_q32", "per_byte_written_q32"):
        if not isinstance(model.get(key), int) or int(model.get(key)) < 0:
            fail("SCHEMA_FAIL")
    budget_outcome = trace.get("budget_outcome")
    if not isinstance(budget_outcome, dict):
        fail("SCHEMA_FAIL")
    steps = max(0, int(trace.get("steps_executed_u64", 0)))
    items = max(0, int(budget_outcome.get("items_used_u64", 0)))
    bytes_read = max(0, int(budget_outcome.get("bytes_read_u64", 0)))
    bytes_written = max(0, int(budget_outcome.get("bytes_written_u64", 0)))
    total = int(model.get("base_cost_q32"))
    total += q32_mul(int(model.get("per_step_q32")), steps)
    total += q32_mul(int(model.get("per_item_q32")), items)
    total += q32_mul(int(model.get("per_byte_read_q32")), bytes_read)
    total += q32_mul(int(model.get("per_byte_written_q32")), bytes_written)
    return max(0, int(total))


def _proposal_commitment_hash(payload: dict[str, Any]) -> str:
    row = dict(payload)
    row.pop("proposal_commitment_hash", None)
    return canon_hash_obj(row)


def select_policy_proposal(
    *,
    inputs_descriptor: dict[str, Any],
    proposals: list[dict[str, Any]],
    predictor: dict[str, Any] | None,
    j_profile: dict[str, Any] | None,
    selection_policy: dict[str, Any],
    observation_report: dict[str, Any] | None = None,
    traces_by_hash: dict[str, dict[str, Any]] | None = None,
    decision_plans_by_hash: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Select winning proposal deterministically.

    The caller must pass proposals in branch index order. Ranking is independent
    of completion order and is recomputed from canonical inputs.
    """

    _validate_inputs_descriptor(inputs_descriptor)
    _validate_selection_policy(selection_policy)
    descriptor_hash = canon_hash_obj(inputs_descriptor)
    if not isinstance(proposals, list) or not proposals:
        fail("SCHEMA_FAIL")

    observation_hash = None
    for key in ("observation_hash", "observation_report_hash"):
        value = inputs_descriptor.get(key)
        if _is_sha256(value):
            observation_hash = str(value)
            break

    j_old_q32 = _compute_j_old_q32(observation_report=observation_report, j_profile=j_profile)

    ranking_rows: list[dict[str, Any]] = []
    proposal_hashes: list[str] = []

    for proposal in proposals:
        _validate_proposal(proposal)
        if str(proposal.get("inputs_descriptor_hash")) != str(descriptor_hash):
            fail("INPUTS_DESCRIPTOR_MISMATCH")
        vm_trace_hash = _require_sha256(proposal.get("vm_trace_hash"))
        decision_plan_hash = _require_sha256(proposal.get("decision_plan_hash"))
        program_id = _require_sha256(proposal.get("policy_program_id"))
        commitment = _require_sha256(proposal.get("proposal_commitment_hash"))
        if _proposal_commitment_hash(proposal) != commitment:
            fail("NONDETERMINISTIC")
        proposal_hash = canon_hash_obj(proposal)
        proposal_hashes.append(proposal_hash)

        if isinstance(traces_by_hash, dict):
            trace_payload = traces_by_hash.get(vm_trace_hash)
            if not isinstance(trace_payload, dict):
                fail("MISSING_STATE_INPUT")
            _validate_vm_trace(trace_payload)
            if canon_hash_obj(trace_payload) != vm_trace_hash:
                fail("NONDETERMINISTIC")
            if str(trace_payload.get("inputs_descriptor_hash")) != str(descriptor_hash):
                fail("INPUTS_DESCRIPTOR_MISMATCH")
            compute_cost_q32 = _cost_from_trace(trace=trace_payload, selection_policy=selection_policy)
        else:
            compute_cost_q32 = max(0, int(proposal.get("compute_cost_q32", 0)))

        if isinstance(decision_plans_by_hash, dict):
            plan_payload = decision_plans_by_hash.get(decision_plan_hash)
            if not isinstance(plan_payload, dict):
                fail("MISSING_STATE_INPUT")
            validate_schema(plan_payload, "omega_decision_plan_v1")
            if canon_hash_obj(plan_payload) != decision_plan_hash:
                fail("NONDETERMINISTIC")
            if str((plan_payload.get("recompute_proof") or {}).get("inputs_hash", "")) != str(descriptor_hash):
                fail("INPUTS_DESCRIPTOR_MISMATCH")

        expected_delta_j_q32 = _predict_delta_q32(
            decision_plan_hash=decision_plan_hash,
            observation_hash=observation_hash,
            predictor=predictor,
        )
        expected_j_new_q32 = int(j_old_q32) + int(expected_delta_j_q32)
        ranking_rows.append(
            {
                "branch_id": str(proposal.get("branch_id", "")),
                "proposal_hash": proposal_hash,
                "vm_trace_hash": vm_trace_hash,
                "decision_plan_hash": decision_plan_hash,
                "expected_J_new_q32": int(expected_j_new_q32),
                "expected_delta_J_q32": int(expected_delta_j_q32),
                "compute_cost_q32": int(compute_cost_q32),
                "program_id": program_id,
                "authoritative_binding_hash": canon_hash_obj(
                    {
                        "inputs_descriptor_hash": descriptor_hash,
                        "branch_id": str(proposal.get("branch_id", "")),
                        "policy_program_id": program_id,
                        "vm_trace_hash": vm_trace_hash,
                        "decision_plan_hash": decision_plan_hash,
                        "expected_J_new_q32": int(expected_j_new_q32),
                        "expected_delta_J_q32": int(expected_delta_j_q32),
                        "compute_cost_q32": int(compute_cost_q32),
                    }
                ),
            }
        )

    ranking_rows_sorted = sorted(
        ranking_rows,
        key=lambda row: (
            -int(row["expected_J_new_q32"]),
            int(row["compute_cost_q32"]),
            str(row["program_id"]),
        ),
    )
    winner = ranking_rows_sorted[0]
    selection_commitment_hash = canon_hash_obj(
        {
            "inputs_descriptor_hash": descriptor_hash,
            "ranking": [
                {
                    "branch_id": str(row["branch_id"]),
                    "program_id": str(row["program_id"]),
                    "vm_trace_hash": str(row["vm_trace_hash"]),
                    "decision_plan_hash": str(row["decision_plan_hash"]),
                    "expected_J_new_q32": int(row["expected_J_new_q32"]),
                    "expected_delta_J_q32": int(row["expected_delta_J_q32"]),
                    "compute_cost_q32": int(row["compute_cost_q32"]),
                    "authoritative_binding_hash": str(row["authoritative_binding_hash"]),
                }
                for row in ranking_rows_sorted
            ],
            "winner_binding_hash": str(winner["authoritative_binding_hash"]),
        }
    )
    receipt = {
        "schema_version": "policy_market_selection_v1",
        "inputs_descriptor_hash": descriptor_hash,
        "proposal_hashes": sorted(proposal_hashes),
        "winner_branch_id": str(winner["branch_id"]),
        "winner_proposal_hash": str(winner["proposal_hash"]),
        "selection_commitment_hash": selection_commitment_hash,
        "ranking": ranking_rows_sorted,
    }
    _validate_selection_receipt(receipt)
    return receipt


__all__ = ["select_policy_proposal"]
