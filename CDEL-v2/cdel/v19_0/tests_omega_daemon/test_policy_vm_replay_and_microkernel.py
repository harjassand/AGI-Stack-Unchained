from __future__ import annotations

import json
import math
import os
import subprocess
import shutil
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "CDEL-v2") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "CDEL-v2"))

from cdel.v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json
from cdel.v18_0.ccap_runtime_v1 import compute_repo_base_tree_id_tolerant
from cdel.v18_0.omega_common_v1 import repo_root as repo_root_v18
from cdel.v18_0.verify_rsi_omega_daemon_v1 import OmegaV18Error, _verify_inputs_descriptor_binding, verify as verify_v18
from cdel.v19_0.common_v1 import OmegaV19Error
from cdel.v19_0.policy_vm_stark_runner_v1 import prove_policy_vm_stark
from cdel.v19_0.verify_policy_vm_stark_proof_v1 import verify_policy_vm_stark_proof
from cdel.v19_0.verify_rsi_omega_daemon_v1 import verify as verify_v19
from orchestrator.omega_v18_0 import coordinator_v1 as coordinator_v18
from orchestrator.omega_v19_0 import coordinator_v1 as coordinator_v19
from orchestrator.omega_v19_0 import microkernel_v1

_WINTERFELL_BACKEND_ID = "WINTERFELL_RS_0_13_1"
_WINTERFELL_BACKEND_VERSION = "0.13.1"
_WINTERFELL_FIELD_ID = "WINTERFELL_F128"
_WINTERFELL_EXTENSION_ID = "FIELD_EXTENSION_NONE_DEGREE_1"
_WINTERFELL_MERKLE_HASHER_ID = "winterfell::crypto::hashers::Blake3_256"
_WINTERFELL_RANDOM_COIN_HASHER_ID = "winterfell::crypto::DefaultRandomCoin<Blake3_256>"
_WINTERFELL_PROOF_OPTIONS_KEYS = [
    "num_queries",
    "blowup_factor",
    "grinding_factor",
    "field_extension",
    "fri_folding_factor",
    "fri_remainder_max_degree",
    "batching_constraints",
    "batching_deep",
    "num_partitions",
    "hash_rate",
]
_PHASE4_CANARY_SEEDS: tuple[int, ...] = tuple(range(19_000_001, 19_000_011))
_PHASE4_CANARY_SLO_BY_PROFILE: dict[str, dict[str, int]] = {
    "POLICY_VM_AIR_PROFILE_96_V1": {
        "p95_prove_time_ms": 3000,
        "p95_verify_time_ms": 250,
        "max_proof_size_bytes": 1_500_000,
    },
    "POLICY_VM_AIR_PROFILE_128_V1": {
        "p95_prove_time_ms": 4500,
        "p95_verify_time_ms": 350,
        "max_proof_size_bytes": 2_200_000,
    },
}


def _default_winterfell_backend_contract() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "policy_vm_winterfell_backend_contract_v1",
        "backend_contract_id": "sha256:" + ("0" * 64),
        "winterfell_backend_id": _WINTERFELL_BACKEND_ID,
        "winterfell_backend_version": _WINTERFELL_BACKEND_VERSION,
        "winterfell_field_id": _WINTERFELL_FIELD_ID,
        "winterfell_extension_id": _WINTERFELL_EXTENSION_ID,
        "winterfell_merkle_hasher_id": _WINTERFELL_MERKLE_HASHER_ID,
        "winterfell_random_coin_hasher_id": _WINTERFELL_RANDOM_COIN_HASHER_ID,
        "winterfell_proof_options_keys": list(_WINTERFELL_PROOF_OPTIONS_KEYS),
    }
    payload["backend_contract_id"] = _sha_obj(
        {k: v for k, v in payload.items() if k != "backend_contract_id"}
    )
    return payload


def _default_winterfell_proof_options(*, profile_kind: str) -> dict[str, object]:
    if profile_kind == "POLICY_VM_AIR_PROFILE_128_V1":
        num_queries = 42
        grinding_factor = 2
    else:
        num_queries = 32
        grinding_factor = 0
    return {
        "num_queries": int(num_queries),
        "blowup_factor": 8,
        "grinding_factor": int(grinding_factor),
        "field_extension": "None",
        "fri_folding_factor": 8,
        "fri_remainder_max_degree": 63,
        "batching_constraints": "Linear",
        "batching_deep": "Linear",
        "num_partitions": 1,
        "hash_rate": 1,
    }


def _build_action_kind_enum() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "action_kind_enum_v1",
        "action_kind_enum_id": "sha256:" + ("0" * 64),
        "entries": [
            {"code_u8": 0, "action_kind": "SAFE_HALT"},
            {"code_u8": 1, "action_kind": "NOOP"},
            {"code_u8": 2, "action_kind": "RUN_CAMPAIGN"},
        ],
    }
    payload["action_kind_enum_id"] = _sha_obj(
        {k: v for k, v in payload.items() if k != "action_kind_enum_id"}
    )
    return payload


def _build_candidate_campaign_ids_list() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "candidate_campaign_ids_list_v1",
        "candidate_campaign_ids_list_id": "sha256:" + ("0" * 64),
        "campaign_ids": [
            "rsi_patch_verifier_v1",
            "rsi_metasearch_knowledge_v1",
        ],
    }
    payload["candidate_campaign_ids_list_id"] = _sha_obj(
        {k: v for k, v in payload.items() if k != "candidate_campaign_ids_list_id"}
    )
    return payload


def _build_air_profile(
    *,
    backend_contract: dict[str, object],
    action_kind_enum_id: str,
    candidate_campaign_ids_list_id: str,
    profile_kind: str = "POLICY_VM_AIR_PROFILE_96_V1",
) -> dict[str, object]:
    proof_options = _default_winterfell_proof_options(profile_kind=profile_kind)
    payload: dict[str, object] = {
        "schema_version": "policy_vm_air_profile_v1",
        "air_profile_id": "sha256:" + ("0" * 64),
        "isa_version": 1,
        "constraint_system_version": 1,
        "proof_system_id": "WINTERFELL_STARK_FRI_V1",
        "base_field_id": "WINTERFELL_F128",
        "extension_degree_u32": 1,
        "commitment_hash_id": _WINTERFELL_MERKLE_HASHER_ID,
        "random_coin_hash_id": _WINTERFELL_RANDOM_COIN_HASHER_ID,
        "proof_options": dict(proof_options),
        "candidate_campaign_ids_list_hash": str(candidate_campaign_ids_list_id),
        "action_kind_enum_hash": str(action_kind_enum_id),
        "action_encoding_kind": "CONST_INDEX_TUPLE_V1",
        "supported_action_kinds": ["SAFE_HALT", "NOOP", "RUN_CAMPAIGN"],
        "winterfell_backend_id": str(backend_contract["winterfell_backend_id"]),
        "winterfell_backend_version": str(backend_contract["winterfell_backend_version"]),
        "winterfell_field_id": str(backend_contract["winterfell_field_id"]),
        "winterfell_extension_id": str(backend_contract["winterfell_extension_id"]),
        "winterfell_merkle_hasher_id": str(backend_contract["winterfell_merkle_hasher_id"]),
        "winterfell_random_coin_hasher_id": str(backend_contract["winterfell_random_coin_hasher_id"]),
        "winterfell_proof_options": dict(proof_options),
        "profile_kind": str(profile_kind),
        "supported_opcodes": [
            "NOP",
            "PUSH_CONST",
            "CMP_Q32",
            "CMP_U64",
            "JZ",
            "JMP",
            "SET_PLAN_FIELD",
            "EMIT_PLAN",
        ],
    }
    payload["air_profile_id"] = _sha_obj({k: v for k, v in payload.items() if k != "air_profile_id"})
    return payload


