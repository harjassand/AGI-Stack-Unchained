"""Verifier for policy_vm_stark_proof_v1 artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .common_v1 import canon_hash_obj, ensure_sha256, fail, load_canon_dict, validate_schema
from .policy_vm_stark_runner_v1 import verify_policy_vm_stark
from .winterfell_contract_v1 import resolve_profile_backend_contract_bindings


_SEMANTIC_TRACE_REPR = "SEMANTIC_TRACE_WITNESS_V1"
_SUPPORTED_REPRESENTATION_KINDS = {_SEMANTIC_TRACE_REPR, "STARK_FRI_PROOF_V1"}
_SUPPORTED_PROFILE_KINDS = {
    "POLICY_VM_SEMANTIC_TRACE_MVP_V1",
    "POLICY_VM_STARK_MVP_V1",
    "POLICY_VM_AIR_PROFILE_96_V1",
    "POLICY_VM_AIR_PROFILE_128_V1",
}
_SUPPORTED_PROOF_KINDS = {"POLICY_VM_SEMANTIC_TRACE_MVP_V1", "POLICY_VM_AIR_MVP_V1"}
_PROFILE_META_FIELDS: tuple[str, ...] = (
    "winterfell_backend_id",
    "winterfell_backend_version",
    "winterfell_field_id",
    "winterfell_extension_id",
    "winterfell_merkle_hasher_id",
    "winterfell_random_coin_hasher_id",
)


def _require_relpath(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        fail("SCHEMA_FAIL")
    text = value.strip()
    path = Path(text)
    if path.is_absolute() or ".." in path.parts:
        fail("SCHEMA_FAIL")
    return text


def _normalize_stack_state(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        fail("NONDETERMINISTIC")
    out: list[dict[str, Any]] = []
    for row in value:
        if not isinstance(row, dict):
            fail("NONDETERMINISTIC")
        kind = str(row.get("kind", "")).strip()
        if not kind:
            fail("NONDETERMINISTIC")
        out.append({"kind": kind, "value": row.get("value")})
    return out


def _cell_bool(cell: dict[str, Any]) -> bool:
    if str(cell.get("kind", "")).strip() != "BOOL" or not isinstance(cell.get("value"), bool):
        fail("NONDETERMINISTIC")
    return bool(cell["value"])


def _cell_int(cell: dict[str, Any], *, allow_q32: bool) -> int:
    kind = str(cell.get("kind", "")).strip()
    if kind == "U64":
        value = cell.get("value")
        if not isinstance(value, int) or int(value) < 0:
            fail("NONDETERMINISTIC")
        return int(value)
    if allow_q32 and kind == "Q32":
        value = cell.get("value")
        if not isinstance(value, int):
            fail("NONDETERMINISTIC")
        return int(value)
    fail("NONDETERMINISTIC")
    return 0


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
    fail("NONDETERMINISTIC")
    return False


def _validate_step_transition(
    *,
    pc_u32: int,
    op: str,
    args: dict[str, Any],
    before_state: list[dict[str, Any]],
    after_state: list[dict[str, Any]],
    next_pc_u32: int,
) -> None:
    if op == "NOP":
        if before_state != after_state or next_pc_u32 != pc_u32 + 1:
            fail("NONDETERMINISTIC")
        return
    if op == "POP":
        if len(before_state) < 1 or after_state != before_state[:-1] or next_pc_u32 != pc_u32 + 1:
            fail("NONDETERMINISTIC")
        return
    if op == "DUP":
        if len(before_state) < 1 or next_pc_u32 != pc_u32 + 1:
            fail("NONDETERMINISTIC")
        expected = list(before_state) + [dict(before_state[-1])]
        if after_state != expected:
            fail("NONDETERMINISTIC")
        return
    if op == "SWAP":
        if len(before_state) < 2 or next_pc_u32 != pc_u32 + 1:
            fail("NONDETERMINISTIC")
        expected = list(before_state)
        expected[-1], expected[-2] = expected[-2], expected[-1]
        if after_state != expected:
            fail("NONDETERMINISTIC")
        return
    if op == "BOOL_NOT":
        if len(before_state) < 1 or next_pc_u32 != pc_u32 + 1:
            fail("NONDETERMINISTIC")
        val = _cell_bool(before_state[-1])
        expected = list(before_state[:-1]) + [{"kind": "BOOL", "value": (not val)}]
        if after_state != expected:
            fail("NONDETERMINISTIC")
        return
    if op in {"BOOL_AND", "BOOL_OR"}:
        if len(before_state) < 2 or next_pc_u32 != pc_u32 + 1:
            fail("NONDETERMINISTIC")
        lhs = _cell_bool(before_state[-2])
        rhs = _cell_bool(before_state[-1])
        out = lhs and rhs if op == "BOOL_AND" else lhs or rhs
        expected = list(before_state[:-2]) + [{"kind": "BOOL", "value": bool(out)}]
        if after_state != expected:
            fail("NONDETERMINISTIC")
        return
    if op in {"CMP_U64", "CMP_Q32"}:
        if len(before_state) < 2 or next_pc_u32 != pc_u32 + 1:
            fail("NONDETERMINISTIC")
        allow_q32 = op == "CMP_Q32"
        lhs = _cell_int(before_state[-2], allow_q32=allow_q32)
        rhs = _cell_int(before_state[-1], allow_q32=allow_q32)
        comp = str(args.get("comparator", "GE")).strip().upper()
        expected = list(before_state[:-2]) + [{"kind": "BOOL", "value": _cmp(lhs, rhs, comp)}]
        if after_state != expected:
            fail("NONDETERMINISTIC")
        return
    if op == "JMP":
        target = int(args.get("pc_u32", -1))
        if target < 0 or next_pc_u32 != target or after_state != before_state:
            fail("NONDETERMINISTIC")
        return
    if op == "JZ":
        if len(before_state) < 1:
            fail("NONDETERMINISTIC")
        cond = _cell_bool(before_state[-1])
        target = int(args.get("pc_u32", -1))
        expected_next = pc_u32 + 1 if cond else target
        if target < 0 or next_pc_u32 != expected_next or after_state != before_state[:-1]:
            fail("NONDETERMINISTIC")
        return
    if op == "PUSH_CONST":
        if len(after_state) != len(before_state) + 1 or after_state[: len(before_state)] != before_state:
            fail("NONDETERMINISTIC")
        if next_pc_u32 != pc_u32 + 1:
            fail("NONDETERMINISTIC")
        top = after_state[-1]
        if str(top.get("kind", "")).strip() not in {"Q32", "U64", "BOOL", "STRING", "HASH"}:
            fail("NONDETERMINISTIC")
        return
    if op == "EMIT_PLAN":
        if len(after_state) != len(before_state) + 1 or after_state[: len(before_state)] != before_state:
            fail("NONDETERMINISTIC")
        top = after_state[-1]
        if str(top.get("kind", "")).strip() != "PLAN_REF":
            fail("NONDETERMINISTIC")
        ensure_sha256(top.get("value"), reason="NONDETERMINISTIC")
        if next_pc_u32 != pc_u32 + 1:
            fail("NONDETERMINISTIC")
        return
    # AIR-MVP does not support this opcode yet.
    fail("NONDETERMINISTIC")


def _profile_from_state(*, state_root: Path | None, air_profile_id: str) -> dict[str, Any] | None:
    if state_root is None:
        return None
    config_dir = state_root.parent / "config"
    if not config_dir.exists() or not config_dir.is_dir():
        fail("MISSING_STATE_INPUT")
    pack_path = config_dir / "rsi_omega_daemon_pack_v1.json"
    if not pack_path.exists() or not pack_path.is_file():
        fail("MISSING_STATE_INPUT")
    pack = load_canon_dict(pack_path)
    rel = str(pack.get("policy_vm_air_profile_rel", "")).strip()
    if not rel:
        fail("SCHEMA_FAIL")
    rel_path = Path(rel)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        fail("SCHEMA_FAIL")
    profile_path = config_dir / rel_path
    if not profile_path.exists() or not profile_path.is_file():
        fail("MISSING_STATE_INPUT")
    profile = load_canon_dict(profile_path)
    validate_schema(profile, "policy_vm_air_profile_v1")
    observed_id = canon_hash_obj({k: v for k, v in profile.items() if k != "air_profile_id"})
    if str(profile.get("air_profile_id", "")) != observed_id:
        fail("PIN_HASH_MISMATCH")
    if observed_id != air_profile_id:
        fail("PIN_HASH_MISMATCH")
    backend_rel = str(pack.get("policy_vm_winterfell_backend_contract_rel", "")).strip()
    if not backend_rel:
        fail("SCHEMA_FAIL")
    backend_rel_path = Path(backend_rel)
    if backend_rel_path.is_absolute() or ".." in backend_rel_path.parts:
        fail("SCHEMA_FAIL")
    backend_path = config_dir / backend_rel_path
    if not backend_path.exists() or not backend_path.is_file():
        fail("MISSING_STATE_INPUT")
    backend_contract = load_canon_dict(backend_path)
    validate_schema(backend_contract, "policy_vm_winterfell_backend_contract_v1")
    observed_backend_id = canon_hash_obj(
        {k: v for k, v in backend_contract.items() if k != "backend_contract_id"}
    )
    if str(backend_contract.get("backend_contract_id", "")) != observed_backend_id:
        fail("PIN_HASH_MISMATCH")
    if observed_backend_id != ensure_sha256(pack.get("policy_vm_winterfell_backend_contract_id"), reason="PIN_HASH_MISMATCH"):
        fail("PIN_HASH_MISMATCH")
    try:
        winterfell_bindings = resolve_profile_backend_contract_bindings(
            profile_payload=profile,
            backend_contract_payload=backend_contract,
            reason="SCHEMA_FAIL",
        )
    except ValueError:
        fail("SCHEMA_FAIL")
    profile_kind = str(profile.get("profile_kind", "")).strip().upper()
    if profile_kind not in _SUPPORTED_PROFILE_KINDS:
        fail("SCHEMA_FAIL")
    supported = profile.get("supported_opcodes")
    if not isinstance(supported, list) or not supported:
        fail("SCHEMA_FAIL")
    supported_ops = {str(row).strip().upper() for row in supported if str(row).strip()}
    if not supported_ops:
        fail("SCHEMA_FAIL")
    action_kind_enum_payload = None
    action_kind_enum_rel = str(pack.get("policy_vm_action_kind_enum_rel", "")).strip()
    action_kind_enum_id = str(pack.get("policy_vm_action_kind_enum_id", "")).strip()
    if action_kind_enum_rel:
        rel_path = Path(action_kind_enum_rel)
        if rel_path.is_absolute() or ".." in rel_path.parts:
            fail("SCHEMA_FAIL")
        path = config_dir / rel_path
        if not path.exists() or not path.is_file():
            fail("MISSING_STATE_INPUT")
        action_kind_enum_payload = load_canon_dict(path)
        validate_schema(action_kind_enum_payload, "action_kind_enum_v1")
        observed_action_kind_enum_id = canon_hash_obj(
            {k: v for k, v in action_kind_enum_payload.items() if k != "action_kind_enum_id"}
        )
        if str(action_kind_enum_payload.get("action_kind_enum_id", "")) != observed_action_kind_enum_id:
            fail("PIN_HASH_MISMATCH")
        if action_kind_enum_id and action_kind_enum_id != observed_action_kind_enum_id:
            fail("PIN_HASH_MISMATCH")
        if str(profile.get("action_kind_enum_hash", "")) != observed_action_kind_enum_id:
            fail("PIN_HASH_MISMATCH")

    candidate_campaign_ids_payload = None
    candidate_campaign_ids_rel = str(pack.get("policy_vm_candidate_campaign_ids_list_rel", "")).strip()
    candidate_campaign_ids_id = str(pack.get("policy_vm_candidate_campaign_ids_list_id", "")).strip()
    if candidate_campaign_ids_rel:
        rel_path = Path(candidate_campaign_ids_rel)
        if rel_path.is_absolute() or ".." in rel_path.parts:
            fail("SCHEMA_FAIL")
        path = config_dir / rel_path
        if not path.exists() or not path.is_file():
            fail("MISSING_STATE_INPUT")
        candidate_campaign_ids_payload = load_canon_dict(path)
        validate_schema(candidate_campaign_ids_payload, "candidate_campaign_ids_list_v1")
        observed_candidate_campaign_ids_id = canon_hash_obj(
            {k: v for k, v in candidate_campaign_ids_payload.items() if k != "candidate_campaign_ids_list_id"}
        )
        if str(candidate_campaign_ids_payload.get("candidate_campaign_ids_list_id", "")) != observed_candidate_campaign_ids_id:
            fail("PIN_HASH_MISMATCH")
        if candidate_campaign_ids_id and candidate_campaign_ids_id != observed_candidate_campaign_ids_id:
            fail("PIN_HASH_MISMATCH")
        if str(profile.get("candidate_campaign_ids_list_hash", "")) != observed_candidate_campaign_ids_id:
            fail("PIN_HASH_MISMATCH")

    return {
        "profile_kind": profile_kind,
        "supported_ops": supported_ops,
        "profile_payload": profile,
        "backend_contract_payload": backend_contract,
        "action_kind_enum_payload": action_kind_enum_payload,
        "candidate_campaign_ids_payload": candidate_campaign_ids_payload,
        "proof_options_hash": ensure_sha256(winterfell_bindings.get("proof_options_hash"), reason="SCHEMA_FAIL"),
        **{field: str(winterfell_bindings.get(field, "")) for field in _PROFILE_META_FIELDS},
    }


def verify_policy_vm_stark_proof(
    payload: dict[str, Any],
    *,
    state_root: Path | None = None,
    expected: dict[str, Any] | None = None,
) -> str:
    validate_schema(payload, "policy_vm_stark_proof_v1")
    declared_id = ensure_sha256(payload.get("proof_id"), reason="SCHEMA_FAIL")
    no_id = dict(payload)
    no_id.pop("proof_id", None)
    if canon_hash_obj(no_id) != declared_id:
        fail("PIN_HASH_MISMATCH")

    inputs_descriptor_hash = ensure_sha256(payload.get("inputs_descriptor_hash"), reason="SCHEMA_FAIL")
    policy_program_id = ensure_sha256(payload.get("policy_program_id"), reason="SCHEMA_FAIL")
    opcode_table_id = ensure_sha256(payload.get("opcode_table_id"), reason="SCHEMA_FAIL")
    merged_hint_state_id = payload.get("merged_hint_state_id")
    if merged_hint_state_id is not None:
        ensure_sha256(merged_hint_state_id, reason="SCHEMA_FAIL")
    air_profile_id = ensure_sha256(payload.get("air_profile_id"), reason="SCHEMA_FAIL")
    if str(payload.get("proof_backend_id", "")).strip() != "WINTERFELL_STARK_FRI_V1":
        fail("SCHEMA_FAIL")
    decision_plan_hash = ensure_sha256(payload.get("decision_plan_hash"), reason="SCHEMA_FAIL")
    steps_executed_u64 = int(payload.get("steps_executed_u64", -1))
    if steps_executed_u64 < 0:
        fail("SCHEMA_FAIL")
    budget_outcome_hash = ensure_sha256(payload.get("budget_outcome_hash"), reason="SCHEMA_FAIL")
    proof_options_hash = ensure_sha256(payload.get("proof_options_hash"), reason="SCHEMA_FAIL")
    proof_representation_kind_raw = str(payload.get("proof_representation_kind", "")).strip().upper()
    if proof_representation_kind_raw:
        if proof_representation_kind_raw not in _SUPPORTED_REPRESENTATION_KINDS:
            fail("SCHEMA_FAIL")
    proof_representation_kind = proof_representation_kind_raw or _SEMANTIC_TRACE_REPR
    proof_bytes_hash = ensure_sha256(payload.get("proof_bytes_hash"), reason="SCHEMA_FAIL")
    proof_bytes_rel = _require_relpath(payload.get("proof_bytes_rel"))
    proof_public_outputs = payload.get("public_outputs")
    if not isinstance(proof_public_outputs, dict):
        fail("SCHEMA_FAIL")
    payload_steps_public = int(proof_public_outputs.get("steps_executed_u64", -1))
    if payload_steps_public < 0:
        fail("SCHEMA_FAIL")
    payload_budget_public = ensure_sha256(proof_public_outputs.get("budget_outcome_hash"), reason="SCHEMA_FAIL")
    if payload_steps_public != steps_executed_u64 or payload_budget_public != budget_outcome_hash:
        fail("NONDETERMINISTIC")

    profile_from_state = _profile_from_state(state_root=state_root, air_profile_id=air_profile_id)
    if isinstance(profile_from_state, dict):
        if str(profile_from_state.get("proof_options_hash", "")) != proof_options_hash:
            fail("NONDETERMINISTIC")
        for field in _PROFILE_META_FIELDS:
            payload_value = payload.get(field)
            if payload_value is None:
                continue
            if str(payload_value).strip() and str(payload_value).strip() != str(profile_from_state.get(field, "")).strip():
                fail("NONDETERMINISTIC")

    if isinstance(expected, dict):
        for key, expected_value in (
            ("inputs_descriptor_hash", inputs_descriptor_hash),
            ("policy_program_id", policy_program_id),
            ("opcode_table_id", opcode_table_id),
            ("decision_plan_hash", decision_plan_hash),
            ("budget_outcome_hash", budget_outcome_hash),
            ("proof_options_hash", proof_options_hash),
        ):
            if key in expected and str(expected.get(key)) != str(expected_value):
                fail("NONDETERMINISTIC")
        if "merged_hint_state_id" in expected and str(expected.get("merged_hint_state_id")) != str(merged_hint_state_id):
            fail("NONDETERMINISTIC")
        if "steps_executed_u64" in expected and int(expected.get("steps_executed_u64")) != steps_executed_u64:
            fail("NONDETERMINISTIC")

    if state_root is None:
        fail("MISSING_STATE_INPUT")

    proof_path = state_root / proof_bytes_rel
    if not proof_path.exists() or not proof_path.is_file():
        fail("MISSING_STATE_INPUT")
    proof_bytes = proof_path.read_bytes()
    if "sha256:" + hashlib.sha256(proof_bytes).hexdigest() != proof_bytes_hash:
        fail("NONDETERMINISTIC")

    if proof_representation_kind == "STARK_FRI_PROOF_V1":
        decision_payload = None
        trace_payload = None
        if isinstance(expected, dict):
            row = expected.get("decision_payload")
            if isinstance(row, dict):
                decision_payload = row
            row = expected.get("trace_payload")
            if isinstance(row, dict):
                trace_payload = row
        if not isinstance(decision_payload, dict):
            decision_path = state_root / "decisions" / f"sha256_{decision_plan_hash.split(':', 1)[1]}.omega_decision_plan_v1.json"
            if decision_path.exists() and decision_path.is_file():
                decision_payload = load_canon_dict(decision_path)
        if not isinstance(trace_payload, dict):
            trace_dir = state_root / "policy" / "traces"
            if trace_dir.exists() and trace_dir.is_dir():
                trace_candidates = sorted(trace_dir.glob("sha256_*.policy_vm_trace_v1.json"), key=lambda row: row.as_posix())
                if len(trace_candidates) == 1:
                    trace_payload = load_canon_dict(trace_candidates[0])
                elif len(trace_candidates) > 1:
                    snapshot_dir = state_root / "snapshot"
                    if snapshot_dir.exists() and snapshot_dir.is_dir():
                        snapshot_rows = sorted(
                            snapshot_dir.glob("sha256_*.omega_tick_snapshot_v1.json"),
                            key=lambda row: row.as_posix(),
                        )
                        best_tick = -1
                        selected_trace_hash = None
                        for row in snapshot_rows:
                            payload = load_canon_dict(row)
                            tick = int(payload.get("tick_u64", -1))
                            if tick > best_tick:
                                best_tick = tick
                                selected_trace_hash = str(payload.get("policy_vm_trace_hash", ""))
                        if isinstance(selected_trace_hash, str) and selected_trace_hash.startswith("sha256:"):
                            trace_path = trace_dir / f"sha256_{selected_trace_hash.split(':', 1)[1]}.policy_vm_trace_v1.json"
                            if trace_path.exists() and trace_path.is_file():
                                trace_payload = load_canon_dict(trace_path)
        if not isinstance(decision_payload, dict):
            fail("MISSING_STATE_INPUT")
        if not isinstance(trace_payload, dict):
            fail("MISSING_STATE_INPUT")
        if canon_hash_obj(decision_payload) != decision_plan_hash:
            fail("NONDETERMINISTIC")
        validate_schema(trace_payload, "policy_vm_trace_v1")

        profile_payload = None
        backend_contract_payload = None
        action_kind_enum_payload = None
        candidate_campaign_ids_payload = None
        if isinstance(expected, dict):
            row = expected.get("air_profile_payload")
            if isinstance(row, dict):
                profile_payload = row
            row = expected.get("backend_contract_payload")
            if isinstance(row, dict):
                backend_contract_payload = row
            row = expected.get("action_kind_enum_payload")
            if isinstance(row, dict):
                action_kind_enum_payload = row
            row = expected.get("candidate_campaign_ids_payload")
            if isinstance(row, dict):
                candidate_campaign_ids_payload = row
        if not isinstance(profile_payload, dict) or not isinstance(backend_contract_payload, dict):
            if not isinstance(profile_from_state, dict):
                fail("MISSING_STATE_INPUT")
            profile_payload = profile_from_state.get("profile_payload")
            backend_contract_payload = profile_from_state.get("backend_contract_payload")
            action_kind_enum_payload = profile_from_state.get("action_kind_enum_payload")
            candidate_campaign_ids_payload = profile_from_state.get("candidate_campaign_ids_payload")
        if not isinstance(profile_payload, dict) or not isinstance(backend_contract_payload, dict):
            fail("MISSING_STATE_INPUT")
        if not isinstance(action_kind_enum_payload, dict) or not isinstance(candidate_campaign_ids_payload, dict):
            fail("MISSING_STATE_INPUT")

        verify_out = verify_policy_vm_stark(
            proof_bytes=proof_bytes,
            trace_payload=trace_payload,
            decision_payload=decision_payload,
            inputs_descriptor_hash=inputs_descriptor_hash,
            policy_program_id=policy_program_id,
            opcode_table_id=opcode_table_id,
            merged_hint_state_id=merged_hint_state_id,
            air_profile_payload=profile_payload,
            backend_contract_payload=backend_contract_payload,
            action_kind_enum_payload=action_kind_enum_payload,
            candidate_campaign_ids_payload=candidate_campaign_ids_payload,
        )
        if not isinstance(verify_out, dict):
            fail("NONDETERMINISTIC")
        observed_statement = verify_out.get("statement")
        observed_public_outputs = verify_out.get("public_outputs")
        observed_options_hash = ensure_sha256(verify_out.get("proof_options_hash"), reason="NONDETERMINISTIC")
        if observed_options_hash != proof_options_hash:
            fail("NONDETERMINISTIC")
        if not isinstance(observed_statement, dict) or not isinstance(observed_public_outputs, dict):
            fail("NONDETERMINISTIC")
        if canon_hash_obj(observed_public_outputs) != canon_hash_obj(proof_public_outputs):
            fail("NONDETERMINISTIC")
        statement_expected = {
            "inputs_descriptor_hash": inputs_descriptor_hash,
            "policy_program_id": policy_program_id,
            "opcode_table_id": opcode_table_id,
            "merged_hint_state_id": merged_hint_state_id,
            "decision_plan_hash": decision_plan_hash,
            "steps_executed_u64": steps_executed_u64,
            "budget_outcome_hash": budget_outcome_hash,
            "air_profile_id": air_profile_id,
            "proof_options_hash": proof_options_hash,
        }
        if canon_hash_obj(observed_statement) != canon_hash_obj(statement_expected):
            fail("NONDETERMINISTIC")
        return "VALID"

    try:
        proof_header = json.loads(proof_bytes.decode("utf-8"))
    except Exception:
        fail("NONDETERMINISTIC")
        return "VALID"
    if not isinstance(proof_header, dict):
        fail("NONDETERMINISTIC")
    if str(proof_header.get("schema_version", "")) != "policy_vm_stark_proof_payload_v1":
        fail("NONDETERMINISTIC")
    proof_kind = str(proof_header.get("proof_kind", "POLICY_VM_AIR_MVP_V1")).strip().upper()
    if proof_kind not in _SUPPORTED_PROOF_KINDS:
        fail("NONDETERMINISTIC")
    if proof_representation_kind != _SEMANTIC_TRACE_REPR:
        fail("NONDETERMINISTIC")
    if int(proof_header.get("constraint_system_version", 0)) < 1:
        fail("NONDETERMINISTIC")
    statement_hash = ensure_sha256(proof_header.get("statement_hash"), reason="NONDETERMINISTIC")
    ensure_sha256(proof_header.get("trace_hash_chain_hash"), reason="NONDETERMINISTIC")
    ensure_sha256(proof_header.get("final_stack_commitment_hash"), reason="NONDETERMINISTIC")
    supported_raw = proof_header.get("supported_opcodes")
    if not isinstance(supported_raw, list) or not supported_raw:
        fail("NONDETERMINISTIC")
    supported_ops = {str(row).strip().upper() for row in supported_raw if str(row).strip()}
    if not supported_ops:
        fail("NONDETERMINISTIC")
    if isinstance(profile_from_state, dict):
        supported_ops_from_profile = profile_from_state.get("supported_ops")
        if supported_ops != supported_ops_from_profile:
            fail("NONDETERMINISTIC")
        profile_kind = str(profile_from_state.get("profile_kind", "")).strip().upper()
        if profile_kind not in _SUPPORTED_PROFILE_KINDS:
            fail("NONDETERMINISTIC")
    statement = {
        "inputs_descriptor_hash": inputs_descriptor_hash,
        "policy_program_id": policy_program_id,
        "opcode_table_id": opcode_table_id,
        "merged_hint_state_id": merged_hint_state_id,
        "decision_plan_hash": decision_plan_hash,
        "steps_executed_u64": steps_executed_u64,
        "budget_outcome_hash": budget_outcome_hash,
        "air_profile_id": air_profile_id,
        "proof_options_hash": proof_options_hash,
    }
    if canon_hash_obj(statement) != statement_hash:
        fail("NONDETERMINISTIC")
    semantic_trace = proof_header.get("semantic_trace")
    if not isinstance(semantic_trace, list):
        fail("NONDETERMINISTIC")
    if len(semantic_trace) != int(steps_executed_u64):
        fail("NONDETERMINISTIC")
    recomputed_chain = "sha256:" + ("0" * 64)
    last_after_state: list[dict[str, Any]] = []
    for row in semantic_trace:
        if not isinstance(row, dict):
            fail("NONDETERMINISTIC")
        pc_u32 = int(row.get("pc_u32", -1))
        if pc_u32 < 0:
            fail("NONDETERMINISTIC")
        op = str(row.get("op", "")).strip().upper()
        if not op or op not in supported_ops:
            fail("NONDETERMINISTIC")
        args = row.get("args")
        if not isinstance(args, dict):
            args = {}
        next_pc_u32 = int(row.get("next_pc_u32", -1))
        if next_pc_u32 < 0:
            fail("NONDETERMINISTIC")
        before_state = _normalize_stack_state(row.get("stack_before_state"))
        after_state = _normalize_stack_state(row.get("stack_after_state"))
        before_commit = canon_hash_obj(before_state)
        after_commit = canon_hash_obj(after_state)
        if str(row.get("stack_before", "")) != before_commit:
            fail("NONDETERMINISTIC")
        if str(row.get("stack_after", "")) != after_commit:
            fail("NONDETERMINISTIC")
        _validate_step_transition(
            pc_u32=pc_u32,
            op=op,
            args=args,
            before_state=before_state,
            after_state=after_state,
            next_pc_u32=next_pc_u32,
        )
        step_payload = {
            "pc_u32": int(pc_u32),
            "op": op,
            "args": dict(args),
            "next_pc_u32": int(next_pc_u32),
            "stack_before": before_commit,
            "stack_after": after_commit,
            "stack_before_state": before_state,
            "stack_after_state": after_state,
        }
        recomputed_chain = canon_hash_obj(
            {
                "prev": recomputed_chain,
                "step": step_payload,
            }
        )
        last_after_state = after_state
    if str(proof_header.get("trace_hash_chain_hash", "")) != recomputed_chain:
        fail("NONDETERMINISTIC")
    if str(proof_header.get("final_stack_commitment_hash", "")) != canon_hash_obj(last_after_state):
        fail("NONDETERMINISTIC")
    return "VALID"


def verify_policy_vm_stark_proof_file(path: Path, *, state_root: Path | None = None) -> str:
    payload = load_canon_dict(path)
    return verify_policy_vm_stark_proof(payload, state_root=state_root)


__all__ = ["verify_policy_vm_stark_proof", "verify_policy_vm_stark_proof_file"]
