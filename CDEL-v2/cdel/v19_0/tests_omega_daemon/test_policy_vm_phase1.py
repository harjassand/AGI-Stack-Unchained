from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "CDEL-v2") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "CDEL-v2"))

from cdel.v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed
from cdel.v18_0.omega_common_v1 import OmegaV18Error, canon_hash_obj
from cdel.v19_0.verify_inputs_descriptor_v1 import verify_inputs_descriptor
from orchestrator.omega_v19_0.policy_vm_v1 import build_inputs_descriptor_v1, run_policy_vm_v1


def _sha(payload: dict) -> str:
    return sha256_prefixed(canon_bytes(payload))


def _fill_program_id(program: dict) -> dict:
    out = dict(program)
    no_id = dict(out)
    no_id.pop("program_id", None)
    out["program_id"] = _sha(no_id)
    return out


def _fill_opcode_table_id(opcode_table: dict) -> dict:
    out = dict(opcode_table)
    no_id = dict(out)
    no_id.pop("opcode_table_id", None)
    out["opcode_table_id"] = _sha(no_id)
    return out


def test_policy_vm_phase1_decision_is_deterministic(tmp_path: Path) -> None:
    pack_src = REPO_ROOT / "campaigns" / "rsi_omega_daemon_v19_0_super_unified"
    pack_dst = tmp_path / "pack"
    shutil.copytree(pack_src, pack_dst)

    program = load_canon_json(pack_dst / "coordinator_isa_program_v1.json")
    opcode_table = load_canon_json(pack_dst / "coordinator_opcode_table_v1.json")
    registry = load_canon_json(pack_dst / "omega_capability_registry_v2.json")

    observation = {
        "schema_version": "omega_observation_report_v1",
        "tick_u64": 7,
        "metrics": {
            "brain_temperature_q32": {"q": 3000000000},
        },
    }
    observation_hash = _sha(observation)
    issue_bundle_hash = "sha256:" + ("1" * 64)
    policy_hash = "sha256:" + ("2" * 64)
    registry_hash = _sha(registry)
    budgets_hash = "sha256:" + ("3" * 64)

    descriptor = build_inputs_descriptor_v1(
        tick_u64=7,
        state_hash="sha256:" + ("5" * 64),
        repo_tree_id="sha256:" + ("9" * 64),
        observation_hash=observation_hash,
        issues_hash=issue_bundle_hash,
        registry_hash=registry_hash,
        policy_program_ids=[str(program["program_id"])],
        predictor_id="sha256:" + ("c" * 64),
        j_profile_id="sha256:" + ("d" * 64),
        opcode_table_id=str(opcode_table["opcode_table_id"]),
        budget_spec_id="sha256:" + ("e" * 64),
        determinism_contract_id="sha256:" + ("f" * 64),
    )
    descriptor_hash = canon_hash_obj(descriptor)

    out_1 = run_policy_vm_v1(
        tick_u64=7,
        mode="DECISION_ONLY",
        inputs_descriptor_hash=descriptor_hash,
        observation_report=observation,
        observation_hash=observation_hash,
        issue_bundle_hash=issue_bundle_hash,
        policy_hash=policy_hash,
        registry=registry,
        registry_hash=registry_hash,
        budgets_hash=budgets_hash,
        program=program,
        opcode_table=opcode_table,
    )
    out_2 = run_policy_vm_v1(
        tick_u64=7,
        mode="DECISION_ONLY",
        inputs_descriptor_hash=descriptor_hash,
        observation_report=observation,
        observation_hash=observation_hash,
        issue_bundle_hash=issue_bundle_hash,
        policy_hash=policy_hash,
        registry=registry,
        registry_hash=registry_hash,
        budgets_hash=budgets_hash,
        program=program,
        opcode_table=opcode_table,
    )

    assert canon_hash_obj(out_1["decision_plan"]) == canon_hash_obj(out_2["decision_plan"])
    assert canon_hash_obj(out_1["policy_vm_trace"]) == canon_hash_obj(out_2["policy_vm_trace"])
    assert out_1["decision_plan"]["recompute_proof"]["inputs_hash"] == descriptor_hash