def _write_proof_profile_contract_to_dir(
    *,
    target_dir: Path,
    pack_path: Path | None = None,
    backend_contract: dict[str, object] | None = None,
    air_profile: dict[str, object] | None = None,
    profile_kind: str = "POLICY_VM_AIR_PROFILE_96_V1",
) -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    backend = dict(backend_contract) if isinstance(backend_contract, dict) else _default_winterfell_backend_contract()
    action_kind_enum = _build_action_kind_enum()
    candidate_campaign_ids = _build_candidate_campaign_ids_list()
    profile = (
        dict(air_profile)
        if isinstance(air_profile, dict)
        else _build_air_profile(
            backend_contract=backend,
            action_kind_enum_id=str(action_kind_enum["action_kind_enum_id"]),
            candidate_campaign_ids_list_id=str(candidate_campaign_ids["candidate_campaign_ids_list_id"]),
            profile_kind=profile_kind,
        )
    )
    write_canon_json(target_dir / "policy_vm_winterfell_backend_contract_v1.json", backend)
    write_canon_json(target_dir / "action_kind_enum_v1.json", action_kind_enum)
    write_canon_json(target_dir / "candidate_campaign_ids_list_v1.json", candidate_campaign_ids)
    write_canon_json(target_dir / "policy_vm_air_profile_v1.json", profile)
    if pack_path is not None:
        pack = load_canon_json(pack_path)
        pack["policy_vm_stark_proof_enable_b"] = True
        pack["policy_vm_air_profile_rel"] = "policy_vm_air_profile_v1.json"
        pack["policy_vm_air_profile_id"] = str(profile["air_profile_id"])
        pack["policy_vm_winterfell_backend_contract_rel"] = "policy_vm_winterfell_backend_contract_v1.json"
        pack["policy_vm_winterfell_backend_contract_id"] = str(backend["backend_contract_id"])
        pack["policy_vm_action_kind_enum_rel"] = "action_kind_enum_v1.json"
        pack["policy_vm_action_kind_enum_id"] = str(action_kind_enum["action_kind_enum_id"])
        pack["policy_vm_candidate_campaign_ids_list_rel"] = "candidate_campaign_ids_list_v1.json"
        pack["policy_vm_candidate_campaign_ids_list_id"] = str(candidate_campaign_ids["candidate_campaign_ids_list_id"])
        write_canon_json(pack_path, pack)
    return backend, profile, action_kind_enum, candidate_campaign_ids


def _write_unit_verifier_config(
    *,
    state_root: Path,
    backend_contract: dict[str, object] | None = None,
    air_profile: dict[str, object] | None = None,
) -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    config_dir = state_root.parent / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    backend, profile, action_kind_enum, candidate_campaign_ids = _write_proof_profile_contract_to_dir(
        target_dir=config_dir,
        backend_contract=backend_contract,
        air_profile=air_profile,
    )
    pack = {
        "schema_version": "rsi_omega_daemon_pack_v2",
        "policy_vm_air_profile_rel": "policy_vm_air_profile_v1.json",
        "policy_vm_air_profile_id": str(profile["air_profile_id"]),
        "policy_vm_winterfell_backend_contract_rel": "policy_vm_winterfell_backend_contract_v1.json",
        "policy_vm_winterfell_backend_contract_id": str(backend["backend_contract_id"]),
        "policy_vm_action_kind_enum_rel": "action_kind_enum_v1.json",
        "policy_vm_action_kind_enum_id": str(action_kind_enum["action_kind_enum_id"]),
        "policy_vm_candidate_campaign_ids_list_rel": "candidate_campaign_ids_list_v1.json",
        "policy_vm_candidate_campaign_ids_list_id": str(candidate_campaign_ids["candidate_campaign_ids_list_id"]),
    }
    write_canon_json(config_dir / "rsi_omega_daemon_pack_v1.json", pack)
    return backend, profile, action_kind_enum, candidate_campaign_ids


def _build_minimal_semantic_proof_payload(
    *,
    state_root: Path,
    backend_contract: dict[str, object] | None = None,
    air_profile: dict[str, object] | None = None,
    embedded_options_override: dict[str, object] | None = None,
) -> tuple[dict[str, object], Path, dict[str, object], dict[str, object], dict[str, object]]:
    backend, profile, action_kind_enum, candidate_campaign_ids = _write_unit_verifier_config(
        state_root=state_root,
        backend_contract=backend_contract,
        air_profile=air_profile,
    )
    proof_options_hash = _sha_obj(dict(profile["proof_options"]))
    decision_payload: dict[str, object] = {
        "schema_version": "omega_decision_plan_v1",
        "plan_id": "sha256:" + ("0" * 64),
        "tick_u64": 1,
        "observation_report_hash": "sha256:" + ("2" * 64),
        "issue_bundle_hash": "sha256:" + ("3" * 64),
        "policy_hash": "sha256:" + ("4" * 64),
        "registry_hash": "sha256:" + ("5" * 64),
        "budgets_hash": "sha256:" + ("6" * 64),
        "action_kind": "NOOP",
        "priority_q32": {"q": 0},
        "tie_break_path": [],
        "recompute_proof": {
            "inputs_hash": "sha256:" + ("1" * 64),
            "plan_hash": "sha256:" + ("e" * 64),
        },
    }
    decision_payload["plan_id"] = _sha_obj({k: v for k, v in decision_payload.items() if k != "plan_id"})
    trace_payload: dict[str, object] = {
        "schema_version": "policy_vm_trace_v1",
        "inputs_descriptor_hash": "sha256:" + ("1" * 64),
        "policy_program_id": "sha256:" + ("2" * 64),
        "branch_id": "b00",
        "round_u32": 0,
        "steps_executed_u64": 1,
        "trace_hash_chain_hash": "sha256:" + ("a" * 64),
        "final_stack_commitment_hash": "sha256:" + ("b" * 64),
        "halt_reason": "EMIT_PLAN",
        "budget_outcome": {
            "items_used_u64": 0,
            "bytes_read_u64": 0,
            "bytes_written_u64": 0,
        },
        "step_log": [
            {
                "pc_u32": 0,
                "op": "EMIT_PLAN",
                "args": {"plan_kind": "DECISION_PLAN_V1"},
                "next_pc_u32": 1,
                "stack_before": "sha256:" + ("c" * 64),
                "stack_after": "sha256:" + ("d" * 64),
                "stack_before_state": [],
                "stack_after_state": [{"kind": "PLAN_REF", "value": str(decision_payload["plan_id"])}],
            }
        ],
    }
    trace_hash = _sha_obj(trace_payload)
    decision_hash = _sha_obj(decision_payload)
    statement: dict[str, object] = {
        "inputs_descriptor_hash": "sha256:" + ("1" * 64),
        "policy_program_id": "sha256:" + ("2" * 64),
        "opcode_table_id": "sha256:" + ("3" * 64),
        "merged_hint_state_id": None,
        "decision_plan_hash": decision_hash,
        "steps_executed_u64": 1,
        "budget_outcome_hash": _sha_obj(dict(trace_payload["budget_outcome"])),
        "air_profile_id": str(profile["air_profile_id"]),
        "proof_options_hash": proof_options_hash,
    }
    proof_out = prove_policy_vm_stark(
        trace_payload=trace_payload,
        decision_payload=decision_payload,
        inputs_descriptor_hash=str(statement["inputs_descriptor_hash"]),
        policy_program_id=str(statement["policy_program_id"]),
        opcode_table_id=str(statement["opcode_table_id"]),
        merged_hint_state_id=None,
        air_profile_payload=profile,
        backend_contract_payload=backend,
        action_kind_enum_payload=action_kind_enum,
        candidate_campaign_ids_payload=candidate_campaign_ids,
    )
    statement = dict(proof_out["statement"])
    proof_bytes = bytes(proof_out["proof_bytes"])
    proof_bytes_hash = sha256_prefixed(proof_bytes)
    proof_bytes_hex = proof_bytes_hash.split(":", 1)[1]
    proof_bin_rel = f"policy/proofs/sha256_{proof_bytes_hex}.policy_vm_stark_proof_v1.bin"
    proof_bin_path = state_root / proof_bin_rel
    proof_bin_path.parent.mkdir(parents=True, exist_ok=True)
    proof_bin_path.write_bytes(proof_bytes)
    decision_dir = state_root / "decisions"
    decision_dir.mkdir(parents=True, exist_ok=True)
    write_canon_json(
        decision_dir / f"sha256_{decision_hash.split(':', 1)[1]}.omega_decision_plan_v1.json",
        decision_payload,
    )
    trace_dir = state_root / "policy" / "traces"
    trace_dir.mkdir(parents=True, exist_ok=True)
    write_canon_json(
        trace_dir / f"sha256_{trace_hash.split(':', 1)[1]}.policy_vm_trace_v1.json",
        trace_payload,
    )
    proof_payload: dict[str, object] = {
        "schema_version": "policy_vm_stark_proof_v1",
        "proof_id": "sha256:" + ("0" * 64),
        **statement,
        "proof_backend_id": "WINTERFELL_STARK_FRI_V1",
        "public_outputs": dict(proof_out["public_outputs"]),
        "proof_representation_kind": "STARK_FRI_PROOF_V1",
        "proof_bytes_hash": proof_bytes_hash,
        "proof_bytes_rel": proof_bin_rel,
        "winterfell_backend_id": str(backend["winterfell_backend_id"]),
        "winterfell_backend_version": str(backend["winterfell_backend_version"]),
        "winterfell_field_id": str(backend["winterfell_field_id"]),
        "winterfell_extension_id": str(backend["winterfell_extension_id"]),
        "winterfell_merkle_hasher_id": str(backend["winterfell_merkle_hasher_id"]),
        "winterfell_random_coin_hasher_id": str(backend["winterfell_random_coin_hasher_id"]),
    }
    proof_payload["proof_id"] = _sha_obj({k: v for k, v in proof_payload.items() if k != "proof_id"})
    return proof_payload, proof_bin_path, statement, backend, profile


