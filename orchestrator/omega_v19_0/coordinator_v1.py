"""Coordinator for RSI Omega daemon v19.0 tick execution."""

from __future__ import annotations

from contextlib import contextmanager
import os
import time
from pathlib import Path
from typing import Any, Iterator

from cdel.v18_0.omega_allowlists_v1 import load_allowlists
from cdel.v18_0.omega_budgets_v1 import debit_budget, load_budgets
from cdel.v18_0.omega_common_v1 import (
    canon_hash_obj,
    fail,
    load_canon_dict,
    validate_schema,
    write_hashed_json,
)
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


def _deterministic_timing_enabled() -> bool:
    raw = str(os.environ.get("OMEGA_V19_DETERMINISTIC_TIMING", "1")).strip().lower()
    return raw not in {"0", "false", "off", "no"}


def _write_payload(dir_path: Path, suffix: str, payload: dict[str, Any], id_field: str | None = None) -> tuple[Path, dict[str, Any], str]:
    return write_hashed_json(dir_path, suffix, payload, id_field=id_field)


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


def run_tick(
    *,
    campaign_pack: Path,
    out_dir: Path,
    tick_u64: int,
    prev_state_dir: Path | None = None,
) -> dict[str, Any]:
    run_root = out_dir.resolve()
    daemon_root = run_root / "daemon" / "rsi_omega_daemon_v19_0"
    config_dir = daemon_root / "config"
    state_root = daemon_root / "state"

    for rel in [
        "state",
        "runaway",
        "observations",
        "issues",
        "decisions",
        "dispatch",
        "ledger",
        "perf",
        "snapshot",
        "subruns",
    ]:
        (state_root / rel).mkdir(parents=True, exist_ok=True)

    lock_path = daemon_root / "LOCK"
    with acquire_lock(lock_path):
        deterministic_timing = _deterministic_timing_enabled()
        tick_start_ns = time.monotonic_ns()
        stage_timings_ns: dict[str, int] = {stage: 0 for stage in _TIMING_STAGES}

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

        active_manifest_before = read_meta_core_active_manifest_hash()
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

        goal_queue_effective = synthesize_goal_queue(
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

        run_seed_u64 = int(os.environ.get("OMEGA_RUN_SEED_U64", int(pack.get("seed_u64", 0))))

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
                subverifier_receipt, subverifier_hash = run_subverifier(
                    tick_u64=tick_u64,
                    dispatch_ctx=dispatch_ctx,
                )
                _mark("run_subverifier", subverifier_start_ns)
                promotion_start_ns = time.monotonic_ns()
                promotion_receipt, promotion_hash = run_promotion(
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
                    subverifier_receipt, subverifier_hash = run_subverifier(
                        tick_u64=tick_u64,
                        dispatch_ctx=dispatch_ctx,
                    )
                    _mark("run_subverifier", subverifier_start_ns)
                    promotion_start_ns = time.monotonic_ns()
                    promotion_receipt, promotion_hash = run_promotion(
                        tick_u64=tick_u64,
                        dispatch_ctx=dispatch_ctx,
                        subverifier_receipt=subverifier_receipt,
                        allowlists=allowlists,
                    )
                    _mark("run_promotion", promotion_start_ns)
            activation_start_ns = time.monotonic_ns()
            (
                activation_receipt,
                activation_hash,
                rollback_receipt,
                rollback_hash,
                active_manifest_after,
            ) = run_activation(
                tick_u64=tick_u64,
                dispatch_ctx=dispatch_ctx,
                promotion_receipt=promotion_receipt,
                healthcheck_suitepack=healthcheck_suite,
                healthcheck_suite_hash=healthcheck_suite_hash,
                active_manifest_hash_before=active_manifest_before,
            )
            _mark("run_activation", activation_start_ns)
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
                "budget_remaining": budget_remaining,
                "cooldowns": cooldowns,
                "goal_queue_hash": goal_queue_hash,
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
        }


__all__ = ["run_tick"]