def test_inputs_descriptor_stable_and_self_consistent() -> None:
    kwargs = {
        "tick_u64": 3,
        "state_hash": "sha256:" + ("1" * 64),
        "repo_tree_id": "sha256:" + ("9" * 64),
        "observation_hash": "sha256:" + ("2" * 64),
        "issues_hash": "sha256:" + ("3" * 64),
        "registry_hash": "sha256:" + ("3" * 64),
        "policy_program_ids": ["sha256:" + ("4" * 64)],
        "predictor_id": "sha256:" + ("5" * 64),
        "j_profile_id": "sha256:" + ("6" * 64),
        "opcode_table_id": "sha256:" + ("b" * 64),
        "budget_spec_id": "sha256:" + ("7" * 64),
        "determinism_contract_id": "sha256:" + ("8" * 64),
    }
    d1 = build_inputs_descriptor_v1(**kwargs)
    d2 = build_inputs_descriptor_v1(**kwargs)

    assert d1 == d2
    assert verify_inputs_descriptor(d1) == "VALID"


def test_policy_vm_decision_only_rejects_yield_hints() -> None:
    opcode_table = _fill_opcode_table_id(
        {
            "schema_version": "coordinator_opcode_table_v1",
            "isa_version": 1,
            "opcode_table_id": "sha256:" + ("0" * 64),
            "opcodes": {
                "YIELD_HINTS": {"enabled_b": True},
            },
            "forbidden_in_phase1": [],
        }
    )

    program = _fill_program_id(
        {
            "schema_version": "coordinator_isa_program_v1",
            "isa_version": 1,
            "program_id": "sha256:" + ("0" * 64),
            "entry_pc_u32": 0,
            "constants": {},
            "instructions": [{"op": "YIELD_HINTS", "args": {"round_u32": 0}}],
            "declared_limits": {
                "max_steps_u64": 16,
                "max_stack_items_u32": 8,
                "max_trace_bytes_u64": 65536,
            },
        }
    )

    with pytest.raises(OmegaV18Error) as exc:
        run_policy_vm_v1(
            tick_u64=1,
            mode="DECISION_ONLY",
            inputs_descriptor_hash="sha256:" + ("a" * 64),
            observation_report={"metrics": {"brain_temperature_q32": {"q": 1}}},
            observation_hash="sha256:" + ("b" * 64),
            issue_bundle_hash="sha256:" + ("c" * 64),
            policy_hash="sha256:" + ("d" * 64),
            registry={"capabilities": []},
            registry_hash="sha256:" + ("e" * 64),
            budgets_hash="sha256:" + ("f" * 64),
            program=program,
            opcode_table=opcode_table,
        )

    assert str(exc.value) == "INVALID:POLICY_MODE_VIOLATION"


def test_policy_vm_stack_type_mismatch_fail_closed() -> None:
    opcode_table = _fill_opcode_table_id(
        {
            "schema_version": "coordinator_opcode_table_v1",
            "isa_version": 1,
            "opcode_table_id": "sha256:" + ("0" * 64),
            "opcodes": {
                "PUSH_CONST": {"enabled_b": True},
                "CMP_Q32": {"enabled_b": True},
            },
            "forbidden_in_phase1": [],
        }
    )

    program = _fill_program_id(
        {
            "schema_version": "coordinator_isa_program_v1",
            "isa_version": 1,
            "program_id": "sha256:" + ("0" * 64),
            "entry_pc_u32": 0,
            "constants": {
                "flag": {"type": "BOOL", "value": True},
                "q": {"type": "Q32", "value": 1},
            },
            "instructions": [
                {"op": "PUSH_CONST", "args": {"key": "flag"}},
                {"op": "PUSH_CONST", "args": {"key": "q"}},
                {"op": "CMP_Q32", "args": {"comparator": "GE"}},
            ],
            "declared_limits": {
                "max_steps_u64": 16,
                "max_stack_items_u32": 8,
                "max_trace_bytes_u64": 65536,
            },
        }
    )

    with pytest.raises(OmegaV18Error) as exc:
        run_policy_vm_v1(
            tick_u64=1,
            mode="DECISION_ONLY",
            inputs_descriptor_hash="sha256:" + ("a" * 64),
            observation_report={"metrics": {"brain_temperature_q32": {"q": 1}}},
            observation_hash="sha256:" + ("b" * 64),
            issue_bundle_hash="sha256:" + ("c" * 64),
            policy_hash="sha256:" + ("d" * 64),
            registry={"capabilities": []},
            registry_hash="sha256:" + ("e" * 64),
            budgets_hash="sha256:" + ("f" * 64),
            program=program,
            opcode_table=opcode_table,
        )

    assert str(exc.value) == "INVALID:STACK_TYPE_MISMATCH"


