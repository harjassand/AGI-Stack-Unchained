"""v19 replay verifier extending v18 with policy VM + policy market checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ..v18_0.ccap_runtime_v1 import compute_repo_base_tree_id_tolerant
from ..v18_0.omega_common_v1 import (
    canon_hash_obj,
    fail as fail_v18,
    load_canon_dict,
    repo_root as repo_root_v18,
)
from ..v18_0.verify_rsi_omega_daemon_v1 import OmegaV18Error
from ..v18_0.verify_rsi_omega_daemon_v1 import verify as verify_v18
from .common_v1 import validate_schema as validate_schema_v19
from .omega_promoter_v1 import _verify_axis_bundle_gate
from .verify_coordinator_isa_program_v1 import verify_program
from .verify_coordinator_opcode_table_v1 import verify_opcode_table
from .verify_counterfactual_trace_example_v1 import verify_counterfactual_trace_example
from .verify_hint_bundle_v1 import verify_hint_bundle
from .verify_inputs_descriptor_v1 import verify_inputs_descriptor
from .verify_merged_hint_state_v1 import verify_merged_hint_state
from .verify_policy_market_selection_v1 import verify_policy_market_selection
from .verify_policy_vm_stark_proof_v1 import verify_policy_vm_stark_proof
from .verify_policy_trace_proposal_v1 import verify_policy_trace_proposal
from .verify_policy_vm_trace_v1 import verify_policy_vm_trace


def _resolve_state_dir(path: Path) -> Path:
    root = path.resolve()
    if (root / "state").is_dir() and (root / "config").is_dir():
        return root / "state"
    if (root / "daemon" / "rsi_omega_daemon_v18_0" / "state").is_dir():
        return root / "daemon" / "rsi_omega_daemon_v18_0" / "state"
    if (root / "daemon" / "rsi_omega_daemon_v19_0" / "state").is_dir():
        return root / "daemon" / "rsi_omega_daemon_v19_0" / "state"
    if root.name == "state" and (root.parent / "config").is_dir():
        return root
    fail_v18("SCHEMA_FAIL")
    return root


def _load_canon_json(path: Path) -> dict[str, Any]:
    payload = load_canon_dict(path)
    if not isinstance(payload, dict):
        fail_v18("SCHEMA_FAIL")
    return payload


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("sha256:") and len(value.split(":", 1)[1]) == 64


def _path_for_hash(dir_path: Path, digest: str, suffix: str) -> Path | None:
    if not _is_sha256(digest):
        return None
    hexd = digest.split(":", 1)[1]
    path = dir_path / f"sha256_{hexd}.{suffix}"
    if path.exists() and path.is_file():
        return path
    return None


def _load_hash_bound_payload(*, dir_path: Path, digest: str, suffix: str, schema_version: str) -> dict[str, Any]:
    path = _path_for_hash(dir_path, digest, suffix)
    if path is None:
        fail_v18("MISSING_STATE_INPUT")
    payload = _load_canon_json(path)
    if str(payload.get("schema_version", "")).strip() != schema_version:
        fail_v18("SCHEMA_FAIL")
    if canon_hash_obj(payload) != digest:
        fail_v18("NONDETERMINISTIC")
    return payload


def _latest_snapshot_or_fail(snapshot_dir: Path) -> dict[str, Any]:
    rows = sorted(snapshot_dir.glob("sha256_*.omega_tick_snapshot_v1.json"), key=lambda row: row.as_posix())
    if not rows:
        fail_v18("MISSING_STATE_INPUT")
    best_payload: dict[str, Any] | None = None
    best_tick = -1
    for row in rows:
        payload = _load_canon_json(row)
        tick = int(payload.get("tick_u64", -1))
        if tick > best_tick:
            best_tick = tick
            best_payload = payload
    if best_payload is None:
        fail_v18("MISSING_STATE_INPUT")
    return best_payload


def _ledger_event_types(state_root: Path) -> list[str]:
    ledger_path = state_root / "ledger" / "omega_ledger_v1.jsonl"
    if not ledger_path.exists() or not ledger_path.is_file():
        fail_v18("MISSING_STATE_INPUT")
    out: list[str] = []
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            fail_v18("SCHEMA_FAIL")
            return []
        if isinstance(row, dict):
            out.append(str(row.get("event_type", "")))
    return out


def _find_nested_hash(state_root: Path, digest: str, suffix: str) -> Path:
    hexd = str(digest).split(":", 1)[1]
    target = f"sha256_{hexd}.{suffix}"
    rows = sorted(state_root.glob(f"dispatch/*/**/{target}"), key=lambda row: row.as_posix())
    if len(rows) != 1:
        fail_v18("MISSING_STATE_INPUT")
    return rows[0]


def _load_promotion_bundle_by_hash(state_root: Path, bundle_hash: str) -> Path | None:
    if not _is_sha256(bundle_hash):
        return None
    hexd = bundle_hash.split(":", 1)[1]
    rows = sorted(state_root.glob(f"subruns/**/sha256_{hexd}.*.json"), key=lambda row: row.as_posix())
    if not rows:
        return None
    return rows[0]


def _rethrow_as_v18(exc: Exception) -> None:
    msg = str(exc).strip()
    if msg.startswith("INVALID:"):
        msg = msg.split(":", 1)[1].strip()
    if not msg:
        msg = "NONDETERMINISTIC"
    fail_v18(msg)


def _load_pack(config_dir: Path) -> dict[str, Any]:
    pack = _load_canon_json(config_dir / "rsi_omega_daemon_pack_v1.json")
    if str(pack.get("schema_version", "")).strip() != "rsi_omega_daemon_pack_v2":
        fail_v18("NONDETERMINISTIC")
    return pack


def _verify_core_policy_assets(*, config_dir: Path, pack: dict[str, Any], descriptor_payload: dict[str, Any]) -> dict[str, Any]:
    opcode_rel = str(pack.get("coordinator_opcode_table_rel", "")).strip()
    if not opcode_rel:
        fail_v18("MISSING_STATE_INPUT")
    opcode_payload = _load_canon_json(config_dir / opcode_rel)
    try:
        verify_opcode_table(opcode_payload)
    except Exception as exc:
        _rethrow_as_v18(exc)
    if str(pack.get("coordinator_opcode_table_id", "")) != str(opcode_payload.get("opcode_table_id", "")):
        fail_v18("PIN_HASH_MISMATCH")
    descriptor_opcode_id = str(
        descriptor_payload.get("opcode_table_id", descriptor_payload.get("coordinator_opcode_table_id", ""))
    ).strip()
    if descriptor_opcode_id and descriptor_opcode_id != str(opcode_payload.get("opcode_table_id", "")):
        fail_v18("INPUTS_DESCRIPTOR_MISMATCH")

    predictor_payload = None
    predictor_id = str(pack.get("predictor_id", "")).strip() or ("sha256:" + ("0" * 64))
    predictor_rel = str(pack.get("predictor_weights_rel", "")).strip()
    if predictor_rel:
        predictor_payload = _load_canon_json(config_dir / predictor_rel)
        payload_predictor_id = predictor_payload.get("predictor_id")
        if payload_predictor_id is not None and str(payload_predictor_id).strip() != predictor_id:
            fail_v18("PREDICTOR_HASH_MISMATCH")
    descriptor_predictor_id = descriptor_payload.get("predictor_id")
    if descriptor_predictor_id is not None and str(descriptor_predictor_id) != predictor_id:
        fail_v18("INPUTS_DESCRIPTOR_MISMATCH")

    j_profile_payload = None
    j_profile_id = str(pack.get("objective_j_profile_id", "")).strip() or ("sha256:" + ("0" * 64))
    j_profile_rel = str(pack.get("objective_j_profile_rel", "")).strip()
    if j_profile_rel:
        j_profile_payload = _load_canon_json(config_dir / j_profile_rel)
        payload_profile_id = j_profile_payload.get("profile_id")
        if payload_profile_id is not None and str(payload_profile_id).strip() != j_profile_id:
            fail_v18("J_PROFILE_HASH_MISMATCH")
    descriptor_j_profile_id = descriptor_payload.get("j_profile_id")
    if descriptor_j_profile_id is not None and str(descriptor_j_profile_id) != j_profile_id:
        fail_v18("INPUTS_DESCRIPTOR_MISMATCH")

    policy_budget_spec_payload = None
    policy_budget_spec_id = str(pack.get("policy_budget_spec_id", "")).strip() or ("sha256:" + ("0" * 64))
    policy_budget_spec_rel = str(pack.get("policy_budget_spec_rel", "")).strip()
    if policy_budget_spec_rel:
        policy_budget_spec_payload = _load_canon_json(config_dir / policy_budget_spec_rel)
        if canon_hash_obj(policy_budget_spec_payload) != policy_budget_spec_id:
            fail_v18("PIN_HASH_MISMATCH")
    descriptor_budget_id = descriptor_payload.get("budget_spec_id")
    if descriptor_budget_id is not None and str(descriptor_budget_id) != policy_budget_spec_id:
        fail_v18("INPUTS_DESCRIPTOR_MISMATCH")

    determinism_contract_payload = None
    determinism_contract_id = str(pack.get("policy_determinism_contract_id", "")).strip() or ("sha256:" + ("0" * 64))
    determinism_contract_rel = str(pack.get("policy_determinism_contract_rel", "")).strip()
    if determinism_contract_rel:
        determinism_contract_payload = _load_canon_json(config_dir / determinism_contract_rel)
        if str(determinism_contract_payload.get("determinism_contract_id", "")) != determinism_contract_id:
            fail_v18("PIN_HASH_MISMATCH")
    descriptor_det_id = descriptor_payload.get("determinism_contract_id")
    if descriptor_det_id is not None and str(descriptor_det_id) != determinism_contract_id:
        fail_v18("INPUTS_DESCRIPTOR_MISMATCH")

    return {
        "opcode_table": opcode_payload,
        "predictor_payload": predictor_payload,
        "predictor_id": predictor_id,
        "j_profile_payload": j_profile_payload,
        "j_profile_id": j_profile_id,
        "policy_budget_spec_payload": policy_budget_spec_payload,
    }


def _verify_decision_only_vm_replay(
    *,
    state_root: Path,
    config_dir: Path,
    pack: dict[str, Any],
    descriptor_payload: dict[str, Any],
    descriptor_hash: str,
    decision_payload: dict[str, Any],
    snapshot: dict[str, Any],
    assets: dict[str, Any],
    skip_vm_replay: bool = False,
) -> None:
    program_rel = str(pack.get("coordinator_isa_program_rel", "")).strip()
    if not program_rel:
        fail_v18("MISSING_STATE_INPUT")
    program = _load_canon_json(config_dir / program_rel)
    try:
        verify_program(program)
    except Exception as exc:
        _rethrow_as_v18(exc)
    if str(pack.get("coordinator_isa_program_id", "")) != str(program.get("program_id", "")):
        fail_v18("PIN_HASH_MISMATCH")
    program_ids = descriptor_payload.get("policy_program_ids")
    if isinstance(program_ids, list):
        if len(program_ids) != 1 or str(program_ids[0]) != str(program.get("program_id", "")):
            fail_v18("INPUTS_DESCRIPTOR_MISMATCH")
    else:
        legacy_program_id = str(descriptor_payload.get("coordinator_isa_program_id", "")).strip()
        if legacy_program_id and legacy_program_id != str(program.get("program_id", "")):
            fail_v18("INPUTS_DESCRIPTOR_MISMATCH")

    trace_hash = snapshot.get("policy_vm_trace_hash")
    trace_payload = None
    if trace_hash is not None:
        if not _is_sha256(trace_hash):
            fail_v18("SCHEMA_FAIL")
        trace_payload = _load_hash_bound_payload(
            dir_path=state_root / "policy" / "traces",
            digest=str(trace_hash),
            suffix="policy_vm_trace_v1.json",
            schema_version="policy_vm_trace_v1",
        )
        try:
            verify_policy_vm_trace(trace_payload)
        except Exception as exc:
            _rethrow_as_v18(exc)

    observation_payload = _load_hash_bound_payload(
        dir_path=state_root / "observations",
        digest=str(snapshot.get("observation_report_hash")),
        suffix="omega_observation_report_v1.json",
        schema_version="omega_observation_report_v1",
    )

    from orchestrator.omega_v19_0.policy_vm_v1 import run_policy_vm_v1

    if skip_vm_replay:
        return

    replay_out = run_policy_vm_v1(
        tick_u64=int(decision_payload.get("tick_u64", 0)),
        mode="DECISION_ONLY",
        inputs_descriptor_hash=descriptor_hash,
        observation_report=observation_payload,
        observation_hash=str(snapshot.get("observation_report_hash")),
        issue_bundle_hash=str(snapshot.get("issue_bundle_hash")),
        policy_hash=str(decision_payload.get("policy_hash")),
        registry=_load_canon_json(config_dir / "omega_capability_registry_v2.json"),
        registry_hash=str(decision_payload.get("registry_hash")),
        budgets_hash=str(decision_payload.get("budgets_hash")),
        program=program,
        opcode_table=assets["opcode_table"],
        predictor_payload=assets["predictor_payload"],
        predictor_id=assets["predictor_id"],
        j_profile_payload=assets["j_profile_payload"],
        j_profile_id=assets["j_profile_id"],
        branch_id=str(pack.get("policy_branch_id", "b00")),
        round_u32=int(pack.get("policy_round_u32", 0)),
        policy_budget_spec=assets["policy_budget_spec_payload"],
    )
    replay_plan = replay_out.get("decision_plan")
    if not isinstance(replay_plan, dict):
        fail_v18("NONDETERMINISTIC")
    if canon_hash_obj(replay_plan) != canon_hash_obj(decision_payload):
        fail_v18("NONDETERMINISTIC")
    if trace_payload is not None:
        replay_trace = replay_out.get("policy_vm_trace")
        if not isinstance(replay_trace, dict):
            fail_v18("NONDETERMINISTIC")
        if canon_hash_obj(replay_trace) != canon_hash_obj(trace_payload):
            fail_v18("NONDETERMINISTIC")


def _verify_policy_market_replay(
    *,
    state_root: Path,
    config_dir: Path,
    pack: dict[str, Any],
    descriptor_payload: dict[str, Any],
    descriptor_hash: str,
    decision_payload: dict[str, Any],
    snapshot: dict[str, Any],
    assets: dict[str, Any],
) -> None:
    selection_hash = snapshot.get("policy_market_selection_hash")
    if not _is_sha256(selection_hash):
        fail_v18("MISSING_STATE_INPUT")
    selection_payload = _load_hash_bound_payload(
        dir_path=state_root / "policy" / "selection",
        digest=str(selection_hash),
        suffix="policy_market_selection_v1.json",
        schema_version="policy_market_selection_v1",
    )
    try:
        verify_policy_market_selection(selection_payload)
    except Exception as exc:
        _rethrow_as_v18(exc)
    if str(selection_payload.get("inputs_descriptor_hash", "")) != descriptor_hash:
        fail_v18("INPUTS_DESCRIPTOR_MISMATCH")

    proposal_hashes = selection_payload.get("proposal_hashes")
    if not isinstance(proposal_hashes, list) or not proposal_hashes:
        fail_v18("SCHEMA_FAIL")
    proposals_by_hash: dict[str, dict[str, Any]] = {}
    traces_by_hash: dict[str, dict[str, Any]] = {}
    decisions_by_hash: dict[str, dict[str, Any]] = {}
    for proposal_hash in proposal_hashes:
        if not _is_sha256(proposal_hash):
            fail_v18("SCHEMA_FAIL")
        proposal_payload = _load_hash_bound_payload(
            dir_path=state_root / "policy" / "proposals",
            digest=str(proposal_hash),
            suffix="policy_trace_proposal_v1.json",
            schema_version="policy_trace_proposal_v1",
        )
        try:
            verify_policy_trace_proposal(proposal_payload)
        except Exception as exc:
            _rethrow_as_v18(exc)
        if str(proposal_payload.get("inputs_descriptor_hash", "")) != descriptor_hash:
            fail_v18("INPUTS_DESCRIPTOR_MISMATCH")
        vm_trace_hash = str(proposal_payload.get("vm_trace_hash", ""))
        trace_payload = _load_hash_bound_payload(
            dir_path=state_root / "policy" / "traces",
            digest=vm_trace_hash,
            suffix="policy_vm_trace_v1.json",
            schema_version="policy_vm_trace_v1",
        )
        try:
            verify_policy_vm_trace(trace_payload)
        except Exception as exc:
            _rethrow_as_v18(exc)
        decision_hash = str(proposal_payload.get("decision_plan_hash", ""))
        decision_branch = _load_hash_bound_payload(
            dir_path=state_root / "policy" / "branch_decisions",
            digest=decision_hash,
            suffix="omega_decision_plan_v1.json",
            schema_version="omega_decision_plan_v1",
        )
        if str((decision_branch.get("recompute_proof") or {}).get("inputs_hash", "")) != descriptor_hash:
            fail_v18("INPUTS_DESCRIPTOR_MISMATCH")
        proposals_by_hash[str(proposal_hash)] = proposal_payload
        traces_by_hash[vm_trace_hash] = trace_payload
        decisions_by_hash[decision_hash] = decision_branch

    hint_files = sorted((state_root / "policy" / "hints").glob("sha256_*.hint_bundle_v1.json"), key=lambda p: p.as_posix())
    hint_hashes_by_branch_round: dict[tuple[str, int], str] = {}
    for path in hint_files:
        hint_payload = _load_canon_json(path)
        hint_hash = "sha256:" + path.name.split(".", 1)[0].split("_", 1)[1]
        if canon_hash_obj(hint_payload) != hint_hash:
            fail_v18("NONDETERMINISTIC")
        try:
            verify_hint_bundle(hint_payload)
        except Exception as exc:
            _rethrow_as_v18(exc)
        branch_id = str(hint_payload.get("branch_id", "")).strip()
        round_u32 = int(hint_payload.get("round_u32", -1))
        if round_u32 < 0 or not branch_id:
            fail_v18("SCHEMA_FAIL")
        hint_hashes_by_branch_round[(branch_id, round_u32)] = hint_hash
    merged_files = sorted((state_root / "policy" / "merged_hints").glob("sha256_*.merged_hint_state_v1.json"), key=lambda p: p.as_posix())
    for path in merged_files:
        payload = _load_canon_json(path)
        if canon_hash_obj(payload) != "sha256:" + path.name.split(".", 1)[0].split("_", 1)[1]:
            fail_v18("NONDETERMINISTIC")
        try:
            verify_merged_hint_state(payload)
        except Exception as exc:
            _rethrow_as_v18(exc)
        round_u32 = int(payload.get("round_u32", -1))
        if round_u32 >= 0:
            expected = sorted(
                value for (branch, rnd), value in hint_hashes_by_branch_round.items() if rnd == round_u32 and branch.startswith("b")
            )
            observed = sorted(str(row) for row in payload.get("contributing_hint_hashes", []))
            if expected and observed != expected:
                fail_v18("HINT_SYNC_VIOLATION")

    selection_policy_rel = str(pack.get("policy_selection_policy_rel", "")).strip()
    if not selection_policy_rel:
        fail_v18("MISSING_STATE_INPUT")
    selection_policy = _load_canon_json(config_dir / selection_policy_rel)

    from orchestrator.omega_bid_market_v2 import select_policy_proposal

    ordered_proposals = sorted(proposals_by_hash.values(), key=lambda row: str(row.get("branch_id", "")))
    replay_selection = select_policy_proposal(
        inputs_descriptor=descriptor_payload,
        proposals=ordered_proposals,
        predictor=assets["predictor_payload"],
        j_profile=assets["j_profile_payload"],
        selection_policy=selection_policy,
        observation_report=_load_hash_bound_payload(
            dir_path=state_root / "observations",
            digest=str(snapshot.get("observation_report_hash")),
            suffix="omega_observation_report_v1.json",
            schema_version="omega_observation_report_v1",
        ),
        traces_by_hash=traces_by_hash,
        decision_plans_by_hash=decisions_by_hash,
    )
    if canon_hash_obj(replay_selection) != str(selection_hash):
        fail_v18("NONDETERMINISTIC")

    winner_hash = str(selection_payload.get("winner_proposal_hash", ""))
    winner = proposals_by_hash.get(winner_hash)
    if not isinstance(winner, dict):
        fail_v18("MISSING_STATE_INPUT")
    winner_decision_hash = str(winner.get("decision_plan_hash", ""))
    if canon_hash_obj(decision_payload) != winner_decision_hash:
        fail_v18("NONDETERMINISTIC")

    cf_hash = snapshot.get("counterfactual_trace_example_hash")
    if cf_hash is not None:
        if not _is_sha256(cf_hash):
            fail_v18("SCHEMA_FAIL")
        cf_payload = _load_hash_bound_payload(
            dir_path=state_root / "policy" / "counterfactual",
            digest=str(cf_hash),
            suffix="counterfactual_trace_example_v1.json",
            schema_version="counterfactual_trace_example_v1",
        )
        try:
            verify_counterfactual_trace_example(cf_payload)
        except Exception as exc:
            _rethrow_as_v18(exc)
        if str(cf_payload.get("inputs_descriptor_hash", "")) != descriptor_hash:
            fail_v18("INPUTS_DESCRIPTOR_MISMATCH")
        if str((cf_payload.get("winner") or {}).get("proposal_hash", "")) != winner_hash:
            fail_v18("NONDETERMINISTIC")


def _verify_policy_path(state_root: Path, snapshot: dict[str, Any]) -> None:
    decision_hash = snapshot.get("decision_plan_hash")
    if not _is_sha256(decision_hash):
        fail_v18("SCHEMA_FAIL")
    decision_payload = _load_hash_bound_payload(
        dir_path=state_root / "decisions",
        digest=str(decision_hash),
        suffix="omega_decision_plan_v1.json",
        schema_version="omega_decision_plan_v1",
    )
    proof = decision_payload.get("recompute_proof")
    if not isinstance(proof, dict):
        fail_v18("NONDETERMINISTIC")
    inputs_hash = proof.get("inputs_hash")
    if not _is_sha256(inputs_hash):
        return

    descriptor_payload = _load_hash_bound_payload(
        dir_path=state_root / "policy" / "inputs",
        digest=str(inputs_hash),
        suffix="inputs_descriptor_v1.json",
        schema_version="inputs_descriptor_v1",
    )
    try:
        verify_inputs_descriptor(descriptor_payload)
    except Exception as exc:
        _rethrow_as_v18(exc)
    if str(snapshot.get("inputs_descriptor_hash")) not in {"None", "null"} and snapshot.get("inputs_descriptor_hash") is not None:
        if str(snapshot.get("inputs_descriptor_hash")) != str(inputs_hash):
            fail_v18("INPUTS_DESCRIPTOR_MISMATCH")
    expected_repo_tree_id = compute_repo_base_tree_id_tolerant(repo_root_v18())
    if str(descriptor_payload.get("repo_tree_id", "")) != str(expected_repo_tree_id):
        fail_v18("INPUTS_DESCRIPTOR_MISMATCH")

    config_dir = state_root.parent / "config"
    if not config_dir.exists() or not config_dir.is_dir():
        fail_v18("MISSING_STATE_INPUT")
    pack = _load_pack(config_dir)
    assets = _verify_core_policy_assets(
        config_dir=config_dir,
        pack=pack,
        descriptor_payload=descriptor_payload,
    )
    proof_hash = snapshot.get("policy_vm_stark_proof_hash")
    proof_runtime_status = snapshot.get("policy_vm_proof_runtime_status")
    if proof_runtime_status is not None:
        runtime_norm = str(proof_runtime_status).strip().upper()
        if runtime_norm not in {"ABSENT", "FAILED", "EMITTED"}:
            fail_v18("SCHEMA_FAIL")
        proof_runtime_status = runtime_norm
    if _is_sha256(proof_hash):
        if proof_runtime_status in {"ABSENT", "FAILED"}:
            fail_v18("NONDETERMINISTIC")
    elif proof_runtime_status == "EMITTED":
        fail_v18("NONDETERMINISTIC")

    ledger_events = _ledger_event_types(state_root)
    if _is_sha256(proof_hash):
        if "POLICY_VM_PROOF" not in ledger_events:
            fail_v18("NONDETERMINISTIC")
    if bool(pack.get("policy_vm_stark_proof_enable_b", False)) and proof_runtime_status in {"ABSENT", "FAILED"}:
        if "POLICY_VM_PROOF_FALLBACK" not in ledger_events:
            fail_v18("NONDETERMINISTIC")

    proof_assets: dict[str, Any] = {}
    if bool(pack.get("policy_vm_stark_proof_enable_b", False)):
        air_profile_rel = str(pack.get("policy_vm_air_profile_rel", "")).strip()
        air_profile_id = str(pack.get("policy_vm_air_profile_id", "")).strip()
        backend_rel = str(pack.get("policy_vm_winterfell_backend_contract_rel", "")).strip()
        backend_id = str(pack.get("policy_vm_winterfell_backend_contract_id", "")).strip()
        action_enum_rel = str(pack.get("policy_vm_action_kind_enum_rel", "")).strip()
        action_enum_id = str(pack.get("policy_vm_action_kind_enum_id", "")).strip()
        campaign_ids_rel = str(pack.get("policy_vm_candidate_campaign_ids_list_rel", "")).strip()
        campaign_ids_id = str(pack.get("policy_vm_candidate_campaign_ids_list_id", "")).strip()
        if not all([air_profile_rel, air_profile_id, backend_rel, backend_id, action_enum_rel, action_enum_id, campaign_ids_rel, campaign_ids_id]):
            fail_v18("MISSING_STATE_INPUT")

        air_profile_payload = _load_canon_json(config_dir / air_profile_rel)
        validate_schema_v19(air_profile_payload, "policy_vm_air_profile_v1")
        observed_air_profile_id = canon_hash_obj({k: v for k, v in air_profile_payload.items() if k != "air_profile_id"})
        if str(air_profile_payload.get("air_profile_id", "")) != observed_air_profile_id:
            fail_v18("PIN_HASH_MISMATCH")
        if observed_air_profile_id != air_profile_id:
            fail_v18("PIN_HASH_MISMATCH")

        backend_payload = _load_canon_json(config_dir / backend_rel)
        validate_schema_v19(backend_payload, "policy_vm_winterfell_backend_contract_v1")
        observed_backend_id = canon_hash_obj({k: v for k, v in backend_payload.items() if k != "backend_contract_id"})
        if str(backend_payload.get("backend_contract_id", "")) != observed_backend_id:
            fail_v18("PIN_HASH_MISMATCH")
        if observed_backend_id != backend_id:
            fail_v18("PIN_HASH_MISMATCH")

        action_kind_enum_payload = _load_canon_json(config_dir / action_enum_rel)
        validate_schema_v19(action_kind_enum_payload, "action_kind_enum_v1")
        observed_action_enum_id = canon_hash_obj({k: v for k, v in action_kind_enum_payload.items() if k != "action_kind_enum_id"})
        if str(action_kind_enum_payload.get("action_kind_enum_id", "")) != observed_action_enum_id:
            fail_v18("PIN_HASH_MISMATCH")
        if observed_action_enum_id != action_enum_id:
            fail_v18("PIN_HASH_MISMATCH")

        candidate_campaign_ids_payload = _load_canon_json(config_dir / campaign_ids_rel)
        validate_schema_v19(candidate_campaign_ids_payload, "candidate_campaign_ids_list_v1")
        observed_campaign_ids_id = canon_hash_obj(
            {k: v for k, v in candidate_campaign_ids_payload.items() if k != "candidate_campaign_ids_list_id"}
        )
        if str(candidate_campaign_ids_payload.get("candidate_campaign_ids_list_id", "")) != observed_campaign_ids_id:
            fail_v18("PIN_HASH_MISMATCH")
        if observed_campaign_ids_id != campaign_ids_id:
            fail_v18("PIN_HASH_MISMATCH")

        if str(air_profile_payload.get("action_kind_enum_hash", "")) != observed_action_enum_id:
            fail_v18("PIN_HASH_MISMATCH")
        if str(air_profile_payload.get("candidate_campaign_ids_list_hash", "")) != observed_campaign_ids_id:
            fail_v18("PIN_HASH_MISMATCH")

        proof_assets = {
            "air_profile_payload": air_profile_payload,
            "backend_contract_payload": backend_payload,
            "action_kind_enum_payload": action_kind_enum_payload,
            "candidate_campaign_ids_payload": candidate_campaign_ids_payload,
        }

    proof_valid = False
    if _is_sha256(proof_hash):
        trace_hash = snapshot.get("policy_vm_trace_hash")
        trace_payload = None
        if _is_sha256(trace_hash):
            trace_payload = _load_hash_bound_payload(
                dir_path=state_root / "policy" / "traces",
                digest=str(trace_hash),
                suffix="policy_vm_trace_v1.json",
                schema_version="policy_vm_trace_v1",
            )
            try:
                verify_policy_vm_trace(trace_payload)
            except Exception as exc:
                _rethrow_as_v18(exc)
        program_ids = descriptor_payload.get("policy_program_ids")
        policy_program_id = None
        if isinstance(program_ids, list) and len(program_ids) == 1 and _is_sha256(program_ids[0]):
            policy_program_id = str(program_ids[0])
        elif _is_sha256(descriptor_payload.get("coordinator_isa_program_id")):
            policy_program_id = str(descriptor_payload.get("coordinator_isa_program_id"))
        if policy_program_id is None and isinstance(program_ids, list):
            proof_payload_peek = _load_hash_bound_payload(
                dir_path=state_root / "policy" / "proofs",
                digest=str(proof_hash),
                suffix="policy_vm_stark_proof_v1.json",
                schema_version="policy_vm_stark_proof_v1",
            )
            candidate_program_id = str(proof_payload_peek.get("policy_program_id", "")).strip()
            if _is_sha256(candidate_program_id) and candidate_program_id in {str(row) for row in program_ids}:
                policy_program_id = candidate_program_id
            else:
                fail_v18("INPUTS_DESCRIPTOR_MISMATCH")
        if policy_program_id is None:
            fail_v18("SCHEMA_FAIL")
        expected = {
            "inputs_descriptor_hash": inputs_hash,
            "policy_program_id": policy_program_id,
            "opcode_table_id": descriptor_payload.get("opcode_table_id"),
            "decision_plan_hash": decision_hash,
            "decision_payload": decision_payload,
        }
        if isinstance(trace_payload, dict):
            expected["trace_payload"] = trace_payload
            expected["steps_executed_u64"] = int(trace_payload.get("steps_executed_u64", 0))
            expected["budget_outcome_hash"] = canon_hash_obj(trace_payload.get("budget_outcome", {}))
        if proof_assets:
            expected.update(proof_assets)
        proof_payload = _load_hash_bound_payload(
            dir_path=state_root / "policy" / "proofs",
            digest=str(proof_hash),
            suffix="policy_vm_stark_proof_v1.json",
            schema_version="policy_vm_stark_proof_v1",
        )
        try:
            verify_policy_vm_stark_proof(proof_payload, state_root=state_root, expected=expected)
            proof_valid = True
        except Exception:
            proof_valid = False

    mode = str(pack.get("policy_vm_mode", "DECISION_ONLY")).strip().upper()
    if mode in {"PROPOSAL_ONLY", "DUAL"} and snapshot.get("policy_market_selection_hash") is not None:
        _verify_policy_market_replay(
            state_root=state_root,
            config_dir=config_dir,
            pack=pack,
            descriptor_payload=descriptor_payload,
            descriptor_hash=str(inputs_hash),
            decision_payload=decision_payload,
            snapshot=snapshot,
            assets=assets,
        )
    else:
        _verify_decision_only_vm_replay(
            state_root=state_root,
            config_dir=config_dir,
            pack=pack,
            descriptor_payload=descriptor_payload,
            descriptor_hash=str(inputs_hash),
            decision_payload=decision_payload,
            snapshot=snapshot,
            assets=assets,
            skip_vm_replay=proof_valid,
        )


def verify(state_dir: Path, *, mode: str = "full") -> str:
    verify_v18(state_dir, mode=mode)

    state_root = _resolve_state_dir(state_dir)
    snapshot = _latest_snapshot_or_fail(state_root / "snapshot")
    _verify_policy_path(state_root, snapshot)

    promo_hash = snapshot.get("promotion_receipt_hash")
    if promo_hash is None:
        return "VALID"

    promotion_path = _find_nested_hash(state_root, str(promo_hash), "omega_promotion_receipt_v1.json")
    promotion_payload = _load_canon_json(promotion_path)
    status = str((promotion_payload.get("result") or {}).get("status", ""))
    if status != "PROMOTED":
        return "VALID"

    bundle_hash = str(promotion_payload.get("promotion_bundle_hash", ""))
    bundle_path = _load_promotion_bundle_by_hash(state_root, bundle_hash)
    if bundle_path is None:
        fail_v18("MISSING_STATE_INPUT")

    bundle_obj = _load_canon_json(bundle_path)
    try:
        _verify_axis_bundle_gate(
            bundle_obj=bundle_obj,
            bundle_path=bundle_path,
            promotion_dir=promotion_path.parent,
        )
    except Exception:
        fail_v18("NONDETERMINISTIC")

    return "VALID"


def main() -> None:
    parser = argparse.ArgumentParser(prog="verify_rsi_omega_daemon_v1_v19")
    parser.add_argument("--mode", required=True)
    parser.add_argument("--state_dir", required=True)
    args = parser.parse_args()

    try:
        print(verify(Path(args.state_dir), mode=args.mode))
    except OmegaV18Error as exc:
        msg = str(exc)
        if not msg.startswith("INVALID:"):
            msg = f"INVALID:{msg}"
        print(msg)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
