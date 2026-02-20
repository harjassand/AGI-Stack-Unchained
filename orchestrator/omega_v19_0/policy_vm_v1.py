"""Coordinator policy VM (v1) with deterministic typed-stack execution."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from cdel.v1_7r.canon import canon_bytes
from cdel.v18_0.omega_common_v1 import canon_hash_obj, fail, q32_mul, validate_schema

_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass
class _StackValue:
    kind: str
    value: Any


@dataclass
class _Budget:
    max_steps_u64: int
    max_stack_items_u32: int
    max_trace_bytes_u64: int
    steps_used_u64: int = 0
    items_used_u64: int = 0
    bytes_read_u64: int = 0
    bytes_written_u64: int = 0
    trace_bytes_u64: int = 0

    def use_step(self) -> None:
        self.steps_used_u64 += 1
        if self.steps_used_u64 > self.max_steps_u64:
            fail("TRACE_BUDGET_EXCEEDED")

    def use_item(self, count: int = 1) -> None:
        self.items_used_u64 += max(0, int(count))

    def use_read(self, count: int) -> None:
        self.bytes_read_u64 += max(0, int(count))

    def use_write(self, count: int) -> None:
        self.bytes_written_u64 += max(0, int(count))

    def use_trace(self, payload: dict[str, Any]) -> None:
        self.trace_bytes_u64 += len(canon_bytes(payload))
        if self.trace_bytes_u64 > self.max_trace_bytes_u64:
            fail("TRACE_BUDGET_EXCEEDED")


def _require_sha256(value: Any, *, reason: str = "SCHEMA_FAIL") -> str:
    if not isinstance(value, str) or _HASH_RE.fullmatch(value) is None:
        fail(reason)
    return value


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and _HASH_RE.fullmatch(value) is not None


def _as_q32_metric(metric: Any) -> int:
    if isinstance(metric, dict) and set(metric.keys()) == {"q"} and isinstance(metric.get("q"), int):
        return int(metric["q"])
    if isinstance(metric, int):
        return int(metric)
    fail("METRIC_TYPE_FAIL")
    return 0


def _const_to_stack(value: Any) -> _StackValue:
    if isinstance(value, dict):
        ctype = str(value.get("type", "")).strip().upper()
        cval = value.get("value")
        if ctype == "Q32" and isinstance(cval, int):
            return _StackValue("Q32", int(cval))
        if ctype == "U64" and isinstance(cval, int) and int(cval) >= 0:
            return _StackValue("U64", int(cval))
        if ctype == "BOOL" and isinstance(cval, bool):
            return _StackValue("BOOL", bool(cval))
        if ctype == "STRING" and isinstance(cval, str):
            return _StackValue("STRING", cval)
        if ctype == "HASH" and isinstance(cval, str):
            return _StackValue("HASH", _require_sha256(cval, reason="SCHEMA_FAIL"))
        fail("SCHEMA_FAIL")
    if isinstance(value, bool):
        return _StackValue("BOOL", bool(value))
    if isinstance(value, int):
        return _StackValue("U64", int(value))
    if isinstance(value, str):
        if _HASH_RE.fullmatch(value):
            return _StackValue("HASH", value)
        return _StackValue("STRING", value)
    fail("SCHEMA_FAIL")
    return _StackValue("STRING", "")


def _stack_commitment(stack: list[_StackValue]) -> str:
    payload = [{"kind": row.kind, "value": row.value} for row in stack]
    return canon_hash_obj(payload)


def _expect(stack: list[_StackValue], kind: str) -> _StackValue:
    if not stack:
        fail("STACK_TYPE_MISMATCH")
    row = stack.pop()
    if row.kind != kind:
        fail("STACK_TYPE_MISMATCH")
    return row


def _expect_q32(stack: list[_StackValue]) -> int:
    if not stack:
        fail("STACK_TYPE_MISMATCH")
    row = stack.pop()
    if row.kind == "Q32":
        return int(row.value)
    if row.kind == "U64":
        return int(row.value)
    fail("STACK_TYPE_MISMATCH")
    return 0


def _expect_u64(stack: list[_StackValue]) -> int:
    row = _expect(stack, "U64")
    return int(row.value)


def _expect_bool(stack: list[_StackValue]) -> bool:
    row = _expect(stack, "BOOL")
    return bool(row.value)


def _stringify_stack_value(value: _StackValue) -> str:
    if value.kind in {"STRING", "HASH", "PLAN_REF", "JSON_OBJ_REF", "HINT_REF"}:
        return str(value.value)
    fail("STACK_TYPE_MISMATCH")
    return ""


def _cmp(lhs: int, rhs: int, comparator: str) -> bool:
    if comparator == "GT":
        return lhs > rhs
    if comparator == "GE":
        return lhs >= rhs
    if comparator == "LT":
        return lhs < rhs
    if comparator == "LE":
        return lhs <= rhs
    if comparator == "EQ":
        return lhs == rhs
    if comparator == "NE":
        return lhs != rhs
    fail("SCHEMA_FAIL")
    return False


def _extract_enabled_opcodes(opcode_table: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    enabled: set[str] = set()
    inactive: set[str] = set()

    entries = opcode_table.get("entries")
    if isinstance(entries, list):
        seen_names: set[str] = set()
        for row in entries:
            if not isinstance(row, dict):
                fail("SCHEMA_FAIL")
            name = str(row.get("opcode_name", "")).strip().upper()
            if not name:
                fail("SCHEMA_FAIL")
            if name in seen_names:
                fail("SCHEMA_FAIL")
            seen_names.add(name)
            if bool(row.get("active_b", True)):
                enabled.add(name)
            else:
                inactive.add(name)
    else:
        opcodes = opcode_table.get("opcodes")
        if isinstance(opcodes, dict):
            for key, row in opcodes.items():
                name = str(key).strip().upper()
                if not name:
                    fail("SCHEMA_FAIL")
                if isinstance(row, dict):
                    if bool(row.get("enabled_b", True)):
                        enabled.add(name)
                    else:
                        inactive.add(name)
                elif isinstance(row, bool):
                    if row:
                        enabled.add(name)
                    else:
                        inactive.add(name)
                elif isinstance(row, str):
                    if row.strip().upper() in {"ON", "ENABLED", "TRUE"}:
                        enabled.add(name)
                    else:
                        inactive.add(name)
                else:
                    fail("SCHEMA_FAIL")
        elif isinstance(opcodes, list):
            for row in opcodes:
                if not isinstance(row, dict):
                    fail("SCHEMA_FAIL")
                name = str(row.get("name", "")).strip().upper()
                if not name:
                    fail("SCHEMA_FAIL")
                if bool(row.get("enabled_b", True)):
                    enabled.add(name)
                else:
                    inactive.add(name)
        else:
            fail("SCHEMA_FAIL")

    forbidden = opcode_table.get("forbidden_in_phase1", [])
    forbidden_set: set[str] = set()
    if not isinstance(forbidden, list):
        fail("SCHEMA_FAIL")
    for row in forbidden:
        if not isinstance(row, str):
            fail("SCHEMA_FAIL")
        name = row.strip().upper()
        if name:
            forbidden_set.add(name)
    return enabled, forbidden_set, inactive


def _finalize_plan_from_fields(
    *,
    tick_u64: int,
    inputs_descriptor_hash: str,
    observation_hash: str,
    issue_bundle_hash: str,
    policy_hash: str,
    registry: dict[str, Any],
    registry_hash: str,
    budgets_hash: str,
    plan_fields: dict[str, Any],
) -> dict[str, Any]:
    action_kind = str(plan_fields.get("action_kind", "NOOP")).strip()
    if action_kind not in {"RUN_CAMPAIGN", "RUN_GOAL_TASK", "NOOP", "SAFE_HALT"}:
        fail("PLAN_SCHEMA_FAIL")

    plan: dict[str, Any] = {
        "schema_version": "omega_decision_plan_v1",
        "plan_id": "sha256:" + ("0" * 64),
        "tick_u64": int(tick_u64),
        "observation_report_hash": observation_hash,
        "issue_bundle_hash": issue_bundle_hash,
        "policy_hash": policy_hash,
        "registry_hash": registry_hash,
        "budgets_hash": budgets_hash,
        "action_kind": action_kind,
        "tie_break_path": ["POLICY_VM_V1"],
        "recompute_proof": {
            "inputs_hash": inputs_descriptor_hash,
            "plan_hash": "sha256:" + ("0" * 64),
        },
    }

    caps_raw = registry.get("capabilities")
    if not isinstance(caps_raw, list):
        fail("SCHEMA_FAIL")
    cap_by_campaign: dict[str, dict[str, Any]] = {}
    for row in caps_raw:
        if isinstance(row, dict):
            campaign_id = str(row.get("campaign_id", "")).strip()
            if campaign_id:
                cap_by_campaign[campaign_id] = row

    if action_kind in {"RUN_CAMPAIGN", "RUN_GOAL_TASK"}:
        campaign_id = str(plan_fields.get("campaign_id", "")).strip()
        if not campaign_id:
            fail("PLAN_SCHEMA_FAIL")
        cap = cap_by_campaign.get(campaign_id)
        if cap is None:
            fail("PLAN_SCHEMA_FAIL")

        plan["campaign_id"] = campaign_id
        plan["capability_id"] = str(plan_fields.get("capability_id") or cap.get("capability_id") or "").strip()
        if not str(plan["capability_id"]).strip():
            fail("PLAN_SCHEMA_FAIL")
        plan["campaign_pack_hash"] = canon_hash_obj({"campaign_pack_rel": cap.get("campaign_pack_rel")})
        plan["expected_verifier_module"] = str(cap.get("verifier_module", "")).strip()
        plan["priority_q32"] = dict(plan_fields.get("priority_q32") or {"q": 1 << 32})
        if action_kind == "RUN_GOAL_TASK":
            goal_id = str(plan_fields.get("goal_id", "")).strip()
            if not goal_id:
                fail("PLAN_SCHEMA_FAIL")
            plan["goal_id"] = goal_id
            plan["assigned_capability_id"] = str(
                plan_fields.get("assigned_capability_id") or plan.get("capability_id") or ""
            ).strip()
            if not plan["assigned_capability_id"]:
                fail("PLAN_SCHEMA_FAIL")

    no_id = dict(plan)
    no_id.pop("plan_id", None)
    plan_id = canon_hash_obj(no_id)
    plan["plan_id"] = plan_id
    plan["recompute_proof"] = {
        "inputs_hash": inputs_descriptor_hash,
        "plan_hash": plan_id,
    }
    validate_schema(plan, "omega_decision_plan_v1")
    return plan


def _serialize_stack(stack: list[_StackValue]) -> list[dict[str, Any]]:
    return [{"kind": row.kind, "value": row.value} for row in stack]


def _deserialize_stack(rows: Any) -> list[_StackValue]:
    if not isinstance(rows, list):
        fail("SCHEMA_FAIL")
    out: list[_StackValue] = []
    for row in rows:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        kind = str(row.get("kind", "")).strip()
        if not kind:
            fail("SCHEMA_FAIL")
        out.append(_StackValue(kind, row.get("value")))
    return out


def _hint_value_norm(item: dict[str, Any]) -> str:
    kind = str(item.get("kind", "")).strip()
    if kind == "Q32_SCORE":
        return str(int(item.get("q32", 0)))
    values = item.get("values")
    if not isinstance(values, list):
        fail("SCHEMA_FAIL")
    return "\x1f".join(str(row) for row in values)


def _hint_sort_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(item.get("kind", "")).strip(),
        str(item.get("key", "")).strip(),
        _hint_value_norm(item),
    )


def _sorted_unique_strings(values: Any) -> list[str]:
    if not isinstance(values, list):
        fail("SCHEMA_FAIL")
    out = sorted({str(row) for row in values if str(row).strip()})
    return out


def _hint_items_from_plan_fields(plan_fields: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key in sorted(plan_fields.keys()):
        value = plan_fields.get(key)
        if isinstance(value, dict) and set(value.keys()) == {"q"} and isinstance(value.get("q"), int):
            out.append({"kind": "Q32_SCORE", "key": str(key), "q32": int(value.get("q"))})
            continue
        if isinstance(value, int):
            out.append({"kind": "Q32_SCORE", "key": str(key), "q32": int(value)})
            continue
        if isinstance(value, list):
            out.append({"kind": "SET", "key": str(key), "values": _sorted_unique_strings(value)})
    out.sort(key=_hint_sort_key)
    return out


def _plan_summary(plan: dict[str, Any], plan_fields: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"action_kind": str(plan.get("action_kind", "")).strip() or "NOOP"}
    campaign_id = str(plan.get("campaign_id", "")).strip()
    if campaign_id:
        out["campaign_id"] = campaign_id
    budget_hint = plan_fields.get("budget_hint_q32")
    if isinstance(budget_hint, dict) and set(budget_hint.keys()) == {"q"} and isinstance(budget_hint.get("q"), int):
        out["budget_hint_q32"] = int(budget_hint.get("q"))
    elif isinstance(budget_hint, int):
        out["budget_hint_q32"] = int(budget_hint)
    return out


def _cost_from_trace(*, trace_payload: dict[str, Any], policy_budget_spec: dict[str, Any] | None) -> int:
    budget = trace_payload.get("budget_outcome")
    if not isinstance(budget, dict):
        fail("SCHEMA_FAIL")
    steps = max(0, int(trace_payload.get("steps_executed_u64", 0)))
    items = max(0, int(budget.get("items_used_u64", 0)))
    bytes_read = max(0, int(budget.get("bytes_read_u64", 0)))
    bytes_written = max(0, int(budget.get("bytes_written_u64", 0)))
    cost_model = {}
    if isinstance(policy_budget_spec, dict):
        row = policy_budget_spec.get("cost_model")
        if isinstance(row, dict):
            cost_model = row
    base = max(0, int(cost_model.get("base_cost_q32", 0)))
    per_step = max(0, int(cost_model.get("per_step_q32", 1 << 32)))
    per_item = max(0, int(cost_model.get("per_item_q32", 1)))
    per_byte_read = max(0, int(cost_model.get("per_byte_read_q32", 0)))
    per_byte_written = max(0, int(cost_model.get("per_byte_written_q32", 0)))
    total = base
    total += q32_mul(per_step, steps)
    total += q32_mul(per_item, items)
    total += q32_mul(per_byte_read, bytes_read)
    total += q32_mul(per_byte_written, bytes_written)
    return max(0, int(total))


def build_inputs_descriptor_v1(
    *,
    tick_u64: int,
    state_hash: str,
    repo_tree_id: str,
    observation_hash: str,
    issues_hash: str,
    registry_hash: str,
    policy_program_ids: list[str],
    predictor_id: str,
    j_profile_id: str,
    opcode_table_id: str,
    budget_spec_id: str,
    determinism_contract_id: str,
) -> dict[str, Any]:
    if not isinstance(policy_program_ids, list) or not policy_program_ids:
        fail("SCHEMA_FAIL")
    if len(policy_program_ids) > 100:
        fail("SCHEMA_FAIL")
    ordered_program_ids = [_require_sha256(row) for row in policy_program_ids]
    payload: dict[str, Any] = {
        "schema_version": "inputs_descriptor_v1",
        "tick_u64": int(tick_u64),
        "state_hash": _require_sha256(state_hash),
        "repo_tree_id": _require_sha256(repo_tree_id),
        "observation_hash": _require_sha256(observation_hash),
        "issues_hash": _require_sha256(issues_hash),
        "registry_hash": _require_sha256(registry_hash),
        "policy_program_ids": ordered_program_ids,
        "predictor_id": _require_sha256(predictor_id),
        "j_profile_id": _require_sha256(j_profile_id),
        "opcode_table_id": _require_sha256(opcode_table_id),
        "budget_spec_id": _require_sha256(budget_spec_id),
        "determinism_contract_id": _require_sha256(determinism_contract_id),
    }
    return payload


def run_policy_vm_v1(
    *,
    tick_u64: int,
    mode: str,
    inputs_descriptor_hash: str,
    observation_report: dict[str, Any],
    observation_hash: str,
    issue_bundle_hash: str,
    policy_hash: str,
    registry: dict[str, Any],
    registry_hash: str,
    budgets_hash: str,
    program: dict[str, Any],
    opcode_table: dict[str, Any],
    predictor_payload: dict[str, Any] | None = None,
    predictor_id: str | None = None,
    j_profile_payload: dict[str, Any] | None = None,
    j_profile_id: str | None = None,
    branch_id: str = "b00",
    round_u32: int = 0,
    resume_state: dict[str, Any] | None = None,
    policy_budget_spec: dict[str, Any] | None = None,
    barrier_ctx: dict[str, Any] | None = None,
    merged_hint_state_by_round: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if str(mode).strip().upper() not in {"DECISION_ONLY", "DUAL", "PROPOSAL_ONLY"}:
        fail("SCHEMA_FAIL")

    if str(program.get("schema_version", "")).strip() != "coordinator_isa_program_v1":
        fail("SCHEMA_FAIL")
    if str(opcode_table.get("schema_version", "")).strip() != "coordinator_opcode_table_v1":
        fail("SCHEMA_FAIL")
    if int(program.get("isa_version", 0)) != 1 or int(opcode_table.get("isa_version", 0)) != 1:
        fail("SCHEMA_FAIL")

    declared_program_id = _require_sha256(program.get("program_id"), reason="SCHEMA_FAIL")
    program_no_id = dict(program)
    program_no_id.pop("program_id", None)
    if canon_hash_obj(program_no_id) != declared_program_id:
        fail("PIN_HASH_MISMATCH")

    declared_opcode_table_id = _require_sha256(opcode_table.get("opcode_table_id"), reason="SCHEMA_FAIL")
    opcode_table_no_id = dict(opcode_table)
    opcode_table_no_id.pop("opcode_table_id", None)
    if canon_hash_obj(opcode_table_no_id) != declared_opcode_table_id:
        fail("PIN_HASH_MISMATCH")

    limits = program.get("declared_limits")
    if not isinstance(limits, dict):
        fail("SCHEMA_FAIL")
    budget = _Budget(
        max_steps_u64=max(1, int(limits.get("max_steps_u64", 0))),
        max_stack_items_u32=max(1, int(limits.get("max_stack_items_u32", 0))),
        max_trace_bytes_u64=max(1, int(limits.get("max_trace_bytes_u64", 0))),
    )

    instructions = program.get("instructions")
    constants = program.get("constants")
    if not isinstance(instructions, list) or not isinstance(constants, dict):
        fail("SCHEMA_FAIL")
    if not instructions:
        fail("SCHEMA_FAIL")

    entry_pc = int(program.get("entry_pc_u32", 0))
    if entry_pc < 0 or entry_pc >= len(instructions):
        fail("SCHEMA_FAIL")

    enabled_opcodes, forbidden_phase1, inactive_opcodes = _extract_enabled_opcodes(opcode_table)

    metrics = observation_report.get("metrics")
    if not isinstance(metrics, dict):
        fail("SCHEMA_FAIL")

    stack: list[_StackValue] = []
    call_stack: list[int] = []
    plan_fields: dict[str, Any] = {}
    merged_by_round = dict(merged_hint_state_by_round or {})
    continuation_state: dict[str, Any] | None = None
    emitted_hint_rounds: set[int] = set()
    emitted_hint_hashes_by_round: dict[int, str] = {}
    expected_hint_hashes_by_round: dict[int, list[str]] = {}

    if isinstance(barrier_ctx, dict):
        merged_raw = barrier_ctx.get("merged_hint_state_by_round")
        if isinstance(merged_raw, dict):
            for key, value in merged_raw.items():
                merged_by_round[int(key)] = dict(value) if isinstance(value, dict) else value
        expected_raw = barrier_ctx.get("expected_hint_hashes_by_round")
        if isinstance(expected_raw, dict):
            for key, value in expected_raw.items():
                if not isinstance(value, list):
                    fail("SCHEMA_FAIL")
                expected_hint_hashes_by_round[int(key)] = sorted(_require_sha256(row) for row in value)
        emitted_raw = barrier_ctx.get("branch_emitted_hint_rounds")
        if isinstance(emitted_raw, list):
            for value in emitted_raw:
                emitted_hint_rounds.add(int(value))
        emitted_hashes_raw = barrier_ctx.get("branch_hint_hashes_by_round")
        if isinstance(emitted_hashes_raw, dict):
            for key, value in emitted_hashes_raw.items():
                emitted_hint_hashes_by_round[int(key)] = _require_sha256(value)

    pc = entry_pc
    halted = False
    halt_reason = "ERROR"
    trace_hash_chain_hash = "sha256:" + ("0" * 64)
    step_log: list[dict[str, Any]] = []
    decision_plan: dict[str, Any] | None = None
    hint_bundle: dict[str, Any] | None = None
    proposal: dict[str, Any] | None = None
    proposal_pending = False

    if isinstance(resume_state, dict):
        pc = int(resume_state.get("pc_u32", entry_pc))
        stack = _deserialize_stack(resume_state.get("stack"))
        call_stack_raw = resume_state.get("call_stack")
        if not isinstance(call_stack_raw, list):
            fail("SCHEMA_FAIL")
        call_stack = [int(row) for row in call_stack_raw]
        plan_fields_raw = resume_state.get("plan_fields")
        if not isinstance(plan_fields_raw, dict):
            fail("SCHEMA_FAIL")
        plan_fields = dict(plan_fields_raw)
        trace_hash_chain_hash = str(resume_state.get("trace_hash_chain_hash", trace_hash_chain_hash))
        if not _is_sha256(trace_hash_chain_hash):
            fail("SCHEMA_FAIL")
        step_log_raw = resume_state.get("step_log")
        if not isinstance(step_log_raw, list):
            fail("SCHEMA_FAIL")
        step_log = [dict(row) for row in step_log_raw if isinstance(row, dict)]
        counters = resume_state.get("budget_counters")
        if not isinstance(counters, dict):
            fail("SCHEMA_FAIL")
        budget.steps_used_u64 = max(0, int(counters.get("steps_used_u64", 0)))
        budget.items_used_u64 = max(0, int(counters.get("items_used_u64", 0)))
        budget.bytes_read_u64 = max(0, int(counters.get("bytes_read_u64", 0)))
        budget.bytes_written_u64 = max(0, int(counters.get("bytes_written_u64", 0)))
        budget.trace_bytes_u64 = max(0, int(counters.get("trace_bytes_u64", 0)))
        rounds_raw = resume_state.get("emitted_hint_rounds")
        if isinstance(rounds_raw, list):
            for value in rounds_raw:
                emitted_hint_rounds.add(int(value))
        hint_hashes_raw = resume_state.get("emitted_hint_hashes_by_round")
        if isinstance(hint_hashes_raw, dict):
            for key, value in hint_hashes_raw.items():
                emitted_hint_hashes_by_round[int(key)] = _require_sha256(value)

    while not halted:
        if pc < 0 or pc >= len(instructions):
            fail("SCHEMA_FAIL")
        budget.use_step()

        ins = instructions[pc]
        if not isinstance(ins, dict):
            fail("SCHEMA_FAIL")
        op = str(ins.get("op", "")).strip().upper()
        args = ins.get("args")
        if not isinstance(args, dict):
            args = {}

        if op in inactive_opcodes:
            fail("OPCODE_DEPRECATED")
        if op not in enabled_opcodes:
            fail("OPCODE_UNKNOWN")
        if op in forbidden_phase1:
            fail("OPCODE_FORBIDDEN_PHASE1")
        if op == "DISPATCH_CAMPAIGN":
            fail("OPCODE_FORBIDDEN_PHASE1")

        stack_before = _stack_commitment(stack)
        stack_before_state = _serialize_stack(stack)
        next_pc = pc + 1

        if op == "NOP":
            pass
        elif op == "PUSH_CONST":
            const_key = str(args.get("key") or args.get("const_key") or "").strip()
            if not const_key or const_key not in constants:
                fail("SCHEMA_FAIL")
            value = _const_to_stack(constants[const_key])
            if len(stack) >= budget.max_stack_items_u32:
                fail("TRACE_BUDGET_EXCEEDED")
            stack.append(value)
            budget.use_item(1)
        elif op == "POP":
            if not stack:
                fail("STACK_TYPE_MISMATCH")
            stack.pop()
        elif op == "DUP":
            if not stack:
                fail("STACK_TYPE_MISMATCH")
            if len(stack) >= budget.max_stack_items_u32:
                fail("TRACE_BUDGET_EXCEEDED")
            row = stack[-1]
            stack.append(_StackValue(row.kind, row.value))
        elif op == "SWAP":
            if len(stack) < 2:
                fail("STACK_TYPE_MISMATCH")
            stack[-1], stack[-2] = stack[-2], stack[-1]
        elif op == "JMP":
            next_pc = int(args.get("pc_u32", -1))
        elif op == "JZ":
            cond = _expect_bool(stack)
            if not cond:
                next_pc = int(args.get("pc_u32", -1))
        elif op == "CALL":
            call_stack.append(pc + 1)
            next_pc = int(args.get("pc_u32", -1))
        elif op == "RET":
            if not call_stack:
                fail("SCHEMA_FAIL")
            next_pc = int(call_stack.pop())
        elif op == "LOAD_OBSERVATION":
            if len(stack) >= budget.max_stack_items_u32:
                fail("TRACE_BUDGET_EXCEEDED")
            stack.append(_StackValue("JSON_OBJ_REF", observation_hash))
            budget.use_read(len(canon_bytes(observation_report)))
        elif op == "LOAD_OBSERVATION_METRIC":
            metric_id = str(args.get("metric_id", "")).strip()
            if not metric_id:
                fail("SCHEMA_FAIL")
            if metric_id not in metrics:
                fail("METRIC_MISSING")
            metric = metrics.get(metric_id)
            if isinstance(metric, dict) and set(metric.keys()) == {"q"} and isinstance(metric.get("q"), int):
                value = _StackValue("Q32", int(metric["q"]))
            elif isinstance(metric, int):
                kind = "U64" if int(metric) >= 0 else "Q32"
                value = _StackValue(kind, int(metric))
            else:
                fail("METRIC_TYPE_FAIL")
                value = _StackValue("U64", 0)
            if len(stack) >= budget.max_stack_items_u32:
                fail("TRACE_BUDGET_EXCEEDED")
            stack.append(value)
            budget.use_item(1)
        elif op == "CMP_Q32":
            rhs = _expect_q32(stack)
            lhs = _expect_q32(stack)
            comp = str(args.get("comparator", "GE")).strip().upper()
            stack.append(_StackValue("BOOL", _cmp(lhs, rhs, comp)))
        elif op == "CMP_U64":
            rhs = _expect_u64(stack)
            lhs = _expect_u64(stack)
            comp = str(args.get("comparator", "GE")).strip().upper()
            stack.append(_StackValue("BOOL", _cmp(lhs, rhs, comp)))
        elif op == "BOOL_NOT":
            stack.append(_StackValue("BOOL", not _expect_bool(stack)))
        elif op == "BOOL_AND":
            rhs = _expect_bool(stack)
            lhs = _expect_bool(stack)
            stack.append(_StackValue("BOOL", bool(lhs and rhs)))
        elif op == "BOOL_OR":
            rhs = _expect_bool(stack)
            lhs = _expect_bool(stack)
            stack.append(_StackValue("BOOL", bool(lhs or rhs)))
        elif op == "SET_PLAN_FIELD":
            field = str(args.get("field", "")).strip()
            if not field:
                fail("SCHEMA_FAIL")
            source = str(args.get("from", "STACK")).strip().upper()
            if source == "CONST":
                const_key = str(args.get("const_key", "")).strip()
                if not const_key or const_key not in constants:
                    fail("SCHEMA_FAIL")
                value = _const_to_stack(constants[const_key])
            else:
                if not stack:
                    fail("STACK_TYPE_MISMATCH")
                value = stack.pop()

            if field == "priority_q32":
                if value.kind == "Q32":
                    plan_fields[field] = {"q": int(value.value)}
                elif value.kind == "U64":
                    plan_fields[field] = {"q": int(value.value)}
                else:
                    fail("STACK_TYPE_MISMATCH")
            elif field == "tie_break_path":
                if value.kind != "STRING":
                    fail("STACK_TYPE_MISMATCH")
                existing = plan_fields.get(field)
                if not isinstance(existing, list):
                    existing = []
                existing.append(str(value.value))
                plan_fields[field] = existing
            else:
                plan_fields[field] = _stringify_stack_value(value)
        elif op == "COMPUTE_J":
            expected_profile_id = _require_sha256(args.get("j_profile_id"), reason="J_PROFILE_HASH_MISMATCH")
            if j_profile_payload is None or j_profile_id is None:
                fail("J_PROFILE_MISSING")
            if _require_sha256(j_profile_id, reason="J_PROFILE_HASH_MISMATCH") != expected_profile_id:
                fail("J_PROFILE_HASH_MISMATCH")
            observed_profile_id = j_profile_payload.get("profile_id")
            if observed_profile_id is not None and _require_sha256(observed_profile_id, reason="J_PROFILE_HASH_MISMATCH") != expected_profile_id:
                fail("J_PROFILE_HASH_MISMATCH")

            weights = j_profile_payload.get("metric_weights")
            if not isinstance(weights, list):
                fail("J_COMPUTE_FAIL")
            bias_q32 = 0
            bias_obj = j_profile_payload.get("bias_q32")
            if isinstance(bias_obj, dict) and set(bias_obj.keys()) == {"q"} and isinstance(bias_obj.get("q"), int):
                bias_q32 = int(bias_obj["q"])
            total_q32 = int(bias_q32)
            for row in weights:
                if not isinstance(row, dict):
                    fail("J_COMPUTE_FAIL")
                metric_id = str(row.get("metric_id", "")).strip()
                if not metric_id:
                    fail("J_COMPUTE_FAIL")
                if metric_id not in metrics:
                    fail("METRIC_MISSING")
                weight_obj = row.get("weight_q32")
                if not (isinstance(weight_obj, dict) and set(weight_obj.keys()) == {"q"} and isinstance(weight_obj.get("q"), int)):
                    fail("J_COMPUTE_FAIL")
                metric_q32 = _as_q32_metric(metrics.get(metric_id))
                total_q32 += q32_mul(metric_q32, int(weight_obj["q"]))
            stack.append(_StackValue("Q32", int(total_q32)))
        elif op == "PREDICT_J_DELTA":
            expected_predictor_id = _require_sha256(args.get("predictor_id"), reason="PREDICTOR_HASH_MISMATCH")
            if predictor_payload is None or predictor_id is None:
                fail("PREDICTOR_MISSING")
            if _require_sha256(predictor_id, reason="PREDICTOR_HASH_MISMATCH") != expected_predictor_id:
                fail("PREDICTOR_HASH_MISMATCH")
            observed_predictor_id = predictor_payload.get("predictor_id")
            if observed_predictor_id is not None and _require_sha256(observed_predictor_id, reason="PREDICTOR_HASH_MISMATCH") != expected_predictor_id:
                fail("PREDICTOR_HASH_MISMATCH")

            plan_ref = _expect(stack, "PLAN_REF")
            plan_hash = _require_sha256(plan_ref.value, reason="PREDICT_FAIL")
            try:
                plan_head = int(plan_hash.split(":", 1)[1][:8], 16)
                obs_head = int(observation_hash.split(":", 1)[1][:8], 16)
            except Exception:
                fail("PREDICT_FAIL")
                plan_head = 0
                obs_head = 0

            bias_obj = predictor_payload.get("bias_q32", {"q": 0})
            w_plan_obj = predictor_payload.get("w_plan_q32", {"q": 0})
            w_obs_obj = predictor_payload.get("w_obs_q32", {"q": 0})
            if not all(
                isinstance(obj, dict) and set(obj.keys()) == {"q"} and isinstance(obj.get("q"), int)
                for obj in [bias_obj, w_plan_obj, w_obs_obj]
            ):
                fail("PREDICT_FAIL")
            delta_q32 = int(bias_obj["q"]) + q32_mul(int(plan_head), int(w_plan_obj["q"])) + q32_mul(
                int(obs_head), int(w_obs_obj["q"])
            )
            stack.append(_StackValue("Q32", int(delta_q32)))
        elif op == "EMIT_PLAN":
            plan_kind = str(args.get("plan_kind", "DECISION_PLAN_V1")).strip().upper()
            if plan_kind != "DECISION_PLAN_V1":
                fail("PLAN_SCHEMA_FAIL")
            decision_plan = _finalize_plan_from_fields(
                tick_u64=tick_u64,
                inputs_descriptor_hash=inputs_descriptor_hash,
                observation_hash=observation_hash,
                issue_bundle_hash=issue_bundle_hash,
                policy_hash=policy_hash,
                registry=registry,
                registry_hash=registry_hash,
                budgets_hash=budgets_hash,
                plan_fields=plan_fields,
            )
            stack.append(_StackValue("PLAN_REF", str(decision_plan["plan_id"])))
            if str(mode).strip().upper() == "DECISION_ONLY":
                halted = True
                halt_reason = "EMIT_PLAN"
        elif op == "YIELD_HINTS":
            if str(mode).strip().upper() == "DECISION_ONLY":
                fail("POLICY_MODE_VIOLATION")
            round_value = int(args.get("round_u32", 0))
            hint_items = _hint_items_from_plan_fields(plan_fields)
            hint_payload = {
                "schema_version": "hint_bundle_v1",
                "inputs_descriptor_hash": inputs_descriptor_hash,
                "policy_program_id": declared_program_id,
                "branch_id": str(branch_id),
                "round_u32": int(round_value),
                "hint_items": hint_items,
            }
            hint_payload["hint_commitment_hash"] = canon_hash_obj(hint_payload)
            hint_bundle = dict(hint_payload)
            max_hint_bytes = int(
                (policy_budget_spec or {}).get("max_hint_bytes_u64", max(1, int(limits.get("max_trace_bytes_u64", 1))))
            )
            if len(canon_bytes(hint_bundle)) > max_hint_bytes:
                fail("TRACE_BUDGET_EXCEEDED")
            emitted_hint_rounds.add(int(round_value))
            emitted_hint_hashes_by_round[int(round_value)] = canon_hash_obj(hint_bundle)
            continuation_state = {
                "pc_u32": int(next_pc),
                "stack": _serialize_stack(stack),
                "call_stack": [int(row) for row in call_stack],
                "plan_fields": dict(plan_fields),
                "trace_hash_chain_hash": trace_hash_chain_hash,
                "step_log": list(step_log),
                "budget_counters": {
                    "steps_used_u64": int(budget.steps_used_u64),
                    "items_used_u64": int(budget.items_used_u64),
                    "bytes_read_u64": int(budget.bytes_read_u64),
                    "bytes_written_u64": int(budget.bytes_written_u64),
                    "trace_bytes_u64": int(budget.trace_bytes_u64),
                },
                "emitted_hint_rounds": sorted(int(row) for row in emitted_hint_rounds),
                "emitted_hint_hashes_by_round": {
                    str(key): value for key, value in sorted(emitted_hint_hashes_by_round.items(), key=lambda row: row[0])
                },
            }
            halted = True
            halt_reason = "YIELD_HINTS"
        elif op == "CONSUME_MERGED_HINT_STATE":
            round_value = int(args.get("round_u32", -1))
            payload = merged_by_round.get(round_value)
            if not isinstance(payload, dict):
                fail("HINT_SYNC_VIOLATION")
            if int(round_value) not in emitted_hint_rounds:
                fail("HINT_SYNC_VIOLATION")
            if str(payload.get("inputs_descriptor_hash", "")) != str(inputs_descriptor_hash):
                fail("HINT_SYNC_VIOLATION")
            expected_hint_hashes = expected_hint_hashes_by_round.get(int(round_value))
            contributing = payload.get("contributing_hint_hashes")
            if not isinstance(contributing, list):
                fail("HINT_SYNC_VIOLATION")
            observed_contributing = sorted(_require_sha256(row, reason="HINT_SYNC_VIOLATION") for row in contributing)
            if expected_hint_hashes is not None:
                if observed_contributing != expected_hint_hashes:
                    fail("HINT_SYNC_VIOLATION")
            own_hint_hash = emitted_hint_hashes_by_round.get(int(round_value))
            if not isinstance(own_hint_hash, str) or own_hint_hash not in observed_contributing:
                fail("HINT_SYNC_VIOLATION")
            state_id = payload.get("state_id")
            if isinstance(state_id, str) and _HASH_RE.fullmatch(state_id):
                hint_ref = state_id
            else:
                hint_ref = canon_hash_obj(payload)
            stack.append(_StackValue("HINT_REF", hint_ref))
        elif op == "HALT_PROPOSE":
            if str(mode).strip().upper() == "DECISION_ONLY":
                fail("POLICY_MODE_VIOLATION")
            if decision_plan is None:
                decision_plan = _finalize_plan_from_fields(
                    tick_u64=tick_u64,
                    inputs_descriptor_hash=inputs_descriptor_hash,
                    observation_hash=observation_hash,
                    issue_bundle_hash=issue_bundle_hash,
                    policy_hash=policy_hash,
                    registry=registry,
                    registry_hash=registry_hash,
                    budgets_hash=budgets_hash,
                    plan_fields=plan_fields,
                )
            proposal_pending = True
            halted = True
            halt_reason = "HALT_PROPOSE"
        else:
            fail("OPCODE_UNKNOWN")

        stack_after = _stack_commitment(stack)
        step_row = {
            "pc_u32": int(pc),
            "op": op,
            "args": dict(args),
            "next_pc_u32": int(next_pc),
            "stack_before": stack_before,
            "stack_after": stack_after,
            "stack_before_state": stack_before_state,
            "stack_after_state": _serialize_stack(stack),
        }
        trace_hash_chain_hash = canon_hash_obj(
            {
                "prev": trace_hash_chain_hash,
                "step": step_row,
            }
        )
        budget.use_trace(step_row)
        step_log.append(step_row)
        pc = int(next_pc)

    if decision_plan is None and str(mode).strip().upper() == "DECISION_ONLY":
        fail("POLICY_MODE_VIOLATION")
    if str(mode).strip().upper() == "DECISION_ONLY" and halt_reason != "EMIT_PLAN":
        fail("POLICY_MODE_VIOLATION")

    trace_payload = {
        "schema_version": "policy_vm_trace_v1",
        "inputs_descriptor_hash": inputs_descriptor_hash,
        "policy_program_id": declared_program_id,
        "branch_id": str(branch_id),
        "round_u32": int(round_u32),
        "halt_reason": halt_reason,
        "steps_executed_u64": int(budget.steps_used_u64),
        "budget_outcome": {
            "items_used_u64": int(budget.items_used_u64),
            "bytes_read_u64": int(budget.bytes_read_u64),
            "bytes_written_u64": int(budget.bytes_written_u64),
        },
        "trace_hash_chain_hash": trace_hash_chain_hash,
        "final_stack_commitment_hash": _stack_commitment(stack),
        "step_log": step_log,
    }
    trace_hash = canon_hash_obj(trace_payload)
    if proposal_pending:
        if decision_plan is None:
            fail("POLICY_MODE_VIOLATION")
        decision_plan_hash = canon_hash_obj(decision_plan)
        expected_j_new_q32 = int(plan_fields.get("expected_J_new_q32", 0)) if isinstance(
            plan_fields.get("expected_J_new_q32"), int
        ) else 0
        expected_delta_j_q32 = int(plan_fields.get("expected_delta_J_q32", 0)) if isinstance(
            plan_fields.get("expected_delta_J_q32"), int
        ) else 0
        proposal = {
            "schema_version": "policy_trace_proposal_v1",
            "inputs_descriptor_hash": inputs_descriptor_hash,
            "policy_program_id": declared_program_id,
            "branch_id": str(branch_id),
            "vm_trace_hash": trace_hash,
            "decision_plan_hash": decision_plan_hash,
            "plan_summary": _plan_summary(decision_plan, plan_fields),
            "expected_J_new_q32": int(expected_j_new_q32),
            "expected_delta_J_q32": int(expected_delta_j_q32),
            "compute_cost_q32": _cost_from_trace(trace_payload=trace_payload, policy_budget_spec=policy_budget_spec),
            "proposal_commitment_hash": "sha256:" + ("0" * 64),
        }
        proposal["proposal_commitment_hash"] = canon_hash_obj(
            {k: v for k, v in proposal.items() if k != "proposal_commitment_hash"}
        )

    return {
        "continuation_state": continuation_state,
        "decision_plan": decision_plan,
        "hint_bundle": hint_bundle,
        "policy_trace_proposal": proposal,
        "policy_vm_trace": trace_payload,
    }


__all__ = ["build_inputs_descriptor_v1", "run_policy_vm_v1"]