def test_policy_vm_trace_budget_exceeded() -> None:
    opcode_table = _fill_opcode_table_id(
        {
            "schema_version": "coordinator_opcode_table_v1",
            "isa_version": 1,
            "opcode_table_id": "sha256:" + ("0" * 64),
            "opcodes": {
                "NOP": {"enabled_b": True},
            },
            "forbidden_in_phase1": [],
        }
    )

    program = _fill_program_id(
        {
            "schema_version": "coordinator_isa_program_v1",
            "isa_version": 1,
            "program_id": "sha256:" + ("0" * 64),
            "entry_pc_u32": 0,
            "constants": {},
            "instructions": [{"op": "NOP", "args": {}}],
            "declared_limits": {
                "max_steps_u64": 16,
                "max_stack_items_u32": 8,
                "max_trace_bytes_u64": 1,
            },
        }
    )

    with pytest.raises(OmegaV18Error) as exc:
        run_policy_vm_v1(
            tick_u64=1,
            mode="DECISION_ONLY",
            inputs_descriptor_hash="sha256:" + ("a" * 64),
            observation_report={"metrics": {"brain_temperature_q32": {"q": 1}}},
            observation_hash="sha256:" + ("b" * 64),
            issue_bundle_hash="sha256:" + ("c" * 64),
            policy_hash="sha256:" + ("d" * 64),
            registry={"capabilities": []},
            registry_hash="sha256:" + ("e" * 64),
            budgets_hash="sha256:" + ("f" * 64),
            program=program,
            opcode_table=opcode_table,
        )

    assert str(exc.value) == "INVALID:TRACE_BUDGET_EXCEEDED"


def test_policy_vm_consume_merged_hint_requires_own_hint_inclusion() -> None:
    opcode_table = _fill_opcode_table_id(
        {
            "schema_version": "coordinator_opcode_table_v1",
            "isa_version": 1,
            "opcode_table_id": "sha256:" + ("0" * 64),
            "opcodes": {
                "PUSH_CONST": {"enabled_b": True},
                "SET_PLAN_FIELD": {"enabled_b": True},
                "YIELD_HINTS": {"enabled_b": True},
                "CONSUME_MERGED_HINT_STATE": {"enabled_b": True},
                "HALT_PROPOSE": {"enabled_b": True},
            },
            "forbidden_in_phase1": [],
        }
    )
    program = _fill_program_id(
        {
            "schema_version": "coordinator_isa_program_v1",
            "isa_version": 1,
            "program_id": "sha256:" + ("0" * 64),
            "entry_pc_u32": 0,
            "constants": {
                "action_kind_safe_halt": {"type": "STRING", "value": "SAFE_HALT"},
            },
            "instructions": [
                {"op": "PUSH_CONST", "args": {"key": "action_kind_safe_halt"}},
                {"op": "SET_PLAN_FIELD", "args": {"field": "action_kind", "from": "STACK"}},
                {"op": "YIELD_HINTS", "args": {"round_u32": 0}},
                {"op": "CONSUME_MERGED_HINT_STATE", "args": {"round_u32": 0}},
                {"op": "HALT_PROPOSE", "args": {}},
            ],
            "declared_limits": {
                "max_steps_u64": 32,
                "max_stack_items_u32": 16,
                "max_trace_bytes_u64": 65536,
            },
        }
    )
    inputs_hash = "sha256:" + ("a" * 64)
    observation_hash = "sha256:" + ("b" * 64)

    pass0 = run_policy_vm_v1(
        tick_u64=1,
        mode="PROPOSAL_ONLY",
        inputs_descriptor_hash=inputs_hash,
        observation_report={"metrics": {"brain_temperature_q32": {"q": 1}}},
        observation_hash=observation_hash,
        issue_bundle_hash="sha256:" + ("c" * 64),
        policy_hash="sha256:" + ("d" * 64),
        registry={"capabilities": []},
        registry_hash="sha256:" + ("e" * 64),
        budgets_hash="sha256:" + ("f" * 64),
        program=program,
        opcode_table=opcode_table,
        branch_id="b00",
        round_u32=0,
    )
    hint_payload = pass0.get("hint_bundle")
    continuation = pass0.get("continuation_state")
    assert isinstance(hint_payload, dict)
    assert isinstance(continuation, dict)
    own_hint_hash = canon_hash_obj(hint_payload)
    forged_other_hash = "sha256:" + ("f" * 64)
    merged_payload = {
        "schema_version": "merged_hint_state_v1",
        "inputs_descriptor_hash": inputs_hash,
        "round_u32": 0,
        "contributing_hint_hashes": [forged_other_hash],
        "merge_policy_id": "sha256:" + ("1" * 64),
        "merged_hints": [],
    }

    with pytest.raises(OmegaV18Error) as exc:
        run_policy_vm_v1(
            tick_u64=1,
            mode="PROPOSAL_ONLY",
            inputs_descriptor_hash=inputs_hash,
            observation_report={"metrics": {"brain_temperature_q32": {"q": 1}}},
            observation_hash=observation_hash,
            issue_bundle_hash="sha256:" + ("c" * 64),
            policy_hash="sha256:" + ("d" * 64),
            registry={"capabilities": []},
            registry_hash="sha256:" + ("e" * 64),
            budgets_hash="sha256:" + ("f" * 64),
            program=program,
            opcode_table=opcode_table,
            branch_id="b00",
            round_u32=0,
            resume_state=continuation,
            barrier_ctx={
                "merged_hint_state_by_round": {0: merged_payload},
                "expected_hint_hashes_by_round": {0: [forged_other_hash]},
                "branch_emitted_hint_rounds": [0],
                "branch_hint_hashes_by_round": {"0": own_hint_hash},
            },
        )

    assert str(exc.value) == "INVALID:HINT_SYNC_VIOLATION"