def _prepare_v19_noop_pack(dst_root: Path, *, max_steps_u64: int = 64) -> Path:
    src = REPO_ROOT / "campaigns" / "rsi_omega_daemon_v19_0_super_unified"
    dst = dst_root / "campaign_pack"
    shutil.copytree(src, dst)

    program = {
        "schema_version": "coordinator_isa_program_v1",
        "isa_version": 1,
        "program_id": "sha256:" + ("0" * 64),
        "entry_pc_u32": 0,
        "constants": {},
        "instructions": [{"op": "EMIT_PLAN", "args": {"plan_kind": "DECISION_PLAN_V1"}}],
        "declared_limits": {
            "max_steps_u64": int(max_steps_u64),
            "max_stack_items_u32": 32,
            "max_trace_bytes_u64": 1_048_576,
        },
    }
    no_id = dict(program)
    no_id.pop("program_id", None)
    program["program_id"] = sha256_prefixed(canon_bytes(no_id))
    write_canon_json(dst / "coordinator_isa_program_v1.json", program)

    opcode_table = load_canon_json(dst / "coordinator_opcode_table_v1.json")
    pack = load_canon_json(dst / "rsi_omega_daemon_pack_v1.json")
    pack["coordinator_isa_program_id"] = str(program["program_id"])
    pack["coordinator_opcode_table_id"] = str(opcode_table["opcode_table_id"])
    pack["policy_vm_mode"] = "DECISION_ONLY"
    write_canon_json(dst / "rsi_omega_daemon_pack_v1.json", pack)

    return dst / "rsi_omega_daemon_pack_v1.json"


def _prepare_v19_opcode_pack(
    dst_root: Path,
    *,
    nop_kind: str,
    nop_active_b: bool,
    nop_binary_sha256: str | None = None,
    deprecated_tick_u64: int = 0,
) -> Path:
    src = REPO_ROOT / "campaigns" / "rsi_omega_daemon_v19_0_super_unified"
    dst = dst_root / "campaign_pack"
    shutil.copytree(src, dst)

    program = {
        "schema_version": "coordinator_isa_program_v1",
        "isa_version": 1,
        "program_id": "sha256:" + ("0" * 64),
        "entry_pc_u32": 0,
        "constants": {},
        "instructions": [
            {"op": "NOP", "args": {}},
            {"op": "EMIT_PLAN", "args": {"plan_kind": "DECISION_PLAN_V1"}},
        ],
        "declared_limits": {
            "max_steps_u64": 64,
            "max_stack_items_u32": 32,
            "max_trace_bytes_u64": 1_048_576,
        },
    }
    program["program_id"] = _sha_obj({k: v for k, v in program.items() if k != "program_id"})
    write_canon_json(dst / "coordinator_isa_program_v1.json", program)

    nop_impl: dict[str, object]
    if nop_kind.upper() == "NATIVE":
        if not isinstance(nop_binary_sha256, str):
            raise AssertionError("nop_binary_sha256 is required for native opcode entries")
        nop_impl = {
            "impl_kind": "NATIVE",
            "op_id": "omega.native.nop.v1",
            "binary_sha256": nop_binary_sha256,
            "abi_version_u32": 1,
            "healthcheck_id": "sha256:" + ("c" * 64),
        }
    else:
        nop_impl = {
            "impl_kind": "BUILTIN",
            "module_id": "policy_vm_v1",
            "function_id": "nop",
        }

    opcode_table = {
        "schema_version": "coordinator_opcode_table_v1",
        "isa_version": 1,
        "opcode_table_id": "sha256:" + ("0" * 64),
        "table_id": "sha256:" + ("1" * 64),
        "entries": [
            {
                "opcode_u16": 1,
                "opcode_name": "EMIT_PLAN",
                "kind": "BUILTIN",
                "active_b": True,
                "impl": {"impl_kind": "BUILTIN", "module_id": "policy_vm_v1", "function_id": "emit_plan"},
                "introduced_tick_u64": 1,
                "deprecated_tick_u64": 0,
            },
            {
                "opcode_u16": 2,
                "opcode_name": "NOP",
                "kind": nop_kind.upper(),
                "active_b": bool(nop_active_b),
                "impl": nop_impl,
                "introduced_tick_u64": 1,
                "deprecated_tick_u64": int(deprecated_tick_u64),
            },
        ],
        "forbidden_in_phase1": [],
    }
    opcode_table["opcode_table_id"] = _sha_obj({k: v for k, v in opcode_table.items() if k != "opcode_table_id"})
    write_canon_json(dst / "coordinator_opcode_table_v1.json", opcode_table)

    pack = load_canon_json(dst / "rsi_omega_daemon_pack_v1.json")
    pack["coordinator_isa_program_id"] = str(program["program_id"])
    pack["coordinator_opcode_table_id"] = str(opcode_table["opcode_table_id"])
    pack["policy_vm_mode"] = "DECISION_ONLY"
    write_canon_json(dst / "rsi_omega_daemon_pack_v1.json", pack)
    return dst / "rsi_omega_daemon_pack_v1.json"


def _enable_policy_vm_proof(
    pack_path: Path,
    *,
    profile_kind: str = "POLICY_VM_AIR_PROFILE_96_V1",
) -> None:
    _write_proof_profile_contract_to_dir(
        target_dir=pack_path.parent,
        pack_path=pack_path,
        profile_kind=profile_kind,
    )


def _sha_obj(payload: dict) -> str:
    return sha256_prefixed(canon_bytes(payload))


