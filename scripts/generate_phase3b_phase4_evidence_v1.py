#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import os
import shutil
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "CDEL-v2") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "CDEL-v2"))

from cdel.v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json
from cdel.v18_0.omega_common_v1 import OmegaV18Error
from cdel.v19_0.verify_rsi_omega_daemon_v1 import verify as verify_v19
from cdel.v19_0.verify_policy_vm_stark_proof_v1 import verify_policy_vm_stark_proof
from orchestrator.omega_v19_0 import coordinator_v1 as coordinator_v19

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


def _sha_obj(payload: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(payload))


def _default_winterfell_backend_contract() -> dict[str, Any]:
    payload: dict[str, Any] = {
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


def _default_winterfell_proof_options(*, profile_kind: str) -> dict[str, Any]:
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


def _build_action_kind_enum() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "action_kind_enum_v1",
        "action_kind_enum_id": "sha256:" + ("0" * 64),
        "entries": [
            {"code_u8": 0, "action_kind": "SAFE_HALT"},
            {"code_u8": 1, "action_kind": "NOOP"},
            {"code_u8": 2, "action_kind": "RUN_CAMPAIGN"},
        ],
    }
    payload["action_kind_enum_id"] = _sha_obj({k: v for k, v in payload.items() if k != "action_kind_enum_id"})
    return payload