def test_policy_vm_opcode_deprecated_fails_closed() -> None:
    opcode_table = _fill_opcode_table_id(
        {
            "schema_version": "coordinator_opcode_table_v1",
            "isa_version": 1,
            "opcode_table_id": "sha256:" + ("0" * 64),
            "table_id": "sha256:" + ("1" * 64),
            "entries": [
                {
                    "opcode_u16": 1,
                    "opcode_name": "NOP",
                    "kind": "BUILTIN",
                    "active_b": False,
                    "impl": {"impl_kind": "BUILTIN", "module_id": "policy_vm_v1", "function_id": "nop"},
                    "introduced_tick_u64": 1,
                    "deprecated_tick_u64": 2,
                }
            ],
            "forbidden_in_phase1": [],
        }
    )
    no_id = dict(opcode_table)
    no_id.pop("opcode_table_id", None)
    opcode_table["opcode_table_id"] = _sha(no_id)

    program = _fill_program_id(
        {
            "schema_version": "coordinator_isa_program_v1",
            "isa_version": 1,
            "program_id": "sha256:" + ("0" * 64),
            "entry_pc_u32": 0,
            "constants": {},
            "instructions": [{"op": "NOP", "args": {}}],
            "declared_limits": {
                "max_steps_u64": 16,
                "max_stack_items_u32": 8,
                "max_trace_bytes_u64": 65536,
            },
        }
    )

    with pytest.raises(OmegaV18Error) as exc:
        run_policy_vm_v1(
            tick_u64=1,
            mode="DECISION_ONLY",
            inputs_descriptor_hash="sha256:" + ("a" * 64),
            observation_report={"metrics": {"brain_temperature_q32": {"q": 1}}},
            observation_hash="sha256:" + ("b" * 64),
            issue_bundle_hash="sha256:" + ("c" * 64),
            policy_hash="sha256:" + ("d" * 64),
            registry={"capabilities": []},
            registry_hash="sha256:" + ("e" * 64),
            budgets_hash="sha256:" + ("f" * 64),
            program=program,
            opcode_table=opcode_table,
        )
    assert str(exc.value) == "INVALID:OPCODE_DEPRECATED"
