"""Deterministic microkernel for RSI Omega daemon v19.0 tick execution."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Iterator

from cdel.v18_0.omega_allowlists_v1 import load_allowlists
from orchestrator.omega_bid_market_v1 import (
    bid_market_enabled,
    build_bid_set_v1,
    build_bid_v1,
    build_decision_plan_from_selection,
    load_latest_bid_market_state,
    load_optional_bid_market_config,
    resolve_bidder_params,
    select_winner,
    settle_and_advance_market_state,
    write_bid_market_state,
    write_bid_selection_receipt,
    write_bid_set_v1,
    write_bid_settlement_receipt,
    write_bid_v1,
)
from cdel.v18_0.omega_budgets_v1 import debit_budget, load_budgets
from cdel.v18_0.omega_common_v1 import (
    canon_hash_obj,
    ensure_sha256,
    fail,
    load_canon_dict,
    repo_root,
    resolve_execution_mode,
    validate_schema,
    write_hashed_json,
)
from cdel.v18_0.ccap_runtime_v1 import compute_repo_base_tree_id_tolerant
from cdel.v19_0.common_v1 import validate_schema as validate_schema_v19
from cdel.v19_0.policy_vm_stark_runner_v1 import prove_policy_vm_stark
from cdel.v19_0.winterfell_contract_v1 import resolve_profile_backend_contract_bindings
from cdel.v18_0.omega_episodic_memory_v1 import (
    build_episodic_memory,
    load_latest_episodic_memory,
    write_episodic_memory,
)
from cdel.v18_0.omega_hotspots_v1 import build_hotspots, load_latest_hotspots, write_hotspots
from cdel.v18_0.omega_ledger_v1 import append_event
from cdel.v18_0.omega_noop_reason_v1 import classify_noop_reason
from cdel.v18_0.omega_objectives_v1 import load_objectives
from cdel.v18_0.omega_policy_ir_v1 import load_policy
from cdel.v18_0.omega_promotion_bundle_v1 import extract_touched_paths, load_bundle
from cdel.v18_0.omega_registry_v2 import load_registry, resolve_campaign
from cdel.v18_0.omega_run_scorecard_v1 import build_run_scorecard, load_latest_run_scorecard, write_run_scorecard
from cdel.v18_0.omega_runaway_v1 import (
    advance_runaway_state,
    bootstrap_runaway_state,
    check_runaway_condition,
    load_latest_runaway_state,
    load_runaway_config,
    runaway_enabled,
    write_runaway_state,
)
from cdel.v18_0.omega_state_v1 import default_state_from_hashes, goals_from_queue, load_latest_state, next_state, write_state
from cdel.v18_0.omega_temperature_v1 import compute_temperature_q32
from cdel.v18_0.omega_tick_outcome_v1 import build_tick_outcome, load_latest_tick_outcome, write_tick_outcome
from cdel.v18_0.omega_tick_perf_v1 import build_tick_perf, load_latest_tick_perf, write_tick_perf
from cdel.v18_0.omega_tick_stats_v1 import build_tick_stats, load_latest_tick_stats, write_tick_stats
from cdel.v18_0.omega_tick_snapshot_v1 import build_snapshot, write_snapshot
from cdel.v18_0.omega_trace_hash_chain_v1 import build_trace_chain, compute_h0, write_trace_chain

from orchestrator.omega_v18_0.applier_v1 import run_activation
from orchestrator.omega_v18_0.decider_v1 import decide
from orchestrator.omega_v18_0.diagnoser_v1 import diagnose
from orchestrator.omega_v18_0.dispatcher_v1 import dispatch_campaign
from orchestrator.omega_v18_0.goal_synthesizer_v1 import synthesize_goal_queue
from orchestrator.omega_v18_0.io_v1 import freeze_pack_config, load_goal_queue, write_goal_queue_effective
from orchestrator.omega_v18_0.locks_v1 import acquire_lock
from orchestrator.omega_v18_0.observer_v1 import observe, read_meta_core_active_manifest_hash
from orchestrator.omega_bid_market_v2 import select_policy_proposal
from .policy_vm_v1 import run_policy_vm_v1
from .promoter_v1 import run_promotion, run_subverifier

_GOAL_STATUSES = {"PENDING", "DONE", "FAILED"}
_FAMILY_BY_CAPABILITY = {
    "RSI_SAS_CODE": "CODE",
    "RSI_SAS_SYSTEM": "SYSTEM",
    "RSI_SAS_KERNEL": "KERNEL",
    "RSI_SAS_METASEARCH": "METASEARCH",
    "RSI_SAS_VAL": "VAL",
    "RSI_SAS_SCIENCE": "SCIENCE",
}
_DETERMINISTIC_TICK_TOTAL_NS = 1_000_000_000
_TIMING_STAGES: tuple[str, ...] = (
    "freeze_pack_config",
    "observe",
    "diagnose",
    "decide",
    "dispatch_campaign",
    "run_subverifier",
    "run_promotion",
    "run_activation",
    "ledger_writes",
    "trace_write",
    "snapshot_write",
)


@contextmanager
def _chdir(path: Path) -> Iterator[None]:
    original = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(original)


@contextmanager
def _temp_env(overrides: dict[str, str]) -> Iterator[None]:
    previous: dict[str, str | None] = {}
    for key, value in overrides.items():
        previous[key] = os.environ.get(key)
        os.environ[key] = str(value)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _deterministic_timing_enabled() -> bool:
    raw = str(os.environ.get("OMEGA_V19_DETERMINISTIC_TIMING", "1")).strip().lower()
    return raw not in {"0", "false", "off", "no"}

def _phase3_mutation_signal_enabled() -> bool:
    # Phase 3 DoD evidence: allow emitting a stable, greppable log line from the
    # mutated coordinator path. Bench/structural runs force this off.
    return str(os.environ.get("OMEGA_PHASE3_MUTATION_SIGNAL", "0")).strip() == "1"


def _write_payload(dir_path: Path, suffix: str, payload: dict[str, Any], id_field: str | None = None) -> tuple[Path, dict[str, Any], str]:
    return write_hashed_json(dir_path, suffix, payload, id_field=id_field)


def _assert_path_within(path: Path, root: Path) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except Exception:
        fail("FORBIDDEN_PATH")


def build_inputs_descriptor_once(
    *,
    tick_u64: int,
    prev_state_hash: str,
    repo_tree_id: str,
    observation_hash: str,
    issue_hash: str,
    registry_hash: str,
    policy_program_ids: list[str],
    predictor_hash: str,
    j_profile_hash: str,
    opcode_table_hash: str,
    policy_budget_spec_hash: str,
    determinism_contract_hash: str,
) -> dict[str, Any]:
    if not isinstance(policy_program_ids, list) or not policy_program_ids or len(policy_program_ids) > 100:
        fail("SCHEMA_FAIL")
    return {
        "schema_version": "inputs_descriptor_v1",
        "tick_u64": int(tick_u64),
        "state_hash": ensure_sha256(prev_state_hash, reason="SCHEMA_FAIL"),
        "repo_tree_id": ensure_sha256(repo_tree_id, reason="SCHEMA_FAIL"),
        "observation_hash": ensure_sha256(observation_hash, reason="SCHEMA_FAIL"),
        "issues_hash": ensure_sha256(issue_hash, reason="SCHEMA_FAIL"),
        "registry_hash": ensure_sha256(registry_hash, reason="SCHEMA_FAIL"),
        "policy_program_ids": [ensure_sha256(row, reason="SCHEMA_FAIL") for row in policy_program_ids],
        "predictor_id": ensure_sha256(predictor_hash, reason="SCHEMA_FAIL"),
        "j_profile_id": ensure_sha256(j_profile_hash, reason="SCHEMA_FAIL"),
        "opcode_table_id": ensure_sha256(opcode_table_hash, reason="SCHEMA_FAIL"),
        "budget_spec_id": ensure_sha256(policy_budget_spec_hash, reason="SCHEMA_FAIL"),
        "determinism_contract_id": ensure_sha256(determinism_contract_hash, reason="SCHEMA_FAIL"),
    }


def _load_pinned_json_payload(
    *,
    config_dir: Path,
    pack: dict[str, Any],
    rel_key: str,
    id_key: str,
    payload_id_field: str | None = None,
    missing_reason: str,
    mismatch_reason: str = "PIN_HASH_MISMATCH",
) -> tuple[dict[str, Any], str]:
    rel_raw = str(pack.get(rel_key, "")).strip()
    if not rel_raw:
        fail(missing_reason)
    rel = Path(rel_raw)
    if rel.is_absolute() or ".." in rel.parts:
        fail("SCHEMA_FAIL")
    declared_id = ensure_sha256(pack.get(id_key), reason=mismatch_reason)
    path = config_dir / rel
    if not path.exists() or not path.is_file():
        fail(missing_reason)
    payload = load_canon_dict(path)
    observed_id = None
    if payload_id_field:
        observed_raw = payload.get(payload_id_field)
        if isinstance(observed_raw, str) and observed_raw.strip():
            observed_id = ensure_sha256(observed_raw, reason=mismatch_reason)
            payload_no_id = dict(payload)
            payload_no_id.pop(payload_id_field, None)
            if canon_hash_obj(payload_no_id) != observed_id:
                fail(mismatch_reason)
    if observed_id is None:
        observed_id = canon_hash_obj(payload)
    if observed_id != declared_id:
        fail(mismatch_reason)
    return payload, observed_id


def _load_prev_state(prev_state_dir: Path | None) -> dict[str, Any] | None:
    if prev_state_dir is None:
        return None
    if (prev_state_dir / "state").is_dir():
        return load_latest_state(prev_state_dir / "state")
    return load_latest_state(prev_state_dir)


def _load_prev_runaway_state(prev_state_dir: Path | None) -> dict[str, Any] | None:
    if prev_state_dir is None:
        return None
    if (prev_state_dir / "runaway").is_dir():
        return load_latest_runaway_state(prev_state_dir / "runaway")
    if (prev_state_dir / "state" / "runaway").is_dir():
        return load_latest_runaway_state(prev_state_dir / "state" / "runaway")
    return None


def _load_prev_market_state(prev_state_dir: Path | None) -> dict[str, Any] | None:
    if prev_state_dir is None:
        return None
    candidates = [
        prev_state_dir / "market" / "state",
        prev_state_dir / "state" / "market" / "state",
    ]
    for state_dir in candidates:
        if state_dir.is_dir():
            payload = load_latest_bid_market_state(state_dir)
            if payload is not None:
                return payload
    return None


def _load_prev_selection_receipt(prev_state_dir: Path | None) -> tuple[dict[str, Any] | None, str | None]:
    if prev_state_dir is None:
        return None, None
    candidates = [
        prev_state_dir / "market" / "selection",
        prev_state_dir / "state" / "market" / "selection",
    ]
    for sel_dir in candidates:
        if not sel_dir.is_dir():
            continue
        rows = sorted(sel_dir.glob("sha256_*.bid_selection_receipt_v1.json"), key=lambda p: p.as_posix())
        if not rows:
            continue
        best: dict[str, Any] | None = None
        best_tick = -1
        for path in rows:
            payload = load_canon_dict(path)
            if payload.get("schema_version") != "bid_selection_receipt_v1":
                continue
            tick = int(payload.get("tick_u64", -1))
            if tick > best_tick:
                best_tick = tick
                best = payload
        if best is None:
            continue
        validate_schema(best, "bid_selection_receipt_v1")
        return best, canon_hash_obj(best)
    return None, None


def _load_prev_tick_perf(prev_state_dir: Path | None) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    if prev_state_dir is None:
        return None, None
    candidates = [
        prev_state_dir / "perf",
        prev_state_dir / "state" / "perf",
    ]
    for perf_dir in candidates:
        payload = load_latest_tick_perf(perf_dir)
        if payload is None:
            continue
        artifact_hash = canon_hash_obj(payload)
        source: dict[str, str] = {
            "schema_id": "omega_tick_perf_v1",
            "artifact_hash": artifact_hash,
            "producer_campaign_id": "rsi_omega_daemon_v18_0",
            "producer_run_id": artifact_hash,
        }
        return payload, source
    return None, None


def _load_prev_tick_stats(prev_state_dir: Path | None) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    if prev_state_dir is None:
        return None, None
    candidates = [
        prev_state_dir / "perf",
        prev_state_dir / "state" / "perf",
    ]
    for perf_dir in candidates:
        payload = load_latest_tick_stats(perf_dir)
        if payload is None:
            continue
        artifact_hash = canon_hash_obj(payload)
        source: dict[str, str] = {
            "schema_id": "omega_tick_stats_v1",
            "artifact_hash": artifact_hash,
            "producer_campaign_id": "rsi_omega_daemon_v18_0",
            "producer_run_id": artifact_hash,
        }
        return payload, source
    return None, None


def _load_prev_run_scorecard(prev_state_dir: Path | None) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    if prev_state_dir is None:
        return None, None
    candidates = [
        prev_state_dir / "perf",
        prev_state_dir / "state" / "perf",
    ]
    for perf_dir in candidates:
        payload = load_latest_run_scorecard(perf_dir)
        if payload is None:
            continue
        artifact_hash = canon_hash_obj(payload)
        source: dict[str, str] = {
            "schema_id": "omega_run_scorecard_v1",
            "artifact_hash": artifact_hash,
            "producer_campaign_id": "rsi_omega_daemon_v18_0",
            "producer_run_id": artifact_hash,
        }
        return payload, source
    return None, None


def _load_prev_observation(prev_state_dir: Path | None) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    if prev_state_dir is None:
        return None, None
    candidates = [
        prev_state_dir / "observations",
        prev_state_dir / "state" / "observations",
    ]
    for obs_dir in candidates:
        best_payload: dict[str, Any] | None = None
        best_tick = -1
        best_path: Path | None = None
        for row in sorted(obs_dir.glob("sha256_*.omega_observation_report_v1.json"), key=lambda path: path.as_posix()):
            payload = load_canon_dict(row)
            validate_schema(payload, "omega_observation_report_v1")
            tick_u64 = int(payload.get("tick_u64", -1))
            if tick_u64 > best_tick or (tick_u64 == best_tick and (best_path is None or row.as_posix() > best_path.as_posix())):
                best_payload = payload
                best_tick = tick_u64
                best_path = row
        if best_payload is None:
            continue
        artifact_hash = canon_hash_obj(best_payload)
        source: dict[str, str] = {
            "schema_id": "omega_observation_report_v1",
            "artifact_hash": artifact_hash,
            "producer_campaign_id": "rsi_omega_daemon_v18_0",
            "producer_run_id": artifact_hash,
        }
        return best_payload, source
    return None, None


def _load_prev_tick_outcome(prev_state_dir: Path | None) -> dict[str, Any] | None:
    if prev_state_dir is None:
        return None
    candidates = [
        prev_state_dir / "perf",
        prev_state_dir / "state" / "perf",
    ]
    for perf_dir in candidates:
        payload = load_latest_tick_outcome(perf_dir)
        if payload is not None:
            return payload
    return None


def _load_prev_hotspots(prev_state_dir: Path | None) -> dict[str, Any] | None:
    if prev_state_dir is None:
        return None
    candidates = [
        prev_state_dir / "perf",
        prev_state_dir / "state" / "perf",
    ]
    for perf_dir in candidates:
        payload = load_latest_hotspots(perf_dir)
        if payload is not None:
            return payload
    return None


def _load_prev_episodic_memory(prev_state_dir: Path | None) -> dict[str, Any] | None:
    if prev_state_dir is None:
        return None
    candidates = [
        prev_state_dir / "perf",
        prev_state_dir / "state" / "perf",
    ]
    for perf_dir in candidates:
        payload = load_latest_episodic_memory(perf_dir)
        if payload is not None:
            return payload
    return None


def _family_from_path(path_rel: str) -> str | None:
    value = str(path_rel).strip().lower()
    checks: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("METASEARCH", ("metasearch", "v16_1")),
        ("SCIENCE", ("science", "v13_0")),
        ("KERNEL", ("kernel", "v15_0")),
        ("SYSTEM", ("system", "v14_0")),
        ("VAL", ("sas_val", "rsi_sas_val", "v17_0")),
        ("CODE", ("sas_code", "rsi_sas_code", "v12_0")),
    )
    for family, needles in checks:
        if any(needle in value for needle in needles):
            return family
    return None


def _touched_families_from_promotion(
    *,
    state_root: Path,
    promotion_receipt: dict[str, Any] | None,
    capability_id: str | None = None,
) -> list[str]:
    out: set[str] = set()
    if capability_id:
        mapped = _FAMILY_BY_CAPABILITY.get(str(capability_id))
        if mapped is not None:
            out.add(mapped)
    if not isinstance(promotion_receipt, dict):
        return sorted(out)

    bundle_hash = str(promotion_receipt.get("promotion_bundle_hash", "")).strip()
    if not bundle_hash.startswith("sha256:") or len(bundle_hash.split(":", 1)[1]) != 64:
        return sorted(out)
    bundle_hex = bundle_hash.split(":", 1)[1]
    bundle_candidates = sorted(state_root.glob(f"subruns/**/sha256_{bundle_hex}.*.json"))
    if not bundle_candidates:
        return sorted(out)
    try:
        bundle_payload, _ = load_bundle(bundle_candidates[0])
        for path_rel in extract_touched_paths(bundle_payload):
            family = _family_from_path(path_rel)
            if family is not None:
                out.add(family)
    except Exception:  # noqa: BLE001
        return sorted(out)
    return sorted(out)


def _goal_id_prefix(goal_id: str) -> str:
    value = str(goal_id).strip()
    if not value:
        return ""
    for prefix in ("goal_self_optimize_core_00_", "goal_auto_00_", "goal_auto_10_", "goal_explore_20_", "goal_auto_90_"):
        if value.startswith(prefix):
            return prefix.rstrip("_")
    parts = value.split("_")
    if len(parts) >= 3:
        return "_".join(parts[:3])
    return value


def _episode_context_hash(*, issue_bundle: dict[str, Any], observation_report: dict[str, Any]) -> str:
    issues = issue_bundle.get("issues")
    metrics = observation_report.get("metrics")
    if not isinstance(issues, list) or not isinstance(metrics, dict):
        fail("SCHEMA_FAIL")
    issue_types = sorted(
        {
            str(row.get("issue_type", "")).strip()
            for row in issues
            if isinstance(row, dict) and str(row.get("issue_type", "")).strip()
        }
    )
    metric_keys = (
        "metasearch_cost_ratio_q32",
        "hotloop_top_share_q32",
        "build_link_fraction_q32",
        "science_rmse_q32",
        "promotion_reject_rate_rat",
        "subverifier_invalid_rate_rat",
        "runaway_blocked_noop_rate_rat",
        "brain_temperature_q32",
    )
    metric_subset = {key: metrics.get(key) for key in metric_keys if key in metrics}
    return canon_hash_obj(
        {
            "issue_types": issue_types,
            "metrics": metric_subset,
        }
    )


def _episodic_outcome(
    *,
    tick_outcome: dict[str, Any],
) -> str:
    action_kind = str(tick_outcome.get("action_kind", ""))
    if action_kind == "NOOP":
        return "NOOP"
    if str(tick_outcome.get("subverifier_status", "")) == "INVALID":
        return "INVALID"
    if (
        str(tick_outcome.get("promotion_status", "")) == "PROMOTED"
        and bool(tick_outcome.get("activation_success", False))
        and bool(tick_outcome.get("manifest_changed", False))
    ):
        return "PROMOTED"
    return "REJECTED"


def _episodic_reason_codes(
    *,
    subverifier_reason_code: str | None,
    tick_outcome: dict[str, Any],
) -> list[str]:
    out: set[str] = set()
    if str(tick_outcome.get("subverifier_status", "")) == "INVALID":
        out.add("SUBVERIFIER_INVALID")
        if subverifier_reason_code:
            out.add(str(subverifier_reason_code))
    promotion_reason_code = str(tick_outcome.get("promotion_reason_code", "")).strip()
    if promotion_reason_code and promotion_reason_code != "N/A":
        out.add(promotion_reason_code)
    activation_reasons = tick_outcome.get("activation_reasons")
    if isinstance(activation_reasons, list):
        for row in activation_reasons:
            value = str(row).strip()
            if value:
                out.add(value)
    return sorted(out)


def _merge_goals(prev_goals: dict[str, Any], goal_queue: dict[str, Any]) -> dict[str, dict[str, int | str]]:
    rows = goal_queue.get("goals")
    if not isinstance(rows, list):
        fail("SCHEMA_FAIL")
    merged: dict[str, dict[str, int | str]] = {}
    for row in rows:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        goal_id = str(row.get("goal_id", "")).strip()
        if not goal_id:
            fail("SCHEMA_FAIL")
        queue_status = str(row.get("status", "PENDING")).strip()
        if queue_status not in _GOAL_STATUSES:
            fail("SCHEMA_FAIL")
        prev_row = prev_goals.get(goal_id)
        if isinstance(prev_row, dict) and str(prev_row.get("status", "")).strip() in _GOAL_STATUSES:
            merged[goal_id] = {
                "status": str(prev_row.get("status", "")).strip(),
                "last_tick_u64": max(0, int(prev_row.get("last_tick_u64", 0))),
            }
            continue
        merged[goal_id] = {
            "status": queue_status,
            "last_tick_u64": 0,
        }
    return merged


def _activation_meta_verdict(dispatch_ctx: dict[str, Any] | None) -> str | None:
    if dispatch_ctx is None:
        return None
    dispatch_dir = dispatch_ctx.get("dispatch_dir")
    if not isinstance(dispatch_dir, str) or not dispatch_dir:
        return None
    out_path = Path(dispatch_dir) / "activation" / "meta_core_activation_out_v1.json"
    if not out_path.exists() or not out_path.is_file():
        return None
    try:
        payload = load_canon_dict(out_path)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(payload, dict):
        return None
    verdict = str(payload.get("verdict", "")).strip()
    return verdict or None


def _load_axis_gate_failure(dispatch_ctx: dict[str, Any] | None) -> dict[str, Any] | None:
    if dispatch_ctx is None:
        return None

    cap = dispatch_ctx.get("campaign_entry")
    if not isinstance(cap, dict):
        fail("SCHEMA_FAIL")
    rel_pattern = str(cap.get("promotion_bundle_rel", "")).strip()
    promotion_dir_rel = Path(rel_pattern).parent

    subrun_root_raw = dispatch_ctx.get("subrun_root_abs")
    dispatch_dir_raw = dispatch_ctx.get("dispatch_dir")
    if not isinstance(subrun_root_raw, (str, Path)):
        fail("SCHEMA_FAIL")
    if not isinstance(dispatch_dir_raw, (str, Path)):
        fail("SCHEMA_FAIL")

    candidate_paths = [
        Path(subrun_root_raw) / promotion_dir_rel / "axis_gate_failure_v1.json",
        Path(dispatch_dir_raw) / "promotion" / "axis_gate_failure_v1.json",
    ]
    axis_path = next((path for path in candidate_paths if path.exists() and path.is_file()), None)
    if axis_path is None:
        return None

    payload = load_canon_dict(axis_path)
    schema_name = str(payload.get("schema_name", "")).strip()
    schema_version = str(payload.get("schema_version", "")).strip()
    outcome = str(payload.get("outcome", "")).strip()
    detail_raw = payload.get("detail")
    detail = str(detail_raw).strip() if isinstance(detail_raw, str) else ""

    if schema_name != "axis_gate_failure_v1":
        fail("SCHEMA_FAIL")
    if schema_version != "v19_0":
        fail("SCHEMA_FAIL")
    if outcome not in {"SAFE_HALT", "SAFE_SPLIT"}:
        fail("SCHEMA_FAIL")
    if not detail:
        fail("SCHEMA_FAIL")

    normalized = dict(payload)
    normalized["schema_name"] = schema_name
    normalized["schema_version"] = schema_version
    normalized["outcome"] = outcome
    normalized["detail"] = detail
    return normalized


def _axis_gate_applies_safe_halt(axis_gate_failure: dict[str, Any] | None) -> bool:
    if axis_gate_failure is None:
        return False
    outcome = str(axis_gate_failure.get("outcome", "")).strip()
    if outcome == "SAFE_HALT":
        return True
    if outcome == "SAFE_SPLIT":
        return False
    fail("SCHEMA_FAIL")
    return False


def _axis_gate_promotion_reason_code(axis_gate_failure: dict[str, Any] | None) -> str | None:
    if axis_gate_failure is None:
        return None
    outcome = str(axis_gate_failure.get("outcome", "")).strip()
    detail = str(axis_gate_failure.get("detail", "")).strip()
    if not detail:
        fail("SCHEMA_FAIL")
    if outcome == "SAFE_HALT":
        return f"AXIS_GATE_SAFE_HALT:{detail}"
    if outcome == "SAFE_SPLIT":
        return f"AXIS_GATE_SAFE_SPLIT:{detail}"
    fail("SCHEMA_FAIL")
    return None


def _resolve_campaign_target_relpath(*, campaign_id: str, registry: dict[str, Any]) -> str:
    cid = str(campaign_id).strip()
    if not cid:
        return ""
    caps = registry.get("capabilities")
    if not isinstance(caps, list):
        fail("SCHEMA_FAIL")
    campaign_pack_rel = ""
    for row in caps:
        if not isinstance(row, dict):
            continue
        if str(row.get("campaign_id", "")).strip() != cid:
            continue
        campaign_pack_rel = str(row.get("campaign_pack_rel", "")).strip()
        break
    if not campaign_pack_rel:
        return ""
    pack_path = (Path.cwd().resolve() / campaign_pack_rel).resolve()
    if not pack_path.exists() or not pack_path.is_file():
        return ""
    pack_obj = load_canon_dict(pack_path)
    if not isinstance(pack_obj, dict):
        fail("SCHEMA_FAIL")
    target_relpath = pack_obj.get("target_relpath")
    if not isinstance(target_relpath, str):
        return ""
    return str(target_relpath).strip()


def _derive_dispatch_seed_u64(
    *,
    prev_state_id: str,
    tick_u64: int,
    campaign_id: str,
    target_relpath: str,
) -> int:
    payload = {
        "schema_id": "omega_dispatch_seed_v1",
        "prev_state_id": str(prev_state_id),
        "tick_u64": int(tick_u64),
        "campaign_id": str(campaign_id),
        "target_relpath": str(target_relpath),
    }
    canon = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    digest = hashlib.sha256(canon).digest()
    return int.from_bytes(digest[-8:], "big", signed=False)


def _ensure_sha256_id(value: Any) -> str:
    text = str(value).strip()
    if len(text) != 71 or not text.startswith("sha256:"):
        fail("SCHEMA_FAIL")
    digest = text.split(":", 1)[1]
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        fail("SCHEMA_FAIL")
    return text


def _load_hashed_payload(
    *,
    path: Path,
    expected_schema_version: str | None = None,
    expected_schema_name: str | None = None,
) -> tuple[dict[str, Any], str]:
    payload = load_canon_dict(path)
    if expected_schema_version is not None and str(payload.get("schema_version", "")).strip() != expected_schema_version:
        fail("SCHEMA_FAIL")
    if expected_schema_name is not None and str(payload.get("schema_name", "")).strip() != expected_schema_name:
        fail("SCHEMA_FAIL")
    observed_hash = canon_hash_obj(payload)

    name = path.name
    if not name.startswith("sha256_"):
        fail("NONDETERMINISTIC")
    digest_hex = name.split(".", 1)[0].split("_", 1)[1]
    if len(digest_hex) != 64 or any(ch not in "0123456789abcdef" for ch in digest_hex):
        fail("NONDETERMINISTIC")
    expected_hash = f"sha256:{digest_hex}"
    if observed_hash != expected_hash:
        fail("NONDETERMINISTIC")
    return payload, observed_hash


def _policy_mode(pack: dict[str, Any]) -> str:
    return str(pack.get("policy_vm_mode", "DECISION_ONLY")).strip().upper()


def _policy_market_enabled(pack: dict[str, Any]) -> bool:
    return _policy_mode(pack) in {"PROPOSAL_ONLY", "DUAL"}


def _hint_sort_key(item: dict[str, Any]) -> tuple[str, str, str]:
    kind = str(item.get("kind", "")).strip()
    key = str(item.get("key", "")).strip()
    if kind == "Q32_SCORE":
        value_norm = str(int(item.get("q32", 0)))
    else:
        values = item.get("values")
        if not isinstance(values, list):
            fail("SCHEMA_FAIL")
        value_norm = "\x1f".join(str(row) for row in values)
    return kind, key, value_norm


def _merge_hint_round_zero(
    *,
    inputs_descriptor_hash: str,
    hint_payloads_by_branch: dict[str, dict[str, Any]],
    merge_policy: dict[str, Any],
) -> dict[str, Any]:
    if str(merge_policy.get("schema_version", "")).strip() != "policy_merge_policy_v1":
        fail("SCHEMA_FAIL")
    branch_ids = sorted(hint_payloads_by_branch.keys())
    if not branch_ids:
        fail("MISSING_STATE_INPUT")
    contributing_hashes: list[str] = []
    q32_scores: dict[str, int] = {}
    sets_by_key: dict[str, set[str]] = {}
    default_set_cap = max(0, int(merge_policy.get("default_set_max_values_u32", 0)))
    per_key_caps_raw = merge_policy.get("set_max_values_by_key_u32") or {}
    if not isinstance(per_key_caps_raw, dict):
        fail("SCHEMA_FAIL")
    per_key_caps = {str(k): max(0, int(v)) for k, v in per_key_caps_raw.items()}
    default_agg = str(merge_policy.get("q32_score_default_aggregator", "SUM")).strip().upper()
    if default_agg not in {"SUM", "MAX"}:
        fail("SCHEMA_FAIL")
    per_key_agg_raw = merge_policy.get("q32_score_aggregators_by_key") or {}
    if not isinstance(per_key_agg_raw, dict):
        fail("SCHEMA_FAIL")
    per_key_agg = {str(k): str(v).strip().upper() for k, v in per_key_agg_raw.items()}
    for value in per_key_agg.values():
        if value not in {"SUM", "MAX"}:
            fail("SCHEMA_FAIL")

    for branch_id in branch_ids:
        hint_payload = hint_payloads_by_branch[branch_id]
        if str(hint_payload.get("schema_version", "")).strip() != "hint_bundle_v1":
            fail("SCHEMA_FAIL")
        if str(hint_payload.get("inputs_descriptor_hash", "")) != str(inputs_descriptor_hash):
            fail("INPUTS_DESCRIPTOR_MISMATCH")
        if int(hint_payload.get("round_u32", -1)) != 0:
            fail("SCHEMA_FAIL")
        hint_hash = canon_hash_obj(hint_payload)
        contributing_hashes.append(hint_hash)
        items = hint_payload.get("hint_items")
        if not isinstance(items, list):
            fail("SCHEMA_FAIL")
        if items != sorted(items, key=_hint_sort_key):
            fail("NONDETERMINISTIC")
        for item in items:
            if not isinstance(item, dict):
                fail("SCHEMA_FAIL")
            kind = str(item.get("kind", "")).strip()
            key = str(item.get("key", "")).strip()
            if not key:
                fail("SCHEMA_FAIL")
            if kind == "Q32_SCORE":
                q = int(item.get("q32", 0))
                agg = per_key_agg.get(key, default_agg)
                if key not in q32_scores:
                    q32_scores[key] = q
                elif agg == "SUM":
                    q32_scores[key] = int(q32_scores[key]) + int(q)
                elif agg == "MAX":
                    q32_scores[key] = max(int(q32_scores[key]), int(q))
                else:
                    fail("SCHEMA_FAIL")
            elif kind == "SET":
                values = item.get("values")
                if not isinstance(values, list):
                    fail("SCHEMA_FAIL")
                if key not in sets_by_key:
                    sets_by_key[key] = set()
                for row in values:
                    val = str(row).strip()
                    if val:
                        sets_by_key[key].add(val)
            else:
                fail("SCHEMA_FAIL")

    merged_hints: list[dict[str, Any]] = []
    for key in sorted(q32_scores.keys()):
        merged_hints.append({"kind": "Q32_SCORE", "key": key, "q32": int(q32_scores[key])})
    for key in sorted(sets_by_key.keys()):
        merged_values = sorted(sets_by_key[key])
        cap = per_key_caps.get(key, default_set_cap)
        merged_values = merged_values[: int(cap)] if int(cap) > 0 else []
        merged_hints.append({"kind": "SET", "key": key, "values": merged_values})
    merged_hints.sort(key=_hint_sort_key)
    merged_payload = {
        "schema_version": "merged_hint_state_v1",
        "inputs_descriptor_hash": inputs_descriptor_hash,
        "round_u32": 0,
        "contributing_hint_hashes": sorted(contributing_hashes),
        "merge_policy_id": str(merge_policy.get("merge_policy_id", "")),
        "merged_hints": merged_hints,
    }
    return merged_payload


def _outcome_code_from_tick(*, promotion_receipt: dict[str, Any] | None, safe_halt: bool) -> str:
    if safe_halt:
        return "CRASHED"
    status = str(((promotion_receipt or {}).get("result") or {}).get("status", "")).strip()
    if status == "PROMOTED":
        return "PROMOTED"
    if status in {"REJECTED", "SKIPPED"}:
        return "REJECTED"
    return "CRASHED"


def _compute_realized_delta_j_q32(
    *,
    prev_observation_report: dict[str, Any] | None,
    observation_report: dict[str, Any],
    j_profile_payload: dict[str, Any] | None,
) -> int:
    if not isinstance(prev_observation_report, dict) or not isinstance(j_profile_payload, dict):
        return 0
    metrics_now = observation_report.get("metrics")
    metrics_prev = prev_observation_report.get("metrics")
    weights = j_profile_payload.get("metric_weights")
    if not isinstance(metrics_now, dict) or not isinstance(metrics_prev, dict) or not isinstance(weights, list):
        return 0
    bias_now = 0
    bias_obj = j_profile_payload.get("bias_q32")
    if isinstance(bias_obj, dict) and set(bias_obj.keys()) == {"q"} and isinstance(bias_obj.get("q"), int):
        bias_now = int(bias_obj.get("q"))
    j_now = int(bias_now)
    j_prev = int(bias_now)
    from cdel.v18_0.omega_common_v1 import q32_mul

    for row in weights:
        if not isinstance(row, dict):
            continue
        metric_id = str(row.get("metric_id", "")).strip()
        weight = row.get("weight_q32")
        if not metric_id:
            continue
        if not (isinstance(weight, dict) and set(weight.keys()) == {"q"} and isinstance(weight.get("q"), int)):
            continue
        now_metric = metrics_now.get(metric_id)
        prev_metric = metrics_prev.get(metric_id)
        now_q = int(now_metric.get("q", 0)) if isinstance(now_metric, dict) and isinstance(now_metric.get("q"), int) else 0
        prev_q = int(prev_metric.get("q", 0)) if isinstance(prev_metric, dict) and isinstance(prev_metric.get("q"), int) else 0
        w_q = int(weight.get("q"))
        j_now += q32_mul(now_q, w_q)
        j_prev += q32_mul(prev_q, w_q)
    return int(j_now - j_prev)

def _find_subrun_payload_by_id(
    *,
    subrun_root: Path,
    artifact_id: str,
    suffix: str,
    expected_schema_version: str | None = None,
    expected_schema_name: str | None = None,
) -> tuple[dict[str, Any], str]:
    artifact_id = _ensure_sha256_id(artifact_id)
    digest_hex = artifact_id.split(":", 1)[1]
    paths = sorted(subrun_root.glob(f"**/sha256_{digest_hex}.{suffix}"), key=lambda row: row.as_posix())
    if len(paths) != 1:
        fail("MISSING_STATE_INPUT")
    payload, observed_hash = _load_hashed_payload(
        path=paths[0],
        expected_schema_version=expected_schema_version,
        expected_schema_name=expected_schema_name,
    )
    if observed_hash != artifact_id:
        fail("NONDETERMINISTIC")
    return payload, observed_hash


def _import_sip_ingestion_artifacts(
    *,
    dispatch_ctx: dict[str, Any] | None,
    state_root: Path,
) -> dict[str, str | None]:
    out: dict[str, str | None] = {
        "knowledge_hash": None,
        "refutation_hash": None,
        "manifest_hash": None,
        "receipt_hash": None,
    }
    if dispatch_ctx is None:
        return out

    subrun_root_raw = dispatch_ctx.get("subrun_root_abs")
    if not isinstance(subrun_root_raw, (str, Path)):
        return out
    subrun_root = Path(subrun_root_raw).resolve()
    if not subrun_root.exists() or not subrun_root.is_dir():
        return out

    knowledge_paths = sorted(
        subrun_root.glob("**/sha256_*.sip_knowledge_artifact_v1.json"),
        key=lambda row: row.as_posix(),
    )
    refutation_paths = sorted(
        subrun_root.glob("**/sha256_*.sip_knowledge_refutation_v1.json"),
        key=lambda row: row.as_posix(),
    )

    if not knowledge_paths and not refutation_paths:
        return out
    if knowledge_paths and refutation_paths:
        fail("SCHEMA_FAIL")

    ingestion_root = state_root / "polymath" / "ingestion"
    (ingestion_root / "knowledge").mkdir(parents=True, exist_ok=True)
    (ingestion_root / "refutations").mkdir(parents=True, exist_ok=True)
    (ingestion_root / "manifests").mkdir(parents=True, exist_ok=True)
    (ingestion_root / "receipts").mkdir(parents=True, exist_ok=True)

    if knowledge_paths:
        knowledge_payload, knowledge_hash = _load_hashed_payload(
            path=knowledge_paths[0],
            expected_schema_version="sip_knowledge_artifact_v1",
        )
        validate_schema(knowledge_payload, "sip_knowledge_artifact_v1")

        _, _knowledge_obj, imported_knowledge_hash = _write_payload(
            ingestion_root / "knowledge",
            "sip_knowledge_artifact_v1.json",
            knowledge_payload,
        )
        if imported_knowledge_hash != knowledge_hash:
            fail("NONDETERMINISTIC")
        out["knowledge_hash"] = imported_knowledge_hash

        manifest_id = _ensure_sha256_id(knowledge_payload.get("sip_manifest_id"))
        receipt_id = _ensure_sha256_id(knowledge_payload.get("sip_seal_receipt_id"))

        manifest_payload, manifest_hash = _find_subrun_payload_by_id(
            subrun_root=subrun_root,
            artifact_id=manifest_id,
            suffix="world_snapshot_manifest_v1.json",
            expected_schema_name="world_snapshot_manifest_v1",
        )
        _, _manifest_obj, imported_manifest_hash = _write_payload(
            ingestion_root / "manifests",
            "world_snapshot_manifest_v1.json",
            manifest_payload,
            id_field="manifest_id",
        )
        if imported_manifest_hash != manifest_hash:
            fail("NONDETERMINISTIC")
        out["manifest_hash"] = imported_manifest_hash

        receipt_payload, receipt_hash = _find_subrun_payload_by_id(
            subrun_root=subrun_root,
            artifact_id=receipt_id,
            suffix="sealed_ingestion_receipt_v1.json",
            expected_schema_name="sealed_ingestion_receipt_v1",
        )
        _, _receipt_obj, imported_receipt_hash = _write_payload(
            ingestion_root / "receipts",
            "sealed_ingestion_receipt_v1.json",
            receipt_payload,
            id_field="receipt_id",
        )
        if imported_receipt_hash != receipt_hash:
            fail("NONDETERMINISTIC")
        out["receipt_hash"] = imported_receipt_hash
        return out

    refutation_payload, refutation_hash = _load_hashed_payload(
        path=refutation_paths[0],
        expected_schema_version="sip_knowledge_refutation_v1",
    )
    validate_schema(refutation_payload, "sip_knowledge_refutation_v1")
    _, _ref_obj, imported_refutation_hash = _write_payload(
        ingestion_root / "refutations",
        "sip_knowledge_refutation_v1.json",
        refutation_payload,
    )
    if imported_refutation_hash != refutation_hash:
        fail("NONDETERMINISTIC")
    out["refutation_hash"] = imported_refutation_hash

    manifest_id_raw = refutation_payload.get("sip_manifest_id")
    if isinstance(manifest_id_raw, str) and manifest_id_raw.strip():
        manifest_id = _ensure_sha256_id(manifest_id_raw)
        manifest_payload, manifest_hash = _find_subrun_payload_by_id(
            subrun_root=subrun_root,
            artifact_id=manifest_id,
            suffix="world_snapshot_manifest_v1.json",
            expected_schema_name="world_snapshot_manifest_v1",
        )
        _, _manifest_obj, imported_manifest_hash = _write_payload(
            ingestion_root / "manifests",
            "world_snapshot_manifest_v1.json",
            manifest_payload,
            id_field="manifest_id",
        )
        if imported_manifest_hash != manifest_hash:
            fail("NONDETERMINISTIC")
        out["manifest_hash"] = imported_manifest_hash

    receipt_id_raw = refutation_payload.get("sip_seal_receipt_id")
    if isinstance(receipt_id_raw, str) and receipt_id_raw.strip():
        receipt_id = _ensure_sha256_id(receipt_id_raw)
        receipt_payload, receipt_hash = _find_subrun_payload_by_id(
            subrun_root=subrun_root,
            artifact_id=receipt_id,
            suffix="sealed_ingestion_receipt_v1.json",
            expected_schema_name="sealed_ingestion_receipt_v1",
        )
        _, _receipt_obj, imported_receipt_hash = _write_payload(
            ingestion_root / "receipts",
            "sealed_ingestion_receipt_v1.json",
            receipt_payload,
            id_field="receipt_id",
        )
        if imported_receipt_hash != receipt_hash:
            fail("NONDETERMINISTIC")
        out["receipt_hash"] = imported_receipt_hash

    return out


def tick_once(
    *,
    campaign_pack: Path,
    out_dir: Path,
    tick_u64: int,
    prev_state_dir: Path | None = None,
    run_subverifier_fn=run_subverifier,
    run_promotion_fn=run_promotion,
    run_activation_fn=run_activation,
    read_meta_core_active_manifest_hash_fn=read_meta_core_active_manifest_hash,
    synthesize_goal_queue_fn=synthesize_goal_queue,
) -> dict[str, Any]:
    run_root = out_dir.resolve()
    daemon_root = run_root / "daemon" / "rsi_omega_daemon_v19_0"
    config_dir = daemon_root / "config"
    state_root = daemon_root / "state"

    for rel in [
        "state",
        "runaway",
        "market/state",
        "market/bids",
        "market/bid_sets",
        "market/selection",
        "market/settlement",
        "observations",
        "issues",
        "decisions",
        "dispatch",
        "ledger",
        "perf",
        "policy/inputs",
        "policy/traces",
        "policy/hints",
        "policy/merged_hints",
        "policy/proposals",
        "policy/selection",
        "policy/counterfactual",
        "policy/workspaces",
        "policy/branches",
        "policy/branch_decisions",
        "snapshot",
        "subruns",
    ]:
        (state_root / rel).mkdir(parents=True, exist_ok=True)

    lock_path = daemon_root / "LOCK"
    with acquire_lock(lock_path):
        execution_mode = resolve_execution_mode()
        # Ensure per-tick native runtime stats are not contaminated by prior ticks
        # in the same Python process.
        try:
            from orchestrator.native.native_router_v1 import drain_runtime_stats

            _ = drain_runtime_stats()
        except Exception:
            pass
        deterministic_timing = _deterministic_timing_enabled()
        if _phase3_mutation_signal_enabled():
            print("SIGNAL=PHASE3_MUTATED_COORDINATOR v=1")
        tick_start_ns = time.monotonic_ns()
        stage_timings_ns: dict[str, int] = {stage: 0 for stage in _TIMING_STAGES}
        goal_queue_fastpath_outcome = "WRITE"

        def _mark(stage: str, stage_start_ns: int) -> None:
            if deterministic_timing:
                stage_timings_ns[stage] = 0
                return
            stage_timings_ns[stage] = int(stage_timings_ns.get(stage, 0)) + (time.monotonic_ns() - stage_start_ns)

        freeze_start_ns = time.monotonic_ns()
        pack, pack_hash = freeze_pack_config(campaign_pack=campaign_pack, config_dir=config_dir)
        _mark("freeze_pack_config", freeze_start_ns)

        policy, policy_hash = load_policy(config_dir / "omega_policy_ir_v1.json")
        registry, registry_hash = load_registry(config_dir / "omega_capability_registry_v2.json")
        objectives, objectives_hash = load_objectives(config_dir / "omega_objectives_v1.json")
        runaway_cfg, _runaway_cfg_hash = load_runaway_config(config_dir / "omega_runaway_config_v1.json")
        budgets, budgets_hash = load_budgets(config_dir / "omega_budgets_v1.json")
        allowlists, allowlists_hash = load_allowlists(config_dir / "omega_allowlists_v1.json")
        healthcheck_suite = load_canon_dict(config_dir / "healthcheck_suitepack_v1.json")
        validate_schema(healthcheck_suite, "healthcheck_suitepack_v1")
        healthcheck_suite_hash = canon_hash_obj(healthcheck_suite)

        goal_queue, goal_queue_hash = load_goal_queue(config_dir)

        bid_market_cfg, bid_market_cfg_hash = load_optional_bid_market_config(config_dir)
        market_enabled = bid_market_enabled(bid_market_cfg)

        prev_state = _load_prev_state(prev_state_dir)
        if prev_state is None:
            prev_state = default_state_from_hashes(
                policy_hash=policy_hash,
                registry_hash=registry_hash,
                objectives_hash=objectives_hash,
                budgets_hash=budgets_hash,
                allowlists_hash=allowlists_hash,
                goal_queue_hash=goal_queue_hash,
                goal_queue=goal_queue,
                budgets=budgets,
            )
        elif not isinstance(prev_state.get("goals"), dict):
            prev_state = dict(prev_state)
            prev_state["goals"] = goals_from_queue(goal_queue)

        active_manifest_before = read_meta_core_active_manifest_hash_fn()
        prev_state = dict(prev_state)
        prev_state["active_manifest_hash"] = active_manifest_before
        _, prev_state, _ = write_state(state_root / "state", prev_state)
        prev_tick_perf, prev_tick_perf_source = _load_prev_tick_perf(prev_state_dir)
        prev_tick_stats, prev_tick_stats_source = _load_prev_tick_stats(prev_state_dir)
        prev_run_scorecard, prev_run_scorecard_source = _load_prev_run_scorecard(prev_state_dir)
        prev_observation_report, _prev_observation_source = _load_prev_observation(prev_state_dir)
        prev_tick_outcome = _load_prev_tick_outcome(prev_state_dir)
        prev_hotspots = _load_prev_hotspots(prev_state_dir)
        prev_episodic_memory = _load_prev_episodic_memory(prev_state_dir)

        observe_start_ns = time.monotonic_ns()
        observation_report, observation_hash = observe(
            tick_u64=tick_u64,
            active_manifest_hash=active_manifest_before,
            policy_hash=policy_hash,
            registry_hash=registry_hash,
            objectives_hash=objectives_hash,
            allow_unbound_fallback=bool(pack.get("allow_unbound_observer_fallback", False)),
            previous_tick_perf=prev_tick_perf,
            previous_tick_perf_source=prev_tick_perf_source,
            previous_tick_stats=prev_tick_stats,
            previous_tick_stats_source=prev_tick_stats_source,
            previous_run_scorecard=prev_run_scorecard,
            previous_run_scorecard_source=prev_run_scorecard_source,
            previous_observation_report=prev_observation_report,
            registry=registry,
        )
        promotion_success_rate = {"num_u64": 0, "den_u64": 1}
        invalid_rate = {"num_u64": 0, "den_u64": 1}
        activation_denied_rate = {"num_u64": 0, "den_u64": 1}
        has_prev_run_scorecard_source = (
            isinstance(prev_run_scorecard_source, dict)
            and all(
                str(prev_run_scorecard_source.get(key, ""))
                for key in ("schema_id", "artifact_hash", "producer_campaign_id", "producer_run_id")
            )
        )
        has_prev_tick_stats_source = (
            isinstance(prev_tick_stats_source, dict)
            and all(
                str(prev_tick_stats_source.get(key, ""))
                for key in ("schema_id", "artifact_hash", "producer_campaign_id", "producer_run_id")
            )
        )
        if isinstance(prev_run_scorecard, dict) and has_prev_run_scorecard_source:
            row = prev_run_scorecard.get("promotion_success_rate_rat")
            if isinstance(row, dict):
                promotion_success_rate = {
                    "num_u64": max(0, int(row.get("num_u64", 0))),
                    "den_u64": max(1, int(row.get("den_u64", 1))),
                }
        if isinstance(prev_tick_stats, dict) and has_prev_tick_stats_source:
            row = prev_tick_stats.get("invalid_rate_rat")
            if isinstance(row, dict):
                invalid_rate = {
                    "num_u64": max(0, int(row.get("num_u64", 0))),
                    "den_u64": max(1, int(row.get("den_u64", 1))),
                }
            run_ticks_u64 = max(1, int(prev_tick_stats.get("run_ticks_u64", 1)))
            activation_denied_rate = {
                "num_u64": max(0, int(prev_tick_stats.get("activation_denied_u64", 0))),
                "den_u64": int(run_ticks_u64),
            }
        temperature_q32 = int(
            compute_temperature_q32(
                promotion_success_rate=promotion_success_rate,
                invalid_rate=invalid_rate,
                activation_denied_rate=activation_denied_rate,
            )
        )
        metrics = observation_report.get("metrics")
        if not isinstance(metrics, dict):
            fail("SCHEMA_FAIL")
        metrics["brain_temperature_q32"] = {"q": int(temperature_q32)}
        metric_series = observation_report.get("metric_series")
        if isinstance(metric_series, dict):
            metric_series["brain_temperature_q32"] = [{"q": int(temperature_q32)}]
        no_id = dict(observation_report)
        no_id.pop("report_id", None)
        observation_report["report_id"] = canon_hash_obj(no_id)
        validate_schema(observation_report, "omega_observation_report_v1")
        _mark("observe", observe_start_ns)
        _, observation_report, observation_hash = _write_payload(
            state_root / "observations",
            "omega_observation_report_v1.json",
            observation_report,
        )

        diagnose_start_ns = time.monotonic_ns()
        issue_bundle, issue_hash = diagnose(
            tick_u64=tick_u64,
            observation_report=observation_report,
            objectives=objectives,
        )
        _mark("diagnose", diagnose_start_ns)
        _, issue_bundle, issue_hash = _write_payload(
            state_root / "issues",
            "omega_issue_bundle_v1.json",
            issue_bundle,
        )

        goal_queue_effective = synthesize_goal_queue_fn(
            tick_u64=tick_u64,
            goal_queue_base=goal_queue,
            state=prev_state,
            issue_bundle=issue_bundle,
            observation_report=observation_report,
            registry=registry,
            runaway_cfg=runaway_cfg,
            run_scorecard=prev_run_scorecard,
            tick_stats=prev_tick_stats,
            tick_outcome=prev_tick_outcome,
            hotspots=prev_hotspots,
            episodic_memory=prev_episodic_memory,
        )
        synthesized_goal_queue_hash = canon_hash_obj(goal_queue_effective)
        if synthesized_goal_queue_hash == str(goal_queue_hash).strip():
            goal_queue_fastpath_outcome = "SKIP"
        else:
            _, goal_queue, goal_queue_hash = write_goal_queue_effective(config_dir, goal_queue_effective)
        prev_state = dict(prev_state)
        prev_state["goals"] = _merge_goals(prev_state.get("goals") or {}, goal_queue)

        prev_runaway_state = _load_prev_runaway_state(prev_state_dir)
        if runaway_enabled(runaway_cfg):
            if prev_runaway_state is None:
                prev_runaway_state = bootstrap_runaway_state(
                    objectives=objectives,
                    objective_set_hash=objectives_hash,
                    observation_report=observation_report,
                )
            elif str(prev_runaway_state.get("objective_set_hash")) != objectives_hash:
                fail("OBJECTIVE_SET_HASH_MISMATCH")
            _, prev_runaway_state, _ = write_runaway_state(state_root / "runaway", prev_runaway_state)

        decide_start_ns = time.monotonic_ns()
        bid_market_state_hash = None
        bid_settlement_receipt_hash = None
        bid_set_hash = None
        bid_selection_receipt_hash = None
        inputs_descriptor_hash = None
        policy_vm_trace_hash = None
        policy_vm_stark_proof_hash = None
        policy_market_selection_hash = None
        policy_market_selection_commitment_hash = None
        counterfactual_trace_example_hash = None
        policy_vm_trace_payload_for_proof: dict[str, Any] | None = None
        policy_vm_proof_program_id: str | None = None
        merged_hint_state_hash_for_proof: str | None = None
        policy_vm_proof_runtime_status = "ABSENT"
        policy_vm_proof_profile_id: str | None = None
        policy_vm_proof_options_hash: str | None = None
        policy_vm_proof_runtime_reason_code: str | None = "NOT_REQUESTED"
        policy_market_selection_payload: dict[str, Any] | None = None
        policy_market_proposals_by_hash: dict[str, dict[str, Any]] = {}
        policy_market_decisions_by_hash: dict[str, dict[str, Any]] = {}
        policy_market_winner_proposal_hash: str | None = None
        policy_market_selection_policy_payload: dict[str, Any] | None = None
        policy_market_j_profile_payload: dict[str, Any] | None = None
        opcode_table: dict[str, Any] | None = None
        opcode_table_hash: str | None = None
        if str(pack.get("schema_version", "")).strip() == "rsi_omega_daemon_pack_v2":
            opcode_table, opcode_table_hash = _load_pinned_json_payload(
                config_dir=config_dir,
                pack=pack,
                rel_key="coordinator_opcode_table_rel",
                id_key="coordinator_opcode_table_id",
                payload_id_field="opcode_table_id",
                missing_reason="OPCODE_TABLE_MISSING",
            )
            predictor_payload = None
            predictor_hash = str(pack.get("predictor_id", "")).strip()
            predictor_rel = str(pack.get("predictor_weights_rel", "")).strip()
            if bool(predictor_rel) != bool(predictor_hash):
                fail("SCHEMA_FAIL")
            if predictor_rel:
                predictor_payload, predictor_hash = _load_pinned_json_payload(
                    config_dir=config_dir,
                    pack=pack,
                    rel_key="predictor_weights_rel",
                    id_key="predictor_id",
                    payload_id_field="predictor_id",
                    missing_reason="PREDICTOR_MISSING",
                    mismatch_reason="PREDICTOR_HASH_MISMATCH",
                )
            if not predictor_hash:
                predictor_hash = "sha256:" + ("0" * 64)

            j_profile_payload = None
            j_profile_hash = str(pack.get("objective_j_profile_id", "")).strip()
            j_profile_rel = str(pack.get("objective_j_profile_rel", "")).strip()
            if bool(j_profile_rel) != bool(j_profile_hash):
                fail("SCHEMA_FAIL")
            if j_profile_rel:
                j_profile_payload, j_profile_hash = _load_pinned_json_payload(
                    config_dir=config_dir,
                    pack=pack,
                    rel_key="objective_j_profile_rel",
                    id_key="objective_j_profile_id",
                    payload_id_field="profile_id",
                    missing_reason="J_PROFILE_MISSING",
                    mismatch_reason="J_PROFILE_HASH_MISMATCH",
                )
            if not j_profile_hash:
                j_profile_hash = "sha256:" + ("0" * 64)

            policy_budget_spec_payload = None
            policy_budget_spec_hash = str(pack.get("policy_budget_spec_id", "")).strip() or ("sha256:" + ("0" * 64))
            if str(pack.get("policy_budget_spec_rel", "")).strip():
                policy_budget_spec_payload, policy_budget_spec_hash = _load_pinned_json_payload(
                    config_dir=config_dir,
                    pack=pack,
                    rel_key="policy_budget_spec_rel",
                    id_key="policy_budget_spec_id",
                    payload_id_field=None,
                    missing_reason="MISSING_STATE_INPUT",
                )
            determinism_contract_payload = None
            determinism_contract_hash = str(pack.get("policy_determinism_contract_id", "")).strip() or (
                "sha256:" + ("0" * 64)
            )
            if str(pack.get("policy_determinism_contract_rel", "")).strip():
                determinism_contract_payload, determinism_contract_hash = _load_pinned_json_payload(
                    config_dir=config_dir,
                    pack=pack,
                    rel_key="policy_determinism_contract_rel",
                    id_key="policy_determinism_contract_id",
                    payload_id_field="determinism_contract_id",
                    missing_reason="MISSING_STATE_INPUT",
                )
            mode = _policy_mode(pack)
            if _policy_market_enabled(pack):
                merge_policy_payload, _merge_policy_hash = _load_pinned_json_payload(
                    config_dir=config_dir,
                    pack=pack,
                    rel_key="policy_merge_policy_rel",
                    id_key="policy_merge_policy_id",
                    payload_id_field="merge_policy_id",
                    missing_reason="MISSING_STATE_INPUT",
                )
                selection_policy_payload, _selection_policy_hash = _load_pinned_json_payload(
                    config_dir=config_dir,
                    pack=pack,
                    rel_key="policy_selection_policy_rel",
                    id_key="policy_selection_policy_id",
                    payload_id_field="selection_policy_id",
                    missing_reason="MISSING_STATE_INPUT",
                )
                policy_market_selection_policy_payload = selection_policy_payload
                policy_market_j_profile_payload = j_profile_payload

                raw_program_rows = pack.get("policy_programs")
                if not isinstance(raw_program_rows, list) or not raw_program_rows:
                    fail("SCHEMA_FAIL")
                if len(raw_program_rows) > 100:
                    fail("SCHEMA_FAIL")
                policy_parallelism_u32 = max(1, int(pack.get("policy_parallelism_u32", len(raw_program_rows))))
                if policy_parallelism_u32 < 1:
                    fail("SCHEMA_FAIL")
                if int(pack.get("policy_hint_rounds_u32", 1)) != 1:
                    fail("SCHEMA_FAIL")
                policy_program_rows: list[tuple[str, dict[str, Any], str]] = []
                for idx, row in enumerate(raw_program_rows):
                    if not isinstance(row, dict):
                        fail("SCHEMA_FAIL")
                    rel = str(row.get("program_rel", "")).strip()
                    expected_id = ensure_sha256(row.get("program_id"), reason="PIN_HASH_MISMATCH")
                    rel_path = Path(rel)
                    if rel_path.is_absolute() or ".." in rel_path.parts:
                        fail("SCHEMA_FAIL")
                    payload = load_canon_dict(config_dir / rel_path)
                    if str(payload.get("schema_version", "")).strip() != "coordinator_isa_program_v1":
                        fail("SCHEMA_FAIL")
                    observed_id = ensure_sha256(payload.get("program_id"), reason="PIN_HASH_MISMATCH")
                    payload_no_id = dict(payload)
                    payload_no_id.pop("program_id", None)
                    if canon_hash_obj(payload_no_id) != observed_id:
                        fail("PIN_HASH_MISMATCH")
                    if observed_id != expected_id:
                        fail("PIN_HASH_MISMATCH")
                    policy_program_rows.append((f"b{idx:02d}", payload, observed_id))

                prev_state_hash = canon_hash_obj(prev_state)
                shared_repo_tree_id = compute_repo_base_tree_id_tolerant(repo_root())
                descriptor_payload = build_inputs_descriptor_once(
                    tick_u64=tick_u64,
                    prev_state_hash=prev_state_hash,
                    repo_tree_id=shared_repo_tree_id,
                    observation_hash=observation_hash,
                    issue_hash=issue_hash,
                    registry_hash=registry_hash,
                    policy_program_ids=[row[2] for row in policy_program_rows],
                    predictor_hash=predictor_hash,
                    j_profile_hash=j_profile_hash,
                    opcode_table_hash=opcode_table_hash,
                    policy_budget_spec_hash=policy_budget_spec_hash,
                    determinism_contract_hash=determinism_contract_hash,
                )
                _, descriptor_payload, inputs_descriptor_hash = _write_payload(
                    state_root / "policy" / "inputs",
                    "inputs_descriptor_v1.json",
                    descriptor_payload,
                )
                hint_payloads_by_branch: dict[str, dict[str, Any]] = {}
                hint_hashes_by_branch: dict[str, str] = {}
                continuations_by_branch: dict[str, dict[str, Any]] = {}
                traces_by_hash: dict[str, dict[str, Any]] = {}
                decisions_by_hash: dict[str, dict[str, Any]] = {}
                proposals_in_branch_order: list[dict[str, Any]] = []
                branch_roots: dict[str, Path] = {}

                for branch_id, program_payload, _program_id in policy_program_rows:
                    branch_root = state_root / "policy" / "branches" / branch_id
                    _assert_path_within(branch_root, state_root / "policy")
                    branch_root.mkdir(parents=True, exist_ok=True)
                    branch_roots[branch_id] = branch_root

                    workspace_dir = branch_root / "workspace"
                    tmp_dir = branch_root / "tmp"
                    cache_dir = branch_root / "cache"
                    workspace_dir.mkdir(parents=True, exist_ok=True)
                    tmp_dir.mkdir(parents=True, exist_ok=True)
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    workspace_meta = {
                        "schema_version": "policy_workspace_v1",
                        "branch_id": branch_id,
                        "repo_tree_id": shared_repo_tree_id,
                        "write_roots": {
                            "workspace_dir": str(workspace_dir),
                            "tmp_dir": str(tmp_dir),
                            "cache_dir": str(cache_dir),
                        },
                    }
                    _write_payload(workspace_dir, "policy_workspace_v1.json", workspace_meta)
                    with _temp_env(
                        {
                            "TMPDIR": str(tmp_dir),
                            "TMP": str(tmp_dir),
                            "TEMP": str(tmp_dir),
                            "OMEGA_BRANCH_CACHE_ROOT": str(cache_dir),
                        }
                    ):
                        vm_out = run_policy_vm_v1(
                            tick_u64=tick_u64,
                            mode="PROPOSAL_ONLY",
                            inputs_descriptor_hash=inputs_descriptor_hash,
                            observation_report=observation_report,
                            observation_hash=observation_hash,
                            issue_bundle_hash=issue_hash,
                            policy_hash=policy_hash,
                            registry=registry,
                            registry_hash=registry_hash,
                            budgets_hash=budgets_hash,
                            program=program_payload,
                            opcode_table=opcode_table,
                            predictor_payload=predictor_payload,
                            predictor_id=predictor_hash,
                            j_profile_payload=j_profile_payload,
                            j_profile_id=j_profile_hash,
                            branch_id=branch_id,
                            round_u32=0,
                            policy_budget_spec=policy_budget_spec_payload,
                        )
                    trace_payload = vm_out.get("policy_vm_trace")
                    hint_payload = vm_out.get("hint_bundle")
                    continuation = vm_out.get("continuation_state")
                    if not isinstance(trace_payload, dict) or not isinstance(hint_payload, dict) or not isinstance(continuation, dict):
                        fail("SCHEMA_FAIL")
                    pass0_traces_dir = branch_root / "round_00" / "pass0" / "traces"
                    pass0_hints_dir = branch_root / "round_00" / "pass0" / "hints"
                    _assert_path_within(pass0_traces_dir, branch_root)
                    _assert_path_within(pass0_hints_dir, branch_root)
                    _pass0_trace_path, trace_payload, trace_hash = _write_payload(
                        pass0_traces_dir,
                        "policy_vm_trace_v1.json",
                        trace_payload,
                    )
                    _, trace_payload, trace_hash = _write_payload(
                        state_root / "policy" / "traces",
                        "policy_vm_trace_v1.json",
                        trace_payload,
                    )
                    traces_by_hash[trace_hash] = trace_payload
                    _pass0_hint_path, hint_payload, hint_hash = _write_payload(
                        pass0_hints_dir,
                        "hint_bundle_v1.json",
                        hint_payload,
                    )
                    _, hint_payload, hint_hash = _write_payload(
                        state_root / "policy" / "hints",
                        "hint_bundle_v1.json",
                        hint_payload,
                    )
                    hint_payloads_by_branch[branch_id] = hint_payload
                    hint_hashes_by_branch[branch_id] = hint_hash
                    continuations_by_branch[branch_id] = continuation

                if set(hint_payloads_by_branch.keys()) != {row[0] for row in policy_program_rows}:
                    fail("HINT_SYNC_VIOLATION")
                merged_hint_payload = _merge_hint_round_zero(
                    inputs_descriptor_hash=inputs_descriptor_hash,
                    hint_payloads_by_branch=hint_payloads_by_branch,
                    merge_policy=merge_policy_payload,
                )
                _, merged_hint_payload, _merged_hint_hash = _write_payload(
                    state_root / "policy" / "merged_hints",
                    "merged_hint_state_v1.json",
                    merged_hint_payload,
                )
                expected_hint_hashes = sorted(hint_hashes_by_branch.values())
                for branch_id, program_payload, _program_id in policy_program_rows:
                    continuation = continuations_by_branch.get(branch_id)
                    if not isinstance(continuation, dict):
                        fail("HINT_SYNC_VIOLATION")
                    branch_root = branch_roots.get(branch_id)
                    if not isinstance(branch_root, Path):
                        fail("HINT_SYNC_VIOLATION")
                    tmp_dir = branch_root / "tmp"
                    cache_dir = branch_root / "cache"
                    with _temp_env(
                        {
                            "TMPDIR": str(tmp_dir),
                            "TMP": str(tmp_dir),
                            "TEMP": str(tmp_dir),
                            "OMEGA_BRANCH_CACHE_ROOT": str(cache_dir),
                        }
                    ):
                        vm_out = run_policy_vm_v1(
                            tick_u64=tick_u64,
                            mode="PROPOSAL_ONLY",
                            inputs_descriptor_hash=inputs_descriptor_hash,
                            observation_report=observation_report,
                            observation_hash=observation_hash,
                            issue_bundle_hash=issue_hash,
                            policy_hash=policy_hash,
                            registry=registry,
                            registry_hash=registry_hash,
                            budgets_hash=budgets_hash,
                            program=program_payload,
                            opcode_table=opcode_table,
                            predictor_payload=predictor_payload,
                            predictor_id=predictor_hash,
                            j_profile_payload=j_profile_payload,
                            j_profile_id=j_profile_hash,
                            branch_id=branch_id,
                            round_u32=0,
                            resume_state=continuation,
                            policy_budget_spec=policy_budget_spec_payload,
                            barrier_ctx={
                                "merged_hint_state_by_round": {0: merged_hint_payload},
                                "expected_hint_hashes_by_round": {0: expected_hint_hashes},
                                "branch_emitted_hint_rounds": [0],
                                "branch_hint_hashes_by_round": {"0": hint_hashes_by_branch[branch_id]},
                            },
                        )
                    trace_payload = vm_out.get("policy_vm_trace")
                    decision_payload = vm_out.get("decision_plan")
                    proposal_payload = vm_out.get("policy_trace_proposal")
                    if not isinstance(trace_payload, dict) or not isinstance(decision_payload, dict) or not isinstance(proposal_payload, dict):
                        fail("SCHEMA_FAIL")
                    pass1_traces_dir = branch_root / "round_00" / "pass1" / "traces"
                    pass1_decisions_dir = branch_root / "round_00" / "pass1" / "decisions"
                    pass1_proposals_dir = branch_root / "round_00" / "pass1" / "proposals"
                    _assert_path_within(pass1_traces_dir, branch_root)
                    _assert_path_within(pass1_decisions_dir, branch_root)
                    _assert_path_within(pass1_proposals_dir, branch_root)
                    _pass1_trace_path, trace_payload, trace_hash = _write_payload(
                        pass1_traces_dir,
                        "policy_vm_trace_v1.json",
                        trace_payload,
                    )
                    _, trace_payload, trace_hash = _write_payload(
                        state_root / "policy" / "traces",
                        "policy_vm_trace_v1.json",
                        trace_payload,
                    )
                    traces_by_hash[trace_hash] = trace_payload
                    _pass1_decision_path, decision_payload, decision_branch_hash = _write_payload(
                        pass1_decisions_dir,
                        "omega_decision_plan_v1.json",
                        decision_payload,
                    )
                    _, decision_payload, decision_branch_hash = _write_payload(
                        state_root / "policy" / "branch_decisions",
                        "omega_decision_plan_v1.json",
                        decision_payload,
                    )
                    decisions_by_hash[decision_branch_hash] = decision_payload
                    if str(proposal_payload.get("vm_trace_hash", "")) != str(trace_hash):
                        fail("NONDETERMINISTIC")
                    if str(proposal_payload.get("decision_plan_hash", "")) != str(decision_branch_hash):
                        fail("NONDETERMINISTIC")
                    _pass1_proposal_path, proposal_payload, proposal_hash = _write_payload(
                        pass1_proposals_dir,
                        "policy_trace_proposal_v1.json",
                        proposal_payload,
                    )
                    _, proposal_payload, proposal_hash = _write_payload(
                        state_root / "policy" / "proposals",
                        "policy_trace_proposal_v1.json",
                        proposal_payload,
                    )
                    proposals_in_branch_order.append(proposal_payload)
                    policy_market_proposals_by_hash[proposal_hash] = proposal_payload
                    policy_market_decisions_by_hash[decision_branch_hash] = decision_payload

                selection_payload = select_policy_proposal(
                    inputs_descriptor=descriptor_payload,
                    proposals=proposals_in_branch_order,
                    predictor=predictor_payload,
                    j_profile=j_profile_payload,
                    selection_policy=selection_policy_payload,
                    observation_report=observation_report,
                    traces_by_hash=traces_by_hash,
                    decision_plans_by_hash=decisions_by_hash,
                )
                _, selection_payload, policy_market_selection_hash = _write_payload(
                    state_root / "policy" / "selection",
                    "policy_market_selection_v1.json",
                    selection_payload,
                )
                policy_market_selection_commitment_hash = str(selection_payload.get("selection_commitment_hash", "")).strip() or None
                policy_market_selection_payload = selection_payload
                policy_market_winner_proposal_hash = str(selection_payload.get("winner_proposal_hash"))
                winner = policy_market_proposals_by_hash.get(policy_market_winner_proposal_hash)
                if not isinstance(winner, dict):
                    fail("MISSING_STATE_INPUT")
                winner_decision_hash = str(winner.get("decision_plan_hash", "")).strip()
                decision_plan = policy_market_decisions_by_hash.get(winner_decision_hash)
                if not isinstance(decision_plan, dict):
                    fail("MISSING_STATE_INPUT")
                if str((decision_plan.get("recompute_proof") or {}).get("inputs_hash", "")) != str(inputs_descriptor_hash):
                    fail("INPUTS_DESCRIPTOR_MISMATCH")
                policy_vm_trace_hash = str(winner.get("vm_trace_hash", "")).strip() or None
                if policy_vm_trace_hash is not None:
                    policy_vm_trace_payload_for_proof = traces_by_hash.get(str(policy_vm_trace_hash))
                policy_vm_proof_program_id = str(winner.get("policy_program_id", "")).strip() or None
                merged_hint_state_hash_for_proof = _merged_hint_hash
                _mark("decide", decide_start_ns)
                _, decision_plan, decision_hash = _write_payload(
                    state_root / "decisions",
                    "omega_decision_plan_v1.json",
                    decision_plan,
                )
            else:
                policy_program, policy_program_hash = _load_pinned_json_payload(
                    config_dir=config_dir,
                    pack=pack,
                    rel_key="coordinator_isa_program_rel",
                    id_key="coordinator_isa_program_id",
                    payload_id_field="program_id",
                    missing_reason="ISA_PROGRAM_MISSING",
                )
                prev_state_hash = canon_hash_obj(prev_state)
                shared_repo_tree_id = compute_repo_base_tree_id_tolerant(repo_root())
                descriptor_payload = build_inputs_descriptor_once(
                    tick_u64=tick_u64,
                    prev_state_hash=prev_state_hash,
                    repo_tree_id=shared_repo_tree_id,
                    observation_hash=observation_hash,
                    issue_hash=issue_hash,
                    registry_hash=registry_hash,
                    policy_program_ids=[policy_program_hash],
                    predictor_hash=predictor_hash,
                    j_profile_hash=j_profile_hash,
                    opcode_table_hash=opcode_table_hash,
                    policy_budget_spec_hash=policy_budget_spec_hash,
                    determinism_contract_hash=determinism_contract_hash,
                )
                _, descriptor_payload, inputs_descriptor_hash = _write_payload(
                    state_root / "policy" / "inputs",
                    "inputs_descriptor_v1.json",
                    descriptor_payload,
                )
                vm_out = run_policy_vm_v1(
                    tick_u64=tick_u64,
                    mode=mode,
                    inputs_descriptor_hash=inputs_descriptor_hash,
                    observation_report=observation_report,
                    observation_hash=observation_hash,
                    issue_bundle_hash=issue_hash,
                    policy_hash=policy_hash,
                    registry=registry,
                    registry_hash=registry_hash,
                    budgets_hash=budgets_hash,
                    program=policy_program,
                    opcode_table=opcode_table,
                    predictor_payload=predictor_payload,
                    predictor_id=predictor_hash,
                    j_profile_payload=j_profile_payload,
                    j_profile_id=j_profile_hash,
                    branch_id=str(pack.get("policy_branch_id", "b00")),
                    round_u32=int(pack.get("policy_round_u32", 0)),
                    policy_budget_spec=policy_budget_spec_payload,
                )
                trace_payload = vm_out.get("policy_vm_trace")
                if not isinstance(trace_payload, dict):
                    fail("SCHEMA_FAIL")
                _, trace_payload, policy_vm_trace_hash = _write_payload(
                    state_root / "policy" / "traces",
                    "policy_vm_trace_v1.json",
                    trace_payload,
                )
                policy_vm_trace_payload_for_proof = trace_payload
                policy_vm_proof_program_id = policy_program_hash
                hint_payload = vm_out.get("hint_bundle")
                if isinstance(hint_payload, dict):
                    _write_payload(state_root / "policy" / "hints", "hint_bundle_v1.json", hint_payload)
                proposal_payload = vm_out.get("policy_trace_proposal")
                if isinstance(proposal_payload, dict):
                    _write_payload(state_root / "policy" / "proposals", "policy_trace_proposal_v1.json", proposal_payload)
                decision_plan = vm_out.get("decision_plan")
                if not isinstance(decision_plan, dict):
                    fail("POLICY_MODE_VIOLATION")
                if str((decision_plan.get("recompute_proof") or {}).get("inputs_hash", "")).strip() != str(
                    inputs_descriptor_hash
                ).strip():
                    fail("INPUTS_DESCRIPTOR_MISMATCH")
                _mark("decide", decide_start_ns)
                _, decision_plan, decision_hash = _write_payload(
                    state_root / "decisions",
                    "omega_decision_plan_v1.json",
                    decision_plan,
                )
        elif not market_enabled:
            decision_plan, decision_hash = decide(
                tick_u64=tick_u64,
                state=prev_state,
                observation_report_hash=observation_hash,
                issue_bundle_hash=issue_hash,
                observation_report=observation_report,
                issue_bundle=issue_bundle,
                policy=policy,
                policy_hash=policy_hash,
                registry=registry,
                registry_hash=registry_hash,
                budgets_hash=budgets_hash,
                goal_queue=goal_queue,
                objectives=objectives,
                runaway_cfg=runaway_cfg,
                runaway_state=prev_runaway_state,
            )
            _mark("decide", decide_start_ns)
            _, decision_plan, decision_hash = _write_payload(
                state_root / "decisions",
                "omega_decision_plan_v1.json",
                decision_plan,
            )
        else:
            if bid_market_cfg is None or bid_market_cfg_hash is None:
                fail("MISSING_STATE_INPUT")
            prev_market_state = _load_prev_market_state(prev_state_dir)
            prev_market_state_hash = None
            if prev_market_state is not None:
                _, prev_market_state, prev_market_state_hash = write_bid_market_state(state_root / "market" / "state", prev_market_state)

            prev_selection_receipt, prev_selection_hash = _load_prev_selection_receipt(prev_state_dir)
            if prev_selection_receipt is not None:
                _, prev_selection_receipt, prev_selection_hash = write_bid_selection_receipt(state_root / "market" / "selection", prev_selection_receipt)

            prev_obs_hash = None
            if isinstance(prev_observation_report, dict):
                # Carry-forward previous observation so settlement can compute J(t-1)
                # over objective metrics that are not carried in metric_series.
                _, prev_observation_report, prev_obs_hash = _write_payload(
                    state_root / "observations",
                    "omega_observation_report_v1.json",
                    prev_observation_report,
                )

            settlement_receipt, market_state_after = settle_and_advance_market_state(
                tick_u64=tick_u64,
                config_hash=bid_market_cfg_hash,
                registry_hash=registry_hash,
                cfg=bid_market_cfg,
                registry=registry,
                objectives=objectives,
                prev_market_state=prev_market_state,
                prev_market_state_hash=prev_market_state_hash,
                prev_selection_receipt=prev_selection_receipt,
                prev_selection_hash=prev_selection_hash,
                prev_observation_report=prev_observation_report if isinstance(prev_observation_report, dict) else None,
                prev_observation_hash=prev_obs_hash,
                cur_observation_report=observation_report,
                cur_observation_hash=observation_hash,
            )
            _, settlement_receipt, bid_settlement_receipt_hash = write_bid_settlement_receipt(
                state_root / "market" / "settlement",
                settlement_receipt,
            )
            _, market_state_after, bid_market_state_hash = write_bid_market_state(
                state_root / "market" / "state",
                market_state_after,
            )
            if str(settlement_receipt.get("market_state_after_hash")) != str(bid_market_state_hash):
                fail("NONDETERMINISTIC")

            market_state_map = {
                str(row.get("campaign_id")): row
                for row in (market_state_after.get("campaign_states") or [])
                if isinstance(row, dict) and str(row.get("campaign_id", "")).strip()
            }
            caps = registry.get("capabilities")
            if not isinstance(caps, list):
                fail("SCHEMA_FAIL")
            bids_by_campaign: dict[str, dict[str, Any]] = {}
            bid_hash_by_campaign: dict[str, str] = {}
            for cap in sorted([row for row in caps if isinstance(row, dict)], key=lambda r: str(r.get("campaign_id"))):
                campaign_id = str(cap.get("campaign_id", "")).strip()
                if not campaign_id or not bool(cap.get("enabled", False)):
                    continue
                st = market_state_map.get(campaign_id)
                if st is None or bool(st.get("disabled_b", False)):
                    continue
                roi_q32, conf_q32, horizon_u64 = resolve_bidder_params(bid_market_cfg, campaign_id)
                cost_q32 = int(((cap.get("budget_cost_hint_q32") or {}).get("q", 0)))
                cost_q32 = max(1, int(cost_q32))
                bid = build_bid_v1(
                    tick_u64=tick_u64,
                    campaign_id=campaign_id,
                    capability_id=str(cap.get("capability_id", "")).strip(),
                    observation_report_hash=observation_hash,
                    market_state_hash=str(bid_market_state_hash),
                    config_hash=bid_market_cfg_hash,
                    registry_hash=registry_hash,
                    roi_q32=roi_q32,
                    confidence_q32=conf_q32,
                    horizon_ticks_u64=horizon_u64,
                    predicted_cost_q32=cost_q32,
                )
                _, bid, bid_hash = write_bid_v1(state_root / "market" / "bids", bid)
                bids_by_campaign[campaign_id] = bid
                bid_hash_by_campaign[campaign_id] = bid_hash

            bid_set = build_bid_set_v1(
                tick_u64=tick_u64,
                observation_report_hash=observation_hash,
                market_state_hash=str(bid_market_state_hash),
                config_hash=bid_market_cfg_hash,
                registry_hash=registry_hash,
                bids_by_campaign=bid_hash_by_campaign,
            )
            _, bid_set, bid_set_hash = write_bid_set_v1(state_root / "market" / "bid_sets", bid_set)
            bid_selection = select_winner(
                tick_u64=tick_u64,
                observation_report_hash=observation_hash,
                market_state=market_state_after,
                market_state_hash=str(bid_market_state_hash),
                config_hash=bid_market_cfg_hash,
                registry_hash=registry_hash,
                bid_set_hash=bid_set_hash,
                bids=bids_by_campaign,
                prev_state=prev_state,
            )
            _, bid_selection, bid_selection_receipt_hash = write_bid_selection_receipt(
                state_root / "market" / "selection",
                bid_selection,
            )
            decision_plan = build_decision_plan_from_selection(
                tick_u64=tick_u64,
                observation_report_hash=observation_hash,
                issue_bundle_hash=issue_hash,
                policy_hash=policy_hash,
                registry_hash=registry_hash,
                budgets_hash=budgets_hash,
                registry=registry,
                selection_receipt=bid_selection,
            )
            _mark("decide", decide_start_ns)
            _, decision_plan, decision_hash = _write_payload(
                state_root / "decisions",
                "omega_decision_plan_v1.json",
                decision_plan,
            )

        run_seed_override_raw = str(os.environ.get("OMEGA_RUN_SEED_U64", "")).strip()
        if run_seed_override_raw:
            run_seed_u64 = int(run_seed_override_raw)
        else:
            prev_state_id = str(prev_state.get("state_id", "")).strip()
            if not prev_state_id:
                fail("SCHEMA_FAIL")
            dispatch_campaign_id = str(decision_plan.get("campaign_id", "")).strip()
            dispatch_target_relpath = _resolve_campaign_target_relpath(
                campaign_id=dispatch_campaign_id,
                registry=registry,
            )
            run_seed_u64 = _derive_dispatch_seed_u64(
                prev_state_id=prev_state_id,
                tick_u64=tick_u64,
                campaign_id=dispatch_campaign_id,
                target_relpath=dispatch_target_relpath,
            )

        dispatch_receipt = None
        dispatch_hash = None
        dispatch_ctx = None
        subverifier_receipt = None
        subverifier_hash = None
        promotion_receipt = None
        promotion_hash = None
        activation_receipt = None
        activation_hash = None
        rollback_receipt = None
        rollback_hash = None
        axis_gate_failure = None
        sip_ingestion_evidence = {
            "knowledge_hash": None,
            "refutation_hash": None,
            "manifest_hash": None,
            "receipt_hash": None,
        }

        safe_halt = decision_plan.get("action_kind") == "SAFE_HALT"

        if str(decision_plan.get("action_kind")) in {"RUN_CAMPAIGN", "RUN_GOAL_TASK"}:
            dispatch_start_ns = time.monotonic_ns()
            dispatch_receipt, dispatch_hash, dispatch_ctx = dispatch_campaign(
                tick_u64=tick_u64,
                decision_plan=decision_plan,
                registry=registry,
                state_root=state_root,
                run_seed_u64=run_seed_u64,
                runaway_cfg=runaway_cfg,
            )
            _mark("dispatch_campaign", dispatch_start_ns)
            subverifier_start_ns = time.monotonic_ns()
            if dispatch_ctx is None:
                subverifier_receipt, subverifier_hash = run_subverifier_fn(
                    tick_u64=tick_u64,
                    dispatch_ctx=dispatch_ctx,
                )
                _mark("run_subverifier", subverifier_start_ns)
                promotion_start_ns = time.monotonic_ns()
                promotion_receipt, promotion_hash = run_promotion_fn(
                    tick_u64=tick_u64,
                    dispatch_ctx=dispatch_ctx,
                    subverifier_receipt=subverifier_receipt,
                    allowlists=allowlists,
                )
                _mark("run_promotion", promotion_start_ns)
            else:
                if not isinstance(dispatch_ctx, dict):
                    fail("SCHEMA_FAIL")
                subrun_root_raw = dispatch_ctx.get("subrun_root_abs")
                if not isinstance(subrun_root_raw, (str, Path)):
                    fail("SCHEMA_FAIL")
                subrun_root_abs = Path(subrun_root_raw).resolve()
                with _chdir(subrun_root_abs):
                    subverifier_receipt, subverifier_hash = run_subverifier_fn(
                        tick_u64=tick_u64,
                        dispatch_ctx=dispatch_ctx,
                    )
                    _mark("run_subverifier", subverifier_start_ns)
                    promotion_start_ns = time.monotonic_ns()
                    promotion_receipt, promotion_hash = run_promotion_fn(
                        tick_u64=tick_u64,
                        dispatch_ctx=dispatch_ctx,
                        subverifier_receipt=subverifier_receipt,
                        allowlists=allowlists,
                    )
                    _mark("run_promotion", promotion_start_ns)
            promotion_status_raw = str((promotion_receipt or {}).get("result", {}).get("status", "")).strip()
            if promotion_status_raw == "PROMOTED":
                activation_start_ns = time.monotonic_ns()
                (
                    activation_receipt,
                    activation_hash,
                    rollback_receipt,
                    rollback_hash,
                    active_manifest_after,
                ) = run_activation_fn(
                    tick_u64=tick_u64,
                    dispatch_ctx=dispatch_ctx,
                    promotion_receipt=promotion_receipt,
                    healthcheck_suitepack=healthcheck_suite,
                    healthcheck_suite_hash=healthcheck_suite_hash,
                    active_manifest_hash_before=active_manifest_before,
                )
                _mark("run_activation", activation_start_ns)
            else:
                active_manifest_after = active_manifest_before
            axis_gate_failure = _load_axis_gate_failure(dispatch_ctx)
            if _axis_gate_applies_safe_halt(axis_gate_failure):
                safe_halt = True

            if subverifier_receipt is not None and ((subverifier_receipt.get("result") or {}).get("status") != "VALID"):
                safe_halt = True
            if promotion_receipt is not None and ((promotion_receipt.get("result") or {}).get("reason_code") == "FORBIDDEN_PATH"):
                safe_halt = True
        else:
            active_manifest_after = active_manifest_before

        budget_remaining = dict(prev_state.get("budget_remaining") or {})
        cooldowns = dict(prev_state.get("cooldowns") or {})

        if str(decision_plan.get("action_kind")) in {"RUN_CAMPAIGN", "RUN_GOAL_TASK"}:
            campaign_id = str((dispatch_receipt or {}).get("campaign_id") or decision_plan.get("campaign_id"))
            cap = resolve_campaign(registry, campaign_id)
            cost_q = int(((cap.get("budget_cost_hint_q32") or {}).get("q", 0)))
            budget_remaining = debit_budget(budget_remaining, cost_q32=cost_q, disk_bytes=0)
            cooldowns[campaign_id] = {
                "next_tick_allowed_u64": int(tick_u64) + int(cap.get("cooldown_ticks_u64", 0)),
            }

        activation_success = bool((activation_receipt or {}).get("activation_success", False))
        activation_reasons_raw = (activation_receipt or {}).get("reasons")
        activation_reasons = []
        if isinstance(activation_reasons_raw, list):
            activation_reasons = [str(row).strip() for row in activation_reasons_raw if str(row).strip()]
        activation_meta_verdict = _activation_meta_verdict(dispatch_ctx)
        manifest_changed = bool(
            (activation_receipt or {}).get("before_active_manifest_hash")
            != (activation_receipt or {}).get("after_active_manifest_hash")
        )
        subverifier_status = str((subverifier_receipt or {}).get("result", {}).get("status", ""))
        subverifier_invalid_stall = (
            dispatch_receipt is not None
            and subverifier_status == "INVALID"
            and not safe_halt
        )
        promoted_and_activated = (
            not safe_halt
            and str((promotion_receipt or {}).get("result", {}).get("status")) == "PROMOTED"
            and activation_success
            and manifest_changed
        )
        promoted_families: list[str] = []
        if str((promotion_receipt or {}).get("result", {}).get("status")) == "PROMOTED":
            promoted_families = _touched_families_from_promotion(
                state_root=state_root,
                promotion_receipt=promotion_receipt,
                capability_id=str(decision_plan.get("capability_id", "")).strip() or None,
            )
        sip_ingestion_evidence = _import_sip_ingestion_artifacts(
            dispatch_ctx=dispatch_ctx,
            state_root=state_root,
        )
        subverifier_reason_code: str | None = None
        reason_code_raw = (subverifier_receipt or {}).get("result", {}).get("reason_code")
        if reason_code_raw is not None:
            value = str(reason_code_raw).strip()
            if value:
                subverifier_reason_code = value

        goals = dict(prev_state.get("goals") or {})
        if str(decision_plan.get("action_kind")) == "RUN_GOAL_TASK":
            goal_id = str(decision_plan.get("goal_id", "")).strip()
            if goal_id:
                goal_row = dict(goals.get(goal_id) or {"status": "PENDING", "last_tick_u64": 0})
                already_active = (
                    str((promotion_receipt or {}).get("result", {}).get("status")) == "SKIPPED"
                    and str((promotion_receipt or {}).get("result", {}).get("reason_code")) == "ALREADY_ACTIVE"
                )
                if (activation_success and manifest_changed) or already_active:
                    goal_row = {"status": "DONE", "last_tick_u64": int(tick_u64)}
                elif safe_halt:
                    goal_row = {"status": "FAILED", "last_tick_u64": int(tick_u64)}
                goals[goal_id] = goal_row

        action_kind = "SAFE_HALT" if safe_halt else str(decision_plan.get("action_kind"))
        summary_code = "SAFE_HALT" if safe_halt else ("OK" if action_kind != "NOOP" else "NO_MATCH")

        state_payload = next_state(
            prev_state,
            tick_u64=tick_u64,
            active_manifest_hash=active_manifest_after,
            budget_remaining=budget_remaining,
            cooldowns=cooldowns,
            action_summary={
                "tick_u64": int(tick_u64),
                "action_kind": action_kind,
                "summary_code": summary_code,
            },
            goal_queue_hash=goal_queue_hash,
            goals=goals,
        )
        _, state_payload, state_hash = write_state(state_root / "state", state_payload)

        runaway_payload = None
        if runaway_enabled(runaway_cfg):
            if not isinstance(prev_runaway_state, dict):
                fail("SCHEMA_FAIL")
            runaway_payload = advance_runaway_state(
                prev_state=prev_runaway_state,
                observation_report=observation_report,
                decision_plan=decision_plan,
                runaway_cfg=runaway_cfg,
                objectives=objectives,
                tick_u64=tick_u64,
                promoted_and_activated=promoted_and_activated,
                subverifier_invalid_stall=subverifier_invalid_stall,
            )
            _, runaway_payload, _ = write_runaway_state(state_root / "runaway", runaway_payload)

        if (
            policy_market_selection_hash is not None
            and isinstance(policy_market_selection_payload, dict)
            and isinstance(inputs_descriptor_hash, str)
        ):
            winner_hash = str(policy_market_selection_payload.get("winner_proposal_hash", "")).strip()
            winner_proposal = policy_market_proposals_by_hash.get(winner_hash)
            if not isinstance(winner_proposal, dict):
                fail("MISSING_STATE_INPUT")
            ranking_rows = policy_market_selection_payload.get("ranking")
            if not isinstance(ranking_rows, list):
                fail("SCHEMA_FAIL")
            expected_j_by_proposal: dict[str, int] = {}
            for row in ranking_rows:
                if not isinstance(row, dict):
                    fail("SCHEMA_FAIL")
                expected_j_by_proposal[str(row.get("proposal_hash", ""))] = int(row.get("expected_J_new_q32", 0))
            loser_hashes = sorted(
                [row for row in policy_market_proposals_by_hash.keys() if str(row) != str(winner_hash)]
            )
            realized_delta_j_q32 = _compute_realized_delta_j_q32(
                prev_observation_report=prev_observation_report,
                observation_report=observation_report,
                j_profile_payload=policy_market_j_profile_payload,
            )
            target_cfg = {}
            if isinstance(policy_market_selection_policy_payload, dict):
                row = policy_market_selection_policy_payload.get("counterfactual_target")
                if isinstance(row, dict):
                    target_cfg = row
            temperature_q32 = max(1, int(target_cfg.get("temperature_q32", 1 << 16)))
            margin_q32 = int(target_cfg.get("margin_q32", 0))
            counterfactual_payload = {
                "schema_version": "counterfactual_trace_example_v1",
                "inputs_descriptor_hash": inputs_descriptor_hash,
                "winner": {
                    "proposal_hash": winner_hash,
                    "branch_id": str(winner_proposal.get("branch_id", "")),
                    "decision_plan_hash": str(winner_proposal.get("decision_plan_hash", "")),
                    "expected_J_new_q32": int(expected_j_by_proposal.get(winner_hash, 0)),
                    "realized_delta_J_q32": int(realized_delta_j_q32),
                    "outcome_code": _outcome_code_from_tick(
                        promotion_receipt=promotion_receipt,
                        safe_halt=safe_halt,
                    ),
                },
                "losers": [
                    {
                        "proposal_hash": loser_hash,
                        "branch_id": str(policy_market_proposals_by_hash[loser_hash].get("branch_id", "")),
                        "decision_plan_hash": str(policy_market_proposals_by_hash[loser_hash].get("decision_plan_hash", "")),
                        "expected_J_new_q32": int(expected_j_by_proposal.get(loser_hash, 0)),
                    }
                    for loser_hash in loser_hashes
                ],
                "training_target": {
                    "kind": "PREFERENCE_Q32",
                    "temperature_q32": int(temperature_q32),
                    "margin_q32": int(margin_q32),
                },
            }
            _, counterfactual_payload, counterfactual_trace_example_hash = _write_payload(
                state_root / "policy" / "counterfactual",
                "counterfactual_trace_example_v1.json",
                counterfactual_payload,
            )

        policy_vm_stark_proof_enabled = bool(pack.get("policy_vm_stark_proof_enable_b", False))
        if policy_vm_stark_proof_enabled:
            if not isinstance(policy_vm_trace_payload_for_proof, dict):
                fail("MISSING_STATE_INPUT")
            if not isinstance(policy_vm_proof_program_id, str) or not policy_vm_proof_program_id:
                fail("MISSING_STATE_INPUT")
            if not isinstance(decision_plan, dict):
                fail("MISSING_STATE_INPUT")
            air_profile_rel = str(pack.get("policy_vm_air_profile_rel", "")).strip()
            air_profile_id = str(pack.get("policy_vm_air_profile_id", "")).strip()
            if not air_profile_rel or not air_profile_id:
                fail("MISSING_STATE_INPUT")
            air_profile_path = config_dir / air_profile_rel
            if not air_profile_path.exists() or not air_profile_path.is_file():
                fail("MISSING_STATE_INPUT")
            air_profile_payload = load_canon_dict(air_profile_path)
            if str(air_profile_payload.get("schema_version", "")).strip() != "policy_vm_air_profile_v1":
                fail("SCHEMA_FAIL")
            profile_kind = str(air_profile_payload.get("profile_kind", "")).strip().upper()
            if profile_kind not in {"POLICY_VM_STARK_MVP_V1", "POLICY_VM_AIR_PROFILE_96_V1", "POLICY_VM_AIR_PROFILE_128_V1"}:
                fail("SCHEMA_FAIL")
            observed_air_profile_id = canon_hash_obj(
                {k: v for k, v in air_profile_payload.items() if k != "air_profile_id"}
            )
            if str(air_profile_payload.get("air_profile_id", "")) != observed_air_profile_id:
                fail("PIN_HASH_MISMATCH")
            if observed_air_profile_id != ensure_sha256(air_profile_id, reason="PIN_HASH_MISMATCH"):
                fail("PIN_HASH_MISMATCH")
            policy_vm_proof_profile_id = observed_air_profile_id
            backend_contract_payload, _ = _load_pinned_json_payload(
                config_dir=config_dir,
                pack=pack,
                rel_key="policy_vm_winterfell_backend_contract_rel",
                id_key="policy_vm_winterfell_backend_contract_id",
                payload_id_field="backend_contract_id",
                missing_reason="MISSING_STATE_INPUT",
            )
            if (
                str(backend_contract_payload.get("schema_version", "")).strip()
                != "policy_vm_winterfell_backend_contract_v1"
            ):
                fail("SCHEMA_FAIL")
            try:
                winterfell_bindings = resolve_profile_backend_contract_bindings(
                    profile_payload=air_profile_payload,
                    backend_contract_payload=backend_contract_payload,
                    reason="SCHEMA_FAIL",
                )
            except ValueError:
                fail("SCHEMA_FAIL")
            proof_options_hash = ensure_sha256(
                winterfell_bindings.get("proof_options_hash"),
                reason="SCHEMA_FAIL",
            )
            policy_vm_proof_options_hash = proof_options_hash

            supported_opcodes_raw = air_profile_payload.get("supported_opcodes")
            if not isinstance(supported_opcodes_raw, list) or not supported_opcodes_raw:
                fail("SCHEMA_FAIL")
            supported_opcodes = sorted({str(row).strip().upper() for row in supported_opcodes_raw if str(row).strip()})
            if not supported_opcodes:
                fail("SCHEMA_FAIL")
            required_stark_ops = {"PUSH_CONST", "CMP_Q32", "CMP_U64", "JZ", "JMP", "SET_PLAN_FIELD", "EMIT_PLAN", "NOP"}
            if not required_stark_ops.issubset(set(supported_opcodes)):
                fail("SCHEMA_FAIL")

            action_kind_enum_payload, _ = _load_pinned_json_payload(
                config_dir=config_dir,
                pack=pack,
                rel_key="policy_vm_action_kind_enum_rel",
                id_key="policy_vm_action_kind_enum_id",
                payload_id_field="action_kind_enum_id",
                missing_reason="MISSING_STATE_INPUT",
            )
            validate_schema_v19(action_kind_enum_payload, "action_kind_enum_v1")
            candidate_campaign_ids_payload, _ = _load_pinned_json_payload(
                config_dir=config_dir,
                pack=pack,
                rel_key="policy_vm_candidate_campaign_ids_list_rel",
                id_key="policy_vm_candidate_campaign_ids_list_id",
                payload_id_field="candidate_campaign_ids_list_id",
                missing_reason="MISSING_STATE_INPUT",
            )
            validate_schema_v19(candidate_campaign_ids_payload, "candidate_campaign_ids_list_v1")

            if str(air_profile_payload.get("action_kind_enum_hash", "")) != str(pack.get("policy_vm_action_kind_enum_id", "")):
                fail("PIN_HASH_MISMATCH")
            if str(air_profile_payload.get("candidate_campaign_ids_list_hash", "")) != str(
                pack.get("policy_vm_candidate_campaign_ids_list_id", "")
            ):
                fail("PIN_HASH_MISMATCH")

            policy_vm_proof_runtime_status = "FAILED"
            policy_vm_proof_runtime_reason_code = "PROVER_FAILURE"
            try:
                proof_out = prove_policy_vm_stark(
                    trace_payload=policy_vm_trace_payload_for_proof,
                    decision_payload=decision_plan,
                    inputs_descriptor_hash=ensure_sha256(inputs_descriptor_hash, reason="SCHEMA_FAIL"),
                    policy_program_id=policy_vm_proof_program_id,
                    opcode_table_id=ensure_sha256(opcode_table_hash, reason="SCHEMA_FAIL"),
                    merged_hint_state_id=merged_hint_state_hash_for_proof,
                    air_profile_payload=air_profile_payload,
                    backend_contract_payload=backend_contract_payload,
                    action_kind_enum_payload=action_kind_enum_payload,
                    candidate_campaign_ids_payload=candidate_campaign_ids_payload,
                )
            except RuntimeError:
                proof_out = None

            if isinstance(proof_out, dict):
                statement = proof_out.get("statement")
                public_outputs = proof_out.get("public_outputs")
                proof_options_hash_observed = ensure_sha256(
                    proof_out.get("proof_options_hash"),
                    reason="NONDETERMINISTIC",
                )
                if proof_options_hash_observed != proof_options_hash:
                    fail("NONDETERMINISTIC")
                policy_vm_proof_options_hash = proof_options_hash_observed
                if not isinstance(statement, dict) or not isinstance(public_outputs, dict):
                    fail("NONDETERMINISTIC")
                if ensure_sha256(statement.get("decision_plan_hash"), reason="NONDETERMINISTIC") != decision_hash:
                    fail("NONDETERMINISTIC")
                if ensure_sha256(statement.get("budget_outcome_hash"), reason="NONDETERMINISTIC") != ensure_sha256(
                    public_outputs.get("budget_outcome_hash"),
                    reason="NONDETERMINISTIC",
                ):
                    fail("NONDETERMINISTIC")

                proof_bytes = proof_out.get("proof_bytes")
                if not isinstance(proof_bytes, (bytes, bytearray)) or not proof_bytes:
                    fail("NONDETERMINISTIC")
                proof_bytes = bytes(proof_bytes)
                proof_bytes_hash = "sha256:" + hashlib.sha256(proof_bytes).hexdigest()
                proof_bytes_hex = proof_bytes_hash.split(":", 1)[1]
                proof_rel = f"policy/proofs/sha256_{proof_bytes_hex}.policy_vm_stark_proof_v1.bin"
                proof_path = state_root / "policy" / "proofs" / f"sha256_{proof_bytes_hex}.policy_vm_stark_proof_v1.bin"
                proof_path.parent.mkdir(parents=True, exist_ok=True)
                proof_path.write_bytes(proof_bytes)
                if "sha256:" + hashlib.sha256(proof_path.read_bytes()).hexdigest() != proof_bytes_hash:
                    fail("NONDETERMINISTIC")
                proof_payload = {
                    "schema_version": "policy_vm_stark_proof_v1",
                    "proof_id": "sha256:" + ("0" * 64),
                    "inputs_descriptor_hash": inputs_descriptor_hash,
                    "policy_program_id": policy_vm_proof_program_id,
                    "opcode_table_id": opcode_table_hash,
                    "merged_hint_state_id": merged_hint_state_hash_for_proof,
                    "air_profile_id": observed_air_profile_id,
                    "proof_backend_id": "WINTERFELL_STARK_FRI_V1",
                    "proof_options_hash": proof_options_hash_observed,
                    "public_outputs": dict(public_outputs),
                    "decision_plan_hash": decision_hash,
                    "steps_executed_u64": int(statement.get("steps_executed_u64", 0)),
                    "budget_outcome_hash": str(statement.get("budget_outcome_hash", "")),
                    "proof_representation_kind": "STARK_FRI_PROOF_V1",
                    "proof_bytes_hash": proof_bytes_hash,
                    "proof_bytes_rel": proof_rel,
                    "winterfell_backend_id": winterfell_bindings.get("winterfell_backend_id"),
                    "winterfell_backend_version": winterfell_bindings.get("winterfell_backend_version"),
                    "winterfell_field_id": winterfell_bindings.get("winterfell_field_id"),
                    "winterfell_extension_id": winterfell_bindings.get("winterfell_extension_id"),
                    "winterfell_merkle_hasher_id": winterfell_bindings.get("winterfell_merkle_hasher_id"),
                    "winterfell_random_coin_hasher_id": winterfell_bindings.get("winterfell_random_coin_hasher_id"),
                }
                _, proof_payload, policy_vm_stark_proof_hash = _write_payload(
                    state_root / "policy" / "proofs",
                    "policy_vm_stark_proof_v1.json",
                    proof_payload,
                    id_field="proof_id",
                )
                policy_vm_proof_runtime_status = "EMITTED"
                policy_vm_proof_runtime_reason_code = "OK"

        ledger_path = state_root / "ledger" / "omega_ledger_v1.jsonl"
        prev_event_id: str | None = None
        artifact_hashes: list[str] = []

        def _emit(event_type: str, artifact_hash: str) -> None:
            nonlocal prev_event_id
            emit_start_ns = time.monotonic_ns()
            row = append_event(
                ledger_path,
                tick_u64=tick_u64,
                event_type=event_type,
                artifact_hash=artifact_hash,
                prev_event_id=prev_event_id,
            )
            _mark("ledger_writes", emit_start_ns)
            prev_event_id = str(row["event_id"])
            artifact_hashes.append(artifact_hash)

        _emit("STATE", state_hash)
        _emit("OBSERVATION", observation_hash)
        _emit("ISSUE", issue_hash)
        if market_enabled:
            if bid_settlement_receipt_hash is None or bid_market_state_hash is None or bid_set_hash is None or bid_selection_receipt_hash is None:
                fail("MISSING_STATE_INPUT")
            _emit("BID_SETTLEMENT", bid_settlement_receipt_hash)
            _emit("BID_MARKET_STATE", bid_market_state_hash)
            _emit("BID_SET", bid_set_hash)
            _emit("BID_SELECTION", bid_selection_receipt_hash)
        if inputs_descriptor_hash is not None:
            _emit("INPUTS_DESCRIPTOR", inputs_descriptor_hash)
        if isinstance(opcode_table_hash, str):
            _emit("OPCODE_TABLE_UPDATE", opcode_table_hash)
        if isinstance(opcode_table, dict):
            opcode_entries = opcode_table.get("entries")
            if isinstance(opcode_entries, list):
                for entry in opcode_entries:
                    if not isinstance(entry, dict):
                        continue
                    kind = str(entry.get("kind", "")).strip().upper()
                    if kind == "NATIVE" and bool(entry.get("active_b", False)):
                        impl = entry.get("impl")
                        if isinstance(impl, dict):
                            binary_sha = str(impl.get("binary_sha256", "")).strip()
                            if binary_sha.startswith("sha256:") and len(binary_sha) == 71:
                                _emit("OPCODE_NATIVE_ACTIVATION", binary_sha)
                    if (not bool(entry.get("active_b", True))) and int(entry.get("deprecated_tick_u64", 0)) == int(tick_u64):
                        _emit("OPCODE_DEPRECATION", canon_hash_obj(entry))
        if policy_vm_trace_hash is not None:
            _emit("POLICY_VM_TRACE", policy_vm_trace_hash)
        if policy_vm_stark_proof_hash is not None:
            _emit("POLICY_VM_PROOF", policy_vm_stark_proof_hash)
        elif policy_vm_stark_proof_enabled:
            _emit("POLICY_VM_PROOF_FALLBACK", decision_hash)
        if policy_market_selection_hash is not None:
            _emit("POLICY_MARKET_SELECTION", policy_market_selection_hash)
        if counterfactual_trace_example_hash is not None:
            _emit("COUNTERFACTUAL_TRACE_EXAMPLE", counterfactual_trace_example_hash)
        _emit("DECISION", decision_hash)
        if dispatch_hash is not None:
            _emit("DISPATCH", dispatch_hash)
        if subverifier_hash is not None:
            _emit("SUBVERIFIER", subverifier_hash)
        if promotion_hash is not None:
            _emit("PROMOTION", promotion_hash)
        if activation_hash is not None:
            _emit("ACTIVATION", activation_hash)
        if rollback_hash is not None:
            _emit("ROLLBACK", rollback_hash)
        sip_ingestion_hash = str((sip_ingestion_evidence or {}).get("knowledge_hash") or "").strip()
        if sip_ingestion_hash:
            _emit("SIP_INGESTION_L0", sip_ingestion_hash)

        # Deterministic evidence that hotpaths actually exercised the runtime
        # router (and, when active, the native backend). We emit this into the
        # trace chain so it is covered by the tick snapshot hash.
        try:
            from orchestrator.native.native_router_v1 import drain_runtime_stats

            native_ops = drain_runtime_stats()
        except Exception:
            native_ops = []
        native_ops_rows = [dict(row) for row in native_ops if isinstance(row, dict)]
        native_ops_rows.append(
            {
                "op_id": f"phase3_coord_goal_queue_fastpath_v1:{goal_queue_fastpath_outcome}",
                "calls_u64": 1,
                "native_returned_u64": 0,
                "py_returned_u64": 1,
                "bytes_in_u64": 0,
                "bytes_out_u64": 0,
                "active_binary_sha256": "",
                "native_load_fail_u64": 0,
                "native_invoke_fail_u64": 0,
                "shadow_mismatch_u64": 0,
            }
        )
        stats_payload = {
            "schema_version": "omega_native_runtime_stats_v1",
            "stats_id": "sha256:" + ("0" * 64),
            "tick_u64": int(tick_u64),
            "ops": native_ops_rows,
        }
        validate_schema(stats_payload, "omega_native_runtime_stats_v1")
        try:
            from cdel.v1_7r.canon import native_canon_disabled
        except Exception:
            native_canon_disabled = None
        if native_canon_disabled is None:
            _, _stats_obj, stats_hash = _write_payload(
                state_root / "ledger" / "native",
                "omega_native_runtime_stats_v1.json",
                stats_payload,
                id_field="stats_id",
            )
        else:
            with native_canon_disabled():
                _, _stats_obj, stats_hash = _write_payload(
                    state_root / "ledger" / "native",
                    "omega_native_runtime_stats_v1.json",
                    stats_payload,
                    id_field="stats_id",
                )
        _emit("NATIVE_RUNTIME_STATS", stats_hash)

        prev_state_hash = canon_hash_obj(prev_state)
        h0 = compute_h0(
            run_seed_u64=run_seed_u64,
            pack_hash=pack_hash,
            policy_hash=policy_hash,
            registry_hash=registry_hash,
            objectives_hash=objectives_hash,
            tick_u64=tick_u64,
            prev_state_hash=prev_state_hash,
        )
        trace_start_ns = time.monotonic_ns()
        trace_payload = build_trace_chain(h0=h0, artifact_hashes=artifact_hashes)
        _, trace_payload, trace_hash = write_trace_chain(state_root / "ledger", trace_payload)
        _mark("trace_write", trace_start_ns)

        snapshot_start_ns = time.monotonic_ns()
        snapshot = build_snapshot(
            {
                "tick_u64": int(tick_u64),
                "state_hash": state_hash,
                "observation_report_hash": observation_hash,
                "issue_bundle_hash": issue_hash,
                "decision_plan_hash": decision_hash,
                "dispatch_receipt_hash": dispatch_hash,
                "subverifier_receipt_hash": subverifier_hash,
                "promotion_receipt_hash": promotion_hash,
                "activation_receipt_hash": activation_hash,
                "rollback_receipt_hash": rollback_hash,
                "trace_hash_chain_hash": trace_hash,
                "execution_mode": execution_mode,
                "budget_remaining": budget_remaining,
                "cooldowns": cooldowns,
                "goal_queue_hash": goal_queue_hash,
                "bid_market_state_hash": bid_market_state_hash if market_enabled else None,
                "bid_settlement_receipt_hash": bid_settlement_receipt_hash if market_enabled else None,
                "bid_set_hash": bid_set_hash if market_enabled else None,
                "bid_selection_receipt_hash": bid_selection_receipt_hash if market_enabled else None,
                "inputs_descriptor_hash": inputs_descriptor_hash,
                "policy_vm_trace_hash": policy_vm_trace_hash,
                "policy_vm_stark_proof_hash": policy_vm_stark_proof_hash,
                "policy_vm_proof_runtime_status": policy_vm_proof_runtime_status,
                "policy_vm_proof_profile_id": policy_vm_proof_profile_id,
                "policy_vm_proof_options_hash": policy_vm_proof_options_hash,
                "policy_vm_proof_runtime_reason_code": policy_vm_proof_runtime_reason_code,
                "policy_market_selection_hash": policy_market_selection_hash,
                "policy_market_selection_commitment_hash": policy_market_selection_commitment_hash,
                "counterfactual_trace_example_hash": counterfactual_trace_example_hash,
            }
        )
        _, snapshot, snapshot_hash = write_snapshot(state_root / "snapshot", snapshot)
        _mark("snapshot_write", snapshot_start_ns)
        _emit("SNAPSHOT", snapshot_hash)

        if safe_halt:
            _emit("SAFE_HALT", snapshot_hash)

        tick_total_ns = _DETERMINISTIC_TICK_TOTAL_NS if deterministic_timing else (time.monotonic_ns() - tick_start_ns)
        timings_line = " ".join(
            [
                f"tick_u64={int(tick_u64)}",
                *(f"{stage}_ns={int(stage_timings_ns[stage])}" for stage in _TIMING_STAGES),
                f"total_ns={tick_total_ns}",
            ]
        )
        timings_path = state_root / "ledger" / "timings.log"
        with timings_path.open("a", encoding="utf-8") as timings_file:
            timings_file.write(timings_line + "\n")

        promotion_result = (promotion_receipt or {}).get("result")
        promotion_status = "N/A"
        promotion_reason_code = "N/A"
        if isinstance(promotion_result, dict):
            status_value = str(promotion_result.get("status", "")).strip()
            if status_value in {"PROMOTED", "REJECTED", "SKIPPED"}:
                promotion_status = status_value
            reason_value = str(promotion_result.get("reason_code", "")).strip()
            if reason_value:
                promotion_reason_code = reason_value
        axis_gate_reason_code = _axis_gate_promotion_reason_code(axis_gate_failure)
        if axis_gate_reason_code is not None:
            promotion_reason_code = axis_gate_reason_code

        perf_payload = build_tick_perf(
            tick_u64=tick_u64,
            action_kind=action_kind,
            total_ns=tick_total_ns,
            stage_ns={key: int(value) for key, value in stage_timings_ns.items()},
            promotion_status=promotion_status,
            activation_success=activation_success,
        )
        write_tick_perf(state_root / "perf", perf_payload)
        if int(tick_u64) % 10 == 0:
            hotspots_payload = build_hotspots(
                tick_u64=tick_u64,
                total_ns_u64=tick_total_ns,
                stage_ns={key: int(value) for key, value in stage_timings_ns.items()},
            )
            write_hotspots(state_root / "perf", hotspots_payload)

        subverifier_status_norm = subverifier_status if subverifier_status in {"VALID", "INVALID"} else "N/A"
        noop_reason = "N/A"
        if action_kind == "NOOP":
            noop_reason = classify_noop_reason(decision_plan.get("tie_break_path"))
        outcome_campaign_id = str((dispatch_receipt or {}).get("campaign_id") or decision_plan.get("campaign_id") or "").strip()

        tick_outcome = build_tick_outcome(
            tick_u64=tick_u64,
            action_kind=action_kind,
            campaign_id=(outcome_campaign_id or None),
            subverifier_status=subverifier_status_norm,
            promotion_status=promotion_status,
            promotion_reason_code=promotion_reason_code,
            activation_success=activation_success,
            activation_reasons=activation_reasons,
            activation_meta_verdict=activation_meta_verdict,
            manifest_changed=manifest_changed,
            safe_halt=safe_halt,
            noop_reason=noop_reason,
            execution_mode=execution_mode,
        )
        write_tick_outcome(state_root / "perf", tick_outcome)

        tick_stats_payload = build_tick_stats(
            tick_u64=tick_u64,
            tick_outcome=tick_outcome,
            previous_tick_stats=prev_tick_stats,
            promoted_families=promoted_families,
        )
        write_tick_stats(state_root / "perf", tick_stats_payload)

        episodic_payload = build_episodic_memory(
            tick_u64=tick_u64,
            previous_memory=prev_episodic_memory,
            episode={
                "tick_u64": int(tick_u64),
                "capability_id": str(decision_plan.get("capability_id", "")).strip(),
                "campaign_id": outcome_campaign_id,
                "goal_id_prefix": _goal_id_prefix(str(decision_plan.get("goal_id", "")).strip()),
                "outcome": _episodic_outcome(tick_outcome=tick_outcome),
                "reason_codes": _episodic_reason_codes(
                    subverifier_reason_code=subverifier_reason_code,
                    tick_outcome=tick_outcome,
                ),
                "context_hash": _episode_context_hash(
                    issue_bundle=issue_bundle,
                    observation_report=observation_report,
                ),
                "touched_families": promoted_families,
            },
        )
        write_episodic_memory(state_root / "perf", episodic_payload)

        scorecard_payload = build_run_scorecard(
            tick_u64=tick_u64,
            tick_perf=perf_payload,
            tick_outcome=tick_outcome,
            goal_queue=goal_queue,
            state_goals=dict(state_payload.get("goals") or {}),
            previous_scorecard=prev_run_scorecard,
        )
        write_run_scorecard(state_root / "perf", scorecard_payload)
        runaway_active, runaway_level_u64, runaway_reason = check_runaway_condition(
            observation_report=observation_report,
            runaway_cfg=runaway_cfg,
            runaway_state=runaway_payload,
        )

        return {
            "status": "SAFE_HALT" if safe_halt else "OK",
            "tick_u64": tick_u64,
            "decision_plan_hash": decision_hash,
            "trace_hash_chain_hash": trace_hash,
            "tick_snapshot_hash": snapshot_hash,
            "action_kind": decision_plan.get("action_kind"),
            "safe_halt": safe_halt,
            "runaway_state": "ACTIVE" if runaway_active else "INACTIVE",
            "runaway_level_u64": int(runaway_level_u64),
            "runaway_reason": str(runaway_reason),
            "sip_ingestion_artifact_hash": (sip_ingestion_evidence or {}).get("knowledge_hash"),
            "sip_ingestion_refutation_hash": (sip_ingestion_evidence or {}).get("refutation_hash"),
            "policy_vm_stark_proof_hash": policy_vm_stark_proof_hash,
            "policy_vm_proof_runtime_status": policy_vm_proof_runtime_status,
            "policy_vm_proof_profile_id": policy_vm_proof_profile_id,
            "policy_vm_proof_options_hash": policy_vm_proof_options_hash,
            "policy_vm_proof_runtime_reason_code": policy_vm_proof_runtime_reason_code,
            "policy_market_selection_hash": policy_market_selection_hash,
            "policy_market_selection_commitment_hash": policy_market_selection_commitment_hash,
            "counterfactual_trace_example_hash": counterfactual_trace_example_hash,
        }


__all__ = [
    "tick_once",
    "_load_axis_gate_failure",
    "_axis_gate_applies_safe_halt",
    "_axis_gate_promotion_reason_code",
]