def _prepare_v19_market_pack(dst_root: Path) -> Path:
    src = REPO_ROOT / "campaigns" / "rsi_omega_daemon_v19_0_super_unified"
    dst = dst_root / "campaign_pack"
    shutil.copytree(src, dst)

    def _write_program(name: str, instructions: list[dict], *, extra_consts: dict | None = None) -> str:
        program = {
            "schema_version": "coordinator_isa_program_v1",
            "isa_version": 1,
            "program_id": "sha256:" + ("0" * 64),
            "entry_pc_u32": 0,
            "constants": {
                "action_kind_safe_halt": {"type": "STRING", "value": "SAFE_HALT"},
            },
            "instructions": instructions,
            "declared_limits": {
                "max_steps_u64": 256,
                "max_stack_items_u32": 64,
                "max_trace_bytes_u64": 1_048_576,
            },
        }
        if isinstance(extra_consts, dict):
            program["constants"].update(extra_consts)
        no_id = dict(program)
        no_id.pop("program_id", None)
        program["program_id"] = _sha_obj(no_id)
        write_canon_json(dst / name, program)
        return str(program["program_id"])

    p00_id = _write_program(
        "policy_program_b00_v1.json",
        [
            {"op": "PUSH_CONST", "args": {"key": "action_kind_safe_halt"}},
            {"op": "SET_PLAN_FIELD", "args": {"field": "action_kind", "from": "STACK"}},
            {"op": "YIELD_HINTS", "args": {"round_u32": 0}},
            {"op": "CONSUME_MERGED_HINT_STATE", "args": {"round_u32": 0}},
            {"op": "HALT_PROPOSE", "args": {}},
        ],
    )
    p01_id = _write_program(
        "policy_program_b01_v1.json",
        [
            {"op": "PUSH_CONST", "args": {"key": "action_kind_safe_halt"}},
            {"op": "SET_PLAN_FIELD", "args": {"field": "action_kind", "from": "STACK"}},
            {"op": "YIELD_HINTS", "args": {"round_u32": 0}},
            {"op": "CONSUME_MERGED_HINT_STATE", "args": {"round_u32": 0}},
            {"op": "NOP", "args": {}},
            {"op": "HALT_PROPOSE", "args": {}},
        ],
    )

    budget_spec = {
        "schema_version": "policy_budget_spec_v1",
        "max_hint_bytes_u64": 1_048_576,
        "cost_model": {
            "base_cost_q32": 0,
            "per_step_q32": 1 << 32,
            "per_item_q32": 0,
            "per_byte_read_q32": 0,
            "per_byte_written_q32": 0,
        },
    }
    budget_spec_id = _sha_obj(budget_spec)
    write_canon_json(dst / "policy_budget_spec_v1.json", budget_spec)

    determinism_contract = {
        "schema_version": "determinism_contract_v1",
        "determinism_contract_id": "sha256:" + ("0" * 64),
        "no_floats_b": True,
        "no_rng_b": True,
        "fixed_sorting_b": True,
        "canonical_json_profile": "GCJ-1",
        "q_format": "Q32",
    }
    determinism_contract["determinism_contract_id"] = _sha_obj(
        {
            k: v
            for k, v in determinism_contract.items()
            if k != "determinism_contract_id"
        }
    )
    write_canon_json(dst / "determinism_contract_v1.json", determinism_contract)

    merge_policy = {
        "schema_version": "policy_merge_policy_v1",
        "merge_policy_id": "sha256:" + ("0" * 64),
        "q32_score_default_aggregator": "SUM",
        "q32_score_aggregators_by_key": {},
        "default_set_max_values_u32": 32,
        "set_max_values_by_key_u32": {},
    }
    merge_policy["merge_policy_id"] = _sha_obj({k: v for k, v in merge_policy.items() if k != "merge_policy_id"})
    write_canon_json(dst / "policy_merge_policy_v1.json", merge_policy)

    selection_policy = {
        "schema_version": "policy_selection_policy_v1",
        "selection_policy_id": "sha256:" + ("0" * 64),
        "cost_model": {
            "base_cost_q32": 0,
            "per_step_q32": 1 << 32,
            "per_item_q32": 0,
            "per_byte_read_q32": 0,
            "per_byte_written_q32": 0,
        },
        "counterfactual_target": {
            "temperature_q32": 1 << 16,
            "margin_q32": 0,
        },
    }
    selection_policy["selection_policy_id"] = _sha_obj(
        {k: v for k, v in selection_policy.items() if k != "selection_policy_id"}
    )
    write_canon_json(dst / "policy_selection_policy_v1.json", selection_policy)

    predictor = {
        "schema_version": "policy_predictor_v1",
        "predictor_id": "sha256:" + ("0" * 64),
        "bias_q32": {"q": 0},
        "w_plan_q32": {"q": 1},
        "w_obs_q32": {"q": 0},
    }
    predictor["predictor_id"] = _sha_obj({k: v for k, v in predictor.items() if k != "predictor_id"})
    write_canon_json(dst / "predictor_weights_v1.json", predictor)

    j_profile = {
        "schema_version": "objective_j_profile_v1",
        "profile_id": "sha256:" + ("0" * 64),
        "metric_weights": [],
        "bias_q32": {"q": 0},
    }
    j_profile["profile_id"] = _sha_obj({k: v for k, v in j_profile.items() if k != "profile_id"})
    write_canon_json(dst / "objective_j_profile_v1.json", j_profile)

    pack = load_canon_json(dst / "rsi_omega_daemon_pack_v1.json")
    pack["policy_vm_mode"] = "PROPOSAL_ONLY"
    pack["policy_programs"] = [
        {"program_rel": "policy_program_b00_v1.json", "program_id": p00_id},
        {"program_rel": "policy_program_b01_v1.json", "program_id": p01_id},
    ]
    pack["policy_budget_spec_rel"] = "policy_budget_spec_v1.json"
    pack["policy_budget_spec_id"] = budget_spec_id
    pack["policy_determinism_contract_rel"] = "determinism_contract_v1.json"
    pack["policy_determinism_contract_id"] = str(determinism_contract["determinism_contract_id"])
    pack["policy_merge_policy_rel"] = "policy_merge_policy_v1.json"
    pack["policy_merge_policy_id"] = str(merge_policy["merge_policy_id"])
    pack["policy_selection_policy_rel"] = "policy_selection_policy_v1.json"
    pack["policy_selection_policy_id"] = str(selection_policy["selection_policy_id"])
    pack["policy_parallelism_u32"] = 2
    pack["policy_hint_rounds_u32"] = 1
    pack["predictor_weights_rel"] = "predictor_weights_v1.json"
    pack["predictor_id"] = str(predictor["predictor_id"])
    pack["objective_j_profile_rel"] = "objective_j_profile_v1.json"
    pack["objective_j_profile_id"] = str(j_profile["profile_id"])
    write_canon_json(dst / "rsi_omega_daemon_pack_v1.json", pack)
    return dst / "rsi_omega_daemon_pack_v1.json"


def _prepare_v18_noop_pack(dst_root: Path) -> Path:
    src = REPO_ROOT / "campaigns" / "rsi_omega_daemon_v18_0"
    dst = dst_root / "campaign_pack"
    shutil.copytree(src, dst)

    policy = load_canon_json(dst / "omega_policy_ir_v1.json")
    policy["rules"] = []
    write_canon_json(dst / "omega_policy_ir_v1.json", policy)

    runaway_cfg = load_canon_json(dst / "omega_runaway_config_v1.json")
    runaway_cfg["enabled"] = False
    write_canon_json(dst / "omega_runaway_config_v1.json", runaway_cfg)

    write_canon_json(
        dst / "goals" / "omega_goal_queue_v1.json",
        {
            "schema_version": "omega_goal_queue_v1",
            "goals": [],
        },
    )
    return dst / "rsi_omega_daemon_pack_v1.json"


def _run_v19_tick(
    *,
    out_dir: Path,
    campaign_pack: Path,
    tick_u64: int,
    prev_state_dir: Path | None = None,
    run_seed_u64: int = 424242,
) -> tuple[dict, Path]:
    prev_mode = os.environ.get("OMEGA_META_CORE_ACTIVATION_MODE")
    prev_allow = os.environ.get("OMEGA_ALLOW_SIMULATE_ACTIVATION")
    prev_seed = os.environ.get("OMEGA_RUN_SEED_U64")
    prev_det = os.environ.get("OMEGA_V19_DETERMINISTIC_TIMING")
    os.environ["OMEGA_META_CORE_ACTIVATION_MODE"] = "simulate"
    os.environ["OMEGA_ALLOW_SIMULATE_ACTIVATION"] = "1"
    os.environ["OMEGA_RUN_SEED_U64"] = str(int(run_seed_u64))
    os.environ["OMEGA_V19_DETERMINISTIC_TIMING"] = "1"
    try:
        result = coordinator_v19.run_tick(
            campaign_pack=campaign_pack,
            out_dir=out_dir,
            tick_u64=tick_u64,
            prev_state_dir=prev_state_dir,
        )
    finally:
        if prev_mode is None:
            os.environ.pop("OMEGA_META_CORE_ACTIVATION_MODE", None)
        else:
            os.environ["OMEGA_META_CORE_ACTIVATION_MODE"] = prev_mode
        if prev_allow is None:
            os.environ.pop("OMEGA_ALLOW_SIMULATE_ACTIVATION", None)
        else:
            os.environ["OMEGA_ALLOW_SIMULATE_ACTIVATION"] = prev_allow
        if prev_seed is None:
            os.environ.pop("OMEGA_RUN_SEED_U64", None)
        else:
            os.environ["OMEGA_RUN_SEED_U64"] = prev_seed
        if prev_det is None:
            os.environ.pop("OMEGA_V19_DETERMINISTIC_TIMING", None)
        else:
            os.environ["OMEGA_V19_DETERMINISTIC_TIMING"] = prev_det

    state_dir = out_dir / "daemon" / "rsi_omega_daemon_v19_0" / "state"
    return result, state_dir


def _run_v18_tick(*, out_dir: Path, campaign_pack: Path, tick_u64: int) -> tuple[dict, Path]:
    prev_mode = os.environ.get("OMEGA_META_CORE_ACTIVATION_MODE")
    prev_allow = os.environ.get("OMEGA_ALLOW_SIMULATE_ACTIVATION")
    os.environ["OMEGA_META_CORE_ACTIVATION_MODE"] = "simulate"
    os.environ["OMEGA_ALLOW_SIMULATE_ACTIVATION"] = "1"
    try:
        result = coordinator_v18.run_tick(
            campaign_pack=campaign_pack,
            out_dir=out_dir,
            tick_u64=tick_u64,
        )
    finally:
        if prev_mode is None:
            os.environ.pop("OMEGA_META_CORE_ACTIVATION_MODE", None)
        else:
            os.environ["OMEGA_META_CORE_ACTIVATION_MODE"] = prev_mode
        if prev_allow is None:
            os.environ.pop("OMEGA_ALLOW_SIMULATE_ACTIVATION", None)
        else:
            os.environ["OMEGA_ALLOW_SIMULATE_ACTIVATION"] = prev_allow

    state_dir = out_dir / "daemon" / "rsi_omega_daemon_v18_0" / "state"
    return result, state_dir


def _patch_v19_stable_hooks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        coordinator_v19,
        "read_meta_core_active_manifest_hash",
        lambda: "sha256:" + ("0" * 64),
    )
    monkeypatch.setattr(
        coordinator_v19,
        "synthesize_goal_queue",
        lambda **kwargs: kwargs["goal_queue_base"],
    )


def _latest_single(path: Path, pattern: str) -> Path:
    rows = sorted(path.glob(pattern), key=lambda row: row.as_posix())
    assert rows
    return rows[-1]


