"""Winterfell STARK runner bridge for policy VM proofs."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .common_v1 import canon_hash_obj, ensure_sha256, fail, repo_root
from .winterfell_contract_v1 import (
    canonicalize_winterfell_proof_options,
    resolve_profile_backend_contract_bindings,
)

_CRATE_MANIFEST = (
    repo_root() / "CDEL-v2" / "cdel" / "v19_0" / "rust" / "policy_vm_stark_rs_v1" / "Cargo.toml"
)

_SUPPORTED_STARK_OPS: dict[str, int] = {
    "NOP": 0,
    "PUSH_CONST": 1,
    "CMP_Q32": 2,
    "CMP_U64": 3,
    "JZ": 4,
    "JMP": 5,
    "SET_PLAN_FIELD": 6,
    "EMIT_PLAN": 7,
}
_FIELD_UNUSED = 255
_FIELD_ACTION_KIND = 0
_FIELD_CAMPAIGN_ID = 1
_FIELD_PRIORITY_Q32 = 2


def _sha64_pair(digest: str) -> tuple[int, int]:
    ensured = ensure_sha256(digest, reason="SCHEMA_FAIL")
    hexd = ensured.split(":", 1)[1]
    return int(hexd[:16], 16), int(hexd[16:32], 16)


def _proof_options_bundle(
    *,
    profile_payload: dict[str, Any],
    backend_contract_payload: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    try:
        bindings = resolve_profile_backend_contract_bindings(
            profile_payload=profile_payload,
            backend_contract_payload=backend_contract_payload,
            reason="SCHEMA_FAIL",
        )
    except ValueError:
        fail("SCHEMA_FAIL")
    keys = bindings.get("winterfell_proof_options_keys")
    if not isinstance(keys, list) or not keys:
        fail("SCHEMA_FAIL")
    try:
        profile_options = canonicalize_winterfell_proof_options(
            options_obj=profile_payload.get("winterfell_proof_options"),
            option_keys=keys,
            reason="SCHEMA_FAIL",
        )
    except ValueError:
        fail("SCHEMA_FAIL")
    profile_options_legacy = profile_payload.get("proof_options")
    if profile_options_legacy is not None:
        try:
            profile_options_legacy = canonicalize_winterfell_proof_options(
                options_obj=profile_options_legacy,
                option_keys=keys,
                reason="SCHEMA_FAIL",
            )
        except ValueError:
            fail("SCHEMA_FAIL")
        if dict(profile_options_legacy) != dict(profile_options):
            fail("SCHEMA_FAIL")
    if dict(profile_options) != dict(bindings.get("winterfell_proof_options") or {}):
        fail("SCHEMA_FAIL")
    proof_options_hash = canon_hash_obj(profile_options)
    if ensure_sha256(proof_options_hash, reason="SCHEMA_FAIL") != ensure_sha256(
        bindings.get("proof_options_hash"),
        reason="SCHEMA_FAIL",
    ):
        fail("SCHEMA_FAIL")
    return profile_options, proof_options_hash


def _action_enum_maps(action_kind_enum_payload: dict[str, Any]) -> tuple[dict[str, int], dict[int, str]]:
    rows = action_kind_enum_payload.get("entries")
    if not isinstance(rows, list) or not rows:
        fail("SCHEMA_FAIL")
    by_kind: dict[str, int] = {}
    by_code: dict[int, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        code = int(row.get("code_u8", -1))
        kind = str(row.get("action_kind", "")).strip()
        if code < 0 or code > 255 or not kind:
            fail("SCHEMA_FAIL")
        if kind in by_kind or code in by_code:
            fail("SCHEMA_FAIL")
        by_kind[kind] = code
        by_code[code] = kind
    return by_kind, by_code


def _campaign_index_map(candidate_campaign_ids_payload: dict[str, Any]) -> dict[str, int]:
    rows = candidate_campaign_ids_payload.get("campaign_ids")
    if not isinstance(rows, list):
        fail("SCHEMA_FAIL")
    out: dict[str, int] = {}
    for idx, value in enumerate(rows):
        campaign_id = str(value).strip()
        if not campaign_id:
            fail("SCHEMA_FAIL")
        if campaign_id in out:
            fail("SCHEMA_FAIL")
        out[campaign_id] = idx
    return out


def _priority_q32_from_plan(decision_payload: dict[str, Any]) -> int:
    row = decision_payload.get("priority_q32")
    if isinstance(row, dict) and set(row.keys()) == {"q"} and isinstance(row.get("q"), int):
        return int(row.get("q"))
    if isinstance(row, int):
        return int(row)
    return 0


def _plan_public_outputs(
    *,
    decision_payload: dict[str, Any],
    trace_payload: dict[str, Any],
    action_kind_enum_payload: dict[str, Any],
    candidate_campaign_ids_payload: dict[str, Any],
) -> dict[str, Any]:
    action_by_kind, _ = _action_enum_maps(action_kind_enum_payload)
    campaign_index_by_id = _campaign_index_map(candidate_campaign_ids_payload)

    action_kind = str(decision_payload.get("action_kind", "")).strip()
    if action_kind not in {"SAFE_HALT", "NOOP", "RUN_CAMPAIGN"}:
        fail("NONDETERMINISTIC")
    if action_kind not in action_by_kind:
        fail("NONDETERMINISTIC")
    action_code = int(action_by_kind[action_kind])

    campaign_index = 65535
    if action_kind == "RUN_CAMPAIGN":
        campaign_id = str(decision_payload.get("campaign_id", "")).strip()
        if campaign_id not in campaign_index_by_id:
            fail("NONDETERMINISTIC")
        campaign_index = int(campaign_index_by_id[campaign_id])

    steps_executed = int(trace_payload.get("steps_executed_u64", 0))
    if steps_executed < 0:
        fail("SCHEMA_FAIL")
    budget_outcome = trace_payload.get("budget_outcome")
    if not isinstance(budget_outcome, dict):
        fail("SCHEMA_FAIL")
    budget_hash = canon_hash_obj(budget_outcome)

    return {
        "action_kind_code_u8": action_code,
        "campaign_id_index_u16": campaign_index,
        "priority_q32_i64": int(_priority_q32_from_plan(decision_payload)),
        "steps_executed_u64": steps_executed,
        "budget_outcome_hash": budget_hash,
    }


def _stark_rows_from_trace(
    *,
    trace_payload: dict[str, Any],
    action_kind_enum_payload: dict[str, Any],
    candidate_campaign_ids_payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    step_log = trace_payload.get("step_log")
    if not isinstance(step_log, list) or not step_log:
        fail("SCHEMA_FAIL")

    action_by_kind, _ = _action_enum_maps(action_kind_enum_payload)
    campaign_index_by_id = _campaign_index_map(candidate_campaign_ids_payload)
    noop_code = action_by_kind.get("NOOP")
    if noop_code is None:
        fail("SCHEMA_FAIL")

    rows: list[dict[str, Any]] = []
    for step in step_log:
        if not isinstance(step, dict):
            fail("SCHEMA_FAIL")
        op = str(step.get("op", "")).strip().upper()
        if op not in _SUPPORTED_STARK_OPS:
            fail("NONDETERMINISTIC")
        args = step.get("args")
        if not isinstance(args, dict):
            args = {}
        pc_u32 = int(step.get("pc_u32", -1))
        next_pc_u32 = int(step.get("next_pc_u32", -1))
        if pc_u32 < 0 or next_pc_u32 < 0:
            fail("SCHEMA_FAIL")
        before_state = step.get("stack_before_state")
        after_state = step.get("stack_after_state")
        if not isinstance(before_state, list) or not isinstance(after_state, list):
            fail("SCHEMA_FAIL")
        jump_target = int(args.get("pc_u32", next_pc_u32))
        if jump_target < 0:
            fail("SCHEMA_FAIL")
        cond_b = False
        if op == "JZ":
            if not before_state or not isinstance(before_state[-1], dict):
                fail("NONDETERMINISTIC")
            top = before_state[-1]
            if str(top.get("kind", "")).strip() != "BOOL" or not isinstance(top.get("value"), bool):
                fail("NONDETERMINISTIC")
            cond_b = bool(top.get("value"))

        set_field_code = _FIELD_UNUSED
        set_value = 0
        if op == "SET_PLAN_FIELD":
            if str(args.get("from", "STACK")).strip().upper() == "CONST":
                # MVP STARK profile only supports stack-driven plan field updates.
                fail("NONDETERMINISTIC")
            field = str(args.get("field", "")).strip()
            if field == "action_kind":
                set_field_code = _FIELD_ACTION_KIND
                if not before_state or not isinstance(before_state[-1], dict):
                    fail("NONDETERMINISTIC")
                value = before_state[-1]
                if str(value.get("kind", "")).strip() != "STRING":
                    fail("NONDETERMINISTIC")
                action_kind = str(value.get("value", "")).strip()
                if action_kind not in action_by_kind:
                    fail("NONDETERMINISTIC")
                set_value = int(action_by_kind[action_kind])
            elif field == "campaign_id":
                set_field_code = _FIELD_CAMPAIGN_ID
                if not before_state or not isinstance(before_state[-1], dict):
                    fail("NONDETERMINISTIC")
                value = before_state[-1]
                if str(value.get("kind", "")).strip() != "STRING":
                    fail("NONDETERMINISTIC")
                campaign_id = str(value.get("value", "")).strip()
                if campaign_id not in campaign_index_by_id:
                    fail("NONDETERMINISTIC")
                set_value = int(campaign_index_by_id[campaign_id])
            elif field == "priority_q32":
                set_field_code = _FIELD_PRIORITY_Q32
                if not before_state or not isinstance(before_state[-1], dict):
                    fail("NONDETERMINISTIC")
                value = before_state[-1]
                kind = str(value.get("kind", "")).strip()
                raw = value.get("value")
                if kind not in {"Q32", "U64"} or not isinstance(raw, int):
                    fail("NONDETERMINISTIC")
                set_value = int(raw)
            else:
                fail("NONDETERMINISTIC")

        rows.append(
            {
                "pc_u32": pc_u32,
                "next_pc_u32": next_pc_u32,
                "op_code_u8": int(_SUPPORTED_STARK_OPS[op]),
                "jump_target_u32": jump_target,
                "cond_b": bool(cond_b),
                "stack_before_depth_u32": len(before_state),
                "stack_after_depth_u32": len(after_state),
                "set_field_code_u8": int(set_field_code),
                "set_value_i64": int(set_value),
            }
        )

    first = rows[0]
    initial_state = {
        "pc_u32": int(first["pc_u32"]),
        "stack_depth_u32": int(first["stack_before_depth_u32"]),
        "action_kind_code_u8": int(noop_code),
        "campaign_id_index_u16": 65535,
        "priority_q32_i64": 0,
    }
    return rows, initial_state


def _build_cli_input(
    *,
    statement: dict[str, Any],
    public_outputs: dict[str, Any],
    trace_payload: dict[str, Any],
    profile_payload: dict[str, Any],
    backend_contract_payload: dict[str, Any],
    action_kind_enum_payload: dict[str, Any],
    candidate_campaign_ids_payload: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    proof_options, proof_options_hash = _proof_options_bundle(
        profile_payload=profile_payload,
        backend_contract_payload=backend_contract_payload,
    )
    statement_hash = canon_hash_obj(statement)
    statement_lo, statement_hi = _sha64_pair(statement_hash)
    budget_lo, budget_hi = _sha64_pair(str(public_outputs["budget_outcome_hash"]))
    trace_lo, trace_hi = _sha64_pair(str(trace_payload.get("trace_hash_chain_hash", "")))
    stack_lo, stack_hi = _sha64_pair(str(trace_payload.get("final_stack_commitment_hash", "")))
    rows, initial_state = _stark_rows_from_trace(
        trace_payload=trace_payload,
        action_kind_enum_payload=action_kind_enum_payload,
        candidate_campaign_ids_payload=candidate_campaign_ids_payload,
    )
    cli_input = {
        "schema_version": "policy_vm_stark_cli_input_v1",
        "statement_hash_lo_u64": statement_lo,
        "statement_hash_hi_u64": statement_hi,
        "budget_hash_lo_u64": budget_lo,
        "budget_hash_hi_u64": budget_hi,
        "trace_hash_lo_u64": trace_lo,
        "trace_hash_hi_u64": trace_hi,
        "final_stack_hash_lo_u64": stack_lo,
        "final_stack_hash_hi_u64": stack_hi,
        "proof_options": dict(proof_options),
        "initial_state": initial_state,
        "public_outputs": {
            "action_kind_code_u8": int(public_outputs["action_kind_code_u8"]),
            "campaign_id_index_u16": int(public_outputs["campaign_id_index_u16"]),
            "priority_q32_i64": int(public_outputs["priority_q32_i64"]),
            "steps_executed_u64": int(public_outputs["steps_executed_u64"]),
        },
        "vm_rows": rows,
    }
    return cli_input, proof_options_hash


def build_statement(
    *,
    inputs_descriptor_hash: str,
    policy_program_id: str,
    opcode_table_id: str,
    merged_hint_state_id: str | None,
    decision_plan_hash: str,
    steps_executed_u64: int,
    budget_outcome_hash: str,
    air_profile_id: str,
    proof_options_hash: str,
) -> dict[str, Any]:
    return {
        "inputs_descriptor_hash": ensure_sha256(inputs_descriptor_hash, reason="SCHEMA_FAIL"),
        "policy_program_id": ensure_sha256(policy_program_id, reason="SCHEMA_FAIL"),
        "opcode_table_id": ensure_sha256(opcode_table_id, reason="SCHEMA_FAIL"),
        "merged_hint_state_id": (
            ensure_sha256(merged_hint_state_id, reason="SCHEMA_FAIL")
            if isinstance(merged_hint_state_id, str) and merged_hint_state_id.strip()
            else None
        ),
        "decision_plan_hash": ensure_sha256(decision_plan_hash, reason="SCHEMA_FAIL"),
        "steps_executed_u64": int(steps_executed_u64),
        "budget_outcome_hash": ensure_sha256(budget_outcome_hash, reason="SCHEMA_FAIL"),
        "air_profile_id": ensure_sha256(air_profile_id, reason="SCHEMA_FAIL"),
        "proof_options_hash": ensure_sha256(proof_options_hash, reason="SCHEMA_FAIL"),
    }


def _run_rust_cli(args: list[str]) -> None:
    run = subprocess.run(args, capture_output=True, text=True, check=False)
    if run.returncode != 0:
        stderr = (run.stderr or "").strip()
        stdout = (run.stdout or "").strip()
        detail = stderr or stdout or "rust stark runner failed"
        raise RuntimeError(detail)


def prove_policy_vm_stark(
    *,
    trace_payload: dict[str, Any],
    decision_payload: dict[str, Any],
    inputs_descriptor_hash: str,
    policy_program_id: str,
    opcode_table_id: str,
    merged_hint_state_id: str | None,
    air_profile_payload: dict[str, Any],
    backend_contract_payload: dict[str, Any],
    action_kind_enum_payload: dict[str, Any],
    candidate_campaign_ids_payload: dict[str, Any],
) -> dict[str, Any]:
    public_outputs = _plan_public_outputs(
        decision_payload=decision_payload,
        trace_payload=trace_payload,
        action_kind_enum_payload=action_kind_enum_payload,
        candidate_campaign_ids_payload=candidate_campaign_ids_payload,
    )
    _proof_options, proof_options_hash = _proof_options_bundle(
        profile_payload=air_profile_payload,
        backend_contract_payload=backend_contract_payload,
    )
    statement = build_statement(
        inputs_descriptor_hash=inputs_descriptor_hash,
        policy_program_id=policy_program_id,
        opcode_table_id=opcode_table_id,
        merged_hint_state_id=merged_hint_state_id,
        decision_plan_hash=canon_hash_obj(decision_payload),
        steps_executed_u64=int(public_outputs["steps_executed_u64"]),
        budget_outcome_hash=str(public_outputs["budget_outcome_hash"]),
        air_profile_id=str(air_profile_payload.get("air_profile_id", "")),
        proof_options_hash=proof_options_hash,
    )
    cli_input, proof_options_hash = _build_cli_input(
        statement=statement,
        public_outputs=public_outputs,
        trace_payload=trace_payload,
        profile_payload=air_profile_payload,
        backend_contract_payload=backend_contract_payload,
        action_kind_enum_payload=action_kind_enum_payload,
        candidate_campaign_ids_payload=candidate_campaign_ids_payload,
    )
    with tempfile.TemporaryDirectory(prefix="policy_vm_stark_rs_v1_") as td:
        root = Path(td)
        input_path = root / "input.json"
        proof_path = root / "proof.bin"
        receipt_path = root / "receipt.json"
        input_path.write_text(
            json.dumps(cli_input, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
            encoding="utf-8",
        )
        _run_rust_cli(
            [
                "cargo",
                "run",
                "--quiet",
                "--manifest-path",
                str(_CRATE_MANIFEST),
                "--",
                "--mode",
                "prove",
                "--input-json",
                str(input_path),
                "--proof-out",
                str(proof_path),
                "--receipt-out",
                str(receipt_path),
            ]
        )
        proof_bytes = proof_path.read_bytes()
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    return {
        "statement": statement,
        "public_outputs": public_outputs,
        "proof_options_hash": proof_options_hash,
        "proof_bytes": proof_bytes,
        "runner_receipt": receipt,
    }


def verify_policy_vm_stark(
    *,
    proof_bytes: bytes,
    trace_payload: dict[str, Any],
    decision_payload: dict[str, Any],
    inputs_descriptor_hash: str,
    policy_program_id: str,
    opcode_table_id: str,
    merged_hint_state_id: str | None,
    air_profile_payload: dict[str, Any],
    backend_contract_payload: dict[str, Any],
    action_kind_enum_payload: dict[str, Any],
    candidate_campaign_ids_payload: dict[str, Any],
) -> dict[str, Any]:
    public_outputs = _plan_public_outputs(
        decision_payload=decision_payload,
        trace_payload=trace_payload,
        action_kind_enum_payload=action_kind_enum_payload,
        candidate_campaign_ids_payload=candidate_campaign_ids_payload,
    )
    _proof_options, proof_options_hash = _proof_options_bundle(
        profile_payload=air_profile_payload,
        backend_contract_payload=backend_contract_payload,
    )
    statement = build_statement(
        inputs_descriptor_hash=inputs_descriptor_hash,
        policy_program_id=policy_program_id,
        opcode_table_id=opcode_table_id,
        merged_hint_state_id=merged_hint_state_id,
        decision_plan_hash=canon_hash_obj(decision_payload),
        steps_executed_u64=int(public_outputs["steps_executed_u64"]),
        budget_outcome_hash=str(public_outputs["budget_outcome_hash"]),
        air_profile_id=str(air_profile_payload.get("air_profile_id", "")),
        proof_options_hash=proof_options_hash,
    )
    cli_input, proof_options_hash = _build_cli_input(
        statement=statement,
        public_outputs=public_outputs,
        trace_payload=trace_payload,
        profile_payload=air_profile_payload,
        backend_contract_payload=backend_contract_payload,
        action_kind_enum_payload=action_kind_enum_payload,
        candidate_campaign_ids_payload=candidate_campaign_ids_payload,
    )
    with tempfile.TemporaryDirectory(prefix="policy_vm_stark_rs_v1_") as td:
        root = Path(td)
        input_path = root / "input.json"
        proof_path = root / "proof.bin"
        receipt_path = root / "receipt.json"
        input_path.write_text(
            json.dumps(cli_input, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
            encoding="utf-8",
        )
        proof_path.write_bytes(proof_bytes)
        _run_rust_cli(
            [
                "cargo",
                "run",
                "--quiet",
                "--manifest-path",
                str(_CRATE_MANIFEST),
                "--",
                "--mode",
                "verify",
                "--input-json",
                str(input_path),
                "--proof-in",
                str(proof_path),
                "--receipt-out",
                str(receipt_path),
            ]
        )
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    return {
        "statement": statement,
        "public_outputs": public_outputs,
        "proof_options_hash": proof_options_hash,
        "runner_receipt": receipt,
    }


__all__ = [
    "build_statement",
    "prove_policy_vm_stark",
    "verify_policy_vm_stark",
]