def _build_candidate_campaign_ids_list() -> dict[str, Any]:
    payload: dict[str, Any] = {
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


def _latest_single(path: Path, pattern: str) -> Path:
    rows = sorted(path.glob(pattern), key=lambda row: row.as_posix())
    if not rows:
        raise FileNotFoundError(f"missing {pattern} under {path}")
    return rows[-1]


def _unit_proof_verdict(*, proof_payload: dict[str, Any], state_root: Path) -> str:
    try:
        verify_policy_vm_stark_proof(proof_payload, state_root=state_root)
        return "VALID"
    except OmegaV18Error as exc:
        return str(exc)
    except Exception as exc:  # noqa: BLE001
        return f"INVALID:{exc}"


@contextmanager
def _temp_env(overrides: dict[str, str]):
    previous = {key: os.environ.get(key) for key in overrides}
    for key, value in overrides.items():
        os.environ[key] = value
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@dataclass
class TickResult:
    result: dict[str, Any]
    state_dir: Path


def _run_v19_tick(
    *,
    campaign_pack: Path,
    out_dir: Path,
    tick_u64: int,
    prev_state_dir: Path | None = None,
    native_canon_bytes: bool = False,
    run_seed_u64: int = 424242,
) -> TickResult:
    env = {
        "OMEGA_META_CORE_ACTIVATION_MODE": "simulate",
        "OMEGA_ALLOW_SIMULATE_ACTIVATION": "1",
        "OMEGA_RUN_SEED_U64": str(int(run_seed_u64)),
        "OMEGA_V19_DETERMINISTIC_TIMING": "1",
    }
    if native_canon_bytes:
        env["OMEGA_NATIVE_CANON_BYTES"] = "1"
    prev_manifest_fn = coordinator_v19.read_meta_core_active_manifest_hash
    prev_synth_fn = coordinator_v19.synthesize_goal_queue
    coordinator_v19.read_meta_core_active_manifest_hash = lambda: "sha256:" + ("0" * 64)
    coordinator_v19.synthesize_goal_queue = lambda **kwargs: kwargs["goal_queue_base"]
    try:
        with _temp_env(env):
            result = coordinator_v19.run_tick(
                campaign_pack=campaign_pack,
                out_dir=out_dir,
                tick_u64=tick_u64,
                prev_state_dir=prev_state_dir,
            )
    finally:
        coordinator_v19.read_meta_core_active_manifest_hash = prev_manifest_fn
        coordinator_v19.synthesize_goal_queue = prev_synth_fn
    state_dir = out_dir / "daemon" / "rsi_omega_daemon_v19_0" / "state"
    return TickResult(result=result, state_dir=state_dir)


def _ledger_event_types(state_dir: Path) -> list[str]:
    ledger_path = state_dir / "ledger" / "omega_ledger_v1.jsonl"
    rows: list[str] = []
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(str(payload.get("event_type", "")))
    return rows


def _prepare_v19_opcode_pack(
    dst_root: Path,
    *,
    nop_kind: str,
    nop_active_b: bool,
    nop_binary_sha256: str | None = None,
    deprecated_tick_u64: int = 0,
) -> Path:
    src = REPO_ROOT / "campaigns" / "rsi_omega_daemon_v19_0_super_unified"
    if dst_root.exists():
        shutil.rmtree(dst_root)
    shutil.copytree(src, dst_root)

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
    write_canon_json(dst_root / "coordinator_isa_program_v1.json", program)

    if nop_kind.upper() == "NATIVE":
        if not isinstance(nop_binary_sha256, str):
            raise ValueError("native opcode table requires nop_binary_sha256")
        nop_impl: dict[str, Any] = {
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
    write_canon_json(dst_root / "coordinator_opcode_table_v1.json", opcode_table)

    pack_path = dst_root / "rsi_omega_daemon_pack_v1.json"
    pack = load_canon_json(pack_path)
    pack["coordinator_isa_program_id"] = str(program["program_id"])
    pack["coordinator_opcode_table_id"] = str(opcode_table["opcode_table_id"])
    pack["policy_vm_mode"] = "DECISION_ONLY"
    write_canon_json(pack_path, pack)
    return pack_path


def _prepare_v19_proof_pack(
    dst_root: Path,
    *,
    profile_kind: str = "POLICY_VM_AIR_PROFILE_96_V1",
    max_steps_u64: int = 64,
) -> Path:
    src = REPO_ROOT / "campaigns" / "rsi_omega_daemon_v19_0_super_unified"
    if dst_root.exists():
        shutil.rmtree(dst_root)
    shutil.copytree(src, dst_root)

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
    program["program_id"] = _sha_obj({k: v for k, v in program.items() if k != "program_id"})
    write_canon_json(dst_root / "coordinator_isa_program_v1.json", program)

    backend_contract = _default_winterfell_backend_contract()
    write_canon_json(dst_root / "policy_vm_winterfell_backend_contract_v1.json", backend_contract)
    action_kind_enum = _build_action_kind_enum()
    write_canon_json(dst_root / "action_kind_enum_v1.json", action_kind_enum)
    candidate_campaign_ids_list = _build_candidate_campaign_ids_list()
    write_canon_json(dst_root / "candidate_campaign_ids_list_v1.json", candidate_campaign_ids_list)

    proof_options = _default_winterfell_proof_options(profile_kind=profile_kind)

    air_profile = {
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
        "candidate_campaign_ids_list_hash": str(candidate_campaign_ids_list["candidate_campaign_ids_list_id"]),
        "action_kind_enum_hash": str(action_kind_enum["action_kind_enum_id"]),
        "action_encoding_kind": "CONST_INDEX_TUPLE_V1",
        "supported_action_kinds": ["SAFE_HALT", "NOOP", "RUN_CAMPAIGN"],
        "winterfell_backend_id": str(backend_contract["winterfell_backend_id"]),
        "winterfell_backend_version": str(backend_contract["winterfell_backend_version"]),
        "winterfell_field_id": str(backend_contract["winterfell_field_id"]),
        "winterfell_extension_id": str(backend_contract["winterfell_extension_id"]),
        "winterfell_merkle_hasher_id": str(backend_contract["winterfell_merkle_hasher_id"]),
        "winterfell_random_coin_hasher_id": str(backend_contract["winterfell_random_coin_hasher_id"]),
        "winterfell_proof_options": dict(proof_options),
        "profile_kind": profile_kind,
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
    air_profile["air_profile_id"] = _sha_obj({k: v for k, v in air_profile.items() if k != "air_profile_id"})
    write_canon_json(dst_root / "policy_vm_air_profile_v1.json", air_profile)

    opcode_table = load_canon_json(dst_root / "coordinator_opcode_table_v1.json")
    pack_path = dst_root / "rsi_omega_daemon_pack_v1.json"
    pack = load_canon_json(pack_path)
    pack["coordinator_isa_program_id"] = str(program["program_id"])
    pack["coordinator_opcode_table_id"] = str(opcode_table["opcode_table_id"])
    pack["policy_vm_mode"] = "DECISION_ONLY"
    pack["policy_vm_stark_proof_enable_b"] = True
    pack["policy_vm_air_profile_rel"] = "policy_vm_air_profile_v1.json"
    pack["policy_vm_air_profile_id"] = str(air_profile["air_profile_id"])
    pack["policy_vm_winterfell_backend_contract_rel"] = "policy_vm_winterfell_backend_contract_v1.json"
    pack["policy_vm_winterfell_backend_contract_id"] = str(backend_contract["backend_contract_id"])
    pack["policy_vm_action_kind_enum_rel"] = "action_kind_enum_v1.json"
    pack["policy_vm_action_kind_enum_id"] = str(action_kind_enum["action_kind_enum_id"])
    pack["policy_vm_candidate_campaign_ids_list_rel"] = "candidate_campaign_ids_list_v1.json"
    pack["policy_vm_candidate_campaign_ids_list_id"] = str(candidate_campaign_ids_list["candidate_campaign_ids_list_id"])
    write_canon_json(pack_path, pack)
    return pack_path


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
    run_root: Path,
    packs_root: Path,
    profile_kind: str,
) -> dict[str, Any]:
    profile_slug = profile_kind.lower()
    pack = _prepare_v19_proof_pack(
        packs_root / f"phase4_canary_pack_{profile_slug}",
        profile_kind=profile_kind,
        max_steps_u64=256,
    )
    program_payload = load_canon_json(pack.parent / "coordinator_isa_program_v1.json")
    declared_limits = program_payload.get("declared_limits")
    if not isinstance(declared_limits, dict) or int(declared_limits.get("max_steps_u64", 0)) != 256:
        raise RuntimeError("phase4 canary pack must pin max_steps_u64=256")

    profile_payload = load_canon_json(pack.parent / "policy_vm_air_profile_v1.json")
    if str(profile_payload.get("profile_kind", "")) != profile_kind:
        raise RuntimeError("phase4 canary profile kind mismatch")

    per_tick: list[dict[str, Any]] = []
    prev_state_dir: Path | None = None
    eligible_ticks_u32 = 0
    fast_path_ticks_u32 = 0
    fallback_ticks_u32 = 0
    emitted_prove_ms: list[int] = []
    emitted_verify_ms: list[int] = []
    emitted_proof_sizes: list[int] = []
    for idx, seed in enumerate(_PHASE4_CANARY_SEEDS, start=1):
        tick = _run_v19_tick(
            campaign_pack=pack,
            out_dir=run_root / f"phase4_canary_{profile_slug}_tick_{idx:02d}",
            tick_u64=idx,
            prev_state_dir=prev_state_dir,
            run_seed_u64=int(seed),
        )
        prev_state_dir = tick.state_dir
        trace_path = _latest_single(tick.state_dir / "policy" / "traces", "sha256_*.policy_vm_trace_v1.json")
        trace_payload = load_canon_json(trace_path)
        steps_executed_u64 = int(trace_payload.get("steps_executed_u64", 0))
        if steps_executed_u64 > 256:
            raise RuntimeError(f"phase4 canary step budget exceeded: steps_executed_u64={steps_executed_u64}")
        snapshot_path = _latest_single(tick.state_dir / "snapshot", "sha256_*.omega_tick_snapshot_v1.json")
        snapshot_payload = load_canon_json(snapshot_path)
        runtime_status = str(snapshot_payload.get("policy_vm_proof_runtime_status", "")).strip().upper()
        proof_hash = str(snapshot_payload.get("policy_vm_stark_proof_hash") or "").strip()
        fallback_reason = str(snapshot_payload.get("policy_vm_proof_fallback_reason_code") or "").strip()
        proof_runtime_reason = str(snapshot_payload.get("policy_vm_proof_runtime_reason_code") or "").strip()
        events = _ledger_event_types(tick.state_dir)

        eligible_ticks_u32 += 1

        prove_time_ms = int(tick.result.get("policy_vm_prove_time_ms", 0))
        verify_time_ms = 0
        proof_size_bytes = 0
        if runtime_status == "EMITTED" and proof_hash.startswith("sha256:"):
            if "POLICY_VM_PROOF" not in events:
                raise RuntimeError("phase4 canary proof tick missing POLICY_VM_PROOF event")
            proof_path = _latest_single(tick.state_dir / "policy" / "proofs", "sha256_*.policy_vm_stark_proof_v1.json")
            proof_payload = load_canon_json(proof_path)
            if _unit_proof_verdict(proof_payload=proof_payload, state_root=tick.state_dir) != "VALID":
                raise RuntimeError("phase4 canary proof warmup verify failed")
            verify_samples_ms: list[int] = []
            for _ in range(5):
                verify_start_ns = time.perf_counter_ns()
                unit_verdict = _unit_proof_verdict(proof_payload=proof_payload, state_root=tick.state_dir)
                verify_samples_ms.append(int((time.perf_counter_ns() - verify_start_ns) // 1_000_000))
                if unit_verdict != "VALID":
                    raise RuntimeError(f"phase4 canary proof verify failed: {unit_verdict}")
            verify_time_ms = min(verify_samples_ms)
            proof_bin = tick.state_dir / str(proof_payload["proof_bytes_rel"])
            proof_size_bytes = int(proof_bin.stat().st_size)
            fast_path_ticks_u32 += 1
            emitted_prove_ms.append(prove_time_ms)
            emitted_verify_ms.append(verify_time_ms)
            emitted_proof_sizes.append(proof_size_bytes)
        else:
            fallback_ticks_u32 += 1
            if "POLICY_VM_PROOF_FALLBACK" not in events:
                raise RuntimeError("phase4 canary fallback tick missing POLICY_VM_PROOF_FALLBACK event")
            if not fallback_reason:
                raise RuntimeError("phase4 canary fallback tick missing policy_vm_proof_fallback_reason_code")

        daemon_verdict = verify_v19(tick.state_dir, mode="full")
        if daemon_verdict != "VALID":
            raise RuntimeError(f"phase4 canary daemon verify failed: {daemon_verdict}")

        per_tick.append(
            {
                "tick_u64": idx,
                "run_seed_u64": int(seed),
                "state_dir": str(tick.state_dir),
                "steps_executed_u64": steps_executed_u64,
                "proof_runtime_status": runtime_status,
                "proof_runtime_reason_code": proof_runtime_reason,
                "proof_fallback_reason_code": fallback_reason or None,
                "proof_hash": proof_hash or None,
                "proof_valid_b": runtime_status == "EMITTED" and proof_hash.startswith("sha256:"),
                "fallback_used_b": runtime_status != "EMITTED",
                "prove_time_ms": int(prove_time_ms),
                "verify_time_ms": int(verify_time_ms),
                "proof_size_bytes": int(proof_size_bytes),
            }
        )

    fast_path_rate = float(fast_path_ticks_u32) / float(eligible_ticks_u32) if eligible_ticks_u32 else 0.0
    fallback_rate = float(fallback_ticks_u32) / float(eligible_ticks_u32) if eligible_ticks_u32 else 0.0
    p95_prove_time_ms = _p95_ms(emitted_prove_ms)
    p95_verify_time_ms = _p95_ms(emitted_verify_ms)
    max_proof_size_bytes = max(emitted_proof_sizes) if emitted_proof_sizes else 0
    slo = _PHASE4_CANARY_SLO_BY_PROFILE[profile_kind]

    gate = {
        "step_budget_ok_b": all(int(row["steps_executed_u64"]) <= 256 for row in per_tick),
        "fast_path_rate_ok_b": fast_path_rate >= 0.80,
        "fallback_rate_ok_b": fallback_rate <= 0.20,
        "p95_prove_time_ok_b": p95_prove_time_ms <= int(slo["p95_prove_time_ms"]),
        "p95_verify_time_ok_b": p95_verify_time_ms <= int(slo["p95_verify_time_ms"]),
        "max_proof_size_ok_b": max_proof_size_bytes <= int(slo["max_proof_size_bytes"]),
    }
    gate["pass_b"] = bool(all(bool(v) for v in gate.values()))
    if not gate["pass_b"]:
        raise RuntimeError(
            f"phase4 canary gate failed for {profile_kind}: "
            f"fast_path_rate={fast_path_rate:.3f} fallback_rate={fallback_rate:.3f} "
            f"p95_prove_ms={p95_prove_time_ms} p95_verify_ms={p95_verify_time_ms} "
            f"max_proof_size_bytes={max_proof_size_bytes}"
        )

    return {
        "profile_kind": profile_kind,
        "policy_vm_air_profile_id": str(profile_payload.get("air_profile_id", "")),
        "eligible_ticks_u32": int(eligible_ticks_u32),
        "fast_path_ticks_u32": int(fast_path_ticks_u32),
        "fallback_ticks_u32": int(fallback_ticks_u32),
        "fast_path_rate": float(fast_path_rate),
        "fallback_rate": float(fallback_rate),
        "p95_prove_time_ms": int(p95_prove_time_ms),
        "p95_verify_time_ms": int(p95_verify_time_ms),
        "max_proof_size_bytes": int(max_proof_size_bytes),
        "slo": dict(slo),
        "gate": gate,
        "run_seed_range_u64": [int(_PHASE4_CANARY_SEEDS[0]), int(_PHASE4_CANARY_SEEDS[-1])],
        "ticks": per_tick,
    }


def main() -> None:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_root = REPO_ROOT / "runs" / f"phase3b_phase4_evidence_{ts}"
    run_root.mkdir(parents=True, exist_ok=True)
    packs_root = run_root / "packs"
    packs_root.mkdir(parents=True, exist_ok=True)

    native_pack = REPO_ROOT / "campaigns" / "rsi_omega_daemon_v19_0_phase1_native_modules_v1" / "rsi_omega_daemon_pack_v1.json"
    native_tick = _run_v19_tick(
        campaign_pack=native_pack,
        out_dir=run_root / "native_activation_tick_1",
        tick_u64=1,
        native_canon_bytes=True,
    )
    dispatch_dirs = sorted(
        [row for row in (native_tick.state_dir / "dispatch").iterdir() if row.is_dir()],
        key=lambda row: row.as_posix(),
    )
    if not dispatch_dirs:
        raise RuntimeError("native activation run did not produce a dispatch dir")
    activation_path = _latest_single(dispatch_dirs[-1] / "activation", "sha256_*.omega_activation_receipt_v1.json")
    activation_payload = load_canon_json(activation_path)
    native_module = activation_payload.get("native_module")
    if not isinstance(native_module, dict):
        raise RuntimeError("native activation receipt missing native_module payload")
    native_binary_sha = str(native_module.get("binary_sha256", ""))

    phase3b_native_pack = _prepare_v19_opcode_pack(
        packs_root / "phase3b_native_opcode_pack",
        nop_kind="NATIVE",
        nop_active_b=True,
        nop_binary_sha256=native_binary_sha,
    )
    phase3b_native_tick = _run_v19_tick(
        campaign_pack=phase3b_native_pack,
        out_dir=run_root / "phase3b_native_opcode_tick_2",
        tick_u64=1,
    )
    phase3b_native_verdict = verify_v19(phase3b_native_tick.state_dir, mode="full")
    phase3b_native_events = _ledger_event_types(phase3b_native_tick.state_dir)
    phase3b_native_trace = _latest_single(
        phase3b_native_tick.state_dir / "policy" / "traces",
        "sha256_*.policy_vm_trace_v1.json",
    )

    active_pack = _prepare_v19_opcode_pack(
        packs_root / "phase3b_active_pack",
        nop_kind="BUILTIN",
        nop_active_b=True,
    )
    dep_tick_1 = _run_v19_tick(
        campaign_pack=active_pack,
        out_dir=run_root / "phase3b_deprecation_tick_1_active",
        tick_u64=1,
    )
    dep_tick_1_verdict = verify_v19(dep_tick_1.state_dir, mode="full")

    deprecated_pack = _prepare_v19_opcode_pack(
        packs_root / "phase3b_deprecated_pack",
        nop_kind="BUILTIN",
        nop_active_b=False,
        deprecated_tick_u64=2,
    )
    deprecation_error: str | None = None
    try:
        _run_v19_tick(
            campaign_pack=deprecated_pack,
            out_dir=run_root / "phase3b_deprecation_tick_2_deprecated",
            tick_u64=2,
            prev_state_dir=dep_tick_1.state_dir,
        )
    except Exception as exc:  # noqa: BLE001
        deprecation_error = str(exc)

    proof_pack = _prepare_v19_proof_pack(packs_root / "phase4_proof_pack")
    proof_tick = _run_v19_tick(
        campaign_pack=proof_pack,
        out_dir=run_root / "phase4_proof_tick_1",
        tick_u64=1,
    )
    proof_state = proof_tick.state_dir
    proof_verdict_before = verify_v19(proof_state, mode="full")
    snapshot_path = _latest_single(proof_state / "snapshot", "sha256_*.omega_tick_snapshot_v1.json")
    snapshot_payload = load_canon_json(snapshot_path)
    proof_hash = str(snapshot_payload.get("policy_vm_stark_proof_hash", ""))
    proof_runtime_status = str(snapshot_payload.get("policy_vm_proof_runtime_status", ""))
    proof_profile_id = str(snapshot_payload.get("policy_vm_proof_profile_id", ""))
    proof_options_hash = str(snapshot_payload.get("policy_vm_proof_options_hash", ""))
    proof_runtime_reason_code = str(snapshot_payload.get("policy_vm_proof_runtime_reason_code", ""))
    proof_fallback_reason_code = str(snapshot_payload.get("policy_vm_proof_fallback_reason_code", ""))
    proof_payload_path = _latest_single(proof_state / "policy" / "proofs", "sha256_*.policy_vm_stark_proof_v1.json")
    proof_payload = load_canon_json(proof_payload_path)
    proof_representation_kind = str(proof_payload.get("proof_representation_kind", ""))
    proof_unit_verdict_before_tamper = _unit_proof_verdict(proof_payload=proof_payload, state_root=proof_state)
    proof_bin_path = proof_state / str(proof_payload["proof_bytes_rel"])
    proof_bin_path.write_bytes(b"tampered")
    proof_unit_verdict_after_tamper = _unit_proof_verdict(proof_payload=proof_payload, state_root=proof_state)
    try:
        daemon_verdict_after_tamper = verify_v19(proof_state, mode="full")
    except Exception as exc:  # noqa: BLE001
        daemon_verdict_after_tamper = f"INVALID:{exc}"
    proof_events = _ledger_event_types(proof_state)

    canary_96 = _collect_phase4_canary_metrics(
        run_root=run_root,
        packs_root=packs_root,
        profile_kind="POLICY_VM_AIR_PROFILE_96_V1",
    )
    canary_128 = _collect_phase4_canary_metrics(
        run_root=run_root,
        packs_root=packs_root,
        profile_kind="POLICY_VM_AIR_PROFILE_128_V1",
    )
    aggregate_eligible = int(canary_96["eligible_ticks_u32"]) + int(canary_128["eligible_ticks_u32"])
    aggregate_fast_path = int(canary_96["fast_path_ticks_u32"]) + int(canary_128["fast_path_ticks_u32"])
    aggregate_fallback = int(canary_96["fallback_ticks_u32"]) + int(canary_128["fallback_ticks_u32"])
    aggregate_fast_path_rate = (
        float(aggregate_fast_path) / float(aggregate_eligible) if aggregate_eligible else 0.0
    )
    aggregate_fallback_rate = (
        float(aggregate_fallback) / float(aggregate_eligible) if aggregate_eligible else 0.0
    )

    bundle = {
        "schema_version": "phase3b_phase4_evidence_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_root": str(run_root),
        "phase3b_activation": {
            "native_activation_tick_state_dir": str(native_tick.state_dir),
            "activation_receipt_path": str(activation_path),
            "activation_success_b": bool(activation_payload.get("activation_success", False)),
            "native_activation_gate_result": str(activation_payload.get("native_activation_gate_result", "")),
            "native_binary_sha256": native_binary_sha,
            "opcode_tick_state_dir": str(phase3b_native_tick.state_dir),
            "opcode_tick_verifier_verdict": phase3b_native_verdict,
            "opcode_tick_trace_path": str(phase3b_native_trace),
            "opcode_tick_ledger_events": phase3b_native_events,
        },
        "phase3b_deprecation": {
            "active_tick_state_dir": str(dep_tick_1.state_dir),
            "active_tick_verifier_verdict": dep_tick_1_verdict,
            "deprecated_tick_error": deprecation_error,
            "historical_replay_still_valid_b": dep_tick_1_verdict == "VALID",
        },
        "phase4_proof_fallback": {
            "proof_tick_state_dir": str(proof_state),
            "proof_hash": proof_hash,
            "proof_payload_path": str(proof_payload_path),
            "proof_representation_kind": proof_representation_kind,
            "proof_profile_id": proof_profile_id,
            "proof_options_hash": proof_options_hash,
            "proof_runtime_status": proof_runtime_status,
            "proof_runtime_reason_code": proof_runtime_reason_code,
            "proof_fallback_reason_code": proof_fallback_reason_code,
            "proof_events": proof_events,
            "daemon_verdict_before_tamper": proof_verdict_before,
            "daemon_verdict_after_tamper": daemon_verdict_after_tamper,
            "proof_unit_verdict_before_tamper": proof_unit_verdict_before_tamper,
            "proof_unit_verdict_after_tamper": proof_unit_verdict_after_tamper,
            "fallback_triggered_b": str(proof_unit_verdict_after_tamper).startswith("INVALID:"),
            "fallback_accept_b": daemon_verdict_after_tamper == "VALID",
        },
        "phase4_canary_gate": {
            "n_ticks_u32": len(_PHASE4_CANARY_SEEDS),
            "run_seed_range_u64": [int(_PHASE4_CANARY_SEEDS[0]), int(_PHASE4_CANARY_SEEDS[-1])],
            "profiles": {
                "POLICY_VM_AIR_PROFILE_96_V1": canary_96,
                "POLICY_VM_AIR_PROFILE_128_V1": canary_128,
            },
            "aggregate": {
                "eligible_ticks_u32": int(aggregate_eligible),
                "fast_path_ticks_u32": int(aggregate_fast_path),
                "fallback_ticks_u32": int(aggregate_fallback),
                "fast_path_rate": float(aggregate_fast_path_rate),
                "fallback_rate": float(aggregate_fallback_rate),
                "fast_path_rate_gate_ok_b": bool(aggregate_fast_path_rate >= 0.80),
                "fallback_rate_gate_ok_b": bool(aggregate_fallback_rate <= 0.20),
            },
        },
    }
    bundle_path = REPO_ROOT / "runs" / "PHASE3B_PHASE4_EVIDENCE_v1.json"
    bundle_path.write_text(json.dumps(bundle, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(str(bundle_path))


if __name__ == "__main__":
    main()