def _ledger_event_types(state_dir: Path) -> list[str]:
    ledger_path = state_dir / "ledger" / "omega_ledger_v1.jsonl"
    if not ledger_path.exists():
        raise AssertionError("missing ledger for state dir")
    out: list[str] = []
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if isinstance(row, dict):
            out.append(str(row.get("event_type", "")))
    return out


def _p95_ms(values: list[int]) -> int:
    if not values:
        return 0
    rows = sorted(max(0, int(row)) for row in values)
    if len(rows) == 1:
        return int(rows[0])
    pos = 0.95 * float(len(rows) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return int(rows[lo])
    frac = pos - float(lo)
    value = float(rows[lo]) + frac * float(rows[hi] - rows[lo])
    return int(round(value))


def _collect_phase4_canary_metrics(
    *,
    base_dir: Path,
    profile_kind: str,
) -> dict[str, object]:
    pack = _prepare_v19_noop_pack(base_dir / "pack_src", max_steps_u64=256)
    _enable_policy_vm_proof(pack, profile_kind=profile_kind)

    program_payload = load_canon_json(pack.parent / "coordinator_isa_program_v1.json")
    declared_limits = program_payload.get("declared_limits")
    assert isinstance(declared_limits, dict)
    assert int(declared_limits.get("max_steps_u64", 0)) == 256

    profile_payload = load_canon_json(pack.parent / "policy_vm_air_profile_v1.json")
    assert str(profile_payload.get("profile_kind", "")) == profile_kind

    prev_state_dir: Path | None = None
    steps_by_tick: list[int] = []
    emitted_prove_ms: list[int] = []
    emitted_verify_ms: list[int] = []
    emitted_proof_sizes: list[int] = []
    eligible_ticks_u32 = 0
    fast_path_ticks_u32 = 0
    fallback_ticks_u32 = 0
    for idx, seed in enumerate(_PHASE4_CANARY_SEEDS, start=1):
        run_dir = base_dir / f"run_{idx:02d}"
        result, state_dir = _run_v19_tick(
            out_dir=run_dir,
            campaign_pack=pack,
            tick_u64=idx,
            prev_state_dir=prev_state_dir,
            run_seed_u64=int(seed),
        )
        prev_state_dir = state_dir

        trace_path = _latest_single(state_dir / "policy" / "traces", "sha256_*.policy_vm_trace_v1.json")
        trace_payload = load_canon_json(trace_path)
        steps_executed_u64 = int(trace_payload.get("steps_executed_u64", 0))
        steps_by_tick.append(steps_executed_u64)
        assert steps_executed_u64 <= 256

        snapshot_path = _latest_single(state_dir / "snapshot", "sha256_*.omega_tick_snapshot_v1.json")
        snapshot_payload = load_canon_json(snapshot_path)
        runtime_status = str(snapshot_payload.get("policy_vm_proof_runtime_status", "")).strip().upper()
        assert runtime_status in {"ABSENT", "FAILED", "EMITTED"}
        proof_hash = str(snapshot_payload.get("policy_vm_stark_proof_hash") or "").strip()
        fallback_reason = str(snapshot_payload.get("policy_vm_proof_fallback_reason_code") or "").strip()
        events = _ledger_event_types(state_dir)

        eligible_ticks_u32 += 1

        if runtime_status == "EMITTED" and proof_hash.startswith("sha256:"):
            assert "POLICY_VM_PROOF" in events
            fast_path_ticks_u32 += 1
            prove_ms = int(result.get("policy_vm_prove_time_ms", 0))
            assert prove_ms >= 0
            emitted_prove_ms.append(prove_ms)

            proof_path = _latest_single(state_dir / "policy" / "proofs", "sha256_*.policy_vm_stark_proof_v1.json")
            proof_payload = load_canon_json(proof_path)
            # Warm one verify call to reduce process startup jitter for p95 gate collection.
            assert verify_policy_vm_stark_proof(proof_payload, state_root=state_dir) == "VALID"
            verify_samples_ms: list[int] = []
            for _ in range(5):
                verify_start_ns = time.perf_counter_ns()
                assert verify_policy_vm_stark_proof(proof_payload, state_root=state_dir) == "VALID"
                verify_samples_ms.append(int((time.perf_counter_ns() - verify_start_ns) // 1_000_000))
            verify_ms = min(verify_samples_ms)
            emitted_verify_ms.append(verify_ms)
            proof_bin = state_dir / str(proof_payload["proof_bytes_rel"])
            emitted_proof_sizes.append(int(proof_bin.stat().st_size))
        else:
            fallback_ticks_u32 += 1
            assert "POLICY_VM_PROOF_FALLBACK" in events
            assert fallback_reason

        daemon_verdict = verify_v19(state_dir, mode="full")
        assert daemon_verdict == "VALID"

    fast_path_rate = float(fast_path_ticks_u32) / float(eligible_ticks_u32) if eligible_ticks_u32 else 0.0
    fallback_rate = float(fallback_ticks_u32) / float(eligible_ticks_u32) if eligible_ticks_u32 else 0.0
    max_steps_u64 = max(steps_by_tick) if steps_by_tick else 0

    return {
        "profile_kind": profile_kind,
        "eligible_ticks_u32": int(eligible_ticks_u32),
        "fast_path_ticks_u32": int(fast_path_ticks_u32),
        "fallback_ticks_u32": int(fallback_ticks_u32),
        "fast_path_rate": float(fast_path_rate),
        "fallback_rate": float(fallback_rate),
        "seeds": list(_PHASE4_CANARY_SEEDS),
        "max_steps_u64": int(max_steps_u64),
        "p95_prove_time_ms": _p95_ms(emitted_prove_ms),
        "p95_verify_time_ms": _p95_ms(emitted_verify_ms),
        "max_proof_size_bytes": max(emitted_proof_sizes) if emitted_proof_sizes else 0,
    }


def test_v19_microkernel_policy_vm_tick_is_deterministic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_v19_stable_hooks(monkeypatch)
    pack = _prepare_v19_noop_pack(tmp_path / "pack_src")

    out_a = tmp_path / "run_a"
    out_b = tmp_path / "run_b"
    result_a, state_a = _run_v19_tick(out_dir=out_a, campaign_pack=pack, tick_u64=1)
    result_b, state_b = _run_v19_tick(out_dir=out_b, campaign_pack=pack, tick_u64=1)

    assert result_a["decision_plan_hash"] == result_b["decision_plan_hash"]
    assert result_a["trace_hash_chain_hash"] == result_b["trace_hash_chain_hash"]
    assert result_a["tick_snapshot_hash"] == result_b["tick_snapshot_hash"]

    assert verify_v19(state_a, mode="full") == "VALID"
    assert verify_v19(state_b, mode="full") == "VALID"


def test_v19_microkernel_time_and_fs_perturbation_do_not_change_decision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_v19_stable_hooks(monkeypatch)

    pack_a = _prepare_v19_noop_pack(tmp_path / "pack_a")
    pack_b = _prepare_v19_noop_pack(tmp_path / "pack_b")
    (pack_b.parent / "zzz_extra_a.txt").write_text("x\n", encoding="utf-8")
    (pack_b.parent / "aaa_extra_b.txt").write_text("y\n", encoding="utf-8")

    seq_a = iter(range(1_000_000, 2_000_000))
    monkeypatch.setattr(microkernel_v1.time, "monotonic_ns", lambda: next(seq_a))
    result_a, _ = _run_v19_tick(out_dir=tmp_path / "time_a", campaign_pack=pack_a, tick_u64=1)

    seq_b = iter(range(9_000_000, 10_000_000))
    monkeypatch.setattr(microkernel_v1.time, "monotonic_ns", lambda: next(seq_b))
    result_b, _ = _run_v19_tick(out_dir=tmp_path / "time_b", campaign_pack=pack_b, tick_u64=1)

    assert result_a["decision_plan_hash"] == result_b["decision_plan_hash"]
    assert result_a["trace_hash_chain_hash"] == result_b["trace_hash_chain_hash"]
    assert result_a["tick_snapshot_hash"] == result_b["tick_snapshot_hash"]


def _run_v19_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    _patch_v19_stable_hooks(monkeypatch)
    pack = _prepare_v19_noop_pack(tmp_path / "pack")
    out_dir = tmp_path / "run"
    _, state_dir = _run_v19_tick(out_dir=out_dir, campaign_pack=pack, tick_u64=1)
    return out_dir, state_dir


@pytest.mark.parametrize("tamper_kind", ["descriptor", "program", "opcode", "trace"])
def test_v19_verifier_rejects_tampered_policy_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper_kind: str,
) -> None:
    out_dir, state_dir = _run_v19_fixture(tmp_path / "base", monkeypatch)
    work_dir = tmp_path / f"tampered_{tamper_kind}"
    shutil.copytree(out_dir, work_dir)

    state_copy = work_dir / "daemon" / "rsi_omega_daemon_v19_0" / "state"
    config_copy = work_dir / "daemon" / "rsi_omega_daemon_v19_0" / "config"

    if tamper_kind == "descriptor":
        path = _latest_single(state_copy / "policy" / "inputs", "sha256_*.inputs_descriptor_v1.json")
        payload = load_canon_json(path)
        payload["tick_u64"] = int(payload.get("tick_u64", 0)) + 1
        write_canon_json(path, payload)
    elif tamper_kind == "program":
        path = config_copy / "coordinator_isa_program_v1.json"
        payload = load_canon_json(path)
        payload["entry_pc_u32"] = int(payload.get("entry_pc_u32", 0)) + 1
        write_canon_json(path, payload)
    elif tamper_kind == "opcode":
        path = config_copy / "coordinator_opcode_table_v1.json"
        payload = load_canon_json(path)
        forbidden = payload.get("forbidden_in_phase1")
        if not isinstance(forbidden, list):
            forbidden = []
        forbidden.append("EMIT_PLAN")
        payload["forbidden_in_phase1"] = forbidden
        write_canon_json(path, payload)
    elif tamper_kind == "trace":
        path = _latest_single(state_copy / "policy" / "traces", "sha256_*.policy_vm_trace_v1.json")
        payload = load_canon_json(path)
        payload["steps_executed_u64"] = int(payload.get("steps_executed_u64", 0)) + 1
        write_canon_json(path, payload)
    else:  # pragma: no cover
        raise AssertionError(f"unknown tamper_kind={tamper_kind}")

    with pytest.raises((OmegaV18Error, OmegaV19Error)):
        verify_v19(state_copy, mode="full")


def test_v18_verifier_accepts_legacy_and_policy_descriptor_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, state_v19 = _run_v19_fixture(tmp_path / "v19", monkeypatch)
    assert verify_v18(state_v19, mode="full") == "VALID"
    assert verify_v19(state_v19, mode="full") == "VALID"

    pack_v18 = _prepare_v18_noop_pack(tmp_path / "v18_pack")
    _, state_v18 = _run_v18_tick(out_dir=tmp_path / "v18_run", campaign_pack=pack_v18, tick_u64=1)
    assert verify_v18(state_v18, mode="full") == "VALID"


def test_descriptor_binding_checks_prev_state_hash_semantics(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    inputs_dir = state_root / "policy" / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)

    descriptor = {
        "schema_version": "inputs_descriptor_v1",
        "tick_u64": 9,
        "state_hash": "sha256:" + ("1" * 64),
        "repo_tree_id": compute_repo_base_tree_id_tolerant(repo_root_v18()),
        "observation_hash": "sha256:" + ("2" * 64),
        "issues_hash": "sha256:" + ("3" * 64),
        "registry_hash": "sha256:" + ("4" * 64),
        "policy_program_ids": ["sha256:" + ("5" * 64)],
        "predictor_id": "sha256:" + ("6" * 64),
        "j_profile_id": "sha256:" + ("7" * 64),
        "opcode_table_id": "sha256:" + ("8" * 64),
        "budget_spec_id": "sha256:" + ("9" * 64),
        "determinism_contract_id": "sha256:" + ("a" * 64),
    }
    descriptor_hash = _sha_obj(descriptor)
    descriptor_hex = descriptor_hash.split(":", 1)[1]
    write_canon_json(inputs_dir / f"sha256_{descriptor_hex}.inputs_descriptor_v1.json", descriptor)

    decision_payload = {
        "tick_u64": 9,
        "observation_report_hash": descriptor["observation_hash"],
        "issue_bundle_hash": descriptor["issues_hash"],
        "registry_hash": descriptor["registry_hash"],
    }
    with pytest.raises(OmegaV18Error) as exc:
        _verify_inputs_descriptor_binding(
            state_root=state_root,
            decision_payload=decision_payload,
            proof={"inputs_hash": descriptor_hash},
            prev_state_payload={"schema_version": "omega_state_v1", "tick_u64": 8},
        )
    assert str(exc.value) == "INVALID:INPUTS_DESCRIPTOR_MISMATCH"


def test_v19_policy_market_mode_selection_and_counterfactual(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_v19_stable_hooks(monkeypatch)
    pack = _prepare_v19_market_pack(tmp_path / "pack_src")

    out_a = tmp_path / "run_a"
    out_b = tmp_path / "run_b"
    result_a, state_a = _run_v19_tick(out_dir=out_a, campaign_pack=pack, tick_u64=1)
    result_b, state_b = _run_v19_tick(out_dir=out_b, campaign_pack=pack, tick_u64=1)

    assert result_a["decision_plan_hash"] == result_b["decision_plan_hash"]
    assert result_a["policy_market_selection_hash"] == result_b["policy_market_selection_hash"]
    assert result_a["counterfactual_trace_example_hash"] == result_b["counterfactual_trace_example_hash"]
    assert result_a["policy_market_selection_hash"] is not None
    assert result_a["counterfactual_trace_example_hash"] is not None

    selection_path = _latest_single(state_a / "policy" / "selection", "sha256_*.policy_market_selection_v1.json")
    selection_payload = load_canon_json(selection_path)
    assert selection_payload["winner_branch_id"] == "b00"

    counterfactual_path = _latest_single(
        state_a / "policy" / "counterfactual",
        "sha256_*.counterfactual_trace_example_v1.json",
    )
    counterfactual_payload = load_canon_json(counterfactual_path)
    losers = counterfactual_payload["losers"]
    assert [row["proposal_hash"] for row in losers] == sorted(row["proposal_hash"] for row in losers)

    assert verify_v19(state_a, mode="full") == "VALID"
    assert verify_v19(state_b, mode="full") == "VALID"


def test_v19_market_mode_deterministic_under_cpu_perturbation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_v19_stable_hooks(monkeypatch)
    pack = _prepare_v19_market_pack(tmp_path / "pack_src")

    burners: list[subprocess.Popen[str]] = []
    for _ in range(2):
        burners.append(
            subprocess.Popen(
                [sys.executable, "-c", "while True:\n    pass\n"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
        )
    try:
        result_a, _ = _run_v19_tick(out_dir=tmp_path / "run_a", campaign_pack=pack, tick_u64=1)
    finally:
        for proc in burners:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                proc.kill()

    result_b, _ = _run_v19_tick(out_dir=tmp_path / "run_b", campaign_pack=pack, tick_u64=1)

    assert result_a["policy_market_selection_hash"] == result_b["policy_market_selection_hash"]
    assert result_a["decision_plan_hash"] == result_b["decision_plan_hash"]
    assert result_a["tick_snapshot_hash"] == result_b["tick_snapshot_hash"]
    assert result_a["trace_hash_chain_hash"] == result_b["trace_hash_chain_hash"]


def test_v19_verifier_rejects_tampered_policy_market_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_v19_stable_hooks(monkeypatch)
    pack = _prepare_v19_market_pack(tmp_path / "pack_src")
    out_dir = tmp_path / "run"
    _, state_dir = _run_v19_tick(out_dir=out_dir, campaign_pack=pack, tick_u64=1)

    work_dir = tmp_path / "tampered"
    shutil.copytree(out_dir, work_dir)
    state_copy = work_dir / "daemon" / "rsi_omega_daemon_v19_0" / "state"
    selection_path = _latest_single(state_copy / "policy" / "selection", "sha256_*.policy_market_selection_v1.json")
    selection_payload = load_canon_json(selection_path)
    selection_payload["winner_branch_id"] = "b01"
    write_canon_json(selection_path, selection_payload)

    with pytest.raises((OmegaV18Error, OmegaV19Error)):
        verify_v19(state_copy, mode="full")


def test_v19_verifier_rejects_missing_branch_hint_from_merged_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_v19_stable_hooks(monkeypatch)
    pack = _prepare_v19_market_pack(tmp_path / "pack_src")
    out_dir = tmp_path / "run"
    _, state_dir = _run_v19_tick(out_dir=out_dir, campaign_pack=pack, tick_u64=1)

    work_dir = tmp_path / "tampered_hints"
    shutil.copytree(out_dir, work_dir)
    state_copy = work_dir / "daemon" / "rsi_omega_daemon_v19_0" / "state"

    merged_path = _latest_single(state_copy / "policy" / "merged_hints", "sha256_*.merged_hint_state_v1.json")
    merged_payload = load_canon_json(merged_path)
    hashes = merged_payload.get("contributing_hint_hashes")
    assert isinstance(hashes, list) and len(hashes) >= 2
    merged_payload["contributing_hint_hashes"] = [str(hashes[0])]
    merged_hash = _sha_obj(merged_payload).split(":", 1)[1]
    tampered_path = merged_path.parent / f"sha256_{merged_hash}.merged_hint_state_v1.json"
    write_canon_json(tampered_path, merged_payload)
    merged_path.unlink()

    with pytest.raises((OmegaV18Error, OmegaV19Error)) as exc:
        verify_v19(state_copy, mode="full")
    assert "HINT_SYNC_VIOLATION" in str(exc.value)


def test_v19_verifier_rejects_tampered_proposal_decision_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_v19_stable_hooks(monkeypatch)
    pack = _prepare_v19_market_pack(tmp_path / "pack_src")
    out_dir = tmp_path / "run"
    _, state_dir = _run_v19_tick(out_dir=out_dir, campaign_pack=pack, tick_u64=1)

    work_dir = tmp_path / "tampered_proposal_decision"
    shutil.copytree(out_dir, work_dir)
    state_copy = work_dir / "daemon" / "rsi_omega_daemon_v19_0" / "state"

    proposal_path = _latest_single(state_copy / "policy" / "proposals", "sha256_*.policy_trace_proposal_v1.json")
    proposal_payload = load_canon_json(proposal_path)
    proposal_payload["decision_plan_hash"] = "sha256:" + ("0" * 64)
    proposal_payload["proposal_commitment_hash"] = _sha_obj(
        {k: v for k, v in proposal_payload.items() if k != "proposal_commitment_hash"}
    )
    proposal_hash_hex = _sha_obj(proposal_payload).split(":", 1)[1]
    tampered_proposal_path = proposal_path.parent / f"sha256_{proposal_hash_hex}.policy_trace_proposal_v1.json"
    write_canon_json(tampered_proposal_path, proposal_payload)
    proposal_path.unlink()

    selection_path = _latest_single(state_copy / "policy" / "selection", "sha256_*.policy_market_selection_v1.json")
    selection_payload = load_canon_json(selection_path)
    selection_payload["proposal_hashes"] = sorted(
        [
            str(_sha_obj(load_canon_json(path)))
            for path in sorted((state_copy / "policy" / "proposals").glob("sha256_*.policy_trace_proposal_v1.json"))
        ]
    )
    ranking = selection_payload.get("ranking")
    assert isinstance(ranking, list)
    updated_hash = _sha_obj(proposal_payload)
    for row in ranking:
        if isinstance(row, dict) and str(row.get("branch_id")) == str(proposal_payload.get("branch_id")):
            row["proposal_hash"] = updated_hash
    if str(selection_payload.get("winner_branch_id")) == str(proposal_payload.get("branch_id")):
        selection_payload["winner_proposal_hash"] = updated_hash
    selection_hash_hex = _sha_obj(selection_payload).split(":", 1)[1]
    tampered_selection_path = selection_path.parent / f"sha256_{selection_hash_hex}.policy_market_selection_v1.json"
    write_canon_json(tampered_selection_path, selection_payload)
    selection_path.unlink()

    snapshot_path = _latest_single(state_copy / "snapshot", "sha256_*.omega_tick_snapshot_v1.json")
    snapshot_payload = load_canon_json(snapshot_path)
    snapshot_payload["policy_market_selection_hash"] = f"sha256:{selection_hash_hex}"
    snapshot_hash_hex = _sha_obj(snapshot_payload).split(":", 1)[1]
    tampered_snapshot_path = snapshot_path.parent / f"sha256_{snapshot_hash_hex}.omega_tick_snapshot_v1.json"
    write_canon_json(tampered_snapshot_path, snapshot_payload)
    snapshot_path.unlink()

    with pytest.raises((OmegaV18Error, OmegaV19Error)):
        verify_v19(state_copy, mode="full")


def test_phase3b_native_opcode_activation_lifecycle_e2e(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_v19_stable_hooks(monkeypatch)

    # Tick 1: run native-module campaign to install/hash-pin binary and pass gate healthcheck.
    native_pack = REPO_ROOT / "campaigns" / "rsi_omega_daemon_v19_0_phase1_native_modules_v1" / "rsi_omega_daemon_pack_v1.json"
    prev_native = os.environ.get("OMEGA_NATIVE_CANON_BYTES")
    os.environ["OMEGA_NATIVE_CANON_BYTES"] = "1"
    try:
        _, native_state = _run_v19_tick(out_dir=tmp_path / "native_tick_1", campaign_pack=native_pack, tick_u64=1)
    finally:
        if prev_native is None:
            os.environ.pop("OMEGA_NATIVE_CANON_BYTES", None)
        else:
            os.environ["OMEGA_NATIVE_CANON_BYTES"] = prev_native

    dispatch_dirs = sorted([row for row in (native_state / "dispatch").iterdir() if row.is_dir()], key=lambda row: row.as_posix())
    assert dispatch_dirs
    activation_path = _latest_single(dispatch_dirs[-1] / "activation", "sha256_*.omega_activation_receipt_v1.json")
    activation_payload = load_canon_json(activation_path)
    assert bool(activation_payload.get("activation_success", False))
    assert str(activation_payload.get("native_activation_gate_result", "")) == "PASS"
    native_module = activation_payload.get("native_module")
    assert isinstance(native_module, dict)
    native_binary_sha = str(native_module.get("binary_sha256", ""))
    assert native_binary_sha.startswith("sha256:")
    native_hex = native_binary_sha.split(":", 1)[1]
    native_ext = ".dylib" if sys.platform == "darwin" else ".so"
    native_blob = REPO_ROOT / ".omega_cache" / "native_blobs" / f"sha256_{native_hex}{native_ext}"
    assert native_blob.exists() and native_blob.is_file()

    # Tick 2: activate opcode table entry bound to the same native hash and execute mapped opcode.
    policy_pack = _prepare_v19_opcode_pack(
        tmp_path / "policy_pack",
        nop_kind="NATIVE",
        nop_active_b=True,
        nop_binary_sha256=native_binary_sha,
    )
    _, state_dir = _run_v19_tick(out_dir=tmp_path / "policy_tick_2", campaign_pack=policy_pack, tick_u64=1)
    assert verify_v19(state_dir, mode="full") == "VALID"

    trace_path = _latest_single(state_dir / "policy" / "traces", "sha256_*.policy_vm_trace_v1.json")
    trace_payload = load_canon_json(trace_path)
    step_log = trace_payload.get("step_log")
    assert isinstance(step_log, list) and step_log
    assert str(step_log[0].get("op", "")) == "NOP"

    events = _ledger_event_types(state_dir)
    assert "OPCODE_TABLE_UPDATE" in events
    assert "OPCODE_NATIVE_ACTIVATION" in events


def test_phase3b_opcode_deprecation_rejects_execution_and_preserves_historical_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_v19_stable_hooks(monkeypatch)

    active_pack = _prepare_v19_opcode_pack(
        tmp_path / "pack_active",
        nop_kind="BUILTIN",
        nop_active_b=True,
    )
    _, state_tick_1 = _run_v19_tick(out_dir=tmp_path / "tick_1_active", campaign_pack=active_pack, tick_u64=1)
    assert verify_v19(state_tick_1, mode="full") == "VALID"

    deprecated_pack = _prepare_v19_opcode_pack(
        tmp_path / "pack_deprecated",
        nop_kind="BUILTIN",
        nop_active_b=False,
        deprecated_tick_u64=2,
    )
    with pytest.raises((OmegaV18Error, OmegaV19Error)) as exc:
        _run_v19_tick(
            out_dir=tmp_path / "tick_2_deprecated",
            campaign_pack=deprecated_pack,
            tick_u64=2,
            prev_state_dir=state_tick_1,
        )
    assert "OPCODE_DEPRECATED" in str(exc.value)

    # Historical replay remains valid for the tick that committed active opcode table id.
    assert verify_v19(state_tick_1, mode="full") == "VALID"


def test_policy_vm_stark_proof_artifact_emitted_and_verified(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_v19_stable_hooks(monkeypatch)
    pack = _prepare_v19_noop_pack(tmp_path / "pack_src")
    _enable_policy_vm_proof(pack)
    out_dir = tmp_path / "run"
    result, state_dir = _run_v19_tick(out_dir=out_dir, campaign_pack=pack, tick_u64=1)
    assert result.get("policy_vm_stark_proof_hash")
    assert result.get("policy_vm_proof_runtime_status") == "EMITTED"

    proof_path = _latest_single(state_dir / "policy" / "proofs", "sha256_*.policy_vm_stark_proof_v1.json")
    proof_payload = load_canon_json(proof_path)
    assert str(proof_payload.get("proof_representation_kind", "")) == "STARK_FRI_PROOF_V1"
    assert str(proof_payload.get("proof_backend_id", "")) == "WINTERFELL_STARK_FRI_V1"
    assert verify_policy_vm_stark_proof(proof_payload, state_root=state_dir) == "VALID"
    assert verify_v19(state_dir, mode="full") == "VALID"
    events = _ledger_event_types(state_dir)
    assert "POLICY_VM_PROOF" in events


def test_policy_vm_stark_proof_tamper_bytes_rejected_by_unit_verifier(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "state"
    proof_payload, proof_bin_path, _, _, _ = _build_minimal_semantic_proof_payload(state_root=state_root)
    assert verify_policy_vm_stark_proof(proof_payload, state_root=state_root) == "VALID"

    proof_bin_path.write_bytes(b"tampered")
    with pytest.raises((OmegaV18Error, OmegaV19Error)):
        verify_policy_vm_stark_proof(proof_payload, state_root=state_root)


def test_policy_vm_stark_proof_tamper_public_output_binding_rejected(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "state"
    proof_payload, _, _, _, _ = _build_minimal_semantic_proof_payload(state_root=state_root)
    assert verify_policy_vm_stark_proof(proof_payload, state_root=state_root) == "VALID"

    public_outputs = dict(proof_payload["public_outputs"])
    public_outputs["priority_q32_i64"] = int(public_outputs.get("priority_q32_i64", 0)) + 1
    proof_payload["public_outputs"] = public_outputs
    proof_payload["proof_id"] = _sha_obj({k: v for k, v in proof_payload.items() if k != "proof_id"})
    with pytest.raises((OmegaV18Error, OmegaV19Error)):
        verify_policy_vm_stark_proof(proof_payload, state_root=state_root)


@pytest.mark.parametrize("drift_kind", ["missing", "extra", "renamed"])
def test_policy_vm_stark_proof_rejects_winterfell_option_name_drift(
    tmp_path: Path,
    drift_kind: str,
) -> None:
    state_root = tmp_path / "state"
    proof_payload, _, _, _, _ = _build_minimal_semantic_proof_payload(state_root=state_root)
    assert verify_policy_vm_stark_proof(proof_payload, state_root=state_root) == "VALID"
    profile_path = state_root.parent / "config" / "policy_vm_air_profile_v1.json"
    profile = load_canon_json(profile_path)
    options = dict(profile["proof_options"])
    if drift_kind == "missing":
        options.pop("num_queries")
    elif drift_kind == "extra":
        options["extra_option"] = 123
    elif drift_kind == "renamed":
        options["num_queries_renamed"] = options.pop("num_queries")
    else:
        raise AssertionError(f"unexpected drift_kind={drift_kind}")
    profile["proof_options"] = dict(options)
    profile["winterfell_proof_options"] = options
    profile["air_profile_id"] = _sha_obj({k: v for k, v in profile.items() if k != "air_profile_id"})
    write_canon_json(profile_path, profile)
    with pytest.raises((OmegaV18Error, OmegaV19Error)):
        verify_policy_vm_stark_proof(proof_payload, state_root=state_root)


def test_policy_vm_stark_proof_rejects_winterfell_backend_version_drift(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "state"
    proof_payload, _, _, _, _ = _build_minimal_semantic_proof_payload(state_root=state_root)
    assert verify_policy_vm_stark_proof(proof_payload, state_root=state_root) == "VALID"
    profile_path = state_root.parent / "config" / "policy_vm_air_profile_v1.json"
    profile = load_canon_json(profile_path)
    profile["winterfell_backend_version"] = "0.13.0"
    profile["air_profile_id"] = _sha_obj({k: v for k, v in profile.items() if k != "air_profile_id"})
    write_canon_json(profile_path, profile)
    with pytest.raises((OmegaV18Error, OmegaV19Error)):
        verify_policy_vm_stark_proof(proof_payload, state_root=state_root)


def test_policy_vm_stark_proof_rejects_winterfell_hasher_drift(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "state"
    proof_payload, _, _, _, _ = _build_minimal_semantic_proof_payload(state_root=state_root)
    assert verify_policy_vm_stark_proof(proof_payload, state_root=state_root) == "VALID"
    profile_path = state_root.parent / "config" / "policy_vm_air_profile_v1.json"
    profile = load_canon_json(profile_path)
    profile["winterfell_merkle_hasher_id"] = "winterfell::crypto::hashers::Sha3_256"
    profile["air_profile_id"] = _sha_obj({k: v for k, v in profile.items() if k != "air_profile_id"})
    write_canon_json(profile_path, profile)
    with pytest.raises((OmegaV18Error, OmegaV19Error)):
        verify_policy_vm_stark_proof(proof_payload, state_root=state_root)


def test_policy_vm_stark_proof_payload_options_hash_tamper_rejected(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "state"
    proof_payload, _, _, _, _ = _build_minimal_semantic_proof_payload(state_root=state_root)
    assert verify_policy_vm_stark_proof(proof_payload, state_root=state_root) == "VALID"

    proof_payload["proof_options_hash"] = "sha256:" + ("d" * 64)
    proof_payload["proof_id"] = _sha_obj({k: v for k, v in proof_payload.items() if k != "proof_id"})
    with pytest.raises((OmegaV18Error, OmegaV19Error)):
        verify_policy_vm_stark_proof(proof_payload, state_root=state_root)


def test_v19_verifier_falls_back_when_policy_vm_stark_proof_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_v19_stable_hooks(monkeypatch)
    pack = _prepare_v19_noop_pack(tmp_path / "pack_src")
    _enable_policy_vm_proof(pack)
    out_dir = tmp_path / "run"
    _, state_dir = _run_v19_tick(out_dir=out_dir, campaign_pack=pack, tick_u64=1)

    proof_path = _latest_single(state_dir / "policy" / "proofs", "sha256_*.policy_vm_stark_proof_v1.json")
    proof_payload = load_canon_json(proof_path)
    proof_bin = state_dir / str(proof_payload["proof_bytes_rel"])
    proof_bin.write_bytes(b"tampered")

    with pytest.raises((OmegaV18Error, OmegaV19Error)):
        verify_policy_vm_stark_proof(proof_payload, state_root=state_dir)

    # Selected rollout policy is fallback replay on invalid proof.
    assert verify_v19(state_dir, mode="full") == "VALID"


def test_phase4_canary_step_budget_pinned_n10(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_v19_stable_hooks(monkeypatch)
    metrics = _collect_phase4_canary_metrics(
        base_dir=tmp_path / "policy_vm_air_profile_96_v1",
        profile_kind="POLICY_VM_AIR_PROFILE_96_V1",
    )
    assert metrics["seeds"] == list(_PHASE4_CANARY_SEEDS)
    assert int(metrics["eligible_ticks_u32"]) == len(_PHASE4_CANARY_SEEDS)
    assert int(metrics["max_steps_u64"]) <= 256


def test_phase4_ci_gate_fast_path_fallback_rates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_v19_stable_hooks(monkeypatch)
    for profile_kind, slo in _PHASE4_CANARY_SLO_BY_PROFILE.items():
        metrics = _collect_phase4_canary_metrics(
            base_dir=tmp_path / f"gate_{profile_kind.lower()}",
            profile_kind=profile_kind,
        )
        assert int(metrics["eligible_ticks_u32"]) == len(_PHASE4_CANARY_SEEDS)
        assert float(metrics["fast_path_rate"]) >= 0.80
        assert float(metrics["fallback_rate"]) <= 0.20
        assert int(metrics["p95_prove_time_ms"]) <= int(slo["p95_prove_time_ms"])
        assert int(metrics["p95_verify_time_ms"]) <= int(slo["p95_verify_time_ms"])
        assert int(metrics["max_proof_size_bytes"]) <= int(slo["max_proof_size_bytes"])


def test_phase4_fallback_reason_code_integrity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_v19_stable_hooks(monkeypatch)
    pack = _prepare_v19_noop_pack(tmp_path / "pack_src")
    _enable_policy_vm_proof(pack)

    def _forced_prover_failure(**_: object) -> dict[str, object]:
        raise RuntimeError("forced-prover-failure")

    monkeypatch.setattr(microkernel_v1, "prove_policy_vm_stark", _forced_prover_failure)
    _, state_dir = _run_v19_tick(out_dir=tmp_path / "run", campaign_pack=pack, tick_u64=1)
    snapshot_path = _latest_single(state_dir / "snapshot", "sha256_*.omega_tick_snapshot_v1.json")
    snapshot_payload = load_canon_json(snapshot_path)
    assert str(snapshot_payload.get("policy_vm_proof_runtime_status", "")) == "FAILED"
    fallback_reason = str(snapshot_payload.get("policy_vm_proof_fallback_reason_code", "")).strip()
    assert fallback_reason
    events = _ledger_event_types(state_dir)
    assert "POLICY_VM_PROOF_FALLBACK" in events
    assert "POLICY_VM_PROOF" not in events
    assert verify_v19(state_dir, mode="full") == "VALID"
