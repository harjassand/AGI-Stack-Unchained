"""Deterministic microkernel for RSI Omega daemon v19.0 tick execution."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
import re
import shutil
import sys
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
from cdel.v18_0.omega_budgets_v1 import debit_budget, has_budget, load_budgets
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
from cdel.v1_7r.canon import canon_bytes
from cdel.v19_0.common_v1 import validate_schema as validate_schema_v19
from cdel.v19_0.conservatism_v1 import evaluate_reject_conservatism
from cdel.v19_0.determinism_witness_v1 import evaluate_determinism_witness
from cdel.v19_0.epistemic.action_market_v1 import (
    build_action_bid_set,
    build_action_bids,
    build_action_market_inputs_manifest,
    build_default_action_market_profile,
    select_action_winner,
    settle_action_selection,
)
from cdel.v19_0.epistemic.usable_index_v1 import (
    append_usable_index_row,
    iter_usable_graphs,
    load_usable_capsule_ids,
)
from cdel.v19_0.policy_vm_stark_runner_v1 import prove_policy_vm_stark
from cdel.v19_0.shadow_airlock_v1 import evaluate_shadow_regime_proposal
from cdel.v19_0.world.merkle_v1 import compute_world_root
from cdel.v19_0.shadow_fs_guard_v1 import (
    build_integrity_report,
    default_shadow_protected_roots_profile,
    diff_file_maps,
    hash_protected_roots,
)
from cdel.v19_0.shadow_j_eval_v1 import (
    build_ccap_receipt_metric_index_for_state_root,
    evaluate_j_comparison,
)
from cdel.v19_0.shadow_invariance_v1 import (
    build_shadow_corpus_invariance_receipt,
)
from cdel.v19_0.shadow_corpus_v1 import load_shadow_corpus_entries
from cdel.v19_0.shadow_runner_v1 import run_shadow_tick
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
from .goal_synthesizer_v1 import (
    suppressed_capability_ids_from_episodic_memory,
    synthesize_goal_queue,
)
from .eval_cadence_v1 import build_eval_report, should_emit_eval
from .mission_goal_ingest_v1 import ingest_mission_goals
from orchestrator.omega_v18_0.io_v1 import freeze_pack_config, load_goal_queue, write_goal_queue_effective
from orchestrator.omega_v18_0.locks_v1 import acquire_lock
from orchestrator.omega_v18_0.observer_v1 import observe, read_meta_core_active_manifest_hash
from orchestrator.omega_bid_market_v2 import select_policy_proposal
from .policy_vm_v1 import run_policy_vm_v1
from .promoter_v1 import run_promotion, run_subverifier
from .orch_bandit.bandit_v1 import (
    BanditError as OrchBanditError,
    compute_context_key as orch_bandit_compute_context_key,
    compute_cost_norm_q32 as orch_bandit_compute_cost_norm_q32,
    select_capability_id as orch_bandit_select_capability_id,
    update_bandit_state as orch_bandit_update_bandit_state,
)
from orchestrator.native.runtime_stats_v1 import (
    RUNTIME_STATS_SOURCE_ID,
    WORK_UNITS_FORMULA_ID,
    derive_total_work_units,
    derive_work_units_from_row,
)

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
_Q32_ONE = 1 << 32
_EPISTEMIC_LOW_CONF_THRESHOLD_Q32 = _Q32_ONE // 2
_MAX_METRIC_SERIES_LEN_U64 = 64
_FAILURE_KEY_RE = re.compile(r"[^a-z0-9_]+")
_LANE_NAMES = {"BASELINE", "CANARY", "FRONTIER"}
_HEAVY_DECLARED_CLASSES = {"FRONTIER_HEAVY", "CANARY_HEAVY"}
_DECLARED_CLASSES = {"FRONTIER_HEAVY", "CANARY_HEAVY", "BASELINE_CORE", "MAINTENANCE"}
_ROUTING_SELECTOR_IDS = {"MARKET", "NON_MARKET", "SCAFFOLD_OVERRIDE", "HARD_LOCK_OVERRIDE"}
_EFFECT_CLASSES = {
    "EFFECT_HEAVY_OK",
    "EFFECT_HEAVY_NO_UTILITY",
    "EFFECT_BASELINE_CORE_OK",
    "EFFECT_MAINTENANCE_OK",
    "EFFECT_REJECTED",
}
_DEFAULT_DEBT_LIMIT_U64 = 3
_DEFAULT_MAX_TICKS_WITHOUT_FRONTIER_ATTEMPT_U64 = 40
_UTILITY_RECOVERY_WINDOW_SHORT_U64 = 50
_UTILITY_RECOVERY_WINDOW_LONG_U64 = 200
_BOOTSTRAP_SH1_FRONTIER_ATTEMPT_THRESHOLD_U64 = 5
_BOOTSTRAP_SH1_UTILITY_DROUGHT_TICK_U64 = 30
_BOOTSTRAP_SH1_REASON_FIRST_HEAVY = "BOOTSTRAP_HEAVY_FIRST_PROMOTION_SH1"
_BOOTSTRAP_SH1_REASON_UTILITY_DROUGHT = "BOOTSTRAP_HEAVY_UTILITY_DROUGHT_SH1"
_DEFAULT_ANTI_MONOPOLY_CONSECUTIVE_LIMIT_U64 = 50
_DEFAULT_ANTI_MONOPOLY_WINDOW_U64 = 50
_DEFAULT_ANTI_MONOPOLY_DIVERSITY_K_U64 = 3
_DEFAULT_ANTI_MONOPOLY_COOLDOWN_U64 = 50
_DEFAULT_ORCH_MLX_MODEL_ID = "mlx-community/Qwen2.5-Coder-14B-Instruct-4bit"
_SHA256_ZERO = "sha256:" + ("0" * 64)
_SH1_CAPABILITY_ID = "RSI_GE_SH1_OPTIMIZER"
_SH1_FRONTIER_DEBT_KEY = "frontier:rsi_ge_sh1_optimizer"
_SH1_CAMPAIGN_ID = "rsi_ge_symbiotic_optimizer_sh1_v0_1"
_BUILTIN_PROBE_SUITE_IDS = (
    "utility_probe_suite_default_v1",
    "utility_stress_probe_suite_default_v1",
)
_REPLAY_STATE_ROOT_REL = "replay_state"
_FORCED_HEAVY_ENV_KEY = "OMEGA_SH1_FORCED_HEAVY_B"
_FORCED_DEBT_KEY_ENV_KEY = "OMEGA_SH1_FORCED_DEBT_KEY"
_FORCED_WIRING_LOCUS_ENV_KEY = "OMEGA_SH1_WIRING_LOCUS_RELPATH"
_MILESTONE_FORCE_SH1_FRONTIER_ENV_KEY = "OMEGA_MILESTONE_FORCE_SH1_FRONTIER_B"
_MILESTONE_FORCE_SH1_FRONTIER_UNTIL_TICK_U64_ENV_KEY = "OMEGA_MILESTONE_FORCE_SH1_FRONTIER_UNTIL_TICK_U64"
_RETENTION_PRUNE_CCAP_EK_RUNS_ENV_KEY = "OMEGA_RETENTION_PRUNE_CCAP_EK_RUNS_B"
_LANE_RECEIPT_FINAL_NAME = "lane_receipt_final.long_run_lane_v1.json"
_FAILED_PATCH_BAN_ENV_KEY = "OMEGA_SH1_FAILED_PATCH_BAN_JSON"
_FAILED_SHAPE_BAN_ENV_KEY = "OMEGA_SH1_FAILED_SHAPE_BAN_JSON"
_LAST_FAILURE_HINT_ENV_KEY = "OMEGA_SH1_LAST_FAILURE_HINT_JSON"
_FORCED_WIRING_LOCUS_PRIMARY_RELPATH = "orchestrator/omega_v18_0/goal_synthesizer_v1.py"
_MAX_FAILED_PATCH_BAN_PER_KEY = 8
_MAX_FAILED_PATCH_BAN_KEYS = 128
_MAX_FAILED_SHAPE_BAN_PER_KEY = 8
_MAX_FAILED_SHAPE_BAN_KEYS = 128
_FAILED_PATCH_BAN_TTL_TICKS_U64 = 80
_FAILED_SHAPE_BAN_TTL_TICKS_U64 = 80
_FORCED_WIRING_LOCUS_FALLBACK_RELPATHS = (
    "orchestrator/omega_v19_0/goal_synthesizer_v1.py",
    "orchestrator/omega_v18_0/goal_synthesizer_v1.py",
    "orchestrator/omega_v18_0/decider_v1.py",
    "orchestrator/common/run_invoker_v1.py",
    "tools/omega/omega_overnight_runner_v1.py",
)
_HARD_TASK_METRIC_IDS: tuple[str, ...] = (
    "hard_task_code_correctness_q32",
    "hard_task_performance_q32",
    "hard_task_reasoning_q32",
    "hard_task_suite_score_q32",
)
_ORCH_PROMOTION_RESULT_KINDS = {
    "PROMOTED_COMMIT",
    "PROMOTED_EXT_QUEUED",
    "REJECTED",
}
_ORCH_TOXIC_REASON_PREFIXES = (
    "HOLDOUT_",
    "PHASE1_PUBLIC_ONLY_VIOLATION",
    "SANDBOX_",
)
_ORCH_TOXIC_REASON_EXACT = {
    "CCAP_ALLOWLIST_VIOLATION",
    "CCAP_PATCH_ALLOWLIST_VIOLATION",
    "BUDGET_EXHAUSTED",
}
_ORCH_REWARD_COMMIT_Q32 = _Q32_ONE
_ORCH_REWARD_EXT_Q32 = _Q32_ONE // 2
_ORCH_REWARD_TOXIC_Q32 = -(_Q32_ONE // 2)
_ORCH_REWARD_HEAVY_UTILITY_BONUS_Q32 = _Q32_ONE // 4
_ACTIVE_ORCH_BANDIT_STATE_POINTER = "ACTIVE_ORCH_BANDIT_STATE"


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


def _env_bool(name: str, *, default: bool = False) -> bool:
    raw = str(os.environ.get(name, "1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _env_u64(name: str, *, default: int, minimum: int = 0) -> int:
    raw = str(os.environ.get(name, str(int(default)))).strip()
    value = int(raw)
    return int(max(int(minimum), value))


def _resolve_orch_runtime_provenance() -> tuple[str, str]:
    backend = str(os.environ.get("ORCH_LLM_BACKEND", "mlx")).strip().lower() or "mlx"
    if backend == "mlx":
        model_id = str(os.environ.get("ORCH_MLX_MODEL", _DEFAULT_ORCH_MLX_MODEL_ID)).strip() or _DEFAULT_ORCH_MLX_MODEL_ID
        return backend, model_id
    model_id = str(os.environ.get("ORCH_MODEL_ID", "")).strip() or f"{backend}:default"
    return backend, model_id


def _premarathon_v63_enabled() -> bool:
    raw = str(os.environ.get("OMEGA_PREMARATHON_V63", "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}

def _phase3_mutation_signal_enabled() -> bool:
    # Phase 3 DoD evidence: allow emitting a stable, greppable log line from the
    # mutated coordinator path. Bench/structural runs force this off.
    return str(os.environ.get("OMEGA_PHASE3_MUTATION_SIGNAL", "0")).strip() == "1"


def _write_payload(dir_path: Path, suffix: str, payload: dict[str, Any], id_field: str | None = None) -> tuple[Path, dict[str, Any], str]:
    return write_hashed_json(dir_path, suffix, payload, id_field=id_field)


def _write_payload_atomic(
    dir_path: Path,
    suffix: str,
    payload: dict[str, Any],
    *,
    id_field: str | None = None,
) -> tuple[Path, dict[str, Any], str]:
    dir_path.mkdir(parents=True, exist_ok=True)
    obj = dict(payload)
    if id_field is not None:
        no_id = dict(obj)
        no_id.pop(id_field, None)
        obj[id_field] = canon_hash_obj(no_id)
    digest = canon_hash_obj(obj)
    out_path = dir_path / f"sha256_{digest.split(':', 1)[1]}.{suffix}"
    content = canon_bytes(obj) + b"\n"

    if out_path.exists():
        existing = out_path.read_bytes()
        if existing.rstrip(b"\n") != content.rstrip(b"\n"):
            fail("NONDETERMINISTIC")
        return out_path, obj, digest

    tmp_name = f".tmp_{out_path.name}.{os.getpid()}.{time.monotonic_ns()}"
    tmp_path = dir_path / tmp_name
    with tmp_path.open("wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, out_path)
    fd = os.open(str(dir_path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return out_path, obj, digest


def _assert_path_within(path: Path, root: Path) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except Exception:
        fail("FORBIDDEN_PATH")


def _ratio_q32(num_u64: int, den_u64: int, *, default_q32: int) -> dict[str, int]:
    den = int(den_u64)
    if den <= 0:
        return {"q": int(max(0, min(_Q32_ONE, default_q32)))}
    num = int(max(0, num_u64))
    q = int((num * _Q32_ONE) // den)
    if q < 0:
        q = 0
    if q > _Q32_ONE:
        q = _Q32_ONE
    return {"q": q}


def _failure_metric_key(reason_code: str) -> str:
    token = _FAILURE_KEY_RE.sub("_", str(reason_code).strip().lower()).strip("_")
    return f"epistemic_failure_{token or 'unknown'}_u64"


def _collect_epistemic_metrics_from_prev_state(prev_state_dir: Path | None) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "epistemic_capsule_count_u64": 0,
        "epistemic_refutation_count_u64": 0,
        "epistemic_failure_total_u64": 0,
        "epistemic_low_confidence_ratio_q32": {"q": 0},
        "epistemic_novelty_ratio_q32": {"q": 0},
        "epistemic_replay_pass_rate_q32": {"q": _Q32_ONE},
    }
    if prev_state_dir is None:
        return metrics
    epi_root = prev_state_dir.resolve() / "epistemic"
    if not epi_root.exists() or not epi_root.is_dir():
        return metrics

    refutation_paths = sorted((epi_root / "refutations").glob("sha256_*.epistemic_capsule_refutation_v1.json"), key=lambda p: p.as_posix())
    usable_capsule_ids = load_usable_capsule_ids(prev_state_dir.resolve())
    graph_paths = iter_usable_graphs(prev_state_dir.resolve())

    capsule_count = int(len(usable_capsule_ids))
    refutation_count = int(len(refutation_paths))
    metrics["epistemic_capsule_count_u64"] = capsule_count
    metrics["epistemic_refutation_count_u64"] = refutation_count
    metrics["epistemic_failure_total_u64"] = refutation_count
    metrics["epistemic_replay_pass_rate_q32"] = _ratio_q32(
        capsule_count,
        capsule_count + refutation_count,
        default_q32=_Q32_ONE,
    )

    low_conf_u64 = 0
    novelty_u64 = 0
    node_total_u64 = 0
    for graph_path in graph_paths:
        payload = load_canon_dict(graph_path)
        if str(payload.get("schema_version", "")).strip() != "qxwmr_graph_v1":
            fail("SCHEMA_FAIL")
        nodes = payload.get("nodes")
        if not isinstance(nodes, list):
            fail("SCHEMA_FAIL")
        for row in nodes:
            if not isinstance(row, dict):
                fail("SCHEMA_FAIL")
            node_total_u64 += 1
            confidence_q32 = int(row.get("confidence_q32", 0))
            if confidence_q32 < _EPISTEMIC_LOW_CONF_THRESHOLD_Q32:
                low_conf_u64 += 1
            if str(row.get("type_id", "")).strip() != "CLAIM":
                novelty_u64 += 1

    metrics["epistemic_low_confidence_ratio_q32"] = _ratio_q32(low_conf_u64, node_total_u64, default_q32=0)
    metrics["epistemic_novelty_ratio_q32"] = _ratio_q32(novelty_u64, node_total_u64, default_q32=0)

    by_reason: dict[str, int] = {}
    for refutation_path in refutation_paths:
        payload = load_canon_dict(refutation_path)
        if str(payload.get("schema_version", "")).strip() != "epistemic_capsule_refutation_v1":
            fail("SCHEMA_FAIL")
        reason = str(payload.get("reason_code", "")).strip()
        key = _failure_metric_key(reason)
        by_reason[key] = int(by_reason.get(key, 0)) + 1
    for key in sorted(by_reason.keys()):
        metrics[key] = int(by_reason[key])

    return metrics


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


def _load_shadow_profile_payload(
    *,
    config_dir: Path,
    pack: dict[str, Any],
    rel_key: str,
    schema_name: str,
    required: bool,
) -> dict[str, Any] | None:
    rel_raw = str(pack.get(rel_key, "")).strip()
    if not rel_raw:
        if required:
            fail("MISSING_STATE_INPUT")
        return None
    rel_path = Path(rel_raw)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        fail("SCHEMA_FAIL")
    path = config_dir / rel_path
    if not path.exists() or not path.is_file():
        fail("MISSING_STATE_INPUT")
    payload = load_canon_dict(path)
    validate_schema_v19(payload, schema_name)
    return payload


def _ensure_shadow_profile_id_match(
    *,
    proposal: dict[str, Any],
    proposal_id_field: str,
    payload: dict[str, Any],
    payload_id_field: str,
) -> None:
    proposal_id = str(proposal.get(proposal_id_field, "")).strip()
    payload_id = str(payload.get(payload_id_field, "")).strip()
    if not proposal_id or not payload_id:
        fail("SCHEMA_FAIL")
    if proposal_id != payload_id:
        fail("PIN_HASH_MISMATCH")


def _fail_shadow_exception(exc: Exception) -> None:
    raw = str(exc).strip()
    reason = raw.split(":", 1)[0] if raw else "SCHEMA_FAIL"
    if reason in {
        "SCHEMA_FAIL",
        "MISSING_STATE_INPUT",
        "NONDETERMINISTIC",
        "SHADOW_FORBIDDEN_WRITE",
        "SHADOW_HASH_BUDGET_EXHAUSTED",
        "SHADOW_PROTECTED_ROOT_MUTATION",
        "SHADOW_RUNNER_FAILED",
    }:
        fail(reason)
    fail("SCHEMA_FAIL")


def _shadow_double_run_rows(count: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx in range(max(0, int(count))):
        digest = canon_hash_obj({"idx": idx, "schema": "shadow_determinism_double_run_v1"})
        rows.append(
            {
                "run_a_hash": str(digest),
                "run_b_hash": str(digest),
            }
        )
    return rows


def _load_shadow_corpus_entry_manifests(
    *,
    config_dir: Path,
    corpus_entries: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    manifests: dict[str, dict[str, Any]] = {}
    for row in corpus_entries:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        entry_manifest_id = ensure_sha256(row.get("entry_manifest_id"), reason="SCHEMA_FAIL")
        hexd = entry_manifest_id.split(":", 1)[1]
        matches = sorted(
            config_dir.rglob(f"sha256_{hexd}.shadow_corpus_entry_manifest_v1.json"),
            key=lambda p: p.as_posix(),
        )
        if len(matches) != 1:
            fail("MISSING_STATE_INPUT")
        payload = load_canon_dict(matches[0])
        validate_schema_v19(payload, "shadow_corpus_entry_manifest_v1")
        if str(payload.get("schema_name", "")) != "shadow_corpus_entry_manifest_v1":
            fail("SCHEMA_FAIL")
        observed_id = canon_hash_obj({k: v for k, v in payload.items() if k != "entry_manifest_id"})
        if str(payload.get("entry_manifest_id", "")) != observed_id:
            fail("NONDETERMINISTIC")
        if observed_id != entry_manifest_id:
            fail("NONDETERMINISTIC")
        manifests[entry_manifest_id] = payload
    return manifests


def _load_shadow_candidate_outputs(*, state_root: Path) -> dict[str, Any]:
    epi_root = state_root / "epistemic"
    capsule_rows = sorted((epi_root / "capsules").glob("sha256_*.epistemic_capsule_v1.json"), key=lambda p: p.as_posix())
    graph_rows = sorted((epi_root / "graphs").glob("sha256_*.qxwmr_graph_v1.json"), key=lambda p: p.as_posix())
    binding_rows = sorted((epi_root / "type_bindings").glob("sha256_*.epistemic_type_binding_v1.json"), key=lambda p: p.as_posix())
    registry_rows = sorted((epi_root / "type_registry").glob("sha256_*.epistemic_type_registry_v1.json"), key=lambda p: p.as_posix())
    eufc_rows = sorted((epi_root / "certs").glob("sha256_*.epistemic_eufc_v1.json"), key=lambda p: p.as_posix())
    strip_receipt_rows = sorted(
        (epi_root / "strip_receipts").glob("sha256_*.epistemic_instruction_strip_receipt_v1.json"),
        key=lambda p: p.as_posix(),
    )
    if not (capsule_rows and graph_rows and binding_rows and registry_rows and eufc_rows and strip_receipt_rows):
        fail("MISSING_STATE_INPUT")
    capsule = load_canon_dict(capsule_rows[-1])
    graph = load_canon_dict(graph_rows[-1])
    type_binding = load_canon_dict(binding_rows[-1])
    type_registry = load_canon_dict(registry_rows[-1])
    eufc = load_canon_dict(eufc_rows[-1])
    strip_receipts = [load_canon_dict(path) for path in strip_receipt_rows]
    validate_schema_v19(capsule, "epistemic_capsule_v1")
    validate_schema_v19(graph, "qxwmr_graph_v1")
    validate_schema_v19(type_binding, "epistemic_type_binding_v1")
    validate_schema_v19(type_registry, "epistemic_type_registry_v1")
    validate_schema_v19(eufc, "epistemic_eufc_v1")
    for strip_receipt in strip_receipts:
        validate_schema_v19(strip_receipt, "epistemic_instruction_strip_receipt_v1")
    task_input_ids = eufc.get("task_input_ids")
    if not isinstance(task_input_ids, list):
        fail("SCHEMA_FAIL")
    strip_contract_ids = sorted(
        {
            ensure_sha256(strip_receipt.get("instruction_strip_contract_id"), reason="SCHEMA_FAIL")
            for strip_receipt in strip_receipts
        }
    )
    if len(strip_contract_ids) != 1:
        fail("NONDETERMINISTIC")
    return {
        "graph_id": ensure_sha256(graph.get("graph_id"), reason="SCHEMA_FAIL"),
        "type_binding_id": ensure_sha256(type_binding.get("binding_id"), reason="SCHEMA_FAIL"),
        "type_registry_id": ensure_sha256(type_registry.get("registry_id"), reason="SCHEMA_FAIL"),
        "cert_id": ensure_sha256(eufc.get("eufc_id"), reason="SCHEMA_FAIL"),
        "cert_profile_id": ensure_sha256(capsule.get("cert_profile_id"), reason="SCHEMA_FAIL"),
        "instruction_strip_contract_id": str(strip_contract_ids[0]),
        "strip_receipt_id": ensure_sha256(capsule.get("strip_receipt_id"), reason="SCHEMA_FAIL"),
        "task_input_ids": sorted(ensure_sha256(v, reason="SCHEMA_FAIL") for v in task_input_ids),
    }


def _run_shadow_sidecar(
    *,
    repo_root_path: Path,
    config_dir: Path,
    state_root: Path,
    pack: dict[str, Any],
    tick_u64: int,
) -> dict[str, Any] | None:
    proposal = _load_shadow_profile_payload(
        config_dir=config_dir,
        pack=pack,
        rel_key="shadow_regime_proposal_rel",
        schema_name="shadow_regime_proposal_v1",
        required=False,
    )
    if proposal is None:
        return None

    evaluation_tiers = _load_shadow_profile_payload(
        config_dir=config_dir,
        pack=pack,
        rel_key="shadow_evaluation_tiers_rel",
        schema_name="shadow_evaluation_tiers_v1",
        required=True,
    )
    protected_profile = _load_shadow_profile_payload(
        config_dir=config_dir,
        pack=pack,
        rel_key="shadow_protected_roots_profile_rel",
        schema_name="shadow_protected_roots_profile_v1",
        required=False,
    )
    if protected_profile is None:
        protected_profile = default_shadow_protected_roots_profile()
    try:
        active_state_root_rel = state_root.resolve().relative_to(repo_root_path.resolve()).as_posix()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("SCHEMA_FAIL") from exc
    protected_profile = dict(protected_profile)
    protected_profile["dynamic_protected_roots"] = [active_state_root_rel]
    corpus_descriptor, _corpus_descriptor_id = _load_pinned_json_payload(
        config_dir=config_dir,
        pack=pack,
        rel_key="shadow_corpus_descriptor_rel",
        id_key="shadow_corpus_descriptor_id",
        payload_id_field="descriptor_id",
        missing_reason="MISSING_STATE_INPUT",
    )
    validate_schema_v19(corpus_descriptor, "corpus_descriptor_v1")
    det_profile = _load_shadow_profile_payload(
        config_dir=config_dir,
        pack=pack,
        rel_key="shadow_witnessed_determinism_profile_rel",
        schema_name="witnessed_determinism_profile_v1",
        required=True,
    )
    j_profile = _load_shadow_profile_payload(
        config_dir=config_dir,
        pack=pack,
        rel_key="shadow_j_comparison_profile_rel",
        schema_name="j_comparison_v1",
        required=True,
    )
    graph_invariance_contract, _graph_contract_id = _load_pinned_json_payload(
        config_dir=config_dir,
        pack=pack,
        rel_key="shadow_graph_invariance_contract_rel",
        id_key="shadow_graph_invariance_contract_id",
        payload_id_field="contract_id",
        missing_reason="MISSING_STATE_INPUT",
    )
    validate_schema_v19(graph_invariance_contract, "graph_invariance_contract_v1")
    type_binding_invariance_contract, _type_contract_id = _load_pinned_json_payload(
        config_dir=config_dir,
        pack=pack,
        rel_key="shadow_type_binding_invariance_contract_rel",
        id_key="shadow_type_binding_invariance_contract_id",
        payload_id_field="contract_id",
        missing_reason="MISSING_STATE_INPUT",
    )
    validate_schema_v19(type_binding_invariance_contract, "type_binding_invariance_contract_v1")
    cert_invariance_contract, _cert_contract_id = _load_pinned_json_payload(
        config_dir=config_dir,
        pack=pack,
        rel_key="shadow_cert_invariance_contract_rel",
        id_key="shadow_cert_invariance_contract_id",
        payload_id_field="contract_id",
        missing_reason="MISSING_STATE_INPUT",
    )
    validate_schema_v19(cert_invariance_contract, "cert_invariance_contract_v1")
    _ensure_shadow_profile_id_match(
        proposal=proposal,
        proposal_id_field="shadow_evaluation_tiers_profile_id",
        payload=evaluation_tiers,
        payload_id_field="profile_id",
    )
    _ensure_shadow_profile_id_match(
        proposal=proposal,
        proposal_id_field="shadow_protected_roots_profile_id",
        payload=protected_profile,
        payload_id_field="profile_id",
    )
    _ensure_shadow_profile_id_match(
        proposal=proposal,
        proposal_id_field="corpus_descriptor_id",
        payload=corpus_descriptor,
        payload_id_field="descriptor_id",
    )
    _ensure_shadow_profile_id_match(
        proposal=proposal,
        proposal_id_field="witnessed_determinism_profile_id",
        payload=det_profile,
        payload_id_field="profile_id",
    )
    _ensure_shadow_profile_id_match(
        proposal=proposal,
        proposal_id_field="j_comparison_profile_id",
        payload=j_profile,
        payload_id_field="comparison_id",
    )

    candidate_regime_id = str(proposal.get("target_regime_id", "")).strip()
    if not candidate_regime_id:
        fail("SCHEMA_FAIL")
    regime_parts = Path(candidate_regime_id).parts
    if len(regime_parts) != 1 or regime_parts[0] in {"", ".", ".."}:
        fail("SCHEMA_FAIL")

    try:
        static_pre = hash_protected_roots(
            repo_root=repo_root_path,
            roots=[str(row) for row in protected_profile.get("static_protected_roots", [])],
            excluded_roots=[str(row) for row in protected_profile.get("excluded_roots", [])],
            hash_budget_spec=dict(protected_profile.get("hash_budget_spec", {})),
            symlink_policy=str(protected_profile.get("symlink_policy", "FAIL_CLOSED")),
        )
    except RuntimeError as exc:
        _fail_shadow_exception(exc)

    observed_write_paths: list[str] = []
    observed_writes_rel = str(pack.get("shadow_observed_writes_rel", "")).strip()
    if observed_writes_rel:
        observed_rel_path = Path(observed_writes_rel)
        if observed_rel_path.is_absolute() or ".." in observed_rel_path.parts:
            fail("SCHEMA_FAIL")
        observed_path = config_dir / observed_rel_path
        if not observed_path.exists() or not observed_path.is_file():
            fail("MISSING_STATE_INPUT")
        observed_payload = load_canon_dict(observed_path)
        rows = observed_payload.get("paths")
        if not isinstance(rows, list):
            fail("SCHEMA_FAIL")
        observed_write_paths = [str(row) for row in rows]

    try:
        runner_receipt = run_shadow_tick(
            repo_root=repo_root_path,
            state_root=state_root,
            candidate_regime_id=candidate_regime_id,
            protected_profile=protected_profile,
            tick_u64=tick_u64,
            observed_write_paths=observed_write_paths,
            candidate_command=None,
            timeout_seconds=60,
        )
    except RuntimeError as exc:
        _fail_shadow_exception(exc)

    try:
        static_post = hash_protected_roots(
            repo_root=repo_root_path,
            roots=[str(row) for row in protected_profile.get("static_protected_roots", [])],
            excluded_roots=[str(row) for row in protected_profile.get("excluded_roots", [])],
            hash_budget_spec=dict(protected_profile.get("hash_budget_spec", {})),
            symlink_policy=str(protected_profile.get("symlink_policy", "FAIL_CLOSED")),
        )
    except RuntimeError as exc:
        _fail_shadow_exception(exc)
    static_mutations = diff_file_maps(static_pre["file_hashes"], static_post["file_hashes"])
    dynamic_mutations = [str(row) for row in runner_receipt.get("dynamic_mutated_paths", [])]
    all_mutations = sorted(set(static_mutations + dynamic_mutations))

    combined_budget = {
        "files_u64": int(static_post["budget"]["files_u64"]) + int(runner_receipt.get("budget", {}).get("files_u64", 0)),
        "bytes_read_u64": int(static_post["budget"]["bytes_read_u64"])
        + int(runner_receipt.get("budget", {}).get("bytes_read_u64", 0)),
        "steps_u64": int(static_post["budget"]["steps_u64"]) + int(runner_receipt.get("budget", {}).get("steps_u64", 0)),
    }
    integrity_reasons: list[str] = []
    if all_mutations:
        integrity_reasons.append("SHADOW_PROTECTED_ROOT_MUTATION")
    if str(runner_receipt.get("status", "PASS")) != "PASS":
        integrity_reasons.extend(str(row) for row in runner_receipt.get("reason_codes", []))
    integrity_report = build_integrity_report(
        tick_u64=tick_u64,
        candidate_regime_id=candidate_regime_id,
        phase="STATIC_TIER",
        scope_hash_pre=str(static_pre["scope_hash"]),
        scope_hash_post=str(static_post["scope_hash"]),
        mutated_paths=all_mutations,
        budget=combined_budget,
        reason_codes=integrity_reasons,
    )

    corpus_descriptor_rel = str(pack.get("shadow_corpus_descriptor_rel", "")).strip()
    if not corpus_descriptor_rel:
        fail("MISSING_STATE_INPUT")
    corpus_descriptor_rel_path = Path(corpus_descriptor_rel)
    if corpus_descriptor_rel_path.is_absolute() or ".." in corpus_descriptor_rel_path.parts:
        fail("SCHEMA_FAIL")
    shadow_corpus_bundle = load_shadow_corpus_entries(
        corpus_descriptor=dict(corpus_descriptor),
        descriptor_dir=(config_dir / corpus_descriptor_rel_path).parent,
    )
    corpus_entries = [dict(row) for row in list(shadow_corpus_bundle.get("corpus_entries") or []) if isinstance(row, dict)]
    if not corpus_entries:
        fail("SCHEMA_FAIL")
    replay_entries = [dict(row) for row in list(shadow_corpus_bundle.get("replay_entries") or []) if isinstance(row, dict)]
    if len(replay_entries) != len(corpus_entries):
        fail("NONDETERMINISTIC")
    entry_manifests_by_id = {
        str(k): dict(v)
        for k, v in dict(shadow_corpus_bundle.get("entry_manifests_by_id") or {}).items()
        if isinstance(v, dict)
    }
    if len(entry_manifests_by_id) != len(corpus_entries):
        fail("NONDETERMINISTIC")

    shadow_cert_profile_id_raw = str(pack.get("shadow_cert_profile_id", "")).strip()
    shadow_instruction_strip_contract_id_raw = str(pack.get("shadow_instruction_strip_contract_id", "")).strip()
    if not shadow_cert_profile_id_raw or not shadow_instruction_strip_contract_id_raw:
        fail("MISSING_STATE_INPUT")
    shadow_cert_profile_id = ensure_sha256(shadow_cert_profile_id_raw, reason="SCHEMA_FAIL")
    shadow_instruction_strip_contract_id = ensure_sha256(shadow_instruction_strip_contract_id_raw, reason="SCHEMA_FAIL")
    for replay_entry in replay_entries:
        contracts = replay_entry.get("contracts")
        expected_outputs = replay_entry.get("expected_outputs")
        if not isinstance(contracts, dict) or not isinstance(expected_outputs, dict):
            fail("SCHEMA_FAIL")
        if ensure_sha256(contracts.get("instruction_strip_contract_id"), reason="SCHEMA_FAIL") != shadow_instruction_strip_contract_id:
            fail("PIN_HASH_MISMATCH")
        if ensure_sha256(contracts.get("cert_profile_id"), reason="SCHEMA_FAIL") != shadow_cert_profile_id:
            fail("PIN_HASH_MISMATCH")
        if ensure_sha256(expected_outputs.get("cert_profile_id"), reason="SCHEMA_FAIL") != shadow_cert_profile_id:
            fail("PIN_HASH_MISMATCH")

    candidate_outputs = _load_shadow_candidate_outputs(state_root=state_root)
    if ensure_sha256(candidate_outputs.get("cert_profile_id"), reason="SCHEMA_FAIL") != shadow_cert_profile_id:
        fail("PIN_HASH_MISMATCH")
    if (
        ensure_sha256(candidate_outputs.get("instruction_strip_contract_id"), reason="SCHEMA_FAIL")
        != shadow_instruction_strip_contract_id
    ):
        fail("PIN_HASH_MISMATCH")
    corpus_invariance_receipt = build_shadow_corpus_invariance_receipt(
        tick_u64=int(tick_u64),
        corpus_entries=corpus_entries,
        entry_manifests_by_id=entry_manifests_by_id,
        graph_contract=dict(graph_invariance_contract),
        type_binding_contract=dict(type_binding_invariance_contract),
        cert_contract=dict(cert_invariance_contract),
        candidate_outputs=candidate_outputs,
    )
    corpus_rows = [
        {
            "baseline_accept_b": True,
            "candidate_accept_b": bool(
                row.get("graph_match_b", False)
                and row.get("type_binding_match_b", False)
                and row.get("cert_match_b", False)
            ),
        }
        for row in list(corpus_invariance_receipt.get("compared_rows") or [])
        if isinstance(row, dict)
    ]
    if not corpus_rows:
        fail("SCHEMA_FAIL")
    conservatism = evaluate_reject_conservatism(
        corpus_results=corpus_rows,
        probe_results=[dict(corpus_rows[0])],
    )

    tier_a_double_runs = int((det_profile.get("tier_a") or {}).get("n_double_runs", 0))
    tier_b_double_runs = int((det_profile.get("tier_b") or {}).get("n_double_runs", 0))
    tier_a_det = evaluate_determinism_witness(
        profile=det_profile,
        tier="TIER_A",
        witness_rows=_shadow_double_run_rows(tier_a_double_runs),
    )
    tier_b_det = evaluate_determinism_witness(
        profile=det_profile,
        tier="TIER_B",
        witness_rows=_shadow_double_run_rows(tier_b_double_runs),
    )

    window_len = max(1, min(8, len(corpus_entries)))
    j19 = [0 for _ in range(window_len)]
    j20 = [0 for _ in range(window_len)]
    tier_a_j_profile = dict(j_profile)
    tier_a_j_profile["per_tick_floor_enabled_b"] = False
    tier_a_j_profile["epsilon_tick_q32"] = 0
    tier_a_j = evaluate_j_comparison(
        profile=tier_a_j_profile,
        j19_window_q32=j19,
        j20_window_q32=j20,
    )
    tier_b_j_profile = dict(j_profile)
    tier_b_j_profile["per_tick_floor_enabled_b"] = True
    tier_b_j_profile["epsilon_tick_q32"] = 0
    tier_b_j = evaluate_j_comparison(
        profile=tier_b_j_profile,
        j19_window_q32=j19,
        j20_window_q32=j20,
    )

    tier_a_pass_b = bool(
        str(runner_receipt.get("status", "PASS")) == "PASS"
        and str(integrity_report.get("status", "FAIL")) == "PASS"
        and bool(conservatism.get("pass_b", False))
        and bool(corpus_invariance_receipt.get("pass_b", False))
        and bool(tier_a_det.get("pass_b", False))
        and bool(tier_a_j.get("window_rule_pass_b", False))
    )
    tier_b_pass_b = bool(
        tier_a_pass_b
        and bool(tier_b_det.get("pass_b", False))
        and bool(tier_b_j.get("window_rule_pass_b", False))
        and bool(tier_b_j.get("per_tick_floor_pass_b", False))
    )

    tier_a_receipt: dict[str, Any] = {
        "schema_name": "shadow_tier_receipt_v1",
        "schema_version": "v19_0",
        "tier": "A",
        "tick_u64": int(tick_u64),
        "candidate_regime_id": candidate_regime_id,
        "n_live_ticks": int((evaluation_tiers.get("tier_a") or {}).get("n_live_ticks", 0)),
        "n_fuzz_cases": int((evaluation_tiers.get("tier_a") or {}).get("n_fuzz_cases", 0)),
        "n_double_runs": int(tier_a_double_runs),
        "conservatism_pass_b": bool(conservatism.get("pass_b", False)),
        "determinism_pass_b": bool(tier_a_det.get("pass_b", False)),
        "window_rule_pass_b": bool(tier_a_j.get("window_rule_pass_b", False)),
        "per_tick_floor_pass_b": bool(tier_a_j.get("per_tick_floor_pass_b", True)),
        "pass_b": bool(tier_a_pass_b),
    }
    tier_b_receipt: dict[str, Any] = {
        "schema_name": "shadow_tier_receipt_v1",
        "schema_version": "v19_0",
        "tier": "B",
        "tick_u64": int(tick_u64),
        "candidate_regime_id": candidate_regime_id,
        "n_live_ticks": int((evaluation_tiers.get("tier_b") or {}).get("n_live_ticks", 0)),
        "n_fuzz_cases": int((evaluation_tiers.get("tier_b") or {}).get("n_fuzz_cases", 0)),
        "n_double_runs": int(tier_b_double_runs),
        "conservatism_pass_b": bool(conservatism.get("pass_b", False)),
        "determinism_pass_b": bool(tier_b_det.get("pass_b", False)),
        "window_rule_pass_b": bool(tier_b_j.get("window_rule_pass_b", False)),
        "per_tick_floor_pass_b": bool(tier_b_j.get("per_tick_floor_pass_b", False)),
        "pass_b": bool(tier_b_pass_b),
    }

    auto_swap_b = bool(pack.get("auto_swap_b", False))
    rollback_evidence_hash = canon_hash_obj(
        {
            "schema_version": "shadow_rollback_evidence_binding_v1",
            "proposal_id": str(proposal.get("proposal_id", "")),
            "candidate_regime_id": candidate_regime_id,
            "tick_u64": int(tick_u64),
            "tier_b_pass_b": bool(tier_b_pass_b),
            "corpus_invariance_receipt_id": str(corpus_invariance_receipt.get("receipt_id", "")),
        }
    )
    readiness_receipt = evaluate_shadow_regime_proposal(
        proposal=proposal,
        tier_a_pass_b=tier_a_pass_b,
        tier_b_pass_b=tier_b_pass_b,
        integrity_guard_verified_b=str(integrity_report.get("status", "FAIL")) == "PASS",
        static_protected_roots_verified_b=not bool(static_mutations),
        dynamic_protected_roots_verified_b=not bool(dynamic_mutations),
        j_window_rule_verified_b=bool(tier_b_j.get("window_rule_pass_b", False)),
        j_per_tick_floor_verified_b=bool(tier_b_j.get("per_tick_floor_pass_b", False)),
        non_weakening_j_verified_b=bool(tier_b_j.get("pass_b", False)),
        corpus_replay_verified_b=bool(conservatism.get("pass_b", False)),
        deterministic_fuzz_verified_b=bool(tier_b_det.get("pass_b", False)),
        rollback_plan_bound_b=True,
        auto_swap_b=auto_swap_b,
        corpus_invariance_verified_b=bool(corpus_invariance_receipt.get("pass_b", False)),
        corpus_invariance_receipt_id=str(corpus_invariance_receipt.get("receipt_id")),
        rollback_evidence_hash=rollback_evidence_hash,
    )
    handoff_rel = str(pack.get("shadow_handoff_receipt_rel", "")).strip()
    if auto_swap_b:
        if not handoff_rel:
            fail("TIER_B_REQUIRED_FOR_SWAP")
        handoff_rel_path = Path(handoff_rel)
        if handoff_rel_path.is_absolute() or ".." in handoff_rel_path.parts:
            fail("SCHEMA_FAIL")
        handoff_path = config_dir / handoff_rel_path
        if not handoff_path.exists() or not handoff_path.is_file():
            fail("MISSING_STATE_INPUT")
        handoff_receipt = load_canon_dict(handoff_path)
        validate_schema_v19(handoff_receipt, "shadow_regime_readiness_receipt_v1")
        if not bool(handoff_receipt.get("runtime_tier_b_pass_b", False)):
            fail("TIER_B_REQUIRED_FOR_SWAP")
        if str(handoff_receipt.get("proposal_id", "")) != str(proposal.get("proposal_id", "")):
            fail("NONDETERMINISTIC")
        if str(handoff_receipt.get("verdict", "")) != "READY":
            fail("TIER_B_REQUIRED_FOR_SWAP")
        if not bool(readiness_receipt.get("runtime_tier_b_pass_b", False)):
            fail("TIER_B_REQUIRED_FOR_SWAP")
    if auto_swap_b and not bool(readiness_receipt.get("runtime_tier_b_pass_b", False)):
        fail("TIER_B_REQUIRED_FOR_SWAP")

    return {
        "integrity_report": integrity_report,
        "tier_a_receipt": tier_a_receipt,
        "tier_b_receipt": tier_b_receipt,
        "readiness_receipt": readiness_receipt,
        "corpus_invariance_receipt": corpus_invariance_receipt,
        "runner_receipt": runner_receipt,
    }


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


def _require_safe_relpath(path_value: Any) -> str:
    rel = str(path_value).strip()
    if not rel:
        fail("SCHEMA_FAIL")
    path = Path(rel)
    if path.is_absolute() or ".." in path.parts or "\\" in rel:
        fail("SCHEMA_FAIL")
    return rel


def _sorted_unique_strings(rows: Any) -> list[str]:
    if not isinstance(rows, list):
        fail("SCHEMA_FAIL")
    out = sorted({str(row).strip() for row in rows if str(row).strip()})
    return out


def _load_optional_long_run_profile(*, config_dir: Path, pack: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    rel_raw = str(pack.get("long_run_profile_rel", "")).strip()
    id_raw = str(pack.get("long_run_profile_id", "")).strip()
    if not rel_raw and not id_raw:
        return None, None
    if bool(rel_raw) != bool(id_raw):
        fail("SCHEMA_FAIL")
    rel = _require_safe_relpath(rel_raw)
    declared_id = ensure_sha256(id_raw, reason="PIN_HASH_MISMATCH")
    path = config_dir / rel
    if not path.exists() or not path.is_file():
        fail("MISSING_STATE_INPUT")
    payload = load_canon_dict(path)
    validate_schema_v19(payload, "long_run_profile_v1")
    profile_id = ensure_sha256(payload.get("profile_id"), reason="PIN_HASH_MISMATCH")
    no_id = dict(payload)
    no_id.pop("profile_id", None)
    if canon_hash_obj(no_id) != profile_id:
        fail("PIN_HASH_MISMATCH")
    if profile_id != declared_id:
        fail("PIN_HASH_MISMATCH")
    return payload, declared_id


def _load_long_run_eval_assets(
    *,
    config_dir: Path,
    pack: dict[str, Any],
    long_run_profile: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    eval_cfg = long_run_profile.get("evaluation")
    if not isinstance(eval_cfg, dict):
        fail("SCHEMA_FAIL")
    ek_rel_profile = _require_safe_relpath(eval_cfg.get("ek_rel"))
    suite_rel_profile = _require_safe_relpath(eval_cfg.get("suite_rel"))

    ek_rel = _require_safe_relpath(pack.get("long_run_eval_kernel_rel"))
    ek_id = ensure_sha256(pack.get("long_run_eval_kernel_id"), reason="PIN_HASH_MISMATCH")
    suite_rel = _require_safe_relpath(pack.get("long_run_eval_suite_rel"))
    suite_id = ensure_sha256(pack.get("long_run_eval_suite_id"), reason="PIN_HASH_MISMATCH")
    if ek_rel != ek_rel_profile or suite_rel != suite_rel_profile:
        fail("PIN_HASH_MISMATCH")

    ek_payload = load_canon_dict(config_dir / ek_rel)
    suite_payload = load_canon_dict(config_dir / suite_rel)
    if canon_hash_obj(ek_payload) != ek_id:
        fail("PIN_HASH_MISMATCH")
    if canon_hash_obj(suite_payload) != suite_id:
        fail("PIN_HASH_MISMATCH")
    return ek_payload, suite_payload


def _load_long_run_utility_policy(
    *,
    config_dir: Path,
    long_run_profile: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    rel_raw = str(long_run_profile.get("utility_policy_rel", "")).strip()
    id_raw = str(long_run_profile.get("utility_policy_id", "")).strip()
    if not rel_raw and not id_raw:
        return None, None
    if bool(rel_raw) != bool(id_raw):
        fail("SCHEMA_FAIL")
    rel = _require_safe_relpath(rel_raw)
    declared_id = ensure_sha256(id_raw, reason="PIN_HASH_MISMATCH")
    path = config_dir / rel
    if not path.exists() or not path.is_file():
        fail("MISSING_STATE_INPUT")
    payload = load_canon_dict(path)
    validate_schema_v19(payload, "utility_policy_v1")
    observed_id = ensure_sha256(payload.get("policy_id"), reason="PIN_HASH_MISMATCH")
    payload_no_id = dict(payload)
    payload_no_id.pop("policy_id", None)
    if canon_hash_obj(payload_no_id) != observed_id:
        fail("PIN_HASH_MISMATCH")
    if observed_id != declared_id:
        fail("PIN_HASH_MISMATCH")
    _validate_probe_suite_resolution_contract(utility_policy=payload)
    return payload, observed_id


def _load_optional_orch_bandit_config(
    *,
    config_dir: Path,
    pack: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    rel_raw = str(pack.get("orch_bandit_config_rel", "")).strip()
    if not rel_raw:
        return None, None
    rel = _require_safe_relpath(rel_raw)
    path = config_dir / rel
    if not path.exists() or not path.is_file():
        fail("MISSING_STATE_INPUT")
    payload = load_canon_dict(path)
    validate_schema_v19(payload, "orch_bandit_config_v1")
    return payload, canon_hash_obj(payload)


def _normalize_orch_bandit_lane_kind(*, lane_name: str | None) -> str:
    lane = str(lane_name or "").strip().upper()
    if lane == "FRONTIER":
        return "FRONTIER_HEAVY"
    if lane in {"BASELINE", "CANARY"}:
        return "BASELINE"
    return "UNKNOWN"


def _normalize_orch_promotion_result_kind(
    *,
    result_kind: Any,
    status: Any,
    activation_kind: Any,
) -> str:
    kind = str(result_kind).strip()
    if kind in _ORCH_PROMOTION_RESULT_KINDS:
        return kind
    normalized_status = str(status).strip().upper()
    if normalized_status == "PROMOTED":
        normalized_activation_kind = str(activation_kind).strip()
        if normalized_activation_kind == "ACTIVATION_KIND_EXT_QUEUED":
            return "PROMOTED_EXT_QUEUED"
        return "PROMOTED_COMMIT"
    return "REJECTED"


def _is_toxic_reason_code(reason_code: Any) -> bool:
    code = str(reason_code).strip()
    if not code:
        return False
    for prefix in _ORCH_TOXIC_REASON_PREFIXES:
        if code.startswith(prefix):
            return True
    return code in _ORCH_TOXIC_REASON_EXACT


def _utility_indicates_effect_heavy_ok(utility_receipt: dict[str, Any] | None) -> bool:
    if not isinstance(utility_receipt, dict):
        return False
    return str(utility_receipt.get("effect_class", "")).strip() == "EFFECT_HEAVY_OK"


def _clamp_orch_reward_q32(value: int) -> int:
    if int(value) < -_Q32_ONE:
        return -_Q32_ONE
    if int(value) > _Q32_ONE:
        return _Q32_ONE
    return int(value)


def _compute_orch_reward_q32(
    *,
    promotion_result_kind: str,
    toxic_fail_b: bool,
    lane_kind: str,
    utility_receipt: dict[str, Any] | None,
) -> int:
    if str(promotion_result_kind) == "PROMOTED_COMMIT":
        r_commit_q32 = int(_ORCH_REWARD_COMMIT_Q32)
        r_ext_q32 = 0
    elif str(promotion_result_kind) == "PROMOTED_EXT_QUEUED":
        r_commit_q32 = 0
        r_ext_q32 = int(_ORCH_REWARD_EXT_Q32)
    else:
        r_commit_q32 = 0
        r_ext_q32 = 0

    r_toxic_penalty_q32 = int(_ORCH_REWARD_TOXIC_Q32 if bool(toxic_fail_b) else 0)
    r_heavy_utility_bonus_q32 = int(
        _ORCH_REWARD_HEAVY_UTILITY_BONUS_Q32
        if str(lane_kind).strip() == "FRONTIER_HEAVY" and _utility_indicates_effect_heavy_ok(utility_receipt)
        else 0
    )
    reward_q32 = int(r_commit_q32) + int(r_ext_q32) + int(r_toxic_penalty_q32) + int(r_heavy_utility_bonus_q32)
    return int(_clamp_orch_reward_q32(reward_q32))


def _orch_bandit_state_dir(*, state_root: Path) -> Path:
    return state_root / "orch_bandit" / "state"


def _read_orch_bandit_pointer(*, state_dir: Path) -> str | None:
    pointer_path = state_dir / _ACTIVE_ORCH_BANDIT_STATE_POINTER
    if not pointer_path.exists() or not pointer_path.is_file():
        return None
    value = pointer_path.read_text(encoding="utf-8").strip()
    return value or None


def _write_orch_bandit_pointer(*, state_dir: Path, state_hash: str) -> None:
    if not _is_sha256(state_hash):
        fail("SCHEMA_FAIL")
    state_dir.mkdir(parents=True, exist_ok=True)
    pointer_path = state_dir / _ACTIVE_ORCH_BANDIT_STATE_POINTER
    tmp_name = f".tmp_{_ACTIVE_ORCH_BANDIT_STATE_POINTER}.{os.getpid()}.{time.monotonic_ns()}"
    tmp_path = state_dir / tmp_name
    tmp_path.write_text(str(state_hash) + "\n", encoding="utf-8")
    os.replace(tmp_path, pointer_path)
    fd = os.open(str(state_dir), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _load_or_bootstrap_orch_bandit_state(
    *,
    state_root: Path,
    ek_id: str,
    kernel_ledger_id: str,
) -> tuple[dict[str, Any], str]:
    state_dir = _orch_bandit_state_dir(state_root=state_root)
    state_dir.mkdir(parents=True, exist_ok=True)
    pointer = _read_orch_bandit_pointer(state_dir=state_dir)
    if isinstance(pointer, str) and pointer:
        if not _is_sha256(pointer):
            fail("NONDETERMINISTIC")
        hexd = pointer.split(":", 1)[1]
        state_path = state_dir / f"sha256_{hexd}.orch_bandit_state_v1.json"
        if not state_path.exists() or not state_path.is_file():
            fail("MISSING_STATE_INPUT")
        payload = load_canon_dict(state_path)
        validate_schema_v19(payload, "orch_bandit_state_v1")
        if canon_hash_obj(payload) != pointer:
            fail("NONDETERMINISTIC")
        return payload, pointer

    bootstrap = {
        "schema_version": "orch_bandit_state_v1",
        "tick_u64": 0,
        "parent_state_hash": _SHA256_ZERO,
        "ek_id": _sha256_or_zero(ek_id),
        "kernel_ledger_id": _sha256_or_zero(kernel_ledger_id),
        "contexts": [],
    }
    validate_schema_v19(bootstrap, "orch_bandit_state_v1")
    _path, obj, digest = _write_payload_atomic(
        state_dir,
        "orch_bandit_state_v1.json",
        bootstrap,
    )
    _write_orch_bandit_pointer(state_dir=state_dir, state_hash=digest)
    return obj, digest


def _derive_orch_bandit_eligible_capability_ids(
    *,
    registry: dict[str, Any],
    utility_policy: dict[str, Any] | None,
    lane_kind: str,
    hard_lock_active_b: bool,
    current_selected_capability_id: str,
    max_arms_u32: int,
) -> list[str]:
    max_arms = int(max(1, int(max_arms_u32)))
    selected_capability_id = str(current_selected_capability_id).strip()
    if bool(hard_lock_active_b):
        if not selected_capability_id:
            fail("BANDIT_FAIL:HARD_LOCK_EMPTY")
        return [selected_capability_id]

    caps = registry.get("capabilities")
    if not isinstance(caps, list):
        fail("SCHEMA_FAIL")
    heavy_lane = str(lane_kind).strip() == "FRONTIER_HEAVY"
    out: list[str] = []
    seen: set[str] = set()
    scanned = 0
    for row in sorted([entry for entry in caps if isinstance(entry, dict)], key=lambda entry: str(entry.get("capability_id", ""))):
        scanned += 1
        if scanned > int(max_arms):
            fail("BANDIT_FAIL:ARM_LIMIT")
        capability_id = str(row.get("capability_id", "")).strip()
        if not capability_id or capability_id in seen:
            continue
        if not bool(row.get("enabled", False)):
            continue
        declared_class = _declared_class_for_capability_id(
            utility_policy=utility_policy,
            capability_id=capability_id,
        )
        is_heavy_capability = declared_class in _HEAVY_DECLARED_CLASSES
        if heavy_lane and not is_heavy_capability:
            continue
        if (not heavy_lane) and is_heavy_capability:
            continue
        out.append(capability_id)
        seen.add(capability_id)
        if len(out) > int(max_arms):
            fail("BANDIT_FAIL:ARM_LIMIT")
    out = sorted(out)
    if not out:
        fail("BANDIT_FAIL:NO_ELIGIBLE_ARMS")
    return out


def _declared_class_for_capability_id(*, utility_policy: dict[str, Any] | None, capability_id: str) -> str:
    capability = str(capability_id).strip()
    if _premarathon_v63_enabled() and capability == _SH1_CAPABILITY_ID:
        return "FRONTIER_HEAVY"
    if isinstance(utility_policy, dict):
        mapping = utility_policy.get("declared_class_by_capability")
        if isinstance(mapping, dict):
            mapped = str(mapping.get(capability, "")).strip().upper()
            if mapped in _DECLARED_CLASSES:
                return mapped
    return "UNCLASSIFIED"


def _probe_registry_v1_from_utility_policy(utility_policy: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(utility_policy, dict):
        return {}
    raw_registry = utility_policy.get("probe_registry_v1")
    if raw_registry is None:
        return {}
    if not isinstance(raw_registry, dict):
        fail("SCHEMA_FAIL")
    normalized: dict[str, dict[str, Any]] = {}
    for probe_id_raw, row in sorted(raw_registry.items(), key=lambda kv: str(kv[0])):
        probe_id = str(probe_id_raw).strip()
        if not probe_id:
            fail("SCHEMA_FAIL")
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        assets_raw = row.get("required_asset_relpaths_v1", [])
        if not isinstance(assets_raw, list):
            fail("SCHEMA_FAIL")
        assets = [_require_safe_relpath(item) for item in assets_raw]
        normalized[probe_id] = {
            "probe_id": probe_id,
            "required_asset_relpaths_v1": assets,
        }
    return normalized


def _available_probe_suite_ids(*, utility_policy: dict[str, Any] | None) -> set[str]:
    available = {str(row).strip() for row in _BUILTIN_PROBE_SUITE_IDS if str(row).strip()}
    available.update(_probe_registry_v1_from_utility_policy(utility_policy).keys())
    return {str(row).strip() for row in available if str(row).strip()}


def _required_probe_suite_ids_from_utility_policy(*, utility_policy: dict[str, Any] | None) -> set[str]:
    if not isinstance(utility_policy, dict):
        return set()
    heavy_policies = utility_policy.get("heavy_policies")
    if not isinstance(heavy_policies, dict):
        fail("SCHEMA_FAIL")
    required: set[str] = set()
    for _capability_id, heavy_policy in sorted(heavy_policies.items(), key=lambda kv: str(kv[0])):
        if not isinstance(heavy_policy, dict):
            fail("SCHEMA_FAIL")
        required_probe_ids = heavy_policy.get("required_probe_ids_v1")
        if isinstance(required_probe_ids, list):
            for probe_id_raw in required_probe_ids:
                probe_id = str(probe_id_raw).strip()
                if probe_id:
                    required.add(probe_id)
        required_probe_id = str(heavy_policy.get("required_probe_id", "")).strip()
        if required_probe_id:
            required.add(required_probe_id)
        probe_suite_id = str(heavy_policy.get("probe_suite_id", "")).strip()
        stress_probe_suite_id = str(heavy_policy.get("stress_probe_suite_id", "")).strip()
        if probe_suite_id:
            required.add(probe_suite_id)
        if stress_probe_suite_id:
            required.add(stress_probe_suite_id)
    return required


def _validate_probe_suite_resolution_contract(*, utility_policy: dict[str, Any] | None) -> None:
    required_suite_ids = sorted(_required_probe_suite_ids_from_utility_policy(utility_policy=utility_policy))
    if not required_suite_ids:
        return
    available_suite_ids = sorted(_available_probe_suite_ids(utility_policy=utility_policy))
    missing_suite_ids = sorted(set(required_suite_ids) - set(available_suite_ids))
    if missing_suite_ids:
        print(
            json.dumps(
                {
                    "event": "HEAVY_POLICY_PROBE_REGISTRY_MISSING_V1",
                    "reason_code": "HEAVY_POLICY_PROBE_REGISTRY_MISSING",
                    "required_suite_ids": required_suite_ids,
                    "available_suite_ids": available_suite_ids,
                    "missing_suite_ids": missing_suite_ids,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        fail("HEAVY_POLICY_PROBE_REGISTRY_MISSING")


def _required_probe_ids_for_capability(
    *,
    utility_policy: dict[str, Any] | None,
    capability_id: str,
) -> tuple[list[str], bool]:
    if str(capability_id).strip() == _SH1_CAPABILITY_ID:
        return [str(row) for row in _BUILTIN_PROBE_SUITE_IDS], True
    if not isinstance(utility_policy, dict):
        return [], False
    heavy_policies = utility_policy.get("heavy_policies")
    if not isinstance(heavy_policies, dict):
        return [], False
    heavy_policy = heavy_policies.get(str(capability_id))
    if not isinstance(heavy_policy, dict):
        return [], False
    eligible_raw = heavy_policy.get("frontier_heavy_eligible_b")
    frontier_heavy_eligible_b = bool(eligible_raw) if isinstance(eligible_raw, bool) else True
    required_probe_ids = heavy_policy.get("required_probe_ids_v1")
    if isinstance(required_probe_ids, list):
        normalized = _sorted_unique_strings(required_probe_ids)
        return normalized, frontier_heavy_eligible_b
    required_probe_id = str(heavy_policy.get("required_probe_id", "")).strip()
    if required_probe_id:
        return [required_probe_id], frontier_heavy_eligible_b
    fallback = _sorted_unique_strings(
        [
            str(heavy_policy.get("probe_suite_id", "")).strip(),
            str(heavy_policy.get("stress_probe_suite_id", "")).strip(),
        ]
    )
    return fallback, frontier_heavy_eligible_b


def _probe_coverage_gate_for_capability(
    *,
    utility_policy: dict[str, Any] | None,
    capability_id: str,
    declared_class: str,
) -> tuple[bool, str | None, dict[str, Any]]:
    declared = str(declared_class).strip().upper()
    heavy_block_reason = "HEAVY_BLOCKED_PROBE_MISSING"
    if declared not in _HEAVY_DECLARED_CLASSES:
        return True, None, {"required_probe_ids_v1": [], "missing_probe_ids_v1": [], "missing_probe_assets_v1": []}
    if str(capability_id).strip() == _SH1_CAPABILITY_ID:
        return True, None, {"required_probe_ids_v1": [], "missing_probe_ids_v1": [], "missing_probe_assets_v1": []}
    required_probe_ids, heavy_eligible_b = _required_probe_ids_for_capability(
        utility_policy=utility_policy,
        capability_id=str(capability_id),
    )
    registry = _probe_registry_v1_from_utility_policy(utility_policy)
    if not heavy_eligible_b:
        return (
            False,
            heavy_block_reason,
            {
                "required_probe_ids_v1": list(required_probe_ids),
                "missing_probe_ids_v1": list(required_probe_ids),
                "missing_probe_assets_v1": [],
            },
        )
    if not required_probe_ids:
        return False, heavy_block_reason, {"required_probe_ids_v1": [], "missing_probe_ids_v1": [], "missing_probe_assets_v1": []}
    missing_probe_ids = [probe_id for probe_id in required_probe_ids if probe_id not in registry]
    if missing_probe_ids:
        return (
            False,
            heavy_block_reason,
            {
                "required_probe_ids_v1": list(required_probe_ids),
                "missing_probe_ids_v1": list(missing_probe_ids),
                "missing_probe_assets_v1": [],
            },
        )
    root = repo_root().resolve()
    missing_assets: list[dict[str, str]] = []
    for probe_id in required_probe_ids:
        row = registry.get(str(probe_id)) or {}
        assets = row.get("required_asset_relpaths_v1", [])
        if not isinstance(assets, list):
            fail("SCHEMA_FAIL")
        for rel in assets:
            asset_rel = _require_safe_relpath(rel)
            candidate = (root / asset_rel).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                fail("SCHEMA_FAIL")
            if not candidate.exists():
                missing_assets.append(
                    {
                        "probe_id": str(probe_id),
                        "asset_relpath": str(asset_rel),
                    }
                )
    if missing_assets:
        return (
            False,
            "DROPPED_PROBE_ASSET_MISSING",
            {
                "required_probe_ids_v1": list(required_probe_ids),
                "missing_probe_ids_v1": [],
                "missing_probe_assets_v1": missing_assets,
            },
        )
    return True, None, {"required_probe_ids_v1": list(required_probe_ids), "missing_probe_ids_v1": [], "missing_probe_assets_v1": []}


def _probe_covered_fallback_capability(
    *,
    utility_policy: dict[str, Any] | None,
    lane_allowed_capability_ids: list[str],
    current_capability_id: str,
    registry: dict[str, Any],
    tick_u64: int,
    state: dict[str, Any],
) -> tuple[str | None, dict[str, Any] | None]:
    candidate_ids = _sorted_unique_strings([_SH1_CAPABILITY_ID, *list(lane_allowed_capability_ids)])
    for capability_id in candidate_ids:
        candidate_capability_id = str(capability_id).strip()
        if not candidate_capability_id or candidate_capability_id == str(current_capability_id).strip():
            continue
        declared_class = _declared_class_for_capability_id(
            utility_policy=utility_policy,
            capability_id=candidate_capability_id,
        )
        gate_pass_b, _drop_code, _drop_detail = _probe_coverage_gate_for_capability(
            utility_policy=utility_policy,
            capability_id=candidate_capability_id,
            declared_class=declared_class,
        )
        if not gate_pass_b:
            continue
        cap_row = _capability_id_to_campaign(
            registry=registry,
            capability_id=candidate_capability_id,
            tick_u64=int(tick_u64),
            state=state,
        )
        if cap_row is None:
            cap_row = _capability_row_for_forced_frontier(
                registry=registry,
                capability_id=candidate_capability_id,
            )
        if cap_row is not None:
            return candidate_capability_id, cap_row
    return None, None


def _capability_id_to_campaign(
    *,
    registry: dict[str, Any],
    capability_id: str,
    tick_u64: int,
    state: dict[str, Any],
) -> dict[str, Any] | None:
    caps = registry.get("capabilities")
    if not isinstance(caps, list):
        fail("SCHEMA_FAIL")
    for row in sorted([entry for entry in caps if isinstance(entry, dict)], key=lambda entry: str(entry.get("campaign_id", ""))):
        if str(row.get("capability_id", "")).strip() != str(capability_id):
            continue
        if not bool(row.get("enabled", False)):
            continue
        campaign_id = str(row.get("campaign_id", "")).strip()
        if not campaign_id:
            continue
        cooldown = int((((state.get("cooldowns") or {}).get(campaign_id) or {}).get("next_tick_allowed_u64", 0)))
        if cooldown > int(tick_u64):
            continue
        cost_q = int(((row.get("budget_cost_hint_q32") or {}).get("q", 0)))
        if not has_budget(state.get("budget_remaining") or {}, cost_q32=cost_q):
            continue
        return row
    return None


def _capability_row_for_forced_frontier(
    *,
    registry: dict[str, Any],
    capability_id: str,
) -> dict[str, Any] | None:
    caps = registry.get("capabilities")
    if not isinstance(caps, list):
        fail("SCHEMA_FAIL")
    for row in sorted([entry for entry in caps if isinstance(entry, dict)], key=lambda entry: str(entry.get("campaign_id", ""))):
        if str(row.get("capability_id", "")).strip() != str(capability_id):
            continue
        if not bool(row.get("enabled", False)):
            continue
        campaign_id = str(row.get("campaign_id", "")).strip()
        if not campaign_id:
            continue
        return row
    return None


def _recompute_decision_plan_identity(plan: dict[str, Any]) -> tuple[dict[str, Any], str]:
    inputs_hash = canon_hash_obj(
        {
            "tick_u64": plan.get("tick_u64"),
            "observation_report_hash": plan.get("observation_report_hash"),
            "issue_bundle_hash": plan.get("issue_bundle_hash"),
            "policy_hash": plan.get("policy_hash"),
            "registry_hash": plan.get("registry_hash"),
            "budgets_hash": plan.get("budgets_hash"),
            "action_kind": plan.get("action_kind"),
            "campaign_id": plan.get("campaign_id"),
            "capability_id": plan.get("capability_id"),
            "goal_id": plan.get("goal_id"),
            "assigned_capability_id": plan.get("assigned_capability_id"),
            "runaway_selected_metric_id": plan.get("runaway_selected_metric_id"),
            "runaway_escalation_level_u64": plan.get("runaway_escalation_level_u64"),
            "runaway_env_overrides": plan.get("runaway_env_overrides"),
        }
    )
    materialized = dict(plan)
    materialized["recompute_proof"] = {"inputs_hash": inputs_hash, "plan_hash": _SHA256_ZERO}
    no_id = dict(materialized)
    no_id.pop("plan_id", None)
    plan_id = canon_hash_obj(no_id)
    materialized["plan_id"] = plan_id
    materialized["recompute_proof"] = {"inputs_hash": inputs_hash, "plan_hash": plan_id}
    validate_schema(materialized, "omega_decision_plan_v1")
    return materialized, canon_hash_obj(materialized)


def _sha256_or_zero(value: Any) -> str:
    candidate = str(value or "").strip()
    if _is_sha256(candidate):
        return candidate
    return _SHA256_ZERO


def _bind_decision_plan_to_inputs_descriptor(
    *,
    decision_plan: dict[str, Any],
    inputs_descriptor_hash: str,
) -> tuple[dict[str, Any], str]:
    descriptor_hash = ensure_sha256(inputs_descriptor_hash, reason="SCHEMA_FAIL")
    materialized = dict(decision_plan)
    materialized["recompute_proof"] = {"inputs_hash": descriptor_hash, "plan_hash": _SHA256_ZERO}
    no_id = dict(materialized)
    no_id.pop("plan_id", None)
    plan_id = canon_hash_obj(no_id)
    materialized["plan_id"] = plan_id
    materialized["recompute_proof"] = {"inputs_hash": descriptor_hash, "plan_hash": plan_id}
    validate_schema(materialized, "omega_decision_plan_v1")
    return materialized, canon_hash_obj(materialized)


def _goal_frontier_id(*, row: dict[str, Any], capability_id: str) -> str | None:
    raw = str(row.get("frontier_id", "")).strip()
    if raw:
        return raw
    return None


def _stable_frontier_id_for_capability(capability_id: str) -> str:
    token = re.sub(r"[^a-z0-9_]+", "_", str(capability_id).strip().lower()).strip("_") or "x"
    return token


def _normalize_goal_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("goals")
    if not isinstance(rows, list):
        fail("SCHEMA_FAIL")
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        goal_id = str(row.get("goal_id", "")).strip()
        capability_id = str(row.get("capability_id", "")).strip()
        status = str(row.get("status", "PENDING")).strip()
        if not goal_id or not capability_id or status not in _GOAL_STATUSES:
            fail("SCHEMA_FAIL")
        out.append(
            {
                "goal_id": goal_id,
                "capability_id": capability_id,
                "frontier_id": _goal_frontier_id(row=row, capability_id=capability_id),
                "status": status,
            }
        )
    return out


def _lane_goal_rows(
    *,
    tick_u64: int,
    lane_name: str,
    capability_ids: list[str],
) -> list[dict[str, Any]]:
    if lane_name not in _LANE_NAMES:
        fail("SCHEMA_FAIL")
    if lane_name == "BASELINE":
        return []
    prefix = "goal_auto_10_lane_canary_" if lane_name == "CANARY" else "goal_auto_90_lane_frontier_"
    out: list[dict[str, Any]] = []
    for idx, capability_id in enumerate(sorted({str(row).strip() for row in capability_ids if str(row).strip()})):
        token = re.sub(r"[^a-z0-9_]+", "_", capability_id.lower()).strip("_") or "x"
        goal_id = f"{prefix}{token}_{int(tick_u64):06d}_{int(idx):02d}"
        out.append(
            {
                "goal_id": goal_id,
                "capability_id": capability_id,
                "frontier_id": _stable_frontier_id_for_capability(capability_id),
                "status": "PENDING",
            }
        )
    return out


def _merge_goal_rows(*, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        goal_id = str(row.get("goal_id", "")).strip()
        capability_id = str(row.get("capability_id", "")).strip()
        frontier_id = str(row.get("frontier_id", "")).strip() or None
        status = str(row.get("status", "PENDING")).strip()
        if not goal_id or not capability_id or status not in _GOAL_STATUSES:
            fail("SCHEMA_FAIL")
        if goal_id not in by_id:
            by_id[goal_id] = {
                "goal_id": goal_id,
                "capability_id": capability_id,
                "frontier_id": frontier_id,
                "status": status,
            }
    return [by_id[key] for key in sorted(by_id.keys())]


def _filter_pending_goals_for_lane(*, rows: list[dict[str, Any]], allowed_capability_ids: list[str]) -> list[dict[str, Any]]:
    allowed = set(allowed_capability_ids)
    out: list[dict[str, Any]] = []
    for row in rows:
        status = str(row["status"]).strip()
        if status != "PENDING" or str(row["capability_id"]).strip() in allowed:
            out.append(dict(row))
    return out


def _load_prev_health_window(*, prev_state_dir: Path | None, window_ticks_u64: int) -> dict[str, Any]:
    out: dict[str, Any] = {
        "schema_name": "long_run_health_window_v1",
        "schema_version": "v19_0",
        "window_ticks_u64": int(max(1, int(window_ticks_u64))),
        "rows": [],
    }
    if prev_state_dir is None:
        return out
    health_dir = Path(prev_state_dir) / "long_run" / "health"
    if not health_dir.exists() or not health_dir.is_dir():
        return out
    rows = sorted(health_dir.glob("sha256_*.long_run_health_window_v1.json"), key=lambda p: p.as_posix())
    if not rows:
        return out
    payload = load_canon_dict(rows[-1])
    if str(payload.get("schema_name", "")).strip() != "long_run_health_window_v1":
        fail("SCHEMA_FAIL")
    if str(payload.get("schema_version", "")).strip() != "v19_0":
        fail("SCHEMA_FAIL")
    window = max(1, int(payload.get("window_ticks_u64", out["window_ticks_u64"])))
    raw_rows = payload.get("rows")
    if not isinstance(raw_rows, list):
        fail("SCHEMA_FAIL")
    normalized_rows: list[dict[str, Any]] = []
    for row in raw_rows:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        normalized_rows.append(
            {
                "tick_u64": int(max(0, int(row.get("tick_u64", 0)))),
                "invalid_b": bool(row.get("invalid_b", False)),
                "budget_exhaust_b": bool(row.get("budget_exhaust_b", False)),
                "route_disabled_b": bool(row.get("route_disabled_b", False)),
            }
        )
    if len(normalized_rows) > window:
        normalized_rows = normalized_rows[-window:]
    return {
        "schema_name": "long_run_health_window_v1",
        "schema_version": "v19_0",
        "window_ticks_u64": int(window),
        "rows": normalized_rows,
    }


def _health_counts(window_payload: dict[str, Any]) -> dict[str, int]:
    rows = window_payload.get("rows")
    if not isinstance(rows, list):
        fail("SCHEMA_FAIL")
    invalid_count = 0
    budget_count = 0
    route_count = 0
    for row in rows:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        if bool(row.get("invalid_b", False)):
            invalid_count += 1
        if bool(row.get("budget_exhaust_b", False)):
            budget_count += 1
        if bool(row.get("route_disabled_b", False)):
            route_count += 1
    return {
        "invalid_count_u64": int(invalid_count),
        "budget_exhaust_count_u64": int(budget_count),
        "route_disabled_count_u64": int(route_count),
    }


def _recent_heavy_utility_ok_counts(*, prev_state_dir: Path | None) -> dict[str, int]:
    out = {
        "last_50_heavy_utility_ok_u64": 0,
        "last_200_heavy_utility_ok_u64": 0,
    }
    if prev_state_dir is None:
        return out
    perf_dir = Path(prev_state_dir) / "perf"
    if not perf_dir.exists() or not perf_dir.is_dir():
        return out
    rows: list[tuple[int, str, bool]] = []
    for path in sorted(perf_dir.glob("sha256_*.omega_tick_outcome_v1.json"), key=lambda p: p.as_posix()):
        payload = load_canon_dict(path)
        if str(payload.get("schema_version", "")).strip() != "omega_tick_outcome_v1":
            continue
        tick_u64 = int(payload.get("tick_u64", -1))
        if tick_u64 < 0:
            continue
        declared_class = str(payload.get("declared_class", "")).strip().upper()
        effect_class = str(payload.get("effect_class", "")).strip().upper()
        heavy_utility_ok_b = bool(
            declared_class in _HEAVY_DECLARED_CLASSES
            and effect_class == "EFFECT_HEAVY_OK"
        )
        rows.append((tick_u64, path.as_posix(), heavy_utility_ok_b))
    if not rows:
        return out
    rows.sort(key=lambda row: (int(row[0]), str(row[1])))
    last_50 = rows[-int(_UTILITY_RECOVERY_WINDOW_SHORT_U64) :]
    last_200 = rows[-int(_UTILITY_RECOVERY_WINDOW_LONG_U64) :]
    out["last_50_heavy_utility_ok_u64"] = int(sum(1 for row in last_50 if bool(row[2])))
    out["last_200_heavy_utility_ok_u64"] = int(sum(1 for row in last_200 if bool(row[2])))
    return out


def _frontier_progress_totals(*, prev_state_dir: Path | None) -> dict[str, int]:
    out = {
        "frontier_attempt_counted_total_u64": 0,
        "heavy_utility_ok_total_u64": 0,
        "heavy_promoted_total_u64": 0,
    }
    if prev_state_dir is None:
        return out
    perf_dir = Path(prev_state_dir) / "perf"
    if not perf_dir.exists() or not perf_dir.is_dir():
        return out
    frontier_attempt_counted_total_u64 = 0
    heavy_utility_ok_total_u64 = 0
    heavy_promoted_total_u64 = 0
    for path in sorted(perf_dir.glob("sha256_*.omega_tick_outcome_v1.json"), key=lambda p: p.as_posix()):
        payload = load_canon_dict(path)
        if str(payload.get("schema_version", "")).strip() != "omega_tick_outcome_v1":
            continue
        if bool(payload.get("frontier_attempt_counted_b", False)):
            frontier_attempt_counted_total_u64 += 1
        declared_class = str(payload.get("declared_class", "")).strip().upper()
        effect_class = str(payload.get("effect_class", "")).strip().upper()
        promotion_status = str(payload.get("promotion_status", "")).strip().upper()
        heavy_declared_b = declared_class in _HEAVY_DECLARED_CLASSES
        if heavy_declared_b and effect_class == "EFFECT_HEAVY_OK":
            heavy_utility_ok_total_u64 += 1
        if heavy_declared_b and promotion_status == "PROMOTED":
            heavy_promoted_total_u64 += 1
    out["frontier_attempt_counted_total_u64"] = int(frontier_attempt_counted_total_u64)
    out["heavy_utility_ok_total_u64"] = int(heavy_utility_ok_total_u64)
    out["heavy_promoted_total_u64"] = int(heavy_promoted_total_u64)
    return out


def _preferred_utility_recovery_capability(*, prev_dependency_debt_state: dict[str, Any] | None) -> str:
    rows_raw = (prev_dependency_debt_state or {}).get("heavy_ok_count_by_capability")
    if not isinstance(rows_raw, dict):
        return _SH1_CAPABILITY_ID
    rows: list[tuple[int, str]] = []
    for capability_id, value in rows_raw.items():
        key = str(capability_id).strip()
        if not key:
            continue
        count = int(max(0, int(value)))
        if count <= 0:
            continue
        rows.append((count, key))
    if not rows:
        return _SH1_CAPABILITY_ID
    rows.sort(key=lambda row: (-int(row[0]), str(row[1])))
    return str(rows[0][1])


def _resolve_lane(
    *,
    tick_u64: int,
    long_run_profile: dict[str, Any],
    prev_health_window: dict[str, Any],
) -> tuple[str, list[str], bool, list[str], dict[str, int]]:
    cadence = long_run_profile.get("lane_cadence")
    lanes = long_run_profile.get("lanes")
    health_gate = long_run_profile.get("frontier_health_gate")
    if not isinstance(cadence, dict) or not isinstance(lanes, dict) or not isinstance(health_gate, dict):
        fail("SCHEMA_FAIL")

    canary_every = max(1, int(cadence.get("canary_every_ticks_u64", 10)))
    frontier_every = max(1, int(cadence.get("frontier_every_ticks_u64", 100)))
    counts = _health_counts(prev_health_window)
    frontier_gate_pass = (
        int(counts["invalid_count_u64"]) <= int(max(0, int(health_gate.get("max_invalid_u64", 0))))
        and int(counts["budget_exhaust_count_u64"]) <= int(max(0, int(health_gate.get("max_budget_exhaust_u64", 0))))
        and int(counts["route_disabled_count_u64"]) <= int(max(0, int(health_gate.get("max_route_disabled_u64", 0))))
    )

    reasons: list[str] = []
    forced = str(os.environ.get("OMEGA_LONG_RUN_FORCE_LANE", "")).strip().upper()
    if forced in _LANE_NAMES:
        lane_name = forced
        reasons.append("FORCED_LANE_OVERRIDE")
        if lane_name == "FRONTIER" and not frontier_gate_pass:
            reasons.append("FORCED_FRONTIER_BYPASS_HEALTH")
    else:
        frontier_due = int(tick_u64) > 0 and (int(tick_u64) % int(frontier_every) == 0)
        canary_due = int(tick_u64) > 0 and (int(tick_u64) % int(canary_every) == 0)
        if frontier_due and frontier_gate_pass:
            lane_name = "FRONTIER"
            reasons.append("CADENCE_FRONTIER")
        elif frontier_due and not frontier_gate_pass:
            lane_name = "CANARY" if canary_due else "BASELINE"
            reasons.append("FRONTIER_HEALTH_BLOCKED")
        elif canary_due:
            lane_name = "CANARY"
            reasons.append("CADENCE_CANARY")
        else:
            lane_name = "BASELINE"
            reasons.append("CADENCE_BASELINE")

    lane_key = {
        "BASELINE": "baseline_capability_ids",
        "CANARY": "canary_capability_ids",
        "FRONTIER": "frontier_capability_ids",
    }[lane_name]
    allowed = _sorted_unique_strings((lanes.get(lane_key) or []))
    return lane_name, allowed, frontier_gate_pass, reasons, counts


def _build_lane_decision_receipt(
    *,
    tick_u64: int,
    lane_name: str,
    forced_lane_override_b: bool,
    frontier_gate_pass_b: bool,
    reason_codes: list[str],
    health_window_ticks_u64: int,
    health_counts: dict[str, int],
    allowed_capability_ids: list[str],
    resolved_orch_llm_backend: str,
    resolved_orch_model_id: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_name": "lane_decision_receipt_v1",
        "schema_version": "v19_0",
        "receipt_id": "sha256:" + ("0" * 64),
        "tick_u64": int(tick_u64),
        "lane_name": lane_name,
        "forced_lane_override_b": bool(forced_lane_override_b),
        "frontier_gate_pass_b": bool(frontier_gate_pass_b),
        "reason_codes": [str(row) for row in reason_codes],
        "resolved_orch_llm_backend": str(resolved_orch_llm_backend).strip().lower(),
        "resolved_orch_model_id": str(resolved_orch_model_id).strip(),
        "health_window": {
            "window_ticks_u64": int(max(1, int(health_window_ticks_u64))),
            "invalid_count_u64": int(max(0, int(health_counts.get("invalid_count_u64", 0)))),
            "budget_exhaust_count_u64": int(max(0, int(health_counts.get("budget_exhaust_count_u64", 0)))),
            "route_disabled_count_u64": int(max(0, int(health_counts.get("route_disabled_count_u64", 0))),
            ),
        },
        "allowed_capability_ids": _sorted_unique_strings(list(allowed_capability_ids)),
    }
    no_id = dict(payload)
    no_id.pop("receipt_id", None)
    payload["receipt_id"] = canon_hash_obj(no_id)
    validate_schema_v19(payload, "lane_decision_receipt_v1")
    return payload


def _persist_lane_decision_receipt_final(*, state_root: Path, lane_decision_receipt: dict[str, Any]) -> str:
    lane_dir = state_root / "long_run" / "lane"
    _, persisted_obj, lane_decision_receipt_hash = _write_payload_atomic(
        lane_dir,
        "lane_decision_receipt_v1.json",
        lane_decision_receipt,
        id_field="receipt_id",
    )
    final_path = lane_dir / _LANE_RECEIPT_FINAL_NAME
    content = canon_bytes(persisted_obj) + b"\n"
    if final_path.exists():
        existing = final_path.read_bytes()
        if existing.rstrip(b"\n") != content.rstrip(b"\n"):
            fail("NONDETERMINISTIC")
    else:
        final_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.write_bytes(content)
    return lane_decision_receipt_hash


def _next_health_window(
    *,
    prev_window: dict[str, Any],
    tick_u64: int,
    tick_outcome: dict[str, Any],
    shadow_summary_payload: dict[str, Any],
) -> dict[str, Any]:
    window_ticks_u64 = int(max(1, int(prev_window.get("window_ticks_u64", 100))))
    rows = prev_window.get("rows")
    if not isinstance(rows, list):
        fail("SCHEMA_FAIL")
    next_rows = [dict(row) for row in rows if isinstance(row, dict)]
    route_disabled_u64 = int(max(0, int(shadow_summary_payload.get("route_disabled_modules_u64", 0))))
    subverifier_status = str(tick_outcome.get("subverifier_status", "")).strip().upper()
    action_kind = str(tick_outcome.get("action_kind", "")).strip().upper()
    promotion_reason_code = str(tick_outcome.get("promotion_reason_code", "")).strip().upper()
    invalid_b = subverifier_status == "INVALID"
    benign_invalid_b = (
        invalid_b
        and action_kind == "SAFE_HALT"
        and promotion_reason_code == "SUBVERIFIER_INVALID"
    )
    next_rows.append(
        {
            "tick_u64": int(tick_u64),
            # SAFE_HALT driven subverifier invalids are expected control outcomes.
            "invalid_b": bool(invalid_b and not benign_invalid_b),
            "budget_exhaust_b": str(tick_outcome.get("noop_reason", "")).strip() == "BUDGET",
            "route_disabled_b": route_disabled_u64 > 0,
        }
    )
    if len(next_rows) > window_ticks_u64:
        next_rows = next_rows[-window_ticks_u64:]
    return {
        "schema_name": "long_run_health_window_v1",
        "schema_version": "v19_0",
        "window_ticks_u64": int(window_ticks_u64),
        "rows": next_rows,
    }


def _default_dependency_debt_state(*, tick_u64: int) -> dict[str, Any]:
    payload = {
        "schema_name": "dependency_debt_state_v1",
        "schema_version": "v19_0",
        "state_id": _SHA256_ZERO,
        "tick_u64": int(max(0, int(tick_u64))),
        "debt_by_key": {},
        "ticks_without_frontier_attempt_by_key": {},
        "first_debt_tick_by_key": {},
        "debt_by_goal_id": {},
        "ticks_without_frontier_attempt_by_goal_id": {},
        "first_debt_tick_by_goal_id": {},
        "maintenance_since_last_frontier_attempt_u64": 0,
        "last_frontier_attempt_tick_u64": 0,
        "last_frontier_attempt_debt_key": None,
        "last_frontier_attempt_goal_id": None,
        "hard_lock_active_b": False,
        "hard_lock_debt_key": None,
        "hard_lock_goal_id": None,
        "scaffold_inflight_ccap_id": None,
        "scaffold_inflight_started_tick_u64": None,
        "max_inflight_ccap_ids_u32": 1,
        "reason_code": "N/A",
        "heavy_ok_count_by_capability": {},
        "heavy_no_utility_count_by_capability": {},
        "maintenance_count_u64": 0,
        "frontier_attempts_u64": 0,
        "failed_patch_ban_by_debt_key_target": {},
        "failed_shape_ban_by_debt_key_target": {},
        "last_failure_nontriviality_cert_by_debt_key": {},
        "last_failure_failed_threshold_by_debt_key": {},
    }
    validate_schema_v19(payload, "dependency_debt_state_v1")
    return payload


def _load_prev_dependency_debt_state(*, prev_state_dir: Path | None) -> dict[str, Any]:
    if prev_state_dir is None:
        return _default_dependency_debt_state(tick_u64=0)
    debt_dir = Path(prev_state_dir) / "long_run" / "debt"
    if not debt_dir.exists() or not debt_dir.is_dir():
        return _default_dependency_debt_state(tick_u64=0)
    rows = sorted(debt_dir.glob("sha256_*.dependency_debt_state_v1.json"), key=lambda p: p.as_posix())
    if not rows:
        return _default_dependency_debt_state(tick_u64=0)
    payload = dict(load_canon_dict(rows[-1]))
    payload.setdefault("debt_by_key", {})
    payload.setdefault("ticks_without_frontier_attempt_by_key", {})
    payload.setdefault("first_debt_tick_by_key", {})
    payload.setdefault("last_frontier_attempt_debt_key", None)
    payload.setdefault("hard_lock_debt_key", None)
    payload.setdefault("scaffold_inflight_ccap_id", None)
    payload.setdefault("scaffold_inflight_started_tick_u64", None)
    payload.setdefault("max_inflight_ccap_ids_u32", 1)
    payload.setdefault("failed_patch_ban_by_debt_key_target", {})
    payload.setdefault("failed_shape_ban_by_debt_key_target", {})
    payload.setdefault("last_failure_nontriviality_cert_by_debt_key", {})
    payload.setdefault("last_failure_failed_threshold_by_debt_key", {})
    if not isinstance(payload.get("debt_by_key"), dict):
        payload["debt_by_key"] = {}
    if not isinstance(payload.get("ticks_without_frontier_attempt_by_key"), dict):
        payload["ticks_without_frontier_attempt_by_key"] = {}
    if not isinstance(payload.get("first_debt_tick_by_key"), dict):
        payload["first_debt_tick_by_key"] = {}
    if not isinstance(payload.get("failed_patch_ban_by_debt_key_target"), dict):
        payload["failed_patch_ban_by_debt_key_target"] = {}
    if not isinstance(payload.get("failed_shape_ban_by_debt_key_target"), dict):
        payload["failed_shape_ban_by_debt_key_target"] = {}
    if not isinstance(payload.get("last_failure_nontriviality_cert_by_debt_key"), dict):
        payload["last_failure_nontriviality_cert_by_debt_key"] = {}
    if not isinstance(payload.get("last_failure_failed_threshold_by_debt_key"), dict):
        payload["last_failure_failed_threshold_by_debt_key"] = {}
    validate_schema_v19(payload, "dependency_debt_state_v1")
    return payload


def _default_anti_monopoly_state(*, tick_u64: int) -> dict[str, Any]:
    payload = {
        "schema_name": "anti_monopoly_state_v1",
        "schema_version": "v19_0",
        "state_id": _SHA256_ZERO,
        "tick_u64": int(max(0, int(tick_u64))),
        "window_ticks_u64": int(_DEFAULT_ANTI_MONOPOLY_WINDOW_U64),
        "consecutive_no_output_limit_u64": int(_DEFAULT_ANTI_MONOPOLY_CONSECUTIVE_LIMIT_U64),
        "low_diversity_campaign_limit_u64": int(_DEFAULT_ANTI_MONOPOLY_DIVERSITY_K_U64),
        "cooldown_for_ticks_u64": int(_DEFAULT_ANTI_MONOPOLY_COOLDOWN_U64),
        "campaign_cooldowns": {},
        "history_rows": [],
        "last_reason_code": "N/A",
    }
    validate_schema_v19(payload, "anti_monopoly_state_v1")
    return payload


def _load_prev_anti_monopoly_state(*, prev_state_dir: Path | None) -> dict[str, Any]:
    if prev_state_dir is None:
        return _default_anti_monopoly_state(tick_u64=0)
    anti_dir = Path(prev_state_dir) / "long_run" / "anti_monopoly"
    if not anti_dir.exists() or not anti_dir.is_dir():
        return _default_anti_monopoly_state(tick_u64=0)
    rows = sorted(anti_dir.glob("sha256_*.anti_monopoly_state_v1.json"), key=lambda p: p.as_posix())
    if not rows:
        return _default_anti_monopoly_state(tick_u64=0)
    payload = load_canon_dict(rows[-1])
    validate_schema_v19(payload, "anti_monopoly_state_v1")
    return payload


def _pending_frontier_goals(
    *,
    goal_queue: dict[str, Any],
    frontier_capability_ids: list[str],
) -> list[dict[str, str]]:
    rows = goal_queue.get("goals")
    if not isinstance(rows, list):
        fail("SCHEMA_FAIL")
    frontier_set = {str(row).strip() for row in frontier_capability_ids if str(row).strip()}
    out: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        status = str(row.get("status", "PENDING")).strip()
        goal_id = str(row.get("goal_id", "")).strip()
        capability_id = str(row.get("capability_id", "")).strip()
        if status != "PENDING":
            continue
        if capability_id not in frontier_set:
            continue
        frontier_id = str(row.get("frontier_id", "")).strip()
        if frontier_id.lower() in {"none", "null", "nil", "n/a"}:
            frontier_id = ""
        if not goal_id or not capability_id:
            fail("SCHEMA_FAIL")
        if not frontier_id:
            frontier_id = capability_id
        frontier_id = str(frontier_id).strip().lower()
        debt_key = _derive_debt_key(frontier_id=frontier_id, capability_id=capability_id)
        out.append(
            {
                "goal_id": goal_id,
                "capability_id": capability_id,
                "frontier_id": frontier_id,
                "debt_key": debt_key,
            }
        )
    return sorted(
        out,
        key=lambda row: (
            str(row["goal_id"]),
            str(row["capability_id"]),
            str(row.get("frontier_id", "")),
            str(row.get("debt_key", "")),
        ),
    )


def _derive_debt_key(*, frontier_id: str | None, capability_id: str) -> str:
    frontier = str(frontier_id or "").strip()
    if frontier.lower() in {"none", "null", "nil", "n/a"}:
        frontier = ""
    if frontier:
        return f"frontier:{frontier}"
    capability = str(capability_id).strip()
    if not capability:
        fail("SCHEMA_FAIL")
    return f"capability:{capability}"


def _u64_map(raw: Any) -> dict[str, int]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int] = {}
    for key, value in raw.items():
        key_s = str(key).strip()
        if not key_s:
            continue
        out[key_s] = int(max(0, int(value)))
    return out


def _normalize_sha256(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text.startswith("sha256:"):
        return None
    digest = text.split(":", 1)[1]
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        return None
    return f"sha256:{digest}"


def _normalize_patch_sha256(value: Any) -> str | None:
    return _normalize_sha256(value)


def _normalize_relpath(value: Any) -> str | None:
    rel = str(value or "").strip().replace("\\", "/")
    if not rel:
        return None
    path = Path(rel)
    if path.is_absolute() or ".." in path.parts:
        return None
    return rel


def _normalize_target_relpaths(raw: Any) -> list[str]:
    rows: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            rel = _normalize_relpath(item)
            if rel is None or rel in rows:
                continue
            rows.append(rel)
    rows = sorted(rows)
    if len(rows) > 2:
        rows = rows[:2]
    return rows


def _target_relpaths_key(*, target_relpaths: list[str]) -> str:
    rows = _normalize_target_relpaths(target_relpaths)
    if not rows:
        return ""
    return "||".join(rows)


def _target_relpaths_from_key(target_key: str) -> list[str]:
    rows = [item for item in str(target_key).split("||") if item]
    return _normalize_target_relpaths(rows)


def _failed_patch_ban_key(*, debt_key: str, target_key: str) -> str:
    return f"{str(debt_key).strip()}|{str(target_key).strip()}"


def _normalize_patch_ban_entry(*, raw: Any, now_tick_u64: int) -> dict[str, Any] | None:
    patch_sha256: str | None = None
    expires_tick_u64: int | None = None
    if isinstance(raw, str):
        patch_sha256 = _normalize_patch_sha256(raw)
        expires_tick_u64 = int(max(0, int(now_tick_u64 + _FAILED_PATCH_BAN_TTL_TICKS_U64)))
    elif isinstance(raw, dict):
        patch_sha256 = _normalize_patch_sha256(raw.get("patch_sha256"))
        raw_exp = raw.get("expires_tick_u64")
        if isinstance(raw_exp, int):
            expires_tick_u64 = int(max(0, int(raw_exp)))
    if patch_sha256 is None or expires_tick_u64 is None:
        return None
    if int(expires_tick_u64) < int(now_tick_u64):
        return None
    return {
        "patch_sha256": patch_sha256,
        "expires_tick_u64": int(expires_tick_u64),
    }


def _normalize_shape_ban_entry(*, raw: Any, now_tick_u64: int) -> dict[str, Any] | None:
    shape_id: str | None = None
    expires_tick_u64: int | None = None
    if isinstance(raw, str):
        shape_id = _normalize_sha256(raw)
        expires_tick_u64 = int(max(0, int(now_tick_u64 + _FAILED_SHAPE_BAN_TTL_TICKS_U64)))
    elif isinstance(raw, dict):
        shape_id = _normalize_sha256(raw.get("shape_id"))
        raw_exp = raw.get("expires_tick_u64")
        if isinstance(raw_exp, int):
            expires_tick_u64 = int(max(0, int(raw_exp)))
    if shape_id is None or expires_tick_u64 is None:
        return None
    if int(expires_tick_u64) < int(now_tick_u64):
        return None
    return {
        "shape_id": shape_id,
        "expires_tick_u64": int(expires_tick_u64),
    }


def _failed_patch_ban_map(raw: Any, *, now_tick_u64: int) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    for key, value in sorted(raw.items(), key=lambda kv: str(kv[0])):
        key_text = str(key).strip()
        if not key_text or "|" not in key_text:
            continue
        if not isinstance(value, list):
            continue
        by_patch: dict[str, int] = {}
        for item in value:
            entry = _normalize_patch_ban_entry(raw=item, now_tick_u64=int(now_tick_u64))
            if entry is None:
                continue
            patch = str(entry["patch_sha256"])
            exp = int(entry["expires_tick_u64"])
            by_patch[patch] = int(max(int(by_patch.get(patch, 0)), exp))
        if not by_patch:
            continue
        rows = [
            {"patch_sha256": patch, "expires_tick_u64": int(exp)}
            for patch, exp in sorted(by_patch.items(), key=lambda kv: (int(kv[1]), str(kv[0])))
        ]
        out[key_text] = rows[-_MAX_FAILED_PATCH_BAN_PER_KEY :]
    if len(out) > _MAX_FAILED_PATCH_BAN_KEYS:
        keys = sorted(out.keys())
        keep = set(keys[-_MAX_FAILED_PATCH_BAN_KEYS :])
        out = {k: list(v) for k, v in out.items() if k in keep}
    return {str(k): list(v) for k, v in sorted(out.items(), key=lambda kv: str(kv[0]))}


def _update_failed_patch_ban_map(
    *,
    prev_map: dict[str, list[dict[str, Any]]],
    now_tick_u64: int,
    debt_key: str | None,
    target_key: str | None,
    patch_sha256: str | None,
    record_failure_b: bool,
) -> dict[str, list[dict[str, Any]]]:
    out = _failed_patch_ban_map(prev_map, now_tick_u64=int(now_tick_u64))
    if not bool(record_failure_b):
        return out
    debt = str(debt_key or "").strip()
    target = str(target_key or "").strip()
    patch = _normalize_patch_sha256(patch_sha256)
    if not debt or not target or patch is None:
        return out
    key = _failed_patch_ban_key(debt_key=debt, target_key=target)
    expires_tick_u64 = int(max(0, int(now_tick_u64 + _FAILED_PATCH_BAN_TTL_TICKS_U64)))
    existing_rows = list(out.get(key, []))
    by_patch = {
        str(row.get("patch_sha256", "")): int(max(0, int(row.get("expires_tick_u64", 0))))
        for row in existing_rows
        if _normalize_patch_sha256(row.get("patch_sha256")) is not None
    }
    by_patch[str(patch)] = int(max(int(by_patch.get(str(patch), 0)), int(expires_tick_u64)))
    rows = [
        {"patch_sha256": str(p), "expires_tick_u64": int(exp)}
        for p, exp in sorted(by_patch.items(), key=lambda kv: (int(kv[1]), str(kv[0])))
        if int(exp) >= int(now_tick_u64)
    ]
    out[key] = rows[-_MAX_FAILED_PATCH_BAN_PER_KEY :]
    if len(out) > _MAX_FAILED_PATCH_BAN_KEYS:
        keys = sorted(out.keys())
        keep = set(keys[-_MAX_FAILED_PATCH_BAN_KEYS :])
        out = {k: list(v) for k, v in out.items() if k in keep}
    return {str(k): list(v) for k, v in sorted(out.items(), key=lambda kv: str(kv[0]))}


def _failed_patch_ban_rows_for_debt_key(
    *,
    ban_map: dict[str, list[dict[str, Any]]],
    debt_key: str | None,
) -> list[dict[str, Any]]:
    debt = str(debt_key or "").strip()
    if not debt:
        return []
    rows: list[dict[str, Any]] = []
    for key, values in sorted(ban_map.items(), key=lambda kv: str(kv[0])):
        key_text = str(key)
        if not key_text.startswith(f"{debt}|"):
            continue
        target_key = key_text.split("|", 1)[1]
        target_relpaths = _target_relpaths_from_key(target_key)
        primary_relpath = target_relpaths[0] if target_relpaths else ""
        for entry in values:
            normalized = _normalize_patch_sha256(entry.get("patch_sha256"))
            if normalized is None:
                continue
            rows.append(
                {
                    "target_relpath": primary_relpath,
                    "target_relpaths": target_relpaths,
                    "target_relpaths_key": target_key,
                    "patch_sha256": normalized,
                }
            )
    return rows


def _failed_shape_ban_map(raw: Any, *, now_tick_u64: int) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    for key, value in sorted(raw.items(), key=lambda kv: str(kv[0])):
        key_text = str(key).strip()
        if not key_text or "|" not in key_text:
            continue
        if not isinstance(value, list):
            continue
        by_shape: dict[str, int] = {}
        for item in value:
            entry = _normalize_shape_ban_entry(raw=item, now_tick_u64=int(now_tick_u64))
            if entry is None:
                continue
            shape = str(entry["shape_id"])
            exp = int(entry["expires_tick_u64"])
            by_shape[shape] = int(max(int(by_shape.get(shape, 0)), exp))
        if not by_shape:
            continue
        rows = [
            {"shape_id": shape, "expires_tick_u64": int(exp)}
            for shape, exp in sorted(by_shape.items(), key=lambda kv: (int(kv[1]), str(kv[0])))
        ]
        out[key_text] = rows[-_MAX_FAILED_SHAPE_BAN_PER_KEY :]
    if len(out) > _MAX_FAILED_SHAPE_BAN_KEYS:
        keys = sorted(out.keys())
        keep = set(keys[-_MAX_FAILED_SHAPE_BAN_KEYS :])
        out = {k: list(v) for k, v in out.items() if k in keep}
    return {str(k): list(v) for k, v in sorted(out.items(), key=lambda kv: str(kv[0]))}


def _update_failed_shape_ban_map(
    *,
    prev_map: dict[str, list[dict[str, Any]]],
    now_tick_u64: int,
    debt_key: str | None,
    target_key: str | None,
    shape_id: str | None,
    record_failure_b: bool,
) -> dict[str, list[dict[str, Any]]]:
    out = _failed_shape_ban_map(prev_map, now_tick_u64=int(now_tick_u64))
    if not bool(record_failure_b):
        return out
    debt = str(debt_key or "").strip()
    target = str(target_key or "").strip()
    shape = _normalize_sha256(shape_id)
    if not debt or not target or shape is None:
        return out
    key = _failed_patch_ban_key(debt_key=debt, target_key=target)
    expires_tick_u64 = int(max(0, int(now_tick_u64 + _FAILED_SHAPE_BAN_TTL_TICKS_U64)))
    existing_rows = list(out.get(key, []))
    by_shape = {
        str(row.get("shape_id", "")): int(max(0, int(row.get("expires_tick_u64", 0))))
        for row in existing_rows
        if _normalize_sha256(row.get("shape_id")) is not None
    }
    by_shape[str(shape)] = int(max(int(by_shape.get(str(shape), 0)), int(expires_tick_u64)))
    rows = [
        {"shape_id": str(s), "expires_tick_u64": int(exp)}
        for s, exp in sorted(by_shape.items(), key=lambda kv: (int(kv[1]), str(kv[0])))
        if int(exp) >= int(now_tick_u64)
    ]
    out[key] = rows[-_MAX_FAILED_SHAPE_BAN_PER_KEY :]
    if len(out) > _MAX_FAILED_SHAPE_BAN_KEYS:
        keys = sorted(out.keys())
        keep = set(keys[-_MAX_FAILED_SHAPE_BAN_KEYS :])
        out = {k: list(v) for k, v in out.items() if k in keep}
    return {str(k): list(v) for k, v in sorted(out.items(), key=lambda kv: str(kv[0]))}


def _failed_shape_ban_rows_for_debt_key(
    *,
    ban_map: dict[str, list[dict[str, Any]]],
    debt_key: str | None,
) -> list[dict[str, Any]]:
    debt = str(debt_key or "").strip()
    if not debt:
        return []
    rows: list[dict[str, Any]] = []
    for key, values in sorted(ban_map.items(), key=lambda kv: str(kv[0])):
        key_text = str(key)
        if not key_text.startswith(f"{debt}|"):
            continue
        target_key = key_text.split("|", 1)[1]
        target_relpaths = _target_relpaths_from_key(target_key)
        primary_relpath = target_relpaths[0] if target_relpaths else ""
        for entry in values:
            normalized = _normalize_sha256(entry.get("shape_id"))
            if normalized is None:
                continue
            rows.append(
                {
                    "target_relpath": primary_relpath,
                    "target_relpaths": target_relpaths,
                    "target_relpaths_key": target_key,
                    "shape_id": normalized,
                }
            )
    return rows


def _wiring_locus_candidates_for_debt_key(
    *,
    tick_u64: int,
    debt_key: str,
    capability_id: str,
    last_failure_cert: dict[str, Any] | None,
) -> list[str]:
    del tick_u64
    del debt_key
    del capability_id
    del last_failure_cert
    candidates: list[str] = []
    primary = _normalize_relpath(_FORCED_WIRING_LOCUS_PRIMARY_RELPATH)
    if primary is not None and primary not in candidates:
        candidates.append(primary)
    for rel in _FORCED_WIRING_LOCUS_FALLBACK_RELPATHS:
        normalized = _normalize_relpath(rel)
        if normalized is None or normalized in candidates:
            continue
        candidates.append(normalized)
    return [str(row) for row in candidates]


def _compute_wiring_locus_relpath(
    *,
    tick_u64: int,
    debt_key: str,
    capability_id: str,
    last_failure_cert: dict[str, Any] | None,
) -> str | None:
    for rel in _wiring_locus_candidates_for_debt_key(
        tick_u64=tick_u64,
        debt_key=debt_key,
        capability_id=capability_id,
        last_failure_cert=last_failure_cert,
    ):
        path = (repo_root() / rel).resolve()
        if not path.exists() or not path.is_file():
            continue
        if not str(rel).endswith(".py"):
            continue
        return str(rel)
    return None


def _selected_candidate_from_precheck(*, dispatch_ctx: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(dispatch_ctx, dict):
        return None
    subrun_root_raw = dispatch_ctx.get("subrun_root_abs")
    if not isinstance(subrun_root_raw, (str, Path)):
        return None
    subrun_root_abs = Path(subrun_root_raw).resolve()
    precheck_dir = subrun_root_abs / "precheck"
    if not precheck_dir.exists() or not precheck_dir.is_dir():
        return None
    rows = sorted(precheck_dir.glob("sha256_*.candidate_precheck_receipt_v1.json"), key=lambda row: row.as_posix())
    if not rows:
        return None
    payload = load_canon_dict(rows[-1])
    validate_schema_v19(payload, "candidate_precheck_receipt_v1")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        fail("SCHEMA_FAIL")
    selected_rows = [row for row in candidates if isinstance(row, dict) and bool(row.get("selected_for_ccap_b", False))]
    if not selected_rows:
        return None
    selected_rows.sort(key=lambda row: int(max(0, int(row.get("candidate_idx_u32", 0)))))
    selected = selected_rows[0]
    target_relpath = _normalize_relpath(selected.get("target_relpath"))
    target_relpaths = _normalize_target_relpaths(selected.get("target_relpaths"))
    if not target_relpaths and target_relpath is not None:
        target_relpaths = [target_relpath]
    target_key = (
        str(selected.get("target_relpaths_key", "")).strip()
        if isinstance(selected.get("target_relpaths_key"), str)
        else ""
    )
    if not target_key:
        target_key = _target_relpaths_key(target_relpaths=target_relpaths)
    if not target_relpaths:
        target_relpaths = _target_relpaths_from_key(target_key)
    if not target_relpaths and target_relpath is not None:
        target_relpaths = [target_relpath]
    if not target_relpaths:
        return None
    target_relpath = target_relpaths[0]
    target_key = _target_relpaths_key(target_relpaths=target_relpaths)
    patch_sha256 = _normalize_patch_sha256(selected.get("patch_sha256"))
    cert = selected.get("nontriviality_cert_v1")
    cert_obj = dict(cert) if isinstance(cert, dict) else None
    shape_id = _normalize_sha256((cert_obj or {}).get("shape_id"))
    failed_threshold_code = str((cert_obj or {}).get("failed_threshold_code", "")).strip() or None
    if patch_sha256 is None:
        return None
    return {
        "target_relpath": target_relpath,
        "target_relpaths": target_relpaths,
        "target_relpaths_key": target_key,
        "patch_sha256": patch_sha256,
        "shape_id": shape_id,
        "nontriviality_cert_v1": cert_obj,
        "failed_threshold_code": failed_threshold_code,
    }


def _project_key_map_from_goal_map(
    *,
    pending_frontier_goals: list[dict[str, str]],
    by_goal: dict[str, int],
) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in pending_frontier_goals:
        goal_id = str(row.get("goal_id", "")).strip()
        debt_key = str(row.get("debt_key", "")).strip()
        if not goal_id or not debt_key:
            continue
        value = int(max(0, int(by_goal.get(goal_id, 0))))
        out[debt_key] = int(max(int(out.get(debt_key, 0)), value))
    return {str(k): int(v) for k, v in sorted(out.items(), key=lambda kv: str(kv[0]))}


def _goal_id_for_debt_key(*, pending_frontier_goals: list[dict[str, str]], debt_key: str) -> str | None:
    matches = [
        row
        for row in pending_frontier_goals
        if isinstance(row, dict) and str(row.get("debt_key", "")).strip() == str(debt_key).strip()
    ]
    if not matches:
        return None
    matches.sort(
        key=lambda row: (
            str(row.get("goal_id", "")),
            str(row.get("capability_id", "")),
            str(row.get("frontier_id", "")),
        )
    )
    goal_id = str(matches[0].get("goal_id", "")).strip()
    return goal_id or None


def _forced_frontier_debt_key(
    *,
    pending_frontier_goals: list[dict[str, str]],
    debt_state: dict[str, Any],
    debt_limit_u64: int,
    max_ticks_without_frontier_attempt_u64: int,
    anticipate_without_attempt_u64: int = 0,
) -> str | None:
    debt_by_key = _u64_map(debt_state.get("debt_by_key"))
    ticks_by_key = _u64_map(debt_state.get("ticks_without_frontier_attempt_by_key"))
    first_debt_tick_by_key = _u64_map(debt_state.get("first_debt_tick_by_key"))
    if not debt_by_key:
        debt_by_goal = _u64_map(debt_state.get("debt_by_goal_id"))
        debt_by_key = _project_key_map_from_goal_map(
            pending_frontier_goals=pending_frontier_goals,
            by_goal=debt_by_goal,
        )
    if not ticks_by_key:
        ticks_by_goal = _u64_map(debt_state.get("ticks_without_frontier_attempt_by_goal_id"))
        ticks_by_key = _project_key_map_from_goal_map(
            pending_frontier_goals=pending_frontier_goals,
            by_goal=ticks_by_goal,
        )
    if not first_debt_tick_by_key:
        first_by_goal = _u64_map(debt_state.get("first_debt_tick_by_goal_id"))
        first_debt_tick_by_key = _project_key_map_from_goal_map(
            pending_frontier_goals=pending_frontier_goals,
            by_goal=first_by_goal,
        )
    candidates: list[tuple[int, str]] = []
    pending_debt_keys = {str(row.get("debt_key", "")).strip() for row in pending_frontier_goals}
    anticipated_ticks_u64 = int(max(0, int(anticipate_without_attempt_u64)))
    for debt_key in sorted(key for key in pending_debt_keys if key):
        debt_u64 = int(max(0, int(debt_by_key.get(debt_key, 0))))
        ticks_u64 = int(max(0, int(ticks_by_key.get(debt_key, 0))))
        if debt_u64 >= int(debt_limit_u64) or (ticks_u64 + 1 + anticipated_ticks_u64) >= int(max_ticks_without_frontier_attempt_u64):
            first_tick = int(max(0, int(first_debt_tick_by_key.get(debt_key, 0))))
            candidates.append((first_tick, debt_key))
    if not candidates:
        return None
    candidates.sort(key=lambda row: (int(row[0]), str(row[1])))
    return str(candidates[0][1])


def _build_dependency_routing_receipt(
    *,
    tick_u64: int,
    selected_capability_id: str,
    selected_declared_class: str,
    frontier_goals_pending_b: bool,
    blocks_goal_id: str | None,
    blocks_debt_key: str | None,
    dependency_debt_delta_i64: int,
    forced_frontier_attempt_b: bool,
    forced_frontier_debt_key: str | None,
    routing_selector_id: str,
    market_frozen_b: bool,
    market_used_for_selection_b: bool,
    reason_codes: list[str],
    context_key: str | None = None,
) -> dict[str, Any]:
    selector_id = str(routing_selector_id).strip()
    if selector_id not in _ROUTING_SELECTOR_IDS and not _is_sha256(selector_id):
        selector_id = "NON_MARKET"
    payload = {
        "schema_name": "dependency_routing_receipt_v1",
        "schema_version": "v19_0",
        "receipt_id": _SHA256_ZERO,
        "tick_u64": int(max(0, int(tick_u64))),
        "selected_capability_id": str(selected_capability_id),
        "selected_declared_class": str(selected_declared_class if selected_declared_class in _DECLARED_CLASSES else "UNCLASSIFIED"),
        "frontier_goals_pending_b": bool(frontier_goals_pending_b),
        "blocks_goal_id": (str(blocks_goal_id) if isinstance(blocks_goal_id, str) and blocks_goal_id.strip() else None),
        "blocks_debt_key": (str(blocks_debt_key) if isinstance(blocks_debt_key, str) and blocks_debt_key.strip() else None),
        "dependency_debt_delta_i64": int(dependency_debt_delta_i64),
        "forced_frontier_attempt_b": bool(forced_frontier_attempt_b),
        "forced_frontier_debt_key": (
            str(forced_frontier_debt_key)
            if isinstance(forced_frontier_debt_key, str) and forced_frontier_debt_key.strip()
            else None
        ),
        "routing_selector_id": selector_id,
        "context_key": (
            str(context_key).strip()
            if isinstance(context_key, str) and _is_sha256(str(context_key).strip())
            else None
        ),
        "market_frozen_b": bool(market_frozen_b),
        "market_used_for_selection_b": bool(market_used_for_selection_b),
        "reason_codes": [str(row) for row in reason_codes],
    }
    no_id = dict(payload)
    no_id.pop("receipt_id", None)
    payload["receipt_id"] = canon_hash_obj(no_id)
    validate_schema_v19(payload, "dependency_routing_receipt_v1")
    return payload


def _with_hard_lock_override_reason(
    *,
    reason_codes: list[str],
    forced_frontier_attempt_b: bool,
    market_selection_in_play_b: bool,
) -> list[str]:
    out = [str(row) for row in reason_codes]
    if bool(forced_frontier_attempt_b) and bool(market_selection_in_play_b):
        if "HARD_LOCK_OVERRIDE_MARKET_SELECTION" not in out:
            out.append("HARD_LOCK_OVERRIDE_MARKET_SELECTION")
    return out


def _routing_selector_for_receipt(
    *,
    reason_codes: list[str],
    forced_frontier_attempt_b: bool,
    market_selection_in_play_b: bool,
) -> tuple[str, bool, bool]:
    reason_set = {str(row).strip() for row in reason_codes if str(row).strip()}
    if bool(forced_frontier_attempt_b):
        selector_id = "HARD_LOCK_OVERRIDE"
    elif "SCAFFOLDING_ALLOWED" in reason_set:
        selector_id = "SCAFFOLD_OVERRIDE"
    elif bool(market_selection_in_play_b):
        selector_id = "MARKET"
    else:
        selector_id = "NON_MARKET"
    market_used_for_selection_b = selector_id == "MARKET"
    market_frozen_b = selector_id in {"SCAFFOLD_OVERRIDE", "HARD_LOCK_OVERRIDE"}
    return selector_id, market_frozen_b, market_used_for_selection_b


def _with_frontier_dispatch_failed_pre_evidence_reason(
    *,
    reason_codes: list[str],
    hard_lock_became_active_b: bool,
    selected_declared_class: str,
    frontier_attempt_counted_b: bool,
) -> list[str]:
    out = [str(row) for row in reason_codes]
    if not bool(hard_lock_became_active_b):
        return out
    selected_frontier_b = str(selected_declared_class).strip() == "FRONTIER_HEAVY"
    if selected_frontier_b and bool(frontier_attempt_counted_b):
        return out
    if "FRONTIER_DISPATCH_FAILED_PRE_EVIDENCE" not in out:
        out.append("FRONTIER_DISPATCH_FAILED_PRE_EVIDENCE")
    return out


def _effective_change_from_effect_class(
    *,
    effect_class: str,
    debt_reduced_b: bool,
) -> bool:
    if effect_class in {"EFFECT_HEAVY_OK", "EFFECT_BASELINE_CORE_OK"}:
        return True
    if effect_class == "EFFECT_MAINTENANCE_OK" and debt_reduced_b:
        return True
    return False


def _frontier_attempt_evidence_satisfied(
    *,
    action_kind: str,
    declared_class_for_tick: str,
    lane_name: str | None = None,
    candidate_bundle_present_b: bool,
    dispatch_receipt: dict[str, Any] | None,
    subverifier_receipt: dict[str, Any] | None,
) -> bool:
    if str(action_kind).strip() not in {"RUN_CAMPAIGN", "RUN_GOAL_TASK"}:
        return False
    is_frontier_lane = str(lane_name or "").strip().upper() == "FRONTIER"
    declared_class = str(declared_class_for_tick).strip()
    if declared_class not in _HEAVY_DECLARED_CLASSES and not is_frontier_lane:
        return False
    if not isinstance(dispatch_receipt, dict) or not isinstance(subverifier_receipt, dict):
        return False
    validate_schema(dispatch_receipt, "omega_dispatch_receipt_v1")
    validate_schema(subverifier_receipt, "omega_subverifier_receipt_v1")
    dispatch_tick_u64 = int(max(0, int(dispatch_receipt.get("tick_u64", -1))))
    sub_tick_u64 = int(max(0, int(subverifier_receipt.get("tick_u64", -1))))
    if dispatch_tick_u64 != sub_tick_u64:
        return False
    dispatch_campaign_id = str(dispatch_receipt.get("campaign_id", "")).strip()
    sub_campaign_id = str(subverifier_receipt.get("campaign_id", "")).strip()
    if not dispatch_campaign_id or not sub_campaign_id or dispatch_campaign_id != sub_campaign_id:
        return False
    sub_status = str(((subverifier_receipt.get("result") or {}).get("status", ""))).strip().upper()
    if sub_status not in {"VALID", "INVALID"}:
        return False
    return True


def _is_sha256(value: Any) -> bool:
    raw = str(value).strip()
    return raw.startswith("sha256:") and len(raw) == 71 and all(ch in "0123456789abcdef" for ch in raw.split(":", 1)[1])


def _selected_capability_id_from_plan(plan: dict[str, Any]) -> str:
    action_kind = str(plan.get("action_kind", "")).strip()
    if action_kind == "RUN_GOAL_TASK":
        return str(plan.get("assigned_capability_id", "")).strip()
    return str(plan.get("capability_id", "")).strip()


def _selected_goal_id_from_plan(plan: dict[str, Any]) -> str | None:
    value = str(plan.get("goal_id", "")).strip()
    return value or None


def _bundle_path_by_hash(*, state_root: Path, bundle_hash: str) -> Path | None:
    if not _is_sha256(bundle_hash) or bundle_hash == _SHA256_ZERO:
        return None
    hexd = bundle_hash.split(":", 1)[1]
    rows = sorted((state_root / "subruns").glob(f"**/sha256_{hexd}.*.json"), key=lambda p: p.as_posix())
    if not rows:
        return None
    # Multiple paths with the same canonical hash are acceptable and deterministic.
    path = rows[-1]
    payload = load_canon_dict(path)
    if canon_hash_obj(payload) != bundle_hash:
        fail("NONDETERMINISTIC")
    return path


def _candidate_bundle_present_from_artifacts(
    *,
    state_root: Path,
    promotion_receipt: dict[str, Any] | None,
) -> bool:
    bundle_hash = str((promotion_receipt or {}).get("promotion_bundle_hash", "")).strip()
    if not _is_sha256(bundle_hash) or bundle_hash == _SHA256_ZERO:
        return False
    return _bundle_path_by_hash(state_root=state_root, bundle_hash=bundle_hash) is not None


def _load_utility_proof_receipt_by_hash(
    *,
    state_root: Path,
    utility_proof_hash: str,
) -> dict[str, Any] | None:
    if not _is_sha256(utility_proof_hash):
        return None
    hexd = utility_proof_hash.split(":", 1)[1]
    rows = sorted(
        state_root.glob(f"dispatch/*/promotion/sha256_{hexd}.utility_proof_receipt_v1.json"),
        key=lambda p: p.as_posix(),
    )
    if not rows:
        return None
    payload = load_canon_dict(rows[-1])
    validate_schema_v19(payload, "utility_proof_receipt_v1")
    if canon_hash_obj(payload) != utility_proof_hash:
        fail("NONDETERMINISTIC")
    return payload


def _probe_executed_from_artifacts(
    *,
    utility_receipt: dict[str, Any] | None,
) -> bool:
    if not isinstance(utility_receipt, dict):
        return False
    probe_suite_id = str(utility_receipt.get("probe_suite_id", "")).strip()
    stress_probe_suite_id = str(utility_receipt.get("stress_probe_suite_id", "")).strip()
    baseline_ref_hash = str(utility_receipt.get("baseline_ref_hash", "")).strip()
    primary_probe = utility_receipt.get("primary_probe")
    stress_probe = utility_receipt.get("stress_probe")
    if not probe_suite_id or not stress_probe_suite_id or not _is_sha256(baseline_ref_hash):
        return False
    if not isinstance(primary_probe, dict) or not isinstance(stress_probe, dict):
        return False
    if not _is_sha256(primary_probe.get("input_hash")) or not _is_sha256(primary_probe.get("output_hash")):
        return False
    if not _is_sha256(stress_probe.get("input_hash")) or not _is_sha256(stress_probe.get("output_hash")):
        return False
    return True


def _dir_size_bytes(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            file_path = Path(root) / name
            try:
                total += int(file_path.stat().st_size)
            except FileNotFoundError:
                continue
    return int(total)


def _prune_ccap_ephemeral_artifacts(
    *,
    dispatch_ctx: dict[str, Any] | None,
    enabled_b: bool,
    tick_u64: int,
) -> None:
    if not enabled_b or not isinstance(dispatch_ctx, dict):
        return
    candidate_dirs: set[Path] = set()
    replay_root_abs: Path | None = None
    subrun_root_raw = dispatch_ctx.get("subrun_root_abs")
    if isinstance(subrun_root_raw, (str, Path)):
        candidate_dirs.add((Path(subrun_root_raw).resolve() / "ccap" / "ek_runs").resolve())
    state_root_raw = dispatch_ctx.get("state_root")
    if isinstance(state_root_raw, (str, Path)):
        state_root = Path(state_root_raw).resolve()
        replay_root_abs = (state_root / _REPLAY_STATE_ROOT_REL).resolve()
        for path in sorted((state_root / "subruns").glob("*/ccap/ek_runs"), key=lambda row: row.as_posix()):
            candidate_dirs.add(path.resolve())
    for ek_runs_dir in sorted(candidate_dirs, key=lambda row: row.as_posix()):
        if not ek_runs_dir.exists() or not ek_runs_dir.is_dir():
            continue
        if replay_root_abs is not None:
            try:
                ek_runs_dir.relative_to(replay_root_abs)
                continue
            except ValueError:
                pass
        before_bytes = _dir_size_bytes(ek_runs_dir)
        shutil.rmtree(ek_runs_dir)
        print(
            json.dumps(
                {
                    "event": "CCAP_EK_RUNS_PRUNED_V1",
                    "tick_u64": int(tick_u64),
                    "pruned_abs": str(ek_runs_dir),
                    "before_bytes_u64": int(before_bytes),
                    "after_bytes_u64": 0,
                },
                separators=(",", ":"),
                sort_keys=True,
            ),
            file=sys.stderr,
        )


def _declared_class_from_promotion_receipt(promotion_receipt: dict[str, Any] | None) -> str:
    raw = str((promotion_receipt or {}).get("declared_class", "")).strip().upper()
    if raw in _DECLARED_CLASSES:
        return raw
    return "UNCLASSIFIED"


def _effect_class_from_promotion_receipt(promotion_receipt: dict[str, Any] | None, *, fallback: str) -> str:
    raw = str((promotion_receipt or {}).get("effect_class", "")).strip().upper()
    if raw in _EFFECT_CLASSES:
        return raw
    if fallback in _EFFECT_CLASSES:
        return fallback
    return "EFFECT_REJECTED"


def _overlay_anti_monopoly_cooldowns(
    *,
    state: dict[str, Any],
    anti_monopoly_state: dict[str, Any] | None,
    tick_u64: int,
) -> dict[str, Any]:
    out = dict(state)
    cooldowns = dict(out.get("cooldowns") or {})
    rows = (anti_monopoly_state or {}).get("campaign_cooldowns")
    if not isinstance(rows, dict):
        out["cooldowns"] = cooldowns
        return out
    for campaign_id, row in sorted(rows.items(), key=lambda kv: str(kv[0])):
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        until_tick_u64 = int(max(0, int(row.get("until_tick_u64", 0))))
        if until_tick_u64 <= int(tick_u64):
            continue
        prev_next = int((((cooldowns.get(str(campaign_id)) or {}).get("next_tick_allowed_u64", 0))))
        cooldowns[str(campaign_id)] = {
            "next_tick_allowed_u64": int(max(prev_next, until_tick_u64)),
        }
    out["cooldowns"] = cooldowns
    return out


def _campaign_pack_hash_for_entry(cap_row: dict[str, Any]) -> str:
    rel = _require_safe_relpath(cap_row.get("campaign_pack_rel"))
    path = repo_root() / rel
    if not path.exists() or not path.is_file():
        fail("MISSING_STATE_INPUT")
    payload = load_canon_dict(path)
    return canon_hash_obj(payload)


def _rewrite_plan_for_frontier_capability_bias(
    *,
    decision_plan: dict[str, Any],
    cap_row: dict[str, Any],
    capability_id: str,
    tie_break_reason: str,
) -> tuple[dict[str, Any], str]:
    tie_break_path = decision_plan.get("tie_break_path")
    if not isinstance(tie_break_path, list):
        fail("SCHEMA_FAIL")
    existing_proof = decision_plan.get("recompute_proof")
    existing_inputs_hash: str | None = None
    if isinstance(existing_proof, dict):
        candidate_inputs_hash = str(existing_proof.get("inputs_hash", "")).strip()
        if _is_sha256(candidate_inputs_hash):
            existing_inputs_hash = candidate_inputs_hash
    payload = dict(decision_plan)
    payload["action_kind"] = "RUN_CAMPAIGN"
    payload["campaign_id"] = str(cap_row.get("campaign_id", "")).strip()
    payload["capability_id"] = str(capability_id).strip()
    payload["campaign_pack_hash"] = _campaign_pack_hash_for_entry(cap_row)
    payload["expected_verifier_module"] = str(cap_row.get("verifier_module", "")).strip()
    priority_q32 = payload.get("priority_q32")
    if not isinstance(priority_q32, dict):
        payload["priority_q32"] = {"q": 0}
    reason_norm = str(tie_break_reason).strip() or "FRONTIER_CAPABILITY_BIAS"
    payload["tie_break_path"] = [*tie_break_path, reason_norm]
    rewritten_plan, rewritten_hash = _recompute_decision_plan_identity(payload)
    if existing_inputs_hash is None:
        return rewritten_plan, rewritten_hash
    rewritten_plan = dict(rewritten_plan)
    rewritten_plan["recompute_proof"] = {
        "inputs_hash": str(existing_inputs_hash),
        "plan_hash": _SHA256_ZERO,
    }
    no_id = dict(rewritten_plan)
    no_id.pop("plan_id", None)
    rewritten_plan_id = canon_hash_obj(no_id)
    rewritten_plan["plan_id"] = rewritten_plan_id
    rewritten_plan["recompute_proof"] = {
        "inputs_hash": str(existing_inputs_hash),
        "plan_hash": str(rewritten_plan_id),
    }
    validate_schema(rewritten_plan, "omega_decision_plan_v1")
    return rewritten_plan, canon_hash_obj(rewritten_plan)


def _rewrite_plan_for_milestone_sh1_frontier(
    *,
    decision_plan: dict[str, Any],
    cap_row: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    return _rewrite_plan_for_frontier_capability_bias(
        decision_plan=decision_plan,
        cap_row=cap_row,
        capability_id=_SH1_CAPABILITY_ID,
        tie_break_reason="MILESTONE_FORCE_SH1_FRONTIER",
    )


def _rewrite_plan_for_forced_frontier_goal(
    *,
    decision_plan: dict[str, Any],
    forced_goal_id: str,
    forced_capability_id: str,
    cap_row: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    tie_break_path = decision_plan.get("tie_break_path")
    if not isinstance(tie_break_path, list):
        fail("SCHEMA_FAIL")
    existing_proof = decision_plan.get("recompute_proof")
    existing_inputs_hash: str | None = None
    if isinstance(existing_proof, dict):
        candidate_inputs_hash = str(existing_proof.get("inputs_hash", "")).strip()
        if _is_sha256(candidate_inputs_hash):
            existing_inputs_hash = candidate_inputs_hash
    payload = dict(decision_plan)
    payload["action_kind"] = "RUN_GOAL_TASK"
    payload["goal_id"] = str(forced_goal_id)
    payload["assigned_capability_id"] = str(forced_capability_id)
    payload["campaign_id"] = str(cap_row.get("campaign_id", "")).strip()
    payload["capability_id"] = str(forced_capability_id)
    payload["campaign_pack_hash"] = _campaign_pack_hash_for_entry(cap_row)
    payload["expected_verifier_module"] = str(cap_row.get("verifier_module", "")).strip()
    priority_q32 = payload.get("priority_q32")
    if not isinstance(priority_q32, dict):
        payload["priority_q32"] = {"q": 0}
    payload["tie_break_path"] = [*tie_break_path, f"FORCED_FRONTIER_GOAL:{forced_goal_id}", "FORCED_FRONTIER_OVERRIDE"]
    rewritten_plan, rewritten_hash = _recompute_decision_plan_identity(payload)
    if existing_inputs_hash is None:
        return rewritten_plan, rewritten_hash
    rewritten_plan = dict(rewritten_plan)
    rewritten_plan["recompute_proof"] = {
        "inputs_hash": str(existing_inputs_hash),
        "plan_hash": _SHA256_ZERO,
    }
    no_id = dict(rewritten_plan)
    no_id.pop("plan_id", None)
    rewritten_plan_id = canon_hash_obj(no_id)
    rewritten_plan["plan_id"] = rewritten_plan_id
    rewritten_plan["recompute_proof"] = {
        "inputs_hash": str(existing_inputs_hash),
        "plan_hash": str(rewritten_plan_id),
    }
    validate_schema(rewritten_plan, "omega_decision_plan_v1")
    return rewritten_plan, canon_hash_obj(rewritten_plan)


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


def _observation_metric_ids(observation_report: dict[str, Any]) -> list[str]:
    rows = observation_report.get("metrics")
    if not isinstance(rows, dict):
        fail("SCHEMA_FAIL")
    out = sorted(str(key).strip() for key in rows.keys() if str(key).strip())
    return out


def _lookup_capsule_tick(*, state_root: Path, capsule_id: str) -> int:
    caps_dir = state_root / "epistemic" / "capsules"
    if not caps_dir.exists() or not caps_dir.is_dir():
        return 0
    for path in sorted(caps_dir.glob("sha256_*.epistemic_capsule_v1.json"), key=lambda p: p.as_posix()):
        payload, _ = _load_hashed_payload(path=path, expected_schema_version="epistemic_capsule_v1")
        if _ensure_sha256_id(payload.get("capsule_id")) != capsule_id:
            continue
        return int(payload.get("tick_u64", 0))
    return 0


def _collect_eufc_window_rows(
    *,
    current_tick_u64: int,
    window_ticks_u64: int,
    state_roots: list[Path],
) -> list[dict[str, Any]]:
    close_tick = int(current_tick_u64)
    open_tick = max(0, close_tick - max(1, int(window_ticks_u64)) + 1)
    by_id: dict[str, int] = {}
    for state_root in state_roots:
        cert_dir = state_root / "epistemic" / "certs"
        if not cert_dir.exists() or not cert_dir.is_dir():
            continue
        for path in sorted(cert_dir.glob("sha256_*.epistemic_eufc_v1.json"), key=lambda p: p.as_posix()):
            payload, _ = _load_hashed_payload(path=path, expected_schema_version="epistemic_eufc_v1")
            eufc_id = _ensure_sha256_id(payload.get("eufc_id"))
            capsule_id = _ensure_sha256_id(payload.get("capsule_id"))
            row_tick = _lookup_capsule_tick(state_root=state_root, capsule_id=capsule_id)
            if row_tick < open_tick or row_tick > close_tick:
                continue
            prev_tick = by_id.get(eufc_id)
            if prev_tick is None or int(row_tick) < int(prev_tick):
                by_id[eufc_id] = int(row_tick)
    rows = [
        {"eufc_id": eufc_id, "tick_u64": int(row_tick)}
        for eufc_id, row_tick in by_id.items()
    ]
    rows.sort(key=lambda row: (int(row["tick_u64"]), str(row["eufc_id"])))
    return rows


def _load_prev_action_market_state_id(prev_state_dir: Path | None) -> str | None:
    if prev_state_dir is None:
        return None
    sel_dir = prev_state_dir.resolve() / "epistemic" / "market" / "actions" / "settlement"
    if not sel_dir.exists() or not sel_dir.is_dir():
        return None
    rows = sorted(sel_dir.glob("sha256_*.epistemic_action_settlement_receipt_v1.json"), key=lambda p: p.as_posix())
    if not rows:
        return None
    payload, _ = _load_hashed_payload(
        path=rows[-1],
        expected_schema_version="epistemic_action_settlement_receipt_v1",
    )
    return _ensure_sha256_id(payload.get("action_settlement_id"))


def _rewrite_eufc_with_credit_attribution(
    *,
    state_root: Path,
    eufc_id: str,
    credit_key: str,
    credit_window_open_tick_u64: int,
    credit_window_close_tick_u64: int,
    credit_window_receipt_ids: list[str],
) -> tuple[dict[str, Any], str]:
    cert_dir = state_root / "epistemic" / "certs"
    eufc_id = _ensure_sha256_id(eufc_id)
    credit_key = _ensure_sha256_id(credit_key)
    receipt_ids = [_ensure_sha256_id(row) for row in list(credit_window_receipt_ids)]
    if len(set(receipt_ids)) != len(receipt_ids):
        fail("SCHEMA_FAIL")
    eufc_path: Path | None = None
    payload: dict[str, Any] | None = None
    for candidate_path in sorted(cert_dir.glob("sha256_*.epistemic_eufc_v1.json"), key=lambda p: p.as_posix()):
        candidate_payload, _ = _load_hashed_payload(path=candidate_path, expected_schema_version="epistemic_eufc_v1")
        if _ensure_sha256_id(candidate_payload.get("eufc_id")) != eufc_id:
            continue
        if eufc_path is not None:
            fail("NONDETERMINISTIC")
        eufc_path = candidate_path
        payload = candidate_payload
    if eufc_path is None or payload is None:
        fail("MISSING_STATE_INPUT")

    credited_keys = sorted(
        {
            _ensure_sha256_id(row)
            for row in list(payload.get("credited_credit_keys") or [])
        }
        | {credit_key}
    )
    materialized = dict(payload)
    materialized["credited_credit_keys"] = credited_keys
    materialized["credit_window_mode"] = "EUFC_WINDOW"
    materialized["credit_window_open_tick_u64"] = int(max(0, int(credit_window_open_tick_u64)))
    materialized["credit_window_close_tick_u64"] = int(
        max(int(materialized["credit_window_open_tick_u64"]), int(credit_window_close_tick_u64))
    )
    materialized["credit_window_receipt_ids"] = list(receipt_ids)
    validate_schema_v19(materialized, "epistemic_eufc_v1")
    _, materialized, observed_hash = _write_payload_atomic(
        cert_dir,
        "epistemic_eufc_v1.json",
        materialized,
        id_field="eufc_id",
    )
    return materialized, observed_hash


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
    state_root: Path | None = None,
) -> int:
    if not isinstance(prev_observation_report, dict):
        return 0
    metrics_now = observation_report.get("metrics")
    metrics_prev = prev_observation_report.get("metrics")
    if not isinstance(metrics_now, dict) or not isinstance(metrics_prev, dict):
        return 0
    tick_now_u64 = int(observation_report.get("tick_u64", -1))
    tick_prev_u64 = int(prev_observation_report.get("tick_u64", -1))
    weights = j_profile_payload.get("metric_weights") if isinstance(j_profile_payload, dict) else []
    if not isinstance(weights, list):
        weights = []

    required_metric_ids: list[str] = []
    for row in weights:
        if not isinstance(row, dict):
            continue
        metric_id = str(row.get("metric_id", "")).strip()
        if metric_id:
            required_metric_ids.append(metric_id)
    required_metric_ids.extend(_HARD_TASK_METRIC_IDS)

    ccap_metric_index_by_tick: dict[int, dict[str, int]] = {}
    if isinstance(state_root, Path):
        try:
            ccap_metric_index_by_tick = build_ccap_receipt_metric_index_for_state_root(
                state_root=state_root,
                required_metric_ids=required_metric_ids,
                require_consistent_mirror_b=True,
            )
        except Exception:
            ccap_metric_index_by_tick = {}

    def _metric_q32_with_receipt_fallback(
        *,
        metrics: dict[str, Any],
        tick_u64: int,
        metric_id: str,
    ) -> int:
        metric = metrics.get(metric_id)
        if isinstance(metric, dict) and isinstance(metric.get("q"), int):
            return int(metric.get("q", 0))
        tick_metrics = ccap_metric_index_by_tick.get(int(tick_u64))
        if isinstance(tick_metrics, dict) and str(metric_id) in tick_metrics:
            return int(tick_metrics[str(metric_id)])
        return 0

    bias_now = 0
    bias_obj = j_profile_payload.get("bias_q32") if isinstance(j_profile_payload, dict) else None
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
        now_q = _metric_q32_with_receipt_fallback(
            metrics=metrics_now,
            tick_u64=int(tick_now_u64),
            metric_id=metric_id,
        )
        prev_q = _metric_q32_with_receipt_fallback(
            metrics=metrics_prev,
            tick_u64=int(tick_prev_u64),
            metric_id=metric_id,
        )
        w_q = int(weight.get("q"))
        j_now += q32_mul(now_q, w_q)
        j_prev += q32_mul(prev_q, w_q)
    hard_task_delta_q32 = 0
    for metric_id in _HARD_TASK_METRIC_IDS:
        now_q = _metric_q32_with_receipt_fallback(
            metrics=metrics_now,
            tick_u64=int(tick_now_u64),
            metric_id=metric_id,
        )
        prev_q = _metric_q32_with_receipt_fallback(
            metrics=metrics_prev,
            tick_u64=int(tick_prev_u64),
            metric_id=metric_id,
        )
        hard_task_delta_q32 += int(now_q) - int(prev_q)
    return int((j_now - j_prev) + int(hard_task_delta_q32))

def _find_subrun_payload_by_id(
    *,
    subrun_root: Path,
    artifact_id: str,
    suffix: str,
    id_field: str | None = None,
    expected_schema_version: str | None = None,
    expected_schema_name: str | None = None,
) -> tuple[dict[str, Any], str]:
    artifact_id = _ensure_sha256_id(artifact_id)
    paths = sorted(subrun_root.glob(f"**/sha256_*.{suffix}"), key=lambda row: row.as_posix())
    matches_by_hash: dict[str, dict[str, Any]] = {}
    for path in paths:
        payload, observed_hash = _load_hashed_payload(
            path=path,
            expected_schema_version=expected_schema_version,
            expected_schema_name=expected_schema_name,
        )
        effective_id = observed_hash
        if id_field is not None:
            declared_id = _ensure_sha256_id(payload.get(id_field))
            payload_no_id = dict(payload)
            payload_no_id.pop(id_field, None)
            if canon_hash_obj(payload_no_id) != declared_id:
                fail("NONDETERMINISTIC")
            effective_id = declared_id
        if effective_id == artifact_id:
            matches_by_hash.setdefault(observed_hash, payload)
    if not matches_by_hash:
        fail("MISSING_STATE_INPUT")
    if len(matches_by_hash) != 1:
        fail("NONDETERMINISTIC")
    observed_hash, payload = next(iter(matches_by_hash.items()))
    return payload, observed_hash


def _verify_declared_id(payload: dict[str, Any], id_field: str) -> str:
    declared = _ensure_sha256_id(payload.get(id_field))
    no_id = dict(payload)
    no_id.pop(id_field, None)
    if canon_hash_obj(no_id) != declared:
        fail("NONDETERMINISTIC")
    return declared


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
            id_field="manifest_id",
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
            id_field="receipt_id",
            expected_schema_name="sealed_ingestion_receipt_v1",
        )
        if _ensure_sha256_id(receipt_payload.get("world_manifest_ref")) != manifest_id:
            fail("NONDETERMINISTIC")
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
    manifest_id: str | None = None
    if isinstance(manifest_id_raw, str) and manifest_id_raw.strip():
        manifest_id = _ensure_sha256_id(manifest_id_raw)
        manifest_payload, manifest_hash = _find_subrun_payload_by_id(
            subrun_root=subrun_root,
            artifact_id=manifest_id,
            suffix="world_snapshot_manifest_v1.json",
            id_field="manifest_id",
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
            id_field="receipt_id",
            expected_schema_name="sealed_ingestion_receipt_v1",
        )
        if manifest_id is not None and _ensure_sha256_id(receipt_payload.get("world_manifest_ref")) != manifest_id:
            fail("NONDETERMINISTIC")
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


def _import_epistemic_capsule_artifacts(
    *,
    dispatch_ctx: dict[str, Any] | None,
    state_root: Path,
) -> dict[str, str | None]:
    out: dict[str, str | None] = {
        "capsule_hash": None,
        "capsule_id": None,
        "world_snapshot_id": None,
        "world_root": None,
        "sip_receipt_id": None,
        "distillate_graph_id": None,
        "strip_receipt_id": None,
        "episode_id": None,
        "refutation_hash": None,
        "type_registry_hash": None,
        "type_binding_hash": None,
        "type_registry_id": None,
        "type_binding_id": None,
        "epistemic_ecac_hash": None,
        "epistemic_eufc_hash": None,
        "epistemic_ecac_id": None,
        "epistemic_eufc_id": None,
        "epistemic_cert_profile_hash": None,
        "epistemic_cert_gate_binding_hash": None,
        "retention_deletion_plan_hash": None,
        "retention_sampling_manifest_hash": None,
        "retention_summary_proof_hash": None,
        "epistemic_kernel_spec_hash": None,
        "epistemic_kernel_spec_id": None,
    }
    if dispatch_ctx is None:
        return out

    subrun_root_raw = dispatch_ctx.get("subrun_root_abs")
    if not isinstance(subrun_root_raw, (str, Path)):
        return out
    subrun_root = Path(subrun_root_raw).resolve()
    if not subrun_root.exists() or not subrun_root.is_dir():
        return out

    capsule_paths = sorted(
        subrun_root.glob("**/sha256_*.epistemic_capsule_v1.json"),
        key=lambda row: row.as_posix(),
    )
    refutation_paths = sorted(
        subrun_root.glob("**/sha256_*.epistemic_capsule_refutation_v1.json"),
        key=lambda row: row.as_posix(),
    )
    if not capsule_paths and not refutation_paths:
        return out
    if len(capsule_paths) > 1 or len(refutation_paths) > 1:
        fail("SCHEMA_FAIL")
    if capsule_paths and refutation_paths:
        fail("SCHEMA_FAIL")

    epi_root = state_root / "epistemic"
    (epi_root / "capsules").mkdir(parents=True, exist_ok=True)
    (epi_root / "usable_capsules").mkdir(parents=True, exist_ok=True)
    (epi_root / "refutations").mkdir(parents=True, exist_ok=True)
    (epi_root / "graphs").mkdir(parents=True, exist_ok=True)
    (epi_root / "strip_receipts").mkdir(parents=True, exist_ok=True)
    (epi_root / "type_registry").mkdir(parents=True, exist_ok=True)
    (epi_root / "type_bindings").mkdir(parents=True, exist_ok=True)
    (epi_root / "type" / "provisionals").mkdir(parents=True, exist_ok=True)
    (epi_root / "type" / "ratifications").mkdir(parents=True, exist_ok=True)
    (epi_root / "certs").mkdir(parents=True, exist_ok=True)
    (epi_root / "certs" / "profiles").mkdir(parents=True, exist_ok=True)
    (epi_root / "contracts").mkdir(parents=True, exist_ok=True)
    (epi_root / "retention").mkdir(parents=True, exist_ok=True)
    (epi_root / "kernels" / "specs").mkdir(parents=True, exist_ok=True)
    (epi_root / "world" / "manifests").mkdir(parents=True, exist_ok=True)
    (epi_root / "world" / "receipts").mkdir(parents=True, exist_ok=True)
    (epi_root / "world" / "snapshots").mkdir(parents=True, exist_ok=True)

    def _unique_payload_from_paths(
        paths: list[Path],
        *,
        schema_version: str,
    ) -> tuple[dict[str, Any], str] | None:
        by_hash: dict[str, dict[str, Any]] = {}
        for path in paths:
            payload, payload_hash = _load_hashed_payload(
                path=path,
                expected_schema_version=schema_version,
            )
            by_hash.setdefault(payload_hash, payload)
        if not by_hash:
            return None
        if len(by_hash) != 1:
            fail("NONDETERMINISTIC")
        payload_hash, payload = next(iter(by_hash.items()))
        return payload, payload_hash

    if refutation_paths:
        refutation_payload, refutation_hash = _load_hashed_payload(
            path=refutation_paths[0],
            expected_schema_version="epistemic_capsule_refutation_v1",
        )
        validate_schema_v19(refutation_payload, "epistemic_capsule_refutation_v1")
        _ = _verify_declared_id(refutation_payload, "refutation_id")
        _, _ref_obj, imported_refutation_hash = _write_payload_atomic(
            epi_root / "refutations",
            "epistemic_capsule_refutation_v1.json",
            refutation_payload,
            id_field="refutation_id",
        )
        if imported_refutation_hash != refutation_hash:
            fail("NONDETERMINISTIC")
        out["refutation_hash"] = imported_refutation_hash
        return out

    capsule_payload, capsule_hash = _load_hashed_payload(
        path=capsule_paths[0],
        expected_schema_version="epistemic_capsule_v1",
    )
    validate_schema_v19(capsule_payload, "epistemic_capsule_v1")
    capsule_id = _verify_declared_id(capsule_payload, "capsule_id")
    _, _capsule_obj, imported_capsule_hash = _write_payload_atomic(
        epi_root / "capsules",
        "epistemic_capsule_v1.json",
        capsule_payload,
        id_field="capsule_id",
    )
    if imported_capsule_hash != capsule_hash:
        fail("NONDETERMINISTIC")

    graph_id = _ensure_sha256_id(capsule_payload.get("distillate_graph_id"))
    strip_receipt_id = _ensure_sha256_id(capsule_payload.get("strip_receipt_id"))
    reduce_contract_id = _ensure_sha256_id(capsule_payload.get("reduce_contract_id"))
    manifest_id = _ensure_sha256_id(capsule_payload.get("sip_manifest_id"))
    receipt_id = _ensure_sha256_id(capsule_payload.get("sip_receipt_id"))
    snapshot_id = _ensure_sha256_id(capsule_payload.get("world_snapshot_id"))
    world_root = _ensure_sha256_id(capsule_payload.get("world_root"))
    episode_id = _ensure_sha256_id(capsule_payload.get("episode_id"))
    usable_b = bool(capsule_payload.get("usable_b"))
    cert_gate_status = str(capsule_payload.get("cert_gate_status", "")).strip().upper()
    if cert_gate_status not in {"PASS", "WARN", "BLOCKED"}:
        fail("SCHEMA_FAIL")
    cert_profile_id_raw = capsule_payload.get("cert_profile_id")
    cert_profile_id = (
        _ensure_sha256_id(cert_profile_id_raw)
        if cert_profile_id_raw is not None
        else "sha256:" + ("0" * 64)
    )

    graph_payload, graph_hash = _find_subrun_payload_by_id(
        subrun_root=subrun_root,
        artifact_id=graph_id,
        suffix="qxwmr_graph_v1.json",
        id_field="graph_id",
        expected_schema_version="qxwmr_graph_v1",
    )
    validate_schema_v19(graph_payload, "qxwmr_graph_v1")
    _, _graph_obj, imported_graph_hash = _write_payload_atomic(
        epi_root / "graphs",
        "qxwmr_graph_v1.json",
        graph_payload,
        id_field="graph_id",
    )
    if imported_graph_hash != graph_hash:
        fail("NONDETERMINISTIC")

    reduce_contract_payload, _reduce_contract_hash = _find_subrun_payload_by_id(
        subrun_root=subrun_root,
        artifact_id=reduce_contract_id,
        suffix="epistemic_reduce_contract_v1.json",
        id_field="contract_id",
        expected_schema_version="epistemic_reduce_contract_v1",
    )
    validate_schema_v19(reduce_contract_payload, "epistemic_reduce_contract_v1")
    instruction_strip_contract_id = _ensure_sha256_id(reduce_contract_payload.get("instruction_strip_contract_id"))
    instruction_strip_contract_payload, instruction_strip_contract_hash = _find_subrun_payload_by_id(
        subrun_root=subrun_root,
        artifact_id=instruction_strip_contract_id,
        suffix="epistemic_instruction_strip_contract_v1.json",
        id_field="contract_id",
        expected_schema_version="epistemic_instruction_strip_contract_v1",
    )
    validate_schema_v19(instruction_strip_contract_payload, "epistemic_instruction_strip_contract_v1")
    _, _strip_contract_obj, imported_strip_contract_hash = _write_payload_atomic(
        epi_root / "contracts",
        "epistemic_instruction_strip_contract_v1.json",
        instruction_strip_contract_payload,
        id_field="contract_id",
    )
    if imported_strip_contract_hash != instruction_strip_contract_hash:
        fail("NONDETERMINISTIC")

    strip_receipt_paths = sorted(
        subrun_root.glob("**/sha256_*.epistemic_instruction_strip_receipt_v1.json"),
        key=lambda row: row.as_posix(),
    )
    if not strip_receipt_paths:
        fail("MISSING_STATE_INPUT")
    strip_receipt_ids: set[str] = set()
    for strip_receipt_path in strip_receipt_paths:
        strip_receipt_payload, _strip_receipt_hash = _load_hashed_payload(
            path=strip_receipt_path,
            expected_schema_version="epistemic_instruction_strip_receipt_v1",
        )
        validate_schema_v19(strip_receipt_payload, "epistemic_instruction_strip_receipt_v1")
        if _ensure_sha256_id(strip_receipt_payload.get("instruction_strip_contract_id")) != instruction_strip_contract_id:
            fail("NONDETERMINISTIC")
        strip_receipt_id_row = _verify_declared_id(strip_receipt_payload, "receipt_id")
        strip_receipt_ids.add(strip_receipt_id_row)
        _write_payload_atomic(
            epi_root / "strip_receipts",
            "epistemic_instruction_strip_receipt_v1.json",
            strip_receipt_payload,
            id_field="receipt_id",
        )
    strip_receipt_set_hash = canon_hash_obj(
        {
            "schema_version": "epistemic_instruction_strip_receipt_set_v1",
            "receipt_ids": sorted(strip_receipt_ids),
        }
    )
    if strip_receipt_set_hash != strip_receipt_id:
        fail("NONDETERMINISTIC")

    manifest_payload, manifest_hash = _find_subrun_payload_by_id(
        subrun_root=subrun_root,
        artifact_id=manifest_id,
        suffix="world_snapshot_manifest_v1.json",
        id_field="manifest_id",
        expected_schema_version="v19_0",
        expected_schema_name="world_snapshot_manifest_v1",
    )
    validate_schema_v19(manifest_payload, "world_snapshot_manifest_v1")
    _, _manifest_obj, imported_manifest_hash = _write_payload_atomic(
        epi_root / "world" / "manifests",
        "world_snapshot_manifest_v1.json",
        manifest_payload,
        id_field="manifest_id",
    )
    if imported_manifest_hash != manifest_hash:
        fail("NONDETERMINISTIC")

    receipt_payload, receipt_hash = _find_subrun_payload_by_id(
        subrun_root=subrun_root,
        artifact_id=receipt_id,
        suffix="sealed_ingestion_receipt_v1.json",
        id_field="receipt_id",
        expected_schema_version="v19_0",
        expected_schema_name="sealed_ingestion_receipt_v1",
    )
    validate_schema_v19(receipt_payload, "sealed_ingestion_receipt_v1")
    _, _receipt_obj, imported_receipt_hash = _write_payload_atomic(
        epi_root / "world" / "receipts",
        "sealed_ingestion_receipt_v1.json",
        receipt_payload,
        id_field="receipt_id",
    )
    if imported_receipt_hash != receipt_hash:
        fail("NONDETERMINISTIC")

    snapshot_payload, snapshot_hash = _find_subrun_payload_by_id(
        subrun_root=subrun_root,
        artifact_id=snapshot_id,
        suffix="world_snapshot_v1.json",
        id_field="world_snapshot_id",
        expected_schema_version="v19_0",
        expected_schema_name="world_snapshot_v1",
    )
    validate_schema_v19(snapshot_payload, "world_snapshot_v1")
    _, _snapshot_obj, imported_snapshot_hash = _write_payload_atomic(
        epi_root / "world" / "snapshots",
        "world_snapshot_v1.json",
        snapshot_payload,
        id_field="world_snapshot_id",
    )
    if imported_snapshot_hash != snapshot_hash:
        fail("NONDETERMINISTIC")

    if _ensure_sha256_id(snapshot_payload.get("world_manifest_ref")) != manifest_id:
        fail("NONDETERMINISTIC")
    if _ensure_sha256_id(snapshot_payload.get("ingestion_receipt_ref")) != receipt_id:
        fail("NONDETERMINISTIC")
    if _ensure_sha256_id(snapshot_payload.get("world_root")) != world_root:
        fail("NONDETERMINISTIC")
    if _ensure_sha256_id(receipt_payload.get("world_manifest_ref")) != manifest_id:
        fail("NONDETERMINISTIC")
    if _ensure_sha256_id(receipt_payload.get("computed_world_root")) != world_root:
        fail("NONDETERMINISTIC")

    gate_results = receipt_payload.get("gate_results")
    if not isinstance(gate_results, dict):
        fail("SCHEMA_FAIL")
    leakage_gate = gate_results.get("leakage_gate")
    non_interference_gate = gate_results.get("non_interference_gate")
    if not isinstance(leakage_gate, dict) or not isinstance(non_interference_gate, dict):
        fail("SCHEMA_FAIL")
    if _ensure_sha256_id(snapshot_payload.get("leakage_gate_receipt_ref")) != canon_hash_obj(leakage_gate):
        fail("NONDETERMINISTIC")
    if _ensure_sha256_id(snapshot_payload.get("non_interference_gate_receipt_ref")) != canon_hash_obj(non_interference_gate):
        fail("NONDETERMINISTIC")

    observed_world_root = compute_world_root(manifest_payload, enforce_sorted=True)
    if observed_world_root != world_root:
        fail("NONDETERMINISTIC")

    type_registry_id_raw = capsule_payload.get("type_registry_id")
    type_binding_id_raw = capsule_payload.get("type_binding_id")
    if (type_registry_id_raw is None) != (type_binding_id_raw is None):
        fail("SCHEMA_FAIL")
    if type_registry_id_raw is not None and type_binding_id_raw is not None:
        type_registry_id = _ensure_sha256_id(type_registry_id_raw)
        type_binding_id = _ensure_sha256_id(type_binding_id_raw)
        if graph_payload.get("type_registry_id") is not None:
            if _ensure_sha256_id(graph_payload.get("type_registry_id")) != type_registry_id:
                fail("NONDETERMINISTIC")

        type_registry_payload, type_registry_hash = _find_subrun_payload_by_id(
            subrun_root=subrun_root,
            artifact_id=type_registry_id,
            suffix="epistemic_type_registry_v1.json",
            id_field="registry_id",
            expected_schema_version="epistemic_type_registry_v1",
        )
        validate_schema_v19(type_registry_payload, "epistemic_type_registry_v1")
        _, _type_registry_obj, imported_type_registry_hash = _write_payload_atomic(
            epi_root / "type_registry",
            "epistemic_type_registry_v1.json",
            type_registry_payload,
            id_field="registry_id",
        )
        if imported_type_registry_hash != type_registry_hash:
            fail("NONDETERMINISTIC")

        type_binding_payload, type_binding_hash = _find_subrun_payload_by_id(
            subrun_root=subrun_root,
            artifact_id=type_binding_id,
            suffix="epistemic_type_binding_v1.json",
            id_field="binding_id",
            expected_schema_version="epistemic_type_binding_v1",
        )
        validate_schema_v19(type_binding_payload, "epistemic_type_binding_v1")
        if _ensure_sha256_id(type_binding_payload.get("graph_id")) != graph_id:
            fail("NONDETERMINISTIC")
        if _ensure_sha256_id(type_binding_payload.get("type_registry_id")) != type_registry_id:
            fail("NONDETERMINISTIC")
        _, _type_binding_obj, imported_type_binding_hash = _write_payload_atomic(
            epi_root / "type_bindings",
            "epistemic_type_binding_v1.json",
            type_binding_payload,
            id_field="binding_id",
        )
        if imported_type_binding_hash != type_binding_hash:
            fail("NONDETERMINISTIC")

        provisional_paths = sorted(
            subrun_root.glob("**/sha256_*.epistemic_type_provisional_v1.json"),
            key=lambda row: row.as_posix(),
        )
        for path in provisional_paths:
            provisional_payload, _provisional_hash = _load_hashed_payload(
                path=path,
                expected_schema_version="epistemic_type_provisional_v1",
            )
            validate_schema_v19(provisional_payload, "epistemic_type_provisional_v1")
            if _ensure_sha256_id(provisional_payload.get("graph_id")) != graph_id:
                fail("NONDETERMINISTIC")
            _write_payload_atomic(
                epi_root / "type" / "provisionals",
                "epistemic_type_provisional_v1.json",
                provisional_payload,
                id_field="provisional_id",
            )

        ratification_paths = sorted(
            subrun_root.glob("**/sha256_*.epistemic_type_ratification_receipt_v1.json"),
            key=lambda row: row.as_posix(),
        )
        for path in ratification_paths:
            ratification_payload, _ratification_hash = _load_hashed_payload(
                path=path,
                expected_schema_version="epistemic_type_ratification_receipt_v1",
            )
            validate_schema_v19(ratification_payload, "epistemic_type_ratification_receipt_v1")
            if _ensure_sha256_id(ratification_payload.get("type_registry_id")) != type_registry_id:
                fail("NONDETERMINISTIC")
            _write_payload_atomic(
                epi_root / "type" / "ratifications",
                "epistemic_type_ratification_receipt_v1.json",
                ratification_payload,
                id_field="receipt_id",
            )

        out["type_registry_hash"] = imported_type_registry_hash
        out["type_binding_hash"] = imported_type_binding_hash
        out["type_registry_id"] = type_registry_id
        out["type_binding_id"] = type_binding_id

    ecac_paths = sorted(subrun_root.glob("**/sha256_*.epistemic_ecac_v1.json"), key=lambda row: row.as_posix())
    eufc_paths = sorted(subrun_root.glob("**/sha256_*.epistemic_eufc_v1.json"), key=lambda row: row.as_posix())
    if ecac_paths or eufc_paths:
        ecac_unique = _unique_payload_from_paths(ecac_paths, schema_version="epistemic_ecac_v1")
        eufc_unique = _unique_payload_from_paths(eufc_paths, schema_version="epistemic_eufc_v1")
        if ecac_unique is None or eufc_unique is None:
            fail("SCHEMA_FAIL")
        ecac_payload, ecac_hash = ecac_unique
        eufc_payload, eufc_hash = eufc_unique
        validate_schema_v19(ecac_payload, "epistemic_ecac_v1")
        validate_schema_v19(eufc_payload, "epistemic_eufc_v1")
        ecac_id = _verify_declared_id(ecac_payload, "ecac_id")
        eufc_id = _verify_declared_id(eufc_payload, "eufc_id")
        if _ensure_sha256_id(ecac_payload.get("capsule_id")) != capsule_id:
            fail("NONDETERMINISTIC")
        if _ensure_sha256_id(eufc_payload.get("capsule_id")) != capsule_id:
            fail("NONDETERMINISTIC")
        if _ensure_sha256_id(ecac_payload.get("graph_id")) != graph_id:
            fail("NONDETERMINISTIC")
        if _ensure_sha256_id(eufc_payload.get("graph_id")) != graph_id:
            fail("NONDETERMINISTIC")
        if out.get("type_binding_id") is not None:
            if _ensure_sha256_id(ecac_payload.get("type_binding_id")) != str(out.get("type_binding_id")):
                fail("NONDETERMINISTIC")
            if _ensure_sha256_id(eufc_payload.get("type_binding_id")) != str(out.get("type_binding_id")):
                fail("NONDETERMINISTIC")
        _, _ecac_obj, imported_ecac_hash = _write_payload_atomic(
            epi_root / "certs",
            "epistemic_ecac_v1.json",
            ecac_payload,
            id_field="ecac_id",
        )
        _, _eufc_obj, imported_eufc_hash = _write_payload_atomic(
            epi_root / "certs",
            "epistemic_eufc_v1.json",
            eufc_payload,
            id_field="eufc_id",
        )
        if imported_ecac_hash != ecac_hash or imported_eufc_hash != eufc_hash:
            fail("NONDETERMINISTIC")
        out["epistemic_ecac_hash"] = imported_ecac_hash
        out["epistemic_eufc_hash"] = imported_eufc_hash
        out["epistemic_ecac_id"] = ecac_id
        out["epistemic_eufc_id"] = eufc_id

    cert_gate_binding_paths = sorted(
        subrun_root.glob("**/sha256_*.epistemic_cert_gate_binding_v1.json"),
        key=lambda row: row.as_posix(),
    )
    cert_gate_binding_unique = _unique_payload_from_paths(
        cert_gate_binding_paths,
        schema_version="epistemic_cert_gate_binding_v1",
    )
    if cert_gate_binding_unique is not None:
        cert_gate_payload, cert_gate_hash = cert_gate_binding_unique
        cert_gate_mode = str(cert_gate_payload.get("cert_gate_mode", "")).strip().upper()
        if cert_gate_mode not in {"OFF", "WARN", "ENFORCE"}:
            fail("SCHEMA_FAIL")
        _ensure_sha256_id(cert_gate_payload.get("objective_profile_id"))
        cert_profile_id_raw = cert_gate_payload.get("cert_profile_id")
        if cert_profile_id_raw is not None:
            _ensure_sha256_id(cert_profile_id_raw)
        _, _cert_gate_obj, imported_cert_gate_hash = _write_payload_atomic(
            epi_root / "contracts",
            "epistemic_cert_gate_binding_v1.json",
            cert_gate_payload,
            id_field=None,
        )
        if imported_cert_gate_hash != cert_gate_hash:
            fail("NONDETERMINISTIC")
        out["epistemic_cert_gate_binding_hash"] = imported_cert_gate_hash

    cert_profile_paths = sorted(
        subrun_root.glob("**/sha256_*.epistemic_cert_profile_v1.json"),
        key=lambda row: row.as_posix(),
    )
    cert_profile_unique = _unique_payload_from_paths(
        cert_profile_paths,
        schema_version="epistemic_cert_profile_v1",
    )
    if cert_profile_unique is not None:
        cert_profile_payload, cert_profile_hash = cert_profile_unique
        validate_schema_v19(cert_profile_payload, "epistemic_cert_profile_v1")
        _, _cert_profile_obj, imported_cert_profile_hash = _write_payload_atomic(
            epi_root / "certs" / "profiles",
            "epistemic_cert_profile_v1.json",
            cert_profile_payload,
            id_field="cert_profile_id",
        )
        if imported_cert_profile_hash != cert_profile_hash:
            fail("NONDETERMINISTIC")
        out["epistemic_cert_profile_hash"] = imported_cert_profile_hash

    retention_policy_paths = sorted(
        subrun_root.glob("**/sha256_*.epistemic_retention_policy_v1.json"),
        key=lambda row: row.as_posix(),
    )
    retention_policy_unique = _unique_payload_from_paths(
        retention_policy_paths,
        schema_version="epistemic_retention_policy_v1",
    )
    if retention_policy_unique is not None:
        retention_policy_payload, _retention_policy_hash = retention_policy_unique
        validate_schema_v19(retention_policy_payload, "epistemic_retention_policy_v1")
        _write_payload_atomic(
            epi_root / "retention",
            "epistemic_retention_policy_v1.json",
            retention_policy_payload,
            id_field="policy_id",
        )

    deletion_paths = sorted(
        subrun_root.glob("**/sha256_*.epistemic_deletion_plan_v1.json"),
        key=lambda row: row.as_posix(),
    )
    deletion_unique = _unique_payload_from_paths(
        deletion_paths,
        schema_version="epistemic_deletion_plan_v1",
    )
    if deletion_unique is not None:
        deletion_payload, deletion_hash = deletion_unique
        validate_schema_v19(deletion_payload, "epistemic_deletion_plan_v1")
        if _ensure_sha256_id(deletion_payload.get("capsule_id")) != capsule_id:
            fail("NONDETERMINISTIC")
        _, _deletion_obj, imported_deletion_hash = _write_payload_atomic(
            epi_root / "retention",
            "epistemic_deletion_plan_v1.json",
            deletion_payload,
            id_field="plan_id",
        )
        if imported_deletion_hash != deletion_hash:
            fail("NONDETERMINISTIC")
        out["retention_deletion_plan_hash"] = imported_deletion_hash

    sampling_paths = sorted(
        subrun_root.glob("**/sha256_*.epistemic_sampling_manifest_v1.json"),
        key=lambda row: row.as_posix(),
    )
    sampling_unique = _unique_payload_from_paths(
        sampling_paths,
        schema_version="epistemic_sampling_manifest_v1",
    )
    if sampling_unique is not None:
        sampling_payload, sampling_hash = sampling_unique
        validate_schema_v19(sampling_payload, "epistemic_sampling_manifest_v1")
        if _ensure_sha256_id(sampling_payload.get("capsule_id")) != capsule_id:
            fail("NONDETERMINISTIC")
        _, _sampling_obj, imported_sampling_hash = _write_payload_atomic(
            epi_root / "retention",
            "epistemic_sampling_manifest_v1.json",
            sampling_payload,
            id_field="manifest_id",
        )
        if imported_sampling_hash != sampling_hash:
            fail("NONDETERMINISTIC")
        out["retention_sampling_manifest_hash"] = imported_sampling_hash

    summary_paths = sorted(
        subrun_root.glob("**/sha256_*.epistemic_summary_proof_v1.json"),
        key=lambda row: row.as_posix(),
    )
    summary_unique = _unique_payload_from_paths(
        summary_paths,
        schema_version="epistemic_summary_proof_v1",
    )
    if summary_unique is not None:
        summary_payload, summary_hash = summary_unique
        validate_schema_v19(summary_payload, "epistemic_summary_proof_v1")
        if _ensure_sha256_id(summary_payload.get("capsule_id")) != capsule_id:
            fail("NONDETERMINISTIC")
        _, _summary_obj, imported_summary_hash = _write_payload_atomic(
            epi_root / "retention",
            "epistemic_summary_proof_v1.json",
            summary_payload,
            id_field="proof_id",
        )
        if imported_summary_hash != summary_hash:
            fail("NONDETERMINISTIC")
        out["retention_summary_proof_hash"] = imported_summary_hash

    kernel_spec_paths = sorted(
        subrun_root.glob("**/sha256_*.epistemic_kernel_spec_v1.json"),
        key=lambda row: row.as_posix(),
    )
    kernel_spec_unique = _unique_payload_from_paths(
        kernel_spec_paths,
        schema_version="epistemic_kernel_spec_v1",
    )
    if kernel_spec_unique is not None:
        kernel_spec_payload, kernel_spec_hash = kernel_spec_unique
        validate_schema_v19(kernel_spec_payload, "epistemic_kernel_spec_v1")
        kernel_spec_id = _verify_declared_id(kernel_spec_payload, "kernel_spec_id")
        _, _kernel_spec_obj, imported_kernel_spec_hash = _write_payload_atomic(
            epi_root / "kernels" / "specs",
            "epistemic_kernel_spec_v1.json",
            kernel_spec_payload,
            id_field="kernel_spec_id",
        )
        if imported_kernel_spec_hash != kernel_spec_hash:
            fail("NONDETERMINISTIC")
        out["epistemic_kernel_spec_hash"] = imported_kernel_spec_hash
        out["epistemic_kernel_spec_id"] = kernel_spec_id

    if usable_b:
        reason_code = "CERT_OK"
        if cert_gate_status == "WARN":
            reason_code = "CERT_WARN"
        elif cert_gate_status == "BLOCKED":
            reason_code = "CERT_BLOCKED"
        _ = append_usable_index_row(
            state_root=state_root,
            capsule_id=capsule_id,
            distillate_graph_id=graph_id,
            usable_b=True,
            cert_gate_status=cert_gate_status,
            cert_profile_id=cert_profile_id,
            reason_code=reason_code,
        )

    out["capsule_hash"] = imported_capsule_hash
    out["capsule_id"] = capsule_id
    out["world_snapshot_id"] = snapshot_id
    out["world_root"] = world_root
    out["sip_receipt_id"] = receipt_id
    out["distillate_graph_id"] = graph_id
    out["strip_receipt_id"] = strip_receipt_id
    out["episode_id"] = episode_id
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
        "epistemic/capsules",
        "epistemic/usable_capsules",
        "epistemic/refutations",
        "epistemic/graphs",
        "epistemic/type_registry",
        "epistemic/type_bindings",
        "epistemic/type/provisionals",
        "epistemic/type/ratifications",
        "epistemic/certs",
        "epistemic/certs/profiles",
        "epistemic/contracts",
        "epistemic/retention",
        "epistemic/kernels/specs",
        "epistemic/market",
        "epistemic/world/manifests",
        "epistemic/world/receipts",
        "epistemic/world/snapshots",
        "snapshot",
        "subruns",
        "shadow/integrity",
        "shadow/tier_a",
        "shadow/tier_b",
        "shadow/readiness",
        "ledger/epistemic",
        "long_run/mission",
        "long_run/lane",
        "long_run/eval",
        "long_run/health",
        "long_run/debt",
        "long_run/anti_monopoly",
        "long_run/loop_breaker",
        "orch_bandit/state",
        "orch_bandit/updates",
    ]:
        (state_root / rel).mkdir(parents=True, exist_ok=True)

    os.environ["OMEGA_DAEMON_STATE_ROOT"] = str(state_root)
    os.environ["OMEGA_TICK_U64"] = str(int(tick_u64))

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
        long_run_profile, long_run_profile_hash = _load_optional_long_run_profile(config_dir=config_dir, pack=pack)
        long_run_eval_kernel_payload: dict[str, Any] | None = None
        long_run_eval_suite_payload: dict[str, Any] | None = None
        long_run_utility_policy_payload: dict[str, Any] | None = None
        long_run_utility_policy_hash: str | None = None
        dependency_debt_limit_u64 = int(_DEFAULT_DEBT_LIMIT_U64)
        max_ticks_without_frontier_attempt_u64 = int(_DEFAULT_MAX_TICKS_WITHOUT_FRONTIER_ATTEMPT_U64)
        anti_monopoly_consecutive_limit_u64 = int(_DEFAULT_ANTI_MONOPOLY_CONSECUTIVE_LIMIT_U64)
        anti_monopoly_window_u64 = int(_DEFAULT_ANTI_MONOPOLY_WINDOW_U64)
        anti_monopoly_diversity_k_u64 = int(_DEFAULT_ANTI_MONOPOLY_DIVERSITY_K_U64)
        anti_monopoly_cooldown_u64 = int(_DEFAULT_ANTI_MONOPOLY_COOLDOWN_U64)
        milestone_force_sh1_frontier_b = _env_bool(_MILESTONE_FORCE_SH1_FRONTIER_ENV_KEY, default=False)
        prune_ccap_ek_runs_b = _env_bool(_RETENTION_PRUNE_CCAP_EK_RUNS_ENV_KEY, default=False)
        resolved_orch_llm_backend, resolved_orch_model_id = _resolve_orch_runtime_provenance()
        milestone_force_sh1_frontier_until_tick_u64 = _env_u64(
            _MILESTONE_FORCE_SH1_FRONTIER_UNTIL_TICK_U64_ENV_KEY,
            default=40,
            minimum=0,
        )
        frontier_capability_ids_for_debt: list[str] = []
        if long_run_profile is not None:
            long_run_eval_kernel_payload, long_run_eval_suite_payload = _load_long_run_eval_assets(
                config_dir=config_dir,
                pack=pack,
                long_run_profile=long_run_profile,
            )
            long_run_utility_policy_payload, long_run_utility_policy_hash = _load_long_run_utility_policy(
                config_dir=config_dir,
                long_run_profile=long_run_profile,
            )
            scope_mode = str(long_run_profile.get("loop_breaker_scope_mode", "")).strip().upper()
            if scope_mode in {"RESET_ON_LAUNCH", "GLOBAL"}:
                os.environ["OMEGA_LONG_RUN_LOOP_BREAKER_SCOPE_MODE"] = scope_mode
            if resolved_orch_llm_backend != "mlx":
                fail("SCHEMA_FAIL")
            os.environ["ORCH_LLM_BACKEND"] = "mlx"
            os.environ["ORCH_MLX_MODEL"] = str(resolved_orch_model_id).strip() or _DEFAULT_ORCH_MLX_MODEL_ID
            resolved_orch_llm_backend, resolved_orch_model_id = _resolve_orch_runtime_provenance()

            lanes_cfg = long_run_profile.get("lanes")
            if isinstance(lanes_cfg, dict):
                frontier_capability_ids_for_debt = _sorted_unique_strings(
                    list(lanes_cfg.get("frontier_capability_ids") or [])
                )
            if _premarathon_v63_enabled():
                frontier_capability_ids_for_debt = [_SH1_CAPABILITY_ID]
            debt_cfg = long_run_profile.get("dependency_debt")
            if isinstance(debt_cfg, dict):
                dependency_debt_limit_u64 = int(max(1, int(debt_cfg.get("debt_limit_u64", _DEFAULT_DEBT_LIMIT_U64))))
                max_ticks_without_frontier_attempt_u64 = int(
                    max(
                        1,
                        int(
                            debt_cfg.get(
                                "max_ticks_without_frontier_attempt_u64",
                                _DEFAULT_MAX_TICKS_WITHOUT_FRONTIER_ATTEMPT_U64,
                            )
                        ),
                    )
                )
            # Long-run discipline invariant: once frontier exists, no-attempt timeout must
            # deterministically force hard-lock by tick 40.
            max_ticks_without_frontier_attempt_u64 = int(
                min(int(max_ticks_without_frontier_attempt_u64), int(_DEFAULT_MAX_TICKS_WITHOUT_FRONTIER_ATTEMPT_U64))
            )
            if _premarathon_v63_enabled():
                # Premarathon must enter forced-heavy quickly; do not allow long scaffold drift.
                max_ticks_without_frontier_attempt_u64 = int(min(int(max_ticks_without_frontier_attempt_u64), 5))
            anti_cfg = long_run_profile.get("anti_monopoly")
            if isinstance(anti_cfg, dict):
                anti_monopoly_consecutive_limit_u64 = int(
                    max(
                        1,
                        int(
                            anti_cfg.get(
                                "consecutive_no_output_limit_u64",
                                _DEFAULT_ANTI_MONOPOLY_CONSECUTIVE_LIMIT_U64,
                            )
                        ),
                    )
                )
                anti_monopoly_window_u64 = int(
                    max(1, int(anti_cfg.get("window_ticks_u64", _DEFAULT_ANTI_MONOPOLY_WINDOW_U64)))
                )
                anti_monopoly_diversity_k_u64 = int(
                    max(
                        1,
                        int(
                            anti_cfg.get(
                                "low_diversity_campaign_limit_u64",
                                _DEFAULT_ANTI_MONOPOLY_DIVERSITY_K_U64,
                            )
                        ),
                    )
                )
                anti_monopoly_cooldown_u64 = int(
                    max(1, int(anti_cfg.get("cooldown_for_ticks_u64", _DEFAULT_ANTI_MONOPOLY_COOLDOWN_U64)))
                )
            milestone_force_sh1_frontier_b = bool(
                long_run_profile.get("milestone_force_sh1_frontier_b", milestone_force_sh1_frontier_b)
            )
            retention_cfg = long_run_profile.get("retention")
            if isinstance(retention_cfg, dict):
                prune_ccap_ek_runs_b = bool(retention_cfg.get("prune_ccap_ek_runs_b", prune_ccap_ek_runs_b))

        milestone_force_sh1_frontier_b = bool(
            milestone_force_sh1_frontier_b
            and int(tick_u64) <= int(milestone_force_sh1_frontier_until_tick_u64)
        )

        orch_bandit_config_payload: dict[str, Any] | None = None
        orch_bandit_config_hash: str | None = None
        orch_bandit_state_in: dict[str, Any] | None = None
        orch_bandit_state_in_id: str = _SHA256_ZERO
        orch_bandit_config_payload, orch_bandit_config_hash = _load_optional_orch_bandit_config(
            config_dir=config_dir,
            pack=pack,
        )
        if orch_bandit_config_payload is not None:
            orch_bandit_ek_id = _sha256_or_zero(pack.get("long_run_eval_kernel_id"))
            orch_bandit_kernel_ledger_id = _sha256_or_zero(
                (long_run_eval_kernel_payload or {}).get("extensions_ledger_id")
            )
            orch_bandit_state_in, orch_bandit_state_in_id = _load_or_bootstrap_orch_bandit_state(
                state_root=state_root,
                ek_id=orch_bandit_ek_id,
                kernel_ledger_id=orch_bandit_kernel_ledger_id,
            )

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
        _, prev_state, prev_state_hash_for_descriptor = write_state(state_root / "state", prev_state)
        prev_tick_perf, prev_tick_perf_source = _load_prev_tick_perf(prev_state_dir)
        prev_tick_stats, prev_tick_stats_source = _load_prev_tick_stats(prev_state_dir)
        prev_run_scorecard, prev_run_scorecard_source = _load_prev_run_scorecard(prev_state_dir)
        prev_observation_report, _prev_observation_source = _load_prev_observation(prev_state_dir)
        prev_tick_outcome = _load_prev_tick_outcome(prev_state_dir)
        prev_hotspots = _load_prev_hotspots(prev_state_dir)
        prev_episodic_memory = _load_prev_episodic_memory(prev_state_dir)
        prev_dependency_debt_state = _load_prev_dependency_debt_state(prev_state_dir=prev_state_dir)
        prev_anti_monopoly_state = _load_prev_anti_monopoly_state(prev_state_dir=prev_state_dir)
        if long_run_profile is not None:
            prev_state = _overlay_anti_monopoly_cooldowns(
                state=prev_state,
                anti_monopoly_state=prev_anti_monopoly_state,
                tick_u64=int(tick_u64),
            )

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
        epistemic_metrics = _collect_epistemic_metrics_from_prev_state(prev_state_dir)
        for metric_id in sorted(epistemic_metrics.keys()):
            metrics[metric_id] = epistemic_metrics[metric_id]
        metric_series = observation_report.get("metric_series")
        if isinstance(metric_series, dict):
            metric_series["brain_temperature_q32"] = [{"q": int(temperature_q32)}]
            prev_metric_series: dict[str, Any] = {}
            if isinstance(prev_observation_report, dict):
                prev_series_raw = prev_observation_report.get("metric_series")
                if isinstance(prev_series_raw, dict):
                    prev_metric_series = prev_series_raw
            for metric_id in sorted(epistemic_metrics.keys()):
                prev_rows = prev_metric_series.get(metric_id)
                carried_rows: list[Any] = []
                if isinstance(prev_rows, list):
                    carried_rows = list(prev_rows)
                    if len(carried_rows) >= _MAX_METRIC_SERIES_LEN_U64:
                        carried_rows = carried_rows[-(_MAX_METRIC_SERIES_LEN_U64 - 1) :]
                carried_rows.append(epistemic_metrics[metric_id])
                metric_series[metric_id] = carried_rows
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
        lane_name = "BASELINE"
        lane_allowed_capability_ids: list[str] = []
        lane_allowed_effective: list[str] = []
        pending_frontier_goals: list[dict[str, str]] = []
        lane_decision_receipt: dict[str, Any] | None = None
        lane_decision_receipt_hash: str | None = None
        mission_goal_receipt_hash: str | None = None
        eval_report_hash: str | None = None
        eval_mode_for_tick = "CLASSIFY_ONLY"
        prev_health_window = _load_prev_health_window(prev_state_dir=prev_state_dir, window_ticks_u64=100)
        if long_run_profile is not None:
            health_cfg = long_run_profile.get("frontier_health_gate")
            if not isinstance(health_cfg, dict):
                fail("SCHEMA_FAIL")
            prev_health_window = _load_prev_health_window(
                prev_state_dir=prev_state_dir,
                window_ticks_u64=int(max(1, int(health_cfg.get("window_ticks_u64", 100)))),
            )
            lane_name, lane_allowed_capability_ids, frontier_gate_pass_b, lane_reason_codes, lane_health_counts = _resolve_lane(
                tick_u64=tick_u64,
                long_run_profile=long_run_profile,
                prev_health_window=prev_health_window,
            )
            lane_decision_receipt = _build_lane_decision_receipt(
                tick_u64=tick_u64,
                lane_name=lane_name,
                forced_lane_override_b=str(os.environ.get("OMEGA_LONG_RUN_FORCE_LANE", "")).strip().upper() in _LANE_NAMES,
                frontier_gate_pass_b=frontier_gate_pass_b,
                reason_codes=lane_reason_codes,
                health_window_ticks_u64=int(prev_health_window.get("window_ticks_u64", 100)),
                health_counts=lane_health_counts,
                allowed_capability_ids=lane_allowed_capability_ids,
                resolved_orch_llm_backend=resolved_orch_llm_backend,
                resolved_orch_model_id=resolved_orch_model_id,
            )

            registry_caps = registry.get("capabilities")
            if not isinstance(registry_caps, list):
                fail("SCHEMA_FAIL")
            registry_known = {
                str(row.get("capability_id", "")).strip()
                for row in registry_caps
                if isinstance(row, dict) and str(row.get("capability_id", "")).strip()
            }
            lane_allowed_effective = sorted(set(lane_allowed_capability_ids).intersection(registry_known))

            runtime_rows = _normalize_goal_rows(goal_queue)
            runtime_rows = _filter_pending_goals_for_lane(
                rows=runtime_rows,
                allowed_capability_ids=lane_allowed_effective,
            )
            runtime_rows.extend(
                _lane_goal_rows(
                    tick_u64=tick_u64,
                    lane_name=lane_name,
                    capability_ids=lane_allowed_effective,
                )
            )

            mission_cfg = long_run_profile.get("mission")
            if not isinstance(mission_cfg, dict):
                fail("SCHEMA_FAIL")
            mission_rel = _require_safe_relpath(mission_cfg.get("mission_request_rel"))
            mission_default_priority = str(mission_cfg.get("default_priority", "MED")).strip().upper()
            mission_max_goals_u64 = int(max(0, int(mission_cfg.get("max_injected_goals_u64", 0))))
            mission_goals, mission_receipt, mission_payload = ingest_mission_goals(
                tick_u64=tick_u64,
                lane_name=lane_name,
                mission_path=repo_root() / mission_rel,
                lane_allowed_capability_ids=lane_allowed_effective,
                registry=registry,
                default_priority=mission_default_priority,
                max_injected_goals_u64=mission_max_goals_u64,
            )
            if isinstance(mission_payload, dict):
                _, _mission_payload_obj, mission_payload_hash = _write_payload_atomic(
                    state_root / "long_run" / "mission",
                    "mission_request_v1.json",
                    mission_payload,
                )
                if mission_receipt.get("mission_hash") != mission_payload_hash:
                    fail("NONDETERMINISTIC")
            runtime_rows.extend(mission_goals)
            runtime_rows = _merge_goal_rows(rows=runtime_rows)
            goal_queue = {
                "schema_version": "omega_goal_queue_v1",
                "goals": runtime_rows,
            }
            validate_schema(goal_queue, "omega_goal_queue_v1")
            goal_queue_hash = canon_hash_obj(goal_queue)
            pending_frontier_goals = _pending_frontier_goals(
                goal_queue=goal_queue,
                frontier_capability_ids=frontier_capability_ids_for_debt,
            )

            _, _mission_receipt_obj, mission_goal_receipt_hash = _write_payload_atomic(
                state_root / "long_run" / "mission",
                "mission_goal_ingest_receipt_v1.json",
                mission_receipt,
                id_field="receipt_id",
            )

            eval_cfg = long_run_profile.get("evaluation")
            if not isinstance(eval_cfg, dict):
                fail("SCHEMA_FAIL")
            eval_mode_for_tick = str(eval_cfg.get("mode", "CLASSIFY_ONLY")).strip().upper()
            eval_every_ticks_u64 = int(max(1, int(eval_cfg.get("eval_every_ticks_u64", 50))))
            hard_task_eval_every_u64 = int(
                max(1, int(eval_cfg.get("hard_task_eval_every_u64", eval_every_ticks_u64)))
            )
            eval_emit_every_ticks_u64 = int(min(eval_every_ticks_u64, hard_task_eval_every_u64))
            force_eval_b = str(os.environ.get("OMEGA_LONG_RUN_FORCE_EVAL", "0")).strip() == "1"
            if should_emit_eval(
                tick_u64=tick_u64,
                eval_every_ticks_u64=eval_emit_every_ticks_u64,
                force_eval_b=force_eval_b,
            ):
                if long_run_eval_kernel_payload is None or long_run_eval_suite_payload is None:
                    fail("MISSING_STATE_INPUT")
                accumulation_counters = {
                    "heavy_ok_count_by_capability": dict((prev_dependency_debt_state or {}).get("heavy_ok_count_by_capability") or {}),
                    "heavy_no_utility_count_by_capability": dict(
                        (prev_dependency_debt_state or {}).get("heavy_no_utility_count_by_capability") or {}
                    ),
                    "maintenance_count": int((prev_dependency_debt_state or {}).get("maintenance_count_u64", 0)),
                    "dependency_debt_snapshot_hash": canon_hash_obj(prev_dependency_debt_state),
                    "frontier_attempts_u64": int((prev_dependency_debt_state or {}).get("frontier_attempts_u64", 0)),
                }
                eval_report_payload = build_eval_report(
                    tick_u64=tick_u64,
                    mode=eval_mode_for_tick,
                    ek_payload=long_run_eval_kernel_payload,
                    suite_payload=long_run_eval_suite_payload,
                    observation_report=observation_report,
                    previous_observation_report=prev_observation_report,
                    run_scorecard=prev_run_scorecard,
                    tick_stats=prev_tick_stats,
                    accumulation_counters=accumulation_counters,
                )
                _, _eval_report_obj, eval_report_hash = _write_payload_atomic(
                    state_root / "long_run" / "eval",
                    "eval_report_v1.json",
                    eval_report_payload,
                    id_field="report_id",
                )
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
        epistemic_market_settlement_hash = None
        epistemic_action_market_inputs_hash = None
        epistemic_action_bid_set_hash = None
        epistemic_action_selection_hash = None
        epistemic_action_settlement_hash = None
        inputs_descriptor_hash = None
        policy_vm_trace_hash = None
        policy_vm_stark_proof_hash = None
        policy_market_selection_hash = None
        policy_market_selection_commitment_hash = None
        counterfactual_trace_example_hash = None
        shadow_integrity_report_hash = None
        shadow_tier_a_receipt_hash = None
        shadow_tier_b_receipt_hash = None
        shadow_readiness_receipt_hash = None
        shadow_corpus_invariance_receipt_hash = None
        utility_proof_hash: str | None = None
        dependency_routing_receipt_hash: str | None = None
        dependency_debt_snapshot_hash: str | None = None
        orch_bandit_update_receipt_hash: str | None = None
        orch_bandit_context_key: str | None = None
        orch_bandit_context_lane_kind = "UNKNOWN"
        orch_bandit_context_runaway_band_u32 = 0
        orch_bandit_context_objective_kind = "UNKNOWN"
        anti_monopoly_state_hash: str | None = None
        policy_vm_trace_payload_for_proof: dict[str, Any] | None = None
        policy_vm_proof_program_id: str | None = None
        merged_hint_state_hash_for_proof: str | None = None
        policy_vm_proof_runtime_status = "ABSENT"
        policy_vm_proof_profile_id: str | None = None
        policy_vm_proof_options_hash: str | None = None
        policy_vm_proof_runtime_reason_code: str | None = "NOT_REQUESTED"
        policy_vm_proof_fallback_reason_code: str | None = None
        policy_vm_prove_time_ms: int | None = None
        policy_vm_proof_size_bytes: int | None = None
        policy_market_selection_payload: dict[str, Any] | None = None
        policy_market_proposals_by_hash: dict[str, dict[str, Any]] = {}
        policy_market_decisions_by_hash: dict[str, dict[str, Any]] = {}
        policy_market_winner_proposal_hash: str | None = None
        policy_market_selection_policy_payload: dict[str, Any] | None = None
        policy_market_j_profile_payload: dict[str, Any] | None = None
        predictor_hash = _SHA256_ZERO
        j_profile_hash = _SHA256_ZERO
        policy_budget_spec_hash = _SHA256_ZERO
        determinism_contract_hash = _SHA256_ZERO
        selected_declared_class = "UNCLASSIFIED"
        selected_capability_id = ""
        selected_goal_id: str | None = None
        forced_frontier_attempt_b = False
        forced_frontier_debt_key: str | None = None
        forced_frontier_goal_id: str | None = None
        milestone_force_sh1_trigger_b = False
        blocks_debt_key: str | None = None
        blocks_goal_id: str | None = None
        dependency_debt_delta_i64 = 0
        dependency_routing_reason_codes: list[str] = ["NO_DEPENDENCY_ROUTING"]
        probe_gate_drop_reason_code: str | None = None
        probe_gate_drop_detail: dict[str, Any] = {
            "required_probe_ids_v1": [],
            "missing_probe_ids_v1": [],
            "missing_probe_assets_v1": [],
        }
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

                shared_repo_tree_id = compute_repo_base_tree_id_tolerant(repo_root())
                descriptor_payload = build_inputs_descriptor_once(
                    tick_u64=tick_u64,
                    prev_state_hash=prev_state_hash_for_descriptor,
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
                shared_repo_tree_id = compute_repo_base_tree_id_tolerant(repo_root())
                descriptor_payload = build_inputs_descriptor_once(
                    tick_u64=tick_u64,
                    prev_state_hash=prev_state_hash_for_descriptor,
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
            shared_repo_tree_id = compute_repo_base_tree_id_tolerant(repo_root())
            descriptor_payload = build_inputs_descriptor_once(
                tick_u64=tick_u64,
                prev_state_hash=prev_state_hash_for_descriptor,
                repo_tree_id=shared_repo_tree_id,
                observation_hash=observation_hash,
                issue_hash=issue_hash,
                registry_hash=registry_hash,
                policy_program_ids=[_sha256_or_zero(pack.get("coordinator_isa_program_id"))],
                predictor_hash=_sha256_or_zero(predictor_hash),
                j_profile_hash=_sha256_or_zero(j_profile_hash),
                opcode_table_hash=_sha256_or_zero(opcode_table_hash or pack.get("coordinator_opcode_table_id")),
                policy_budget_spec_hash=_sha256_or_zero(policy_budget_spec_hash),
                determinism_contract_hash=_sha256_or_zero(determinism_contract_hash),
            )
            _, descriptor_payload, inputs_descriptor_hash = _write_payload(
                state_root / "policy" / "inputs",
                "inputs_descriptor_v1.json",
                descriptor_payload,
            )
            decision_plan, decision_hash = _bind_decision_plan_to_inputs_descriptor(
                decision_plan=decision_plan,
                inputs_descriptor_hash=inputs_descriptor_hash,
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
                winner_effect_class=(
                    str((prev_tick_outcome or {}).get("effect_class", "")).strip()
                    if isinstance(prev_tick_outcome, dict)
                    else None
                ),
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
            suppressed_capability_ids = suppressed_capability_ids_from_episodic_memory(
                tick_u64=int(tick_u64),
                episodic_memory=prev_episodic_memory,
            )
            suppressed_campaign_ids: set[str] = set()
            for cap_row in caps:
                if not isinstance(cap_row, dict):
                    continue
                capability_id = str(cap_row.get("capability_id", "")).strip()
                campaign_id = str(cap_row.get("campaign_id", "")).strip()
                if capability_id in suppressed_capability_ids and campaign_id:
                    suppressed_campaign_ids.add(campaign_id)
            bids_by_campaign: dict[str, dict[str, Any]] = {}
            bid_hash_by_campaign: dict[str, str] = {}
            for cap in sorted([row for row in caps if isinstance(row, dict)], key=lambda r: str(r.get("campaign_id"))):
                campaign_id = str(cap.get("campaign_id", "")).strip()
                if not campaign_id or not bool(cap.get("enabled", False)):
                    continue
                if campaign_id in suppressed_campaign_ids:
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
            shared_repo_tree_id = compute_repo_base_tree_id_tolerant(repo_root())
            descriptor_payload = build_inputs_descriptor_once(
                tick_u64=tick_u64,
                prev_state_hash=prev_state_hash_for_descriptor,
                repo_tree_id=shared_repo_tree_id,
                observation_hash=observation_hash,
                issue_hash=issue_hash,
                registry_hash=registry_hash,
                policy_program_ids=[_sha256_or_zero(pack.get("coordinator_isa_program_id"))],
                predictor_hash=_sha256_or_zero(predictor_hash),
                j_profile_hash=_sha256_or_zero(j_profile_hash),
                opcode_table_hash=_sha256_or_zero(opcode_table_hash or pack.get("coordinator_opcode_table_id")),
                policy_budget_spec_hash=_sha256_or_zero(policy_budget_spec_hash),
                determinism_contract_hash=_sha256_or_zero(determinism_contract_hash),
            )
            _, descriptor_payload, inputs_descriptor_hash = _write_payload(
                state_root / "policy" / "inputs",
                "inputs_descriptor_v1.json",
                descriptor_payload,
            )
            decision_plan, decision_hash = _bind_decision_plan_to_inputs_descriptor(
                decision_plan=decision_plan,
                inputs_descriptor_hash=inputs_descriptor_hash,
            )
            _mark("decide", decide_start_ns)
            _, decision_plan, decision_hash = _write_payload(
                state_root / "decisions",
                "omega_decision_plan_v1.json",
                decision_plan,
            )

        frontier_goals_pending_b = bool(pending_frontier_goals)
        pending_frontier_goal_by_id = {
            str(row.get("goal_id", "")).strip(): dict(row)
            for row in pending_frontier_goals
            if isinstance(row, dict) and str(row.get("goal_id", "")).strip()
        }
        selected_capability_id = _selected_capability_id_from_plan(decision_plan)
        selected_goal_id = _selected_goal_id_from_plan(decision_plan)
        selected_declared_class = _declared_class_for_capability_id(
            utility_policy=long_run_utility_policy_payload,
            capability_id=selected_capability_id,
        )
        market_selection_in_play_b = bool(
            (bid_selection_receipt_hash is not None)
            or (policy_market_selection_hash is not None)
        )
        if long_run_profile is not None:
            forced_frontier_debt_key = _forced_frontier_debt_key(
                pending_frontier_goals=pending_frontier_goals,
                debt_state=prev_dependency_debt_state,
                debt_limit_u64=dependency_debt_limit_u64,
                max_ticks_without_frontier_attempt_u64=max_ticks_without_frontier_attempt_u64,
                # Anticipate this tick's no-attempt branch so hard-lock forcing is
                # applied in the same tick that would otherwise activate the lock.
                anticipate_without_attempt_u64=1,
            )
            if forced_frontier_debt_key is not None:
                forced_frontier_attempt_b = True
                forced_frontier_goal_id = _goal_id_for_debt_key(
                    pending_frontier_goals=pending_frontier_goals,
                    debt_key=str(forced_frontier_debt_key),
                )
                if forced_frontier_goal_id is None:
                    fail("SCHEMA_FAIL")
                forced_goal_row = pending_frontier_goal_by_id.get(str(forced_frontier_goal_id))
                if forced_goal_row is None:
                    fail("SCHEMA_FAIL")
                forced_capability_id = str(forced_goal_row.get("capability_id", "")).strip()
                eligible_cap_row = _capability_id_to_campaign(
                    registry=registry,
                    capability_id=forced_capability_id,
                    tick_u64=int(tick_u64),
                    state=prev_state,
                )
                cap_row = (
                    eligible_cap_row
                    if eligible_cap_row is not None
                    else _capability_row_for_forced_frontier(
                        registry=registry,
                        capability_id=forced_capability_id,
                    )
                )
                if cap_row is None:
                    fail("SCHEMA_FAIL")
                current_goal_id = _selected_goal_id_from_plan(decision_plan)
                current_capability = _selected_capability_id_from_plan(decision_plan)
                if current_goal_id != str(forced_frontier_goal_id) or current_capability != forced_capability_id:
                    decision_plan, decision_hash = _rewrite_plan_for_forced_frontier_goal(
                        decision_plan=decision_plan,
                        forced_goal_id=str(forced_frontier_goal_id),
                        forced_capability_id=forced_capability_id,
                        cap_row=cap_row,
                    )
                    _, decision_plan, decision_hash = _write_payload(
                        state_root / "decisions",
                        "omega_decision_plan_v1.json",
                        decision_plan,
                    )
                if eligible_cap_row is not None:
                    dependency_routing_reason_codes = [
                        "DEPENDENCY_DEBT_LIMIT_REACHED_FORCING_FRONTIER_ATTEMPT",
                        "FORCED_TARGETED_FRONTIER_ATTEMPT",
                    ]
                else:
                    dependency_routing_reason_codes = [
                        "DEPENDENCY_DEBT_LIMIT_REACHED_FORCING_FRONTIER_ATTEMPT",
                        "FORCED_FRONTIER_ATTEMPT_NOT_ELIGIBLE",
                        "FORCED_TARGETED_FRONTIER_ATTEMPT",
                    ]
                dependency_routing_reason_codes = _with_hard_lock_override_reason(
                    reason_codes=dependency_routing_reason_codes,
                    forced_frontier_attempt_b=forced_frontier_attempt_b,
                    market_selection_in_play_b=market_selection_in_play_b,
                )

            prev_hard_lock_active_b_for_milestone = bool((prev_dependency_debt_state or {}).get("hard_lock_active_b", False))
            milestone_force_sh1_trigger_b = bool(
                milestone_force_sh1_frontier_b and (forced_frontier_attempt_b or prev_hard_lock_active_b_for_milestone)
            )
            if milestone_force_sh1_trigger_b:
                sh1_cap_row = _capability_id_to_campaign(
                    registry=registry,
                    capability_id=_SH1_CAPABILITY_ID,
                    tick_u64=int(tick_u64),
                    state=prev_state,
                )
                if sh1_cap_row is None:
                    sh1_cap_row = _capability_row_for_forced_frontier(
                        registry=registry,
                        capability_id=_SH1_CAPABILITY_ID,
                    )
                if sh1_cap_row is None:
                    fail("SCHEMA_FAIL")
                current_capability = _selected_capability_id_from_plan(decision_plan)
                current_action_kind = str(decision_plan.get("action_kind", "")).strip()
                if current_capability != _SH1_CAPABILITY_ID or current_action_kind not in {"RUN_CAMPAIGN", "RUN_GOAL_TASK"}:
                    decision_plan, decision_hash = _rewrite_plan_for_milestone_sh1_frontier(
                        decision_plan=decision_plan,
                        cap_row=sh1_cap_row,
                    )
                    _, decision_plan, decision_hash = _write_payload(
                        state_root / "decisions",
                        "omega_decision_plan_v1.json",
                        decision_plan,
                    )
                forced_frontier_attempt_b = True
                if "FORCED_TARGETED_FRONTIER_ATTEMPT" not in dependency_routing_reason_codes:
                    dependency_routing_reason_codes.append("FORCED_TARGETED_FRONTIER_ATTEMPT")
                if "MILESTONE_FORCE_SH1_FRONTIER" not in dependency_routing_reason_codes:
                    dependency_routing_reason_codes.append("MILESTONE_FORCE_SH1_FRONTIER")
                dependency_routing_reason_codes = _with_hard_lock_override_reason(
                    reason_codes=dependency_routing_reason_codes,
                    forced_frontier_attempt_b=forced_frontier_attempt_b,
                    market_selection_in_play_b=market_selection_in_play_b,
                )
                lane_name = "FRONTIER"
                lane_reason_codes = [str(row).strip() for row in lane_reason_codes if str(row).strip()]
                if "MILESTONE_FORCE_SH1_FRONTIER" not in lane_reason_codes:
                    lane_reason_codes.append("MILESTONE_FORCE_SH1_FRONTIER")
                lane_allowed_capability_ids = _sorted_unique_strings([*lane_allowed_capability_ids, _SH1_CAPABILITY_ID])
                lane_decision_receipt = _build_lane_decision_receipt(
                    tick_u64=tick_u64,
                    lane_name=lane_name,
                    forced_lane_override_b=str(os.environ.get("OMEGA_LONG_RUN_FORCE_LANE", "")).strip().upper() in _LANE_NAMES,
                    frontier_gate_pass_b=frontier_gate_pass_b,
                    reason_codes=lane_reason_codes,
                    health_window_ticks_u64=int(prev_health_window.get("window_ticks_u64", 100)),
                    health_counts=lane_health_counts,
                    allowed_capability_ids=lane_allowed_capability_ids,
                    resolved_orch_llm_backend=resolved_orch_llm_backend,
                    resolved_orch_model_id=resolved_orch_model_id,
                )

            frontier_progress_totals = _frontier_progress_totals(prev_state_dir=prev_state_dir)
            frontier_attempt_counted_total_u64 = int(
                frontier_progress_totals.get("frontier_attempt_counted_total_u64", 0)
            )
            heavy_utility_ok_total_u64 = int(
                frontier_progress_totals.get("heavy_utility_ok_total_u64", 0)
            )
            heavy_promoted_total_u64 = int(
                frontier_progress_totals.get("heavy_promoted_total_u64", 0)
            )
            bootstrap_reason_code: str | None = None
            if (
                lane_name == "FRONTIER"
                and not forced_frontier_attempt_b
                and not milestone_force_sh1_trigger_b
            ):
                if (
                    heavy_promoted_total_u64 == 0
                    and frontier_attempt_counted_total_u64 == int(_BOOTSTRAP_SH1_FRONTIER_ATTEMPT_THRESHOLD_U64)
                ):
                    bootstrap_reason_code = _BOOTSTRAP_SH1_REASON_FIRST_HEAVY
                elif int(tick_u64) >= int(_BOOTSTRAP_SH1_UTILITY_DROUGHT_TICK_U64) and heavy_utility_ok_total_u64 == 0:
                    bootstrap_reason_code = _BOOTSTRAP_SH1_REASON_UTILITY_DROUGHT
            if isinstance(bootstrap_reason_code, str):
                bootstrap_cap_row = _capability_id_to_campaign(
                    registry=registry,
                    capability_id=_SH1_CAPABILITY_ID,
                    tick_u64=int(tick_u64),
                    state=prev_state,
                )
                if bootstrap_cap_row is None:
                    bootstrap_cap_row = _capability_row_for_forced_frontier(
                        registry=registry,
                        capability_id=_SH1_CAPABILITY_ID,
                    )
                if bootstrap_cap_row is not None:
                    current_capability = _selected_capability_id_from_plan(decision_plan)
                    current_action_kind = str(decision_plan.get("action_kind", "")).strip()
                    if current_capability != _SH1_CAPABILITY_ID or current_action_kind not in {"RUN_CAMPAIGN", "RUN_GOAL_TASK"}:
                        decision_plan, decision_hash = _rewrite_plan_for_frontier_capability_bias(
                            decision_plan=decision_plan,
                            cap_row=bootstrap_cap_row,
                            capability_id=_SH1_CAPABILITY_ID,
                            tie_break_reason=str(bootstrap_reason_code),
                        )
                        _, decision_plan, decision_hash = _write_payload(
                            state_root / "decisions",
                            "omega_decision_plan_v1.json",
                            decision_plan,
                        )
                    if str(bootstrap_reason_code) not in dependency_routing_reason_codes:
                        dependency_routing_reason_codes.append(str(bootstrap_reason_code))
                    lane_reason_codes = [str(row).strip() for row in lane_reason_codes if str(row).strip()]
                    if str(bootstrap_reason_code) not in lane_reason_codes:
                        lane_reason_codes.append(str(bootstrap_reason_code))
                    lane_allowed_capability_ids = _sorted_unique_strings([*lane_allowed_capability_ids, _SH1_CAPABILITY_ID])
                    lane_decision_receipt = _build_lane_decision_receipt(
                        tick_u64=tick_u64,
                        lane_name=lane_name,
                        forced_lane_override_b=str(os.environ.get("OMEGA_LONG_RUN_FORCE_LANE", "")).strip().upper() in _LANE_NAMES,
                        frontier_gate_pass_b=frontier_gate_pass_b,
                        reason_codes=lane_reason_codes,
                        health_window_ticks_u64=int(prev_health_window.get("window_ticks_u64", 100)),
                        health_counts=lane_health_counts,
                        allowed_capability_ids=lane_allowed_capability_ids,
                        resolved_orch_llm_backend=resolved_orch_llm_backend,
                        resolved_orch_model_id=resolved_orch_model_id,
                    )

            utility_recovery_counts = _recent_heavy_utility_ok_counts(prev_state_dir=prev_state_dir)
            utility_recovery_drought_b = bool(
                int(utility_recovery_counts.get("last_50_heavy_utility_ok_u64", 0)) == 0
                and int(utility_recovery_counts.get("last_200_heavy_utility_ok_u64", 0)) == 0
            )
            if (
                lane_name == "FRONTIER"
                and utility_recovery_drought_b
                and not forced_frontier_attempt_b
                and not milestone_force_sh1_trigger_b
            ):
                recovery_capability_id = _preferred_utility_recovery_capability(
                    prev_dependency_debt_state=prev_dependency_debt_state
                )
                recovery_cap_row = _capability_id_to_campaign(
                    registry=registry,
                    capability_id=recovery_capability_id,
                    tick_u64=int(tick_u64),
                    state=prev_state,
                )
                if recovery_cap_row is None:
                    recovery_cap_row = _capability_row_for_forced_frontier(
                        registry=registry,
                        capability_id=recovery_capability_id,
                    )
                if recovery_cap_row is not None:
                    current_capability = _selected_capability_id_from_plan(decision_plan)
                    current_action_kind = str(decision_plan.get("action_kind", "")).strip()
                    if current_capability != recovery_capability_id or current_action_kind not in {"RUN_CAMPAIGN", "RUN_GOAL_TASK"}:
                        decision_plan, decision_hash = _rewrite_plan_for_frontier_capability_bias(
                            decision_plan=decision_plan,
                            cap_row=recovery_cap_row,
                            capability_id=recovery_capability_id,
                            tie_break_reason=f"UTILITY_DROUGHT_RECOVERY:{recovery_capability_id}",
                        )
                        _, decision_plan, decision_hash = _write_payload(
                            state_root / "decisions",
                            "omega_decision_plan_v1.json",
                            decision_plan,
                        )
                    if "UTILITY_DROUGHT_RECOVERY_BIAS" not in dependency_routing_reason_codes:
                        dependency_routing_reason_codes.append("UTILITY_DROUGHT_RECOVERY_BIAS")
                    if recovery_capability_id == _SH1_CAPABILITY_ID and "UTILITY_DROUGHT_RECOVERY_SH1" not in dependency_routing_reason_codes:
                        dependency_routing_reason_codes.append("UTILITY_DROUGHT_RECOVERY_SH1")
                    lane_reason_codes = [str(row).strip() for row in lane_reason_codes if str(row).strip()]
                    if "UTILITY_DROUGHT_RECOVERY_BIAS" not in lane_reason_codes:
                        lane_reason_codes.append("UTILITY_DROUGHT_RECOVERY_BIAS")
                    lane_allowed_capability_ids = _sorted_unique_strings([*lane_allowed_capability_ids, recovery_capability_id])
                    lane_decision_receipt = _build_lane_decision_receipt(
                        tick_u64=tick_u64,
                        lane_name=lane_name,
                        forced_lane_override_b=str(os.environ.get("OMEGA_LONG_RUN_FORCE_LANE", "")).strip().upper() in _LANE_NAMES,
                        frontier_gate_pass_b=frontier_gate_pass_b,
                        reason_codes=lane_reason_codes,
                        health_window_ticks_u64=int(prev_health_window.get("window_ticks_u64", 100)),
                        health_counts=lane_health_counts,
                        allowed_capability_ids=lane_allowed_capability_ids,
                        resolved_orch_llm_backend=resolved_orch_llm_backend,
                        resolved_orch_model_id=resolved_orch_model_id,
                    )

            if lane_decision_receipt is not None:
                lane_decision_receipt_hash = _persist_lane_decision_receipt_final(
                    state_root=state_root,
                    lane_decision_receipt=lane_decision_receipt,
                )

            selected_capability_id = _selected_capability_id_from_plan(decision_plan)
            selected_goal_id = _selected_goal_id_from_plan(decision_plan)
            selected_declared_class = _declared_class_for_capability_id(
                utility_policy=long_run_utility_policy_payload,
                capability_id=selected_capability_id,
            )
            if milestone_force_sh1_trigger_b and str(selected_capability_id).strip() == _SH1_CAPABILITY_ID:
                selected_declared_class = "FRONTIER_HEAVY"
            selected_action_kind_after_lane = str(decision_plan.get("action_kind", "")).strip()
            if selected_action_kind_after_lane in {"RUN_CAMPAIGN", "RUN_GOAL_TASK"}:
                probe_gate_pass_b, probe_gate_reason_code, probe_gate_detail = _probe_coverage_gate_for_capability(
                    utility_policy=long_run_utility_policy_payload,
                    capability_id=selected_capability_id,
                    declared_class=selected_declared_class,
                )
                if not probe_gate_pass_b:
                    fallback_capability_id: str | None = None
                    fallback_cap_row: dict[str, Any] | None = None
                    # Keep forced-targeting semantics intact; only auto-rewrite when not in forced frontier mode.
                    if not forced_frontier_attempt_b and not milestone_force_sh1_trigger_b:
                        fallback_capability_id, fallback_cap_row = _probe_covered_fallback_capability(
                            utility_policy=long_run_utility_policy_payload,
                            lane_allowed_capability_ids=lane_allowed_capability_ids,
                            current_capability_id=selected_capability_id,
                            registry=registry,
                            tick_u64=int(tick_u64),
                            state=prev_state,
                        )
                    if fallback_capability_id is not None and fallback_cap_row is not None:
                        decision_plan, decision_hash = _rewrite_plan_for_frontier_capability_bias(
                            decision_plan=decision_plan,
                            cap_row=fallback_cap_row,
                            capability_id=str(fallback_capability_id),
                            tie_break_reason=f"PROBE_COVERAGE_FALLBACK:{selected_capability_id}->{fallback_capability_id}",
                        )
                        _, decision_plan, decision_hash = _write_payload(
                            state_root / "decisions",
                            "omega_decision_plan_v1.json",
                            decision_plan,
                        )
                        selected_capability_id = _selected_capability_id_from_plan(decision_plan)
                        selected_goal_id = _selected_goal_id_from_plan(decision_plan)
                        selected_declared_class = _declared_class_for_capability_id(
                            utility_policy=long_run_utility_policy_payload,
                            capability_id=selected_capability_id,
                        )
                        if milestone_force_sh1_trigger_b and str(selected_capability_id).strip() == _SH1_CAPABILITY_ID:
                            selected_declared_class = "FRONTIER_HEAVY"
                        if "PROBE_COVERAGE_FALLBACK" not in dependency_routing_reason_codes:
                            dependency_routing_reason_codes.append("PROBE_COVERAGE_FALLBACK")
                    else:
                        probe_gate_drop_reason_code = str(probe_gate_reason_code or "DROPPED_PROBE_MISSING")
                        probe_gate_drop_detail = (
                            dict(probe_gate_detail)
                            if isinstance(probe_gate_detail, dict)
                            else {"required_probe_ids_v1": [], "missing_probe_ids_v1": [], "missing_probe_assets_v1": []}
                        )
            if frontier_goals_pending_b and selected_declared_class == "MAINTENANCE":
                candidate_blocks_goal = None
                if isinstance(selected_goal_id, str) and selected_goal_id in pending_frontier_goal_by_id:
                    candidate_blocks_goal = selected_goal_id
                elif isinstance(forced_frontier_goal_id, str) and forced_frontier_goal_id in pending_frontier_goal_by_id:
                    candidate_blocks_goal = forced_frontier_goal_id
                elif pending_frontier_goal_by_id:
                    candidate_blocks_goal = sorted(pending_frontier_goal_by_id.keys())[0]
                if candidate_blocks_goal is None:
                    fail("SCHEMA_FAIL")
                blocks_goal_id = str(candidate_blocks_goal)
                blocks_row = pending_frontier_goal_by_id.get(blocks_goal_id)
                if not isinstance(blocks_row, dict):
                    fail("SCHEMA_FAIL")
                blocks_debt_key = str(blocks_row.get("debt_key", "")).strip() or None
                if blocks_debt_key is None:
                    fail("SCHEMA_FAIL")
                dependency_debt_delta_i64 = 1
                dependency_routing_reason_codes = ["FRONTIER_BLOCKED_BY_PREREQ", "SCAFFOLDING_ALLOWED"]
            elif forced_frontier_attempt_b and forced_frontier_goal_id is not None:
                blocks_goal_id = str(forced_frontier_goal_id)
                blocks_debt_key = str(forced_frontier_debt_key) if forced_frontier_debt_key else None
                dependency_debt_delta_i64 = 0
                if not dependency_routing_reason_codes:
                    dependency_routing_reason_codes = [
                        "DEPENDENCY_DEBT_LIMIT_REACHED_FORCING_FRONTIER_ATTEMPT",
                        "FORCED_TARGETED_FRONTIER_ATTEMPT",
                    ]
            else:
                blocks_debt_key = None
                blocks_goal_id = None
                dependency_debt_delta_i64 = 0
                if not dependency_routing_reason_codes:
                    dependency_routing_reason_codes = ["NO_DEPENDENCY_ROUTING"]
            if probe_gate_drop_reason_code is not None:
                if str(probe_gate_drop_reason_code) not in dependency_routing_reason_codes:
                    dependency_routing_reason_codes.append(str(probe_gate_drop_reason_code))
                print(
                    json.dumps(
                        {
                            "event": "PROBE_COVERAGE_DROP_V1",
                            "tick_u64": int(tick_u64),
                            "capability_id": str(selected_capability_id),
                            "declared_class": str(selected_declared_class),
                            "reason_code": str(probe_gate_drop_reason_code),
                            "detail": dict(probe_gate_drop_detail),
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    file=sys.stderr,
                )
            # Persist dependency routing receipt after frontier-attempt evidence is known
            # so hard-lock transition outcomes are recorded in the same tick.

        if (
            orch_bandit_config_payload is not None
            and isinstance(orch_bandit_state_in, dict)
        ):
            try:
                action_kind_for_bandit = str(decision_plan.get("action_kind", "")).strip()
                orch_bandit_context_lane_kind = _normalize_orch_bandit_lane_kind(lane_name=lane_name)
                orch_bandit_context_runaway_band_u32 = int(
                    max(0, min(int(decision_plan.get("runaway_escalation_level_u64", 0)), 5))
                )
                orch_bandit_context_objective_kind = str(action_kind_for_bandit).strip() or "UNKNOWN"
                orch_bandit_context_key = orch_bandit_compute_context_key(
                    lane_kind=orch_bandit_context_lane_kind,
                    runaway_level_u32=orch_bandit_context_runaway_band_u32,
                    objective_kind=orch_bandit_context_objective_kind,
                )
                orch_bandit_hard_lock_active_b = bool(
                    bool(forced_frontier_attempt_b)
                    or bool((prev_dependency_debt_state or {}).get("hard_lock_active_b", False))
                    or action_kind_for_bandit == "RUN_GOAL_TASK"
                )
                eligible_capability_ids = _derive_orch_bandit_eligible_capability_ids(
                    registry=registry,
                    utility_policy=long_run_utility_policy_payload,
                    lane_kind=orch_bandit_context_lane_kind,
                    hard_lock_active_b=orch_bandit_hard_lock_active_b,
                    current_selected_capability_id=selected_capability_id,
                    max_arms_u32=int(orch_bandit_config_payload.get("max_arms_per_context_u32", 1)),
                )
                bandit_selected_capability_id = orch_bandit_select_capability_id(
                    config=orch_bandit_config_payload,
                    state=orch_bandit_state_in,
                    context_key=str(orch_bandit_context_key),
                    eligible_capability_ids=list(eligible_capability_ids),
                )
                if action_kind_for_bandit != "RUN_CAMPAIGN":
                    selected_capability_id = str(bandit_selected_capability_id)
                    selected_declared_class = _declared_class_for_capability_id(
                        utility_policy=long_run_utility_policy_payload,
                        capability_id=selected_capability_id,
                    )
                if (
                    action_kind_for_bandit == "RUN_CAMPAIGN"
                    and str(bandit_selected_capability_id) != str(selected_capability_id)
                ):
                    bandit_cap_row = _capability_id_to_campaign(
                        registry=registry,
                        capability_id=str(bandit_selected_capability_id),
                        tick_u64=int(tick_u64),
                        state=prev_state,
                    )
                    if bandit_cap_row is None and orch_bandit_hard_lock_active_b:
                        bandit_cap_row = _capability_row_for_forced_frontier(
                            registry=registry,
                            capability_id=str(bandit_selected_capability_id),
                        )
                    if bandit_cap_row is None:
                        fail("BANDIT_FAIL:NO_ELIGIBLE_ARMS")
                    decision_plan, decision_hash = _rewrite_plan_for_frontier_capability_bias(
                        decision_plan=decision_plan,
                        cap_row=bandit_cap_row,
                        capability_id=str(bandit_selected_capability_id),
                        tie_break_reason=f"BANDIT_V1:{bandit_selected_capability_id}",
                    )
                    _, decision_plan, decision_hash = _write_payload(
                        state_root / "decisions",
                        "omega_decision_plan_v1.json",
                        decision_plan,
                    )
                    selected_capability_id = _selected_capability_id_from_plan(decision_plan)
                    selected_goal_id = _selected_goal_id_from_plan(decision_plan)
                    selected_declared_class = _declared_class_for_capability_id(
                        utility_policy=long_run_utility_policy_payload,
                        capability_id=selected_capability_id,
                    )
            except OrchBanditError as exc:
                fail(str(exc))

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
        candidate_bundle_present_b = False
        probe_executed_b = False
        frontier_attempt_counted_b = False
        frontier_attempt_goal_id: str | None = None
        frontier_attempt_debt_key: str | None = None
        declared_class_for_tick = selected_declared_class if selected_declared_class in _DECLARED_CLASSES else "UNCLASSIFIED"
        effect_class_for_tick = "EFFECT_REJECTED"
        sip_ingestion_evidence = {
            "knowledge_hash": None,
            "refutation_hash": None,
            "manifest_hash": None,
            "receipt_hash": None,
        }
        selected_candidate_target_relpath: str | None = None
        selected_candidate_target_relpaths: list[str] = []
        selected_candidate_target_key: str | None = None
        selected_candidate_patch_sha256: str | None = None
        selected_candidate_shape_id: str | None = None
        selected_candidate_nontriviality_cert_v1: dict[str, Any] | None = None
        selected_candidate_failed_threshold_code: str | None = None
        epistemic_capsule_evidence = {
            "capsule_hash": None,
            "capsule_id": None,
            "world_snapshot_id": None,
            "world_root": None,
            "sip_receipt_id": None,
            "distillate_graph_id": None,
            "episode_id": None,
            "refutation_hash": None,
            "type_registry_hash": None,
            "type_binding_hash": None,
            "type_registry_id": None,
            "type_binding_id": None,
            "epistemic_ecac_hash": None,
            "epistemic_eufc_hash": None,
            "epistemic_ecac_id": None,
            "epistemic_eufc_id": None,
            "epistemic_cert_profile_hash": None,
            "epistemic_cert_gate_binding_hash": None,
            "retention_deletion_plan_hash": None,
            "retention_sampling_manifest_hash": None,
            "retention_summary_proof_hash": None,
            "epistemic_kernel_spec_hash": None,
            "epistemic_kernel_spec_id": None,
        }

        dispatch_env_overrides: dict[str, str] = {}
        prev_failed_patch_ban_map = _failed_patch_ban_map(
            (prev_dependency_debt_state or {}).get("failed_patch_ban_by_debt_key_target"),
            now_tick_u64=int(tick_u64),
        )
        prev_failed_shape_ban_map = _failed_shape_ban_map(
            (prev_dependency_debt_state or {}).get("failed_shape_ban_by_debt_key_target"),
            now_tick_u64=int(tick_u64),
        )
        prev_last_failure_nontriviality_cert_by_debt_key = dict(
            (prev_dependency_debt_state or {}).get("last_failure_nontriviality_cert_by_debt_key") or {}
        )
        prev_last_failure_failed_threshold_by_debt_key = {
            str(key): str(value)
            for key, value in dict((prev_dependency_debt_state or {}).get("last_failure_failed_threshold_by_debt_key") or {}).items()
            if str(key).strip() and str(value).strip()
        }
        selected_action_kind = str(decision_plan.get("action_kind", "")).strip()
        milestone_force_sh1_dispatch_b = bool(
            milestone_force_sh1_trigger_b
            and selected_action_kind in {"RUN_CAMPAIGN", "RUN_GOAL_TASK"}
            and str(selected_capability_id).strip() == _SH1_CAPABILITY_ID
        )
        if (
            selected_action_kind in {"RUN_CAMPAIGN", "RUN_GOAL_TASK"}
            and bool(forced_frontier_attempt_b or milestone_force_sh1_dispatch_b)
            and str(selected_capability_id).strip() == _SH1_CAPABILITY_ID
        ):
            forced_debt_key_for_env = str(forced_frontier_debt_key or blocks_debt_key or "").strip()
            if forced_debt_key_for_env:
                dispatch_env_overrides[_FORCED_DEBT_KEY_ENV_KEY] = forced_debt_key_for_env
                ban_rows = _failed_patch_ban_rows_for_debt_key(
                    ban_map=prev_failed_patch_ban_map,
                    debt_key=forced_debt_key_for_env,
                )
                if ban_rows:
                    dispatch_env_overrides[_FAILED_PATCH_BAN_ENV_KEY] = json.dumps(
                        ban_rows,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                shape_ban_rows = _failed_shape_ban_rows_for_debt_key(
                    ban_map=prev_failed_shape_ban_map,
                    debt_key=forced_debt_key_for_env,
                )
                if shape_ban_rows:
                    dispatch_env_overrides[_FAILED_SHAPE_BAN_ENV_KEY] = json.dumps(
                        shape_ban_rows,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                last_failure_cert = prev_last_failure_nontriviality_cert_by_debt_key.get(str(forced_debt_key_for_env))
                last_failure_threshold = str(
                    prev_last_failure_failed_threshold_by_debt_key.get(str(forced_debt_key_for_env), "")
                ).strip()
                if isinstance(last_failure_cert, dict) or last_failure_threshold:
                    dispatch_env_overrides[_LAST_FAILURE_HINT_ENV_KEY] = json.dumps(
                        {
                            "debt_key": str(forced_debt_key_for_env),
                            "failed_threshold_code": (last_failure_threshold or None),
                            "nontriviality_cert_v1": (dict(last_failure_cert) if isinstance(last_failure_cert, dict) else None),
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    )
            elif _premarathon_v63_enabled() and not milestone_force_sh1_dispatch_b:
                fail("PRECHECK_FAIL:UNBOUND_DEBT_KEY")
        if selected_action_kind in {"RUN_CAMPAIGN", "RUN_GOAL_TASK"} and str(selected_capability_id).strip() == _SH1_CAPABILITY_ID:
            normalized_overrides = {
                str(key): str(value)
                for key, value in sorted(dispatch_env_overrides.items(), key=lambda kv: str(kv[0]))
            }
            print(
                json.dumps(
                    {
                        "event": "SH1_DISPATCH_ENV_OVERRIDES_V1",
                        "tick_u64": int(tick_u64),
                        "capability_id": str(selected_capability_id),
                        "campaign_id": str(decision_plan.get("campaign_id", "")).strip() or None,
                        "forced_heavy_b": int(normalized_overrides.get(_FORCED_HEAVY_ENV_KEY) == "1"),
                        "forced_debt_key": normalized_overrides.get(_FORCED_DEBT_KEY_ENV_KEY),
                        "wiring_locus_relpath": normalized_overrides.get(_FORCED_WIRING_LOCUS_ENV_KEY),
                        "override_keys_v1": list(normalized_overrides.keys()),
                        "env_overrides": normalized_overrides,
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                file=sys.stderr,
            )

        safe_halt = decision_plan.get("action_kind") == "SAFE_HALT"

        if (
            str(decision_plan.get("action_kind")) in {"RUN_CAMPAIGN", "RUN_GOAL_TASK"}
            and probe_gate_drop_reason_code is None
        ):
            dispatch_start_ns = time.monotonic_ns()
            dispatch_receipt, dispatch_hash, dispatch_ctx = dispatch_campaign(
                tick_u64=tick_u64,
                decision_plan=decision_plan,
                registry=registry,
                state_root=state_root,
                run_seed_u64=run_seed_u64,
                runaway_cfg=runaway_cfg,
                dispatch_env_overrides=dispatch_env_overrides,
            )
            _mark("dispatch_campaign", dispatch_start_ns)
            try:
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
            finally:
                _prune_ccap_ephemeral_artifacts(
                    dispatch_ctx=dispatch_ctx,
                    enabled_b=bool(prune_ccap_ek_runs_b),
                    tick_u64=int(tick_u64),
                )
        else:
            active_manifest_after = active_manifest_before

        if isinstance(dispatch_receipt, dict) and str(dispatch_receipt.get("campaign_id", "")).strip() == _SH1_CAMPAIGN_ID:
            selected_candidate = _selected_candidate_from_precheck(dispatch_ctx=dispatch_ctx)
            if selected_candidate is not None:
                selected_candidate_target_relpath = str(selected_candidate.get("target_relpath", "")).strip() or None
                selected_candidate_target_relpaths = [
                    str(row)
                    for row in _normalize_target_relpaths(selected_candidate.get("target_relpaths"))
                ]
                selected_candidate_target_key = str(selected_candidate.get("target_relpaths_key", "")).strip() or None
                if not selected_candidate_target_key:
                    selected_candidate_target_key = _target_relpaths_key(target_relpaths=selected_candidate_target_relpaths)
                selected_candidate_patch_sha256 = _normalize_patch_sha256(selected_candidate.get("patch_sha256"))
                selected_candidate_shape_id = _normalize_sha256(selected_candidate.get("shape_id"))
                cert_obj = selected_candidate.get("nontriviality_cert_v1")
                selected_candidate_nontriviality_cert_v1 = dict(cert_obj) if isinstance(cert_obj, dict) else None
                threshold_code_raw = selected_candidate.get("failed_threshold_code")
                threshold_code = str(threshold_code_raw).strip() if threshold_code_raw is not None else ""
                selected_candidate_failed_threshold_code = threshold_code or None

        utility_proof_hash_raw = str((promotion_receipt or {}).get("utility_proof_hash", "")).strip()
        utility_proof_hash = utility_proof_hash_raw if _is_sha256(utility_proof_hash_raw) else None
        utility_proof_receipt = (
            _load_utility_proof_receipt_by_hash(state_root=state_root, utility_proof_hash=utility_proof_hash)
            if isinstance(utility_proof_hash, str)
            else None
        )
        candidate_bundle_present_b = _candidate_bundle_present_from_artifacts(
            state_root=state_root,
            promotion_receipt=promotion_receipt,
        )
        probe_executed_b = _probe_executed_from_artifacts(utility_receipt=utility_proof_receipt)
        declared_class_for_tick = _declared_class_from_promotion_receipt(promotion_receipt)
        if declared_class_for_tick == "UNCLASSIFIED" and selected_declared_class in _DECLARED_CLASSES:
            declared_class_for_tick = str(selected_declared_class)
        promotion_status_tmp = str((promotion_receipt or {}).get("result", {}).get("status", "")).strip().upper()
        promotion_reason_tmp = str((promotion_receipt or {}).get("result", {}).get("reason_code", "")).strip()
        subverifier_status_tmp = str((subverifier_receipt or {}).get("result", {}).get("status", "")).strip().upper()
        utility_ok_tmp = bool((utility_proof_receipt or {}).get("utility_ok_b", False))
        fallback_effect_class = "EFFECT_REJECTED"
        if probe_gate_drop_reason_code is not None:
            fallback_effect_class = "EFFECT_REJECTED"
        elif declared_class_for_tick in _HEAVY_DECLARED_CLASSES:
            if promotion_reason_tmp == "NO_UTILITY_GAIN_SHADOW" or not utility_ok_tmp:
                fallback_effect_class = "EFFECT_HEAVY_NO_UTILITY"
            elif promotion_status_tmp == "PROMOTED":
                fallback_effect_class = "EFFECT_HEAVY_OK"
        elif declared_class_for_tick == "BASELINE_CORE" and promotion_status_tmp == "PROMOTED":
            fallback_effect_class = "EFFECT_BASELINE_CORE_OK"
        elif declared_class_for_tick == "MAINTENANCE" and subverifier_status_tmp == "VALID":
            fallback_effect_class = "EFFECT_MAINTENANCE_OK"
        effect_class_for_tick = _effect_class_from_promotion_receipt(
            promotion_receipt,
            fallback=fallback_effect_class,
        )

        dispatched_capability_id = str((dispatch_receipt or {}).get("capability_id", "")).strip() or selected_capability_id
        if _frontier_attempt_evidence_satisfied(
            action_kind=str(decision_plan.get("action_kind", "")).strip(),
            declared_class_for_tick=declared_class_for_tick,
            lane_name=lane_name,
            candidate_bundle_present_b=bool(candidate_bundle_present_b),
            dispatch_receipt=dispatch_receipt,
            subverifier_receipt=subverifier_receipt,
        ):
            frontier_attempt_counted_b = True
            if isinstance(selected_goal_id, str) and selected_goal_id in pending_frontier_goal_by_id:
                frontier_attempt_goal_id = selected_goal_id
            else:
                for row in pending_frontier_goals:
                    if not isinstance(row, dict):
                        fail("SCHEMA_FAIL")
                    if str(row.get("capability_id", "")).strip() == dispatched_capability_id:
                        frontier_attempt_goal_id = str(row.get("goal_id", "")).strip() or None
                        if frontier_attempt_goal_id:
                            break
            if frontier_attempt_goal_id is None and isinstance(blocks_goal_id, str) and blocks_goal_id:
                frontier_attempt_goal_id = str(blocks_goal_id)
            if frontier_attempt_goal_id is not None:
                frontier_row = pending_frontier_goal_by_id.get(str(frontier_attempt_goal_id))
                if isinstance(frontier_row, dict):
                    frontier_attempt_debt_key = str(frontier_row.get("debt_key", "")).strip() or None
            if frontier_attempt_debt_key is None and isinstance(blocks_debt_key, str) and blocks_debt_key.strip():
                frontier_attempt_debt_key = str(blocks_debt_key).strip()
            if frontier_attempt_debt_key is None:
                pending_debt_key_rows = sorted(
                    {
                        str(row.get("debt_key", "")).strip()
                        for row in pending_frontier_goals
                        if isinstance(row, dict) and str(row.get("debt_key", "")).strip()
                    }
                )
                if pending_debt_key_rows:
                    frontier_attempt_debt_key = str(pending_debt_key_rows[0])
            if frontier_attempt_counted_b and frontier_attempt_debt_key is None:
                if milestone_force_sh1_trigger_b and str(dispatched_capability_id).strip() == _SH1_CAPABILITY_ID:
                    frontier_attempt_debt_key = "frontier:milestone_sh1"
                elif _premarathon_v63_enabled():
                    fail("PRECHECK_FAIL:UNBOUND_DEBT_KEY")
                else:
                    frontier_attempt_debt_key = "__UNBOUND_FRONTIER_ATTEMPT__"

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
        epistemic_capsule_evidence = _import_epistemic_capsule_artifacts(
            dispatch_ctx=dispatch_ctx,
            state_root=state_root,
        )
        subverifier_reason_code: str | None = None
        reason_code_raw = (subverifier_receipt or {}).get("result", {}).get("reason_code")
        if reason_code_raw is not None:
            value = str(reason_code_raw).strip()
            if value:
                subverifier_reason_code = value
        subverifier_nontriviality_cert_v1 = (
            dict((subverifier_receipt or {}).get("nontriviality_cert_v1") or {})
            if isinstance((subverifier_receipt or {}).get("nontriviality_cert_v1"), dict)
            else None
        )

        if isinstance(decision_plan, dict):
            winner_campaign_id = str((dispatch_receipt or {}).get("campaign_id") or decision_plan.get("campaign_id", "")).strip()
            if winner_campaign_id:
                capsule_id_raw = (epistemic_capsule_evidence or {}).get("capsule_id")
                ecac_id_raw = (epistemic_capsule_evidence or {}).get("epistemic_ecac_id")
                eufc_id_raw = (epistemic_capsule_evidence or {}).get("epistemic_eufc_id")
                graph_id_raw = (epistemic_capsule_evidence or {}).get("distillate_graph_id")
                capsule_id = _ensure_sha256_id(capsule_id_raw) if isinstance(capsule_id_raw, str) and capsule_id_raw.strip() else None
                ecac_id = _ensure_sha256_id(ecac_id_raw) if isinstance(ecac_id_raw, str) and ecac_id_raw.strip() else None
                eufc_id = _ensure_sha256_id(eufc_id_raw) if isinstance(eufc_id_raw, str) and eufc_id_raw.strip() else None
                graph_id = _ensure_sha256_id(graph_id_raw) if isinstance(graph_id_raw, str) and graph_id_raw.strip() else None

                action_market_profile = build_default_action_market_profile()
                _, action_market_profile, _action_market_profile_hash = _write_payload_atomic(
                    state_root / "epistemic" / "market" / "actions" / "profiles",
                    "epistemic_action_market_profile_v1.json",
                    action_market_profile,
                    id_field="profile_id",
                )
                prior_action_state_id = _load_prev_action_market_state_id(prev_state_dir)
                state_roots_for_window = [state_root]
                if prev_state_dir is not None:
                    state_roots_for_window.append(prev_state_dir.resolve())
                eufc_window_rows = _collect_eufc_window_rows(
                    current_tick_u64=int(tick_u64),
                    window_ticks_u64=int(action_market_profile.get("eufc_window_ticks_u64", 8)),
                    state_roots=state_roots_for_window,
                )
                eufc_window_close_tick = int(tick_u64)
                eufc_window_open_tick = max(
                    0,
                    int(tick_u64) - int(action_market_profile.get("eufc_window_ticks_u64", 8)) + 1,
                )
                action_inputs_manifest = build_action_market_inputs_manifest(
                    tick_u64=int(tick_u64),
                    market_profile_id=str(action_market_profile.get("profile_id")),
                    prior_market_state_id=prior_action_state_id,
                    observation_report_hash=str(observation_hash),
                    observation_metric_ids=_observation_metric_ids(observation_report),
                    eligible_capsule_ids=([capsule_id] if capsule_id is not None else []),
                    eligible_graph_ids=([graph_id] if graph_id is not None else []),
                    eligible_ecac_ids=([ecac_id] if ecac_id is not None else []),
                    eligible_eufc_ids=([eufc_id] if eufc_id is not None else []),
                    eufc_window_receipt_rows=eufc_window_rows,
                    eufc_window_open_tick_u64=eufc_window_open_tick,
                    eufc_window_close_tick_u64=eufc_window_close_tick,
                )
                _, action_inputs_manifest, epistemic_action_market_inputs_hash = _write_payload_atomic(
                    state_root / "epistemic" / "market" / "actions" / "inputs",
                    "epistemic_action_market_inputs_v1.json",
                    action_inputs_manifest,
                    id_field="inputs_manifest_id",
                )
                action_bids = build_action_bids(
                    inputs_manifest=action_inputs_manifest,
                    market_profile=action_market_profile,
                )
                written_action_bids: list[dict[str, Any]] = []
                for bid_row in sorted(action_bids, key=lambda row: str(row.get("action_kind", ""))):
                    _, bid_obj, _ = _write_payload_atomic(
                        state_root / "epistemic" / "market" / "actions" / "bids",
                        "epistemic_action_bid_v1.json",
                        bid_row,
                        id_field="bid_id",
                    )
                    written_action_bids.append(dict(bid_obj))
                action_bid_set = build_action_bid_set(
                    inputs_manifest=action_inputs_manifest,
                    market_profile=action_market_profile,
                    bids=written_action_bids,
                )
                _, action_bid_set, epistemic_action_bid_set_hash = _write_payload_atomic(
                    state_root / "epistemic" / "market" / "actions" / "bid_sets",
                    "epistemic_action_bid_set_v1.json",
                    action_bid_set,
                    id_field="bid_set_id",
                )
                action_selection = select_action_winner(
                    inputs_manifest=action_inputs_manifest,
                    market_profile=action_market_profile,
                    bid_set=action_bid_set,
                    bids=written_action_bids,
                )
                _, action_selection, epistemic_action_selection_hash = _write_payload_atomic(
                    state_root / "epistemic" / "market" / "actions" / "selection",
                    "epistemic_action_selection_receipt_v1.json",
                    action_selection,
                    id_field="selection_id",
                )
                action_settlement = settle_action_selection(
                    inputs_manifest=action_inputs_manifest,
                    selection_receipt=action_selection,
                    produced_capsule_id=capsule_id,
                )
                _, action_settlement, epistemic_action_settlement_hash = _write_payload_atomic(
                    state_root / "epistemic" / "market" / "actions" / "settlement",
                    "epistemic_action_settlement_receipt_v1.json",
                    action_settlement,
                    id_field="action_settlement_id",
                )
                credit_key_raw = action_settlement.get("credit_key")
                if eufc_id is not None and isinstance(credit_key_raw, str) and credit_key_raw.strip():
                    _updated_eufc_payload, _updated_eufc_hash = _rewrite_eufc_with_credit_attribution(
                        state_root=state_root,
                        eufc_id=eufc_id,
                        credit_key=credit_key_raw,
                        credit_window_open_tick_u64=int(action_inputs_manifest.get("eufc_window_open_tick_u64", 0)),
                        credit_window_close_tick_u64=int(action_inputs_manifest.get("eufc_window_close_tick_u64", 0)),
                        credit_window_receipt_ids=[str(row) for row in list(action_inputs_manifest.get("eufc_window_receipt_ids") or [])],
                    )
                    eufc_id = _ensure_sha256_id(_updated_eufc_payload.get("eufc_id"))
                    if isinstance(epistemic_capsule_evidence, dict):
                        epistemic_capsule_evidence["epistemic_eufc_id"] = eufc_id
                        epistemic_capsule_evidence["epistemic_eufc_hash"] = _updated_eufc_hash

                settlement_binding_hash = canon_hash_obj(
                    {
                        "schema_version": "epistemic_market_settlement_binding_v1",
                        "tick_u64": int(tick_u64),
                        "inputs_manifest_id": str(action_inputs_manifest.get("inputs_manifest_id")),
                        "bid_selection_receipt_hash": (
                            str(bid_selection_receipt_hash)
                            if isinstance(bid_selection_receipt_hash, str) and bid_selection_receipt_hash
                            else "sha256:" + ("0" * 64)
                        ),
                        "bid_settlement_receipt_hash": (
                            str(bid_settlement_receipt_hash)
                            if isinstance(bid_settlement_receipt_hash, str) and bid_settlement_receipt_hash
                            else "sha256:" + ("0" * 64)
                        ),
                        "winner_campaign_id": winner_campaign_id,
                        "capsule_id": capsule_id,
                        "ecac_id": ecac_id,
                        "eufc_id": eufc_id,
                        "action_bid_set_hash": epistemic_action_bid_set_hash,
                        "action_selection_receipt_hash": epistemic_action_selection_hash,
                        "action_settlement_receipt_hash": epistemic_action_settlement_hash,
                    }
                )
                settlement_payload = {
                    "schema_version": "epistemic_market_settlement_v1",
                    "settlement_id": "sha256:" + ("0" * 64),
                    "tick_u64": int(tick_u64),
                    "inputs_manifest_id": str(action_inputs_manifest.get("inputs_manifest_id")),
                    "bid_selection_receipt_hash": (
                        str(bid_selection_receipt_hash)
                        if isinstance(bid_selection_receipt_hash, str) and bid_selection_receipt_hash
                        else "sha256:" + ("0" * 64)
                    ),
                    "bid_settlement_receipt_hash": (
                        str(bid_settlement_receipt_hash)
                        if isinstance(bid_settlement_receipt_hash, str) and bid_settlement_receipt_hash
                        else "sha256:" + ("0" * 64)
                    ),
                    "winner_campaign_id": winner_campaign_id,
                    "capsule_id": capsule_id,
                    "ecac_id": ecac_id,
                    "eufc_id": eufc_id,
                    "action_bid_set_hash": epistemic_action_bid_set_hash,
                    "action_selection_receipt_hash": epistemic_action_selection_hash,
                    "action_settlement_receipt_hash": epistemic_action_settlement_hash,
                    "binding_hash": settlement_binding_hash,
                }
                validate_schema_v19(settlement_payload, "epistemic_market_settlement_v1")
                _, _settlement_obj, epistemic_market_settlement_hash = _write_payload_atomic(
                    state_root / "epistemic" / "market",
                    "epistemic_market_settlement_v1.json",
                    settlement_payload,
                    id_field="settlement_id",
                )

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
        debt_reduced_b = False
        effective_change_b = False
        if long_run_profile is not None:
            pending_debt_keys = sorted(
                {
                    str(row.get("debt_key", "")).strip()
                    for row in pending_frontier_goals
                    if isinstance(row, dict) and str(row.get("debt_key", "")).strip()
                }
            )
            prev_debt_by_key = _u64_map((prev_dependency_debt_state or {}).get("debt_by_key"))
            prev_ticks_by_key = _u64_map((prev_dependency_debt_state or {}).get("ticks_without_frontier_attempt_by_key"))
            prev_first_by_key = _u64_map((prev_dependency_debt_state or {}).get("first_debt_tick_by_key"))
            if not prev_debt_by_key:
                prev_debt_by_key = _project_key_map_from_goal_map(
                    pending_frontier_goals=pending_frontier_goals,
                    by_goal=_u64_map((prev_dependency_debt_state or {}).get("debt_by_goal_id")),
                )
            if not prev_ticks_by_key:
                prev_ticks_by_key = _project_key_map_from_goal_map(
                    pending_frontier_goals=pending_frontier_goals,
                    by_goal=_u64_map((prev_dependency_debt_state or {}).get("ticks_without_frontier_attempt_by_goal_id")),
                )
            if not prev_first_by_key:
                prev_first_by_key = _project_key_map_from_goal_map(
                    pending_frontier_goals=pending_frontier_goals,
                    by_goal=_u64_map((prev_dependency_debt_state or {}).get("first_debt_tick_by_goal_id")),
                )
            if frontier_attempt_counted_b and not str(frontier_attempt_debt_key or "").strip():
                fail("SCHEMA_FAIL")
            next_debt_by_key: dict[str, int] = {}
            next_ticks_by_key: dict[str, int] = {}
            next_first_by_key: dict[str, int] = {}
            for debt_key in pending_debt_keys:
                prev_debt = int(max(0, int(prev_debt_by_key.get(debt_key, 0))))
                prev_ticks = int(max(0, int(prev_ticks_by_key.get(debt_key, 0))))
                next_debt = int(prev_debt)
                next_ticks = int(prev_ticks)
                if frontier_attempt_counted_b and debt_key == str(frontier_attempt_debt_key or ""):
                    next_debt = 0
                    next_ticks = 0
                else:
                    if int(dependency_debt_delta_i64) > 0 and str(blocks_debt_key or "") == debt_key:
                        next_debt = int(next_debt + int(dependency_debt_delta_i64))
                    next_ticks = int(next_ticks + 1)
                if next_debt > 0:
                    next_debt_by_key[debt_key] = int(next_debt)
                if next_ticks > 0:
                    next_ticks_by_key[debt_key] = int(next_ticks)
                if next_debt > 0 or next_ticks > 0:
                    if prev_debt > 0 or prev_ticks > 0:
                        next_first_by_key[debt_key] = int(max(0, int(prev_first_by_key.get(debt_key, int(tick_u64)))))
                    else:
                        next_first_by_key[debt_key] = int(tick_u64)
                debt_reduced_b = bool(debt_reduced_b or (next_debt < prev_debt))

            compat_debt_by_goal: dict[str, int] = {}
            compat_ticks_by_goal: dict[str, int] = {}
            compat_first_by_goal: dict[str, int] = {}
            for goal_id, row in sorted(pending_frontier_goal_by_id.items(), key=lambda kv: str(kv[0])):
                if not isinstance(row, dict):
                    fail("SCHEMA_FAIL")
                debt_key = str(row.get("debt_key", "")).strip()
                if not debt_key:
                    fail("SCHEMA_FAIL")
                debt_u64 = int(max(0, int(next_debt_by_key.get(debt_key, 0))))
                if debt_u64 <= 0:
                    continue
                compat_debt_by_goal[str(goal_id)] = int(debt_u64)
                compat_ticks_by_goal[str(goal_id)] = int(max(0, int(next_ticks_by_key.get(debt_key, 0))))
                compat_first_by_goal[str(goal_id)] = int(max(0, int(next_first_by_key.get(debt_key, int(tick_u64)))))

            heavy_ok_count_by_capability = dict((prev_dependency_debt_state or {}).get("heavy_ok_count_by_capability") or {})
            heavy_no_utility_count_by_capability = dict(
                (prev_dependency_debt_state or {}).get("heavy_no_utility_count_by_capability") or {}
            )
            maintenance_count_u64 = int(max(0, int((prev_dependency_debt_state or {}).get("maintenance_count_u64", 0))))
            frontier_attempts_u64 = int(max(0, int((prev_dependency_debt_state or {}).get("frontier_attempts_u64", 0))))
            if selected_capability_id:
                if effect_class_for_tick == "EFFECT_HEAVY_OK":
                    heavy_ok_count_by_capability[selected_capability_id] = int(
                        max(0, int(heavy_ok_count_by_capability.get(selected_capability_id, 0))) + 1
                    )
                elif effect_class_for_tick == "EFFECT_HEAVY_NO_UTILITY":
                    heavy_no_utility_count_by_capability[selected_capability_id] = int(
                        max(0, int(heavy_no_utility_count_by_capability.get(selected_capability_id, 0))) + 1
                    )
            if effect_class_for_tick == "EFFECT_MAINTENANCE_OK":
                maintenance_count_u64 += 1
            if frontier_attempt_counted_b:
                frontier_attempts_u64 += 1

            failure_debt_key = (
                frontier_attempt_debt_key
                or (str(forced_frontier_debt_key).strip() if isinstance(forced_frontier_debt_key, str) else None)
                or (str(blocks_debt_key).strip() if isinstance(blocks_debt_key, str) else None)
            )
            record_failed_frontier_attempt_b = bool(
                str(dispatched_capability_id).strip() == _SH1_CAPABILITY_ID
                and bool(forced_frontier_attempt_b or frontier_attempt_counted_b)
                and str(effect_class_for_tick).strip() != "EFFECT_HEAVY_OK"
            )
            failed_patch_ban_by_debt_key_target = _update_failed_patch_ban_map(
                prev_map=prev_failed_patch_ban_map,
                now_tick_u64=int(tick_u64),
                debt_key=failure_debt_key,
                target_key=selected_candidate_target_key,
                patch_sha256=selected_candidate_patch_sha256,
                record_failure_b=record_failed_frontier_attempt_b,
            )
            failed_shape_ban_by_debt_key_target = _update_failed_shape_ban_map(
                prev_map=prev_failed_shape_ban_map,
                now_tick_u64=int(tick_u64),
                debt_key=failure_debt_key,
                target_key=selected_candidate_target_key,
                shape_id=selected_candidate_shape_id,
                record_failure_b=record_failed_frontier_attempt_b,
            )
            last_failure_nontriviality_cert_by_debt_key = {
                str(key): dict(value)
                for key, value in sorted(prev_last_failure_nontriviality_cert_by_debt_key.items(), key=lambda kv: str(kv[0]))
                if str(key).strip() and isinstance(value, dict)
            }
            last_failure_failed_threshold_by_debt_key = {
                str(key): str(value)
                for key, value in sorted(prev_last_failure_failed_threshold_by_debt_key.items(), key=lambda kv: str(kv[0]))
                if str(key).strip() and str(value).strip()
            }
            if (
                record_failed_frontier_attempt_b
                and isinstance(failure_debt_key, str)
                and str(failure_debt_key).strip()
                and str(subverifier_reason_code or "").strip() == "VERIFY_ERROR:INSUFFICIENT_NONTRIVIAL_DELTA"
                and isinstance(subverifier_nontriviality_cert_v1, dict)
            ):
                key = str(failure_debt_key).strip()
                last_failure_nontriviality_cert_by_debt_key[key] = dict(subverifier_nontriviality_cert_v1)
                failed_threshold_code = str(
                    (subverifier_nontriviality_cert_v1 or {}).get("failed_threshold_code")
                    or (selected_candidate_failed_threshold_code or "")
                ).strip()
                if failed_threshold_code:
                    last_failure_failed_threshold_by_debt_key[key] = failed_threshold_code

            prev_forced_debt_key = _forced_frontier_debt_key(
                pending_frontier_goals=pending_frontier_goals,
                debt_state={
                    "debt_by_key": next_debt_by_key,
                    "ticks_without_frontier_attempt_by_key": next_ticks_by_key,
                    "first_debt_tick_by_key": next_first_by_key,
                },
                debt_limit_u64=dependency_debt_limit_u64,
                max_ticks_without_frontier_attempt_u64=max_ticks_without_frontier_attempt_u64,
            )
            prev_forced_goal = (
                _goal_id_for_debt_key(pending_frontier_goals=pending_frontier_goals, debt_key=prev_forced_debt_key)
                if isinstance(prev_forced_debt_key, str) and prev_forced_debt_key
                else None
            )
            prev_hard_lock_active_b = bool((prev_dependency_debt_state or {}).get("hard_lock_active_b", False))
            next_hard_lock_active_b = bool(forced_frontier_attempt_b or (prev_forced_debt_key is not None))
            hard_lock_debt_key_for_tick = (
                str(forced_frontier_debt_key).strip()
                if bool(forced_frontier_attempt_b) and isinstance(forced_frontier_debt_key, str) and str(forced_frontier_debt_key).strip()
                else (
                    str(prev_forced_debt_key).strip()
                    if isinstance(prev_forced_debt_key, str) and str(prev_forced_debt_key).strip()
                    else None
                )
            )
            hard_lock_goal_id_for_tick = (
                str(forced_frontier_goal_id).strip()
                if bool(forced_frontier_attempt_b) and isinstance(forced_frontier_goal_id, str) and str(forced_frontier_goal_id).strip()
                else (
                    str(prev_forced_goal).strip()
                    if isinstance(prev_forced_goal, str) and str(prev_forced_goal).strip()
                    else None
                )
            )
            hard_lock_became_active_b = bool((not prev_hard_lock_active_b) and next_hard_lock_active_b)
            dependency_routing_reason_codes = _with_frontier_dispatch_failed_pre_evidence_reason(
                reason_codes=dependency_routing_reason_codes,
                hard_lock_became_active_b=hard_lock_became_active_b,
                selected_declared_class=selected_declared_class,
                frontier_attempt_counted_b=frontier_attempt_counted_b,
            )
            routing_selector_id, market_frozen_b, market_used_for_selection_b = _routing_selector_for_receipt(
                reason_codes=list(dependency_routing_reason_codes),
                forced_frontier_attempt_b=bool(forced_frontier_attempt_b),
                market_selection_in_play_b=bool(market_selection_in_play_b),
            )
            if orch_bandit_config_payload is not None and isinstance(orch_bandit_config_hash, str):
                routing_selector_id = str(orch_bandit_config_hash)
                market_used_for_selection_b = False
            dependency_routing_receipt = _build_dependency_routing_receipt(
                tick_u64=tick_u64,
                selected_capability_id=selected_capability_id,
                selected_declared_class=selected_declared_class,
                frontier_goals_pending_b=frontier_goals_pending_b,
                blocks_goal_id=blocks_goal_id,
                blocks_debt_key=blocks_debt_key,
                dependency_debt_delta_i64=int(dependency_debt_delta_i64),
                forced_frontier_attempt_b=bool(forced_frontier_attempt_b),
                forced_frontier_debt_key=forced_frontier_debt_key,
                routing_selector_id=routing_selector_id,
                context_key=orch_bandit_context_key,
                market_frozen_b=bool(market_frozen_b),
                market_used_for_selection_b=bool(market_used_for_selection_b),
                reason_codes=list(dependency_routing_reason_codes),
            )
            _, _dependency_routing_obj, dependency_routing_receipt_hash = _write_payload_atomic(
                state_root / "long_run" / "debt",
                "dependency_routing_receipt_v1.json",
                dependency_routing_receipt,
                id_field="receipt_id",
            )
            maintenance_since_last_frontier_attempt_u64 = int(
                max(0, int((prev_dependency_debt_state or {}).get("maintenance_since_last_frontier_attempt_u64", 0)))
            )
            if frontier_attempt_counted_b:
                maintenance_since_last_frontier_attempt_u64 = 0
            elif frontier_goals_pending_b:
                maintenance_since_last_frontier_attempt_u64 += 1
            else:
                maintenance_since_last_frontier_attempt_u64 = 0

            last_frontier_attempt_tick_u64 = int(max(0, int((prev_dependency_debt_state or {}).get("last_frontier_attempt_tick_u64", 0))))
            last_frontier_attempt_debt_key = str(
                (prev_dependency_debt_state or {}).get("last_frontier_attempt_debt_key", "")
            ).strip() or None
            last_frontier_attempt_goal_id = (prev_dependency_debt_state or {}).get("last_frontier_attempt_goal_id")
            if frontier_attempt_counted_b:
                last_frontier_attempt_tick_u64 = int(tick_u64)
                last_frontier_attempt_debt_key = str(frontier_attempt_debt_key) if frontier_attempt_debt_key else None
                last_frontier_attempt_goal_id = str(frontier_attempt_goal_id) if frontier_attempt_goal_id else None
            elif last_frontier_attempt_debt_key:
                projected_last_goal = _goal_id_for_debt_key(
                    pending_frontier_goals=pending_frontier_goals,
                    debt_key=last_frontier_attempt_debt_key,
                )
                if projected_last_goal is not None:
                    last_frontier_attempt_goal_id = projected_last_goal

            debt_reason_code = "N/A"
            if prev_forced_debt_key is not None:
                debt_reason_code = "DEPENDENCY_DEBT_LIMIT_REACHED_FORCING_FRONTIER_ATTEMPT"
            elif frontier_attempt_counted_b:
                debt_reason_code = "FRONTIER_ATTEMPT_COUNTED"

            scaffold_inflight_ccap_id = (
                str((prev_dependency_debt_state or {}).get("scaffold_inflight_ccap_id", "")).strip()
                if isinstance((prev_dependency_debt_state or {}).get("scaffold_inflight_ccap_id"), str)
                else None
            )
            if not scaffold_inflight_ccap_id:
                scaffold_inflight_ccap_id = None
            scaffold_inflight_started_tick_u64_raw = (prev_dependency_debt_state or {}).get("scaffold_inflight_started_tick_u64")
            if scaffold_inflight_ccap_id is None:
                scaffold_inflight_started_tick_u64 = None
            elif isinstance(scaffold_inflight_started_tick_u64_raw, int):
                scaffold_inflight_started_tick_u64 = int(max(0, int(scaffold_inflight_started_tick_u64_raw)))
            else:
                scaffold_inflight_started_tick_u64 = int(tick_u64)

            dependency_debt_state_payload = {
                "schema_name": "dependency_debt_state_v1",
                "schema_version": "v19_0",
                "state_id": _SHA256_ZERO,
                "tick_u64": int(tick_u64),
                "debt_by_key": {str(k): int(v) for k, v in sorted(next_debt_by_key.items(), key=lambda kv: str(kv[0]))},
                "ticks_without_frontier_attempt_by_key": {
                    str(k): int(v) for k, v in sorted(next_ticks_by_key.items(), key=lambda kv: str(kv[0]))
                },
                "first_debt_tick_by_key": {str(k): int(v) for k, v in sorted(next_first_by_key.items(), key=lambda kv: str(kv[0]))},
                "debt_by_goal_id": {str(k): int(v) for k, v in sorted(compat_debt_by_goal.items(), key=lambda kv: str(kv[0]))},
                "ticks_without_frontier_attempt_by_goal_id": {
                    str(k): int(v) for k, v in sorted(compat_ticks_by_goal.items(), key=lambda kv: str(kv[0]))
                },
                "first_debt_tick_by_goal_id": {str(k): int(v) for k, v in sorted(compat_first_by_goal.items(), key=lambda kv: str(kv[0]))},
                "maintenance_since_last_frontier_attempt_u64": int(maintenance_since_last_frontier_attempt_u64),
                "last_frontier_attempt_tick_u64": int(last_frontier_attempt_tick_u64),
                "last_frontier_attempt_debt_key": (
                    str(last_frontier_attempt_debt_key)
                    if isinstance(last_frontier_attempt_debt_key, str) and last_frontier_attempt_debt_key.strip()
                    else None
                ),
                "last_frontier_attempt_goal_id": (
                    str(last_frontier_attempt_goal_id)
                    if isinstance(last_frontier_attempt_goal_id, str) and last_frontier_attempt_goal_id.strip()
                    else None
                ),
                "hard_lock_active_b": bool(next_hard_lock_active_b),
                "hard_lock_debt_key": (
                    str(hard_lock_debt_key_for_tick)
                    if isinstance(hard_lock_debt_key_for_tick, str) and hard_lock_debt_key_for_tick.strip()
                    else None
                ),
                "hard_lock_goal_id": (
                    str(hard_lock_goal_id_for_tick)
                    if isinstance(hard_lock_goal_id_for_tick, str) and hard_lock_goal_id_for_tick.strip()
                    else None
                ),
                "scaffold_inflight_ccap_id": scaffold_inflight_ccap_id,
                "scaffold_inflight_started_tick_u64": scaffold_inflight_started_tick_u64,
                "max_inflight_ccap_ids_u32": 1,
                "reason_code": str(debt_reason_code),
                "heavy_ok_count_by_capability": {
                    str(k): int(max(0, int(v))) for k, v in sorted(heavy_ok_count_by_capability.items(), key=lambda kv: str(kv[0]))
                },
                "heavy_no_utility_count_by_capability": {
                    str(k): int(max(0, int(v))) for k, v in sorted(heavy_no_utility_count_by_capability.items(), key=lambda kv: str(kv[0]))
                },
                "maintenance_count_u64": int(max(0, int(maintenance_count_u64))),
                "frontier_attempts_u64": int(max(0, int(frontier_attempts_u64))),
                "failed_patch_ban_by_debt_key_target": {
                    str(k): list(v)
                    for k, v in sorted(failed_patch_ban_by_debt_key_target.items(), key=lambda kv: str(kv[0]))
                },
                "failed_shape_ban_by_debt_key_target": {
                    str(k): list(v)
                    for k, v in sorted(failed_shape_ban_by_debt_key_target.items(), key=lambda kv: str(kv[0]))
                },
                "last_failure_nontriviality_cert_by_debt_key": {
                    str(k): dict(v)
                    for k, v in sorted(last_failure_nontriviality_cert_by_debt_key.items(), key=lambda kv: str(kv[0]))
                },
                "last_failure_failed_threshold_by_debt_key": {
                    str(k): str(v)
                    for k, v in sorted(last_failure_failed_threshold_by_debt_key.items(), key=lambda kv: str(kv[0]))
                },
            }
            validate_schema_v19(dependency_debt_state_payload, "dependency_debt_state_v1")
            _, _dependency_debt_obj, dependency_debt_snapshot_hash = _write_payload_atomic(
                state_root / "long_run" / "debt",
                "dependency_debt_state_v1.json",
                dependency_debt_state_payload,
                id_field="state_id",
            )

            anti_cooldowns_prev = (prev_anti_monopoly_state or {}).get("campaign_cooldowns")
            anti_history_prev = (prev_anti_monopoly_state or {}).get("history_rows")
            if not isinstance(anti_cooldowns_prev, dict) or not isinstance(anti_history_prev, list):
                fail("SCHEMA_FAIL")
            campaign_cooldowns: dict[str, dict[str, Any]] = {}
            for campaign_id, row in sorted(anti_cooldowns_prev.items(), key=lambda kv: str(kv[0])):
                if not isinstance(row, dict):
                    fail("SCHEMA_FAIL")
                until_tick_u64 = int(max(0, int(row.get("until_tick_u64", 0))))
                if until_tick_u64 <= int(tick_u64):
                    continue
                campaign_cooldowns[str(campaign_id)] = {
                    "until_tick_u64": int(until_tick_u64),
                    "reason_code": str(row.get("reason_code", "N/A") or "N/A"),
                }
            history_rows = [dict(row) for row in anti_history_prev if isinstance(row, dict)]
            outcome_campaign_id = str((dispatch_receipt or {}).get("campaign_id") or decision_plan.get("campaign_id", "")).strip()
            if outcome_campaign_id:
                history_rows.append(
                    {
                        "tick_u64": int(tick_u64),
                        "campaign_id": outcome_campaign_id,
                        "candidate_bundle_present_b": bool(candidate_bundle_present_b),
                        "effective_change_b": bool(_effective_change_from_effect_class(effect_class=effect_class_for_tick, debt_reduced_b=debt_reduced_b)),
                        "effect_class": str(effect_class_for_tick),
                    }
                )
            if len(history_rows) > int(anti_monopoly_window_u64):
                history_rows = history_rows[-int(anti_monopoly_window_u64) :]

            anti_reason_code = "N/A"
            if history_rows:
                streak_campaign_id = str(history_rows[-1].get("campaign_id", "")).strip()
                no_effect_streak = 0
                for row in reversed(history_rows):
                    if str(row.get("campaign_id", "")).strip() != streak_campaign_id:
                        break
                    if bool(row.get("effective_change_b", False)):
                        break
                    no_effect_streak += 1
                if streak_campaign_id and no_effect_streak >= int(anti_monopoly_consecutive_limit_u64):
                    campaign_cooldowns[streak_campaign_id] = {
                        "until_tick_u64": int(tick_u64 + anti_monopoly_cooldown_u64),
                        "reason_code": "ANTI_MONOPOLY_NO_OUTPUT",
                    }
                    anti_reason_code = "ANTI_MONOPOLY_NO_OUTPUT"
                else:
                    window_rows = history_rows[-int(anti_monopoly_window_u64) :]
                    effective_change_count = sum(1 for row in window_rows if bool(row.get("effective_change_b", False)))
                    campaign_ids = [str(row.get("campaign_id", "")).strip() for row in window_rows if str(row.get("campaign_id", "")).strip()]
                    unique_campaign_ids = sorted(set(campaign_ids))
                    if window_rows and effective_change_count == 0 and len(unique_campaign_ids) <= int(anti_monopoly_diversity_k_u64):
                        freq: dict[str, int] = {}
                        for campaign_id in campaign_ids:
                            freq[campaign_id] = int(freq.get(campaign_id, 0) + 1)
                        if freq:
                            offender = sorted(freq.items(), key=lambda kv: (-int(kv[1]), str(kv[0])))[0][0]
                            campaign_cooldowns[str(offender)] = {
                                "until_tick_u64": int(tick_u64 + anti_monopoly_cooldown_u64),
                                "reason_code": "ANTI_MONOPOLY_LOW_DIVERSITY_NO_EFFECT",
                            }
                            anti_reason_code = "ANTI_MONOPOLY_LOW_DIVERSITY_NO_EFFECT"
            anti_monopoly_state_payload = {
                "schema_name": "anti_monopoly_state_v1",
                "schema_version": "v19_0",
                "state_id": _SHA256_ZERO,
                "tick_u64": int(tick_u64),
                "window_ticks_u64": int(max(1, int(anti_monopoly_window_u64))),
                "consecutive_no_output_limit_u64": int(max(1, int(anti_monopoly_consecutive_limit_u64))),
                "low_diversity_campaign_limit_u64": int(max(1, int(anti_monopoly_diversity_k_u64))),
                "cooldown_for_ticks_u64": int(max(1, int(anti_monopoly_cooldown_u64))),
                "campaign_cooldowns": campaign_cooldowns,
                "history_rows": history_rows,
                "last_reason_code": str(anti_reason_code),
            }
            validate_schema_v19(anti_monopoly_state_payload, "anti_monopoly_state_v1")
            _, _anti_monopoly_obj, anti_monopoly_state_hash = _write_payload_atomic(
                state_root / "long_run" / "anti_monopoly",
                "anti_monopoly_state_v1.json",
                anti_monopoly_state_payload,
                id_field="state_id",
            )

        effective_change_b = _effective_change_from_effect_class(
            effect_class=effect_class_for_tick,
            debt_reduced_b=debt_reduced_b,
        )

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
                state_root=state_root,
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
            policy_vm_prove_time_ms = 0
            policy_vm_proof_size_bytes = 0
            proof_start_ns = time.monotonic_ns()
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
            policy_vm_prove_time_ms = max(0, int((time.monotonic_ns() - proof_start_ns) // 1_000_000))

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
                policy_vm_proof_size_bytes = len(proof_bytes)
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
                policy_vm_proof_fallback_reason_code = None

            if policy_vm_stark_proof_hash is None:
                fallback_reason = str(policy_vm_proof_runtime_reason_code or "").strip()
                policy_vm_proof_fallback_reason_code = fallback_reason or "PROOF_NOT_EMITTED"

        shadow_artifacts = _run_shadow_sidecar(
            repo_root_path=repo_root(),
            config_dir=config_dir,
            state_root=state_root,
            pack=pack,
            tick_u64=tick_u64,
        )
        if isinstance(shadow_artifacts, dict):
            integrity_payload = shadow_artifacts.get("integrity_report")
            tier_a_payload = shadow_artifacts.get("tier_a_receipt")
            tier_b_payload = shadow_artifacts.get("tier_b_receipt")
            readiness_payload = shadow_artifacts.get("readiness_receipt")
            corpus_invariance_payload = shadow_artifacts.get("corpus_invariance_receipt")
            if isinstance(integrity_payload, dict):
                _, _shadow_integrity_obj, shadow_integrity_report_hash = _write_payload(
                    state_root / "shadow" / "integrity",
                    "shadow_fs_integrity_report_v1.json",
                    integrity_payload,
                    id_field="report_id",
                )
            if isinstance(tier_a_payload, dict):
                _, _shadow_tier_a_obj, shadow_tier_a_receipt_hash = _write_payload(
                    state_root / "shadow" / "tier_a",
                    "shadow_tier_receipt_v1.json",
                    tier_a_payload,
                )
            if isinstance(tier_b_payload, dict):
                _, _shadow_tier_b_obj, shadow_tier_b_receipt_hash = _write_payload(
                    state_root / "shadow" / "tier_b",
                    "shadow_tier_receipt_v1.json",
                    tier_b_payload,
                )
            if isinstance(readiness_payload, dict):
                _, _shadow_readiness_obj, shadow_readiness_receipt_hash = _write_payload(
                    state_root / "shadow" / "readiness",
                    "shadow_regime_readiness_receipt_v1.json",
                    readiness_payload,
                    id_field="receipt_id",
                )
            if isinstance(corpus_invariance_payload, dict):
                _, _shadow_corpus_invariance_obj, shadow_corpus_invariance_receipt_hash = _write_payload(
                    state_root / "shadow" / "invariance",
                    "shadow_corpus_invariance_receipt_v1.json",
                    corpus_invariance_payload,
                    id_field="receipt_id",
                )

        # Deterministic measurement guarantee: if a heavy attempt is counted, emit an
        # eval report for this tick even when cadence would otherwise skip.
        if (
            long_run_profile is not None
            and eval_report_hash is None
            and bool(frontier_attempt_counted_b)
            and str(declared_class_for_tick).strip() in _HEAVY_DECLARED_CLASSES
        ):
            if long_run_eval_kernel_payload is None or long_run_eval_suite_payload is None:
                fail("MISSING_STATE_INPUT")
            late_heavy_ok_count_by_capability = dict((prev_dependency_debt_state or {}).get("heavy_ok_count_by_capability") or {})
            late_heavy_no_utility_count_by_capability = dict(
                (prev_dependency_debt_state or {}).get("heavy_no_utility_count_by_capability") or {}
            )
            late_maintenance_count_u64 = int((prev_dependency_debt_state or {}).get("maintenance_count_u64", 0))
            late_frontier_attempts_u64 = int((prev_dependency_debt_state or {}).get("frontier_attempts_u64", 0))
            if selected_capability_id:
                if effect_class_for_tick == "EFFECT_HEAVY_OK":
                    late_heavy_ok_count_by_capability[selected_capability_id] = int(
                        max(0, int(late_heavy_ok_count_by_capability.get(selected_capability_id, 0))) + 1
                    )
                elif effect_class_for_tick == "EFFECT_HEAVY_NO_UTILITY":
                    late_heavy_no_utility_count_by_capability[selected_capability_id] = int(
                        max(0, int(late_heavy_no_utility_count_by_capability.get(selected_capability_id, 0))) + 1
                    )
            if effect_class_for_tick == "EFFECT_MAINTENANCE_OK":
                late_maintenance_count_u64 += 1
            late_frontier_attempts_u64 += 1
            late_eval_report_payload = build_eval_report(
                tick_u64=tick_u64,
                mode=eval_mode_for_tick,
                ek_payload=long_run_eval_kernel_payload,
                suite_payload=long_run_eval_suite_payload,
                observation_report=observation_report,
                previous_observation_report=prev_observation_report,
                run_scorecard=prev_run_scorecard,
                tick_stats=prev_tick_stats,
                accumulation_counters={
                    "heavy_ok_count_by_capability": dict(late_heavy_ok_count_by_capability),
                    "heavy_no_utility_count_by_capability": dict(late_heavy_no_utility_count_by_capability),
                    "maintenance_count": int(max(0, int(late_maintenance_count_u64))),
                    "dependency_debt_snapshot_hash": (
                        dependency_debt_snapshot_hash
                        if isinstance(dependency_debt_snapshot_hash, str) and _is_sha256(dependency_debt_snapshot_hash)
                        else canon_hash_obj(prev_dependency_debt_state)
                    ),
                    "frontier_attempts_u64": int(max(0, int(late_frontier_attempts_u64))),
                },
            )
            _, _late_eval_report_obj, eval_report_hash = _write_payload_atomic(
                state_root / "long_run" / "eval",
                "eval_report_v1.json",
                late_eval_report_payload,
                id_field="report_id",
            )

        ledger_path = state_root / "ledger" / "omega_ledger_v1.jsonl"
        prev_event_id: str | None = None
        if ledger_path.exists():
            if not ledger_path.is_file():
                fail("SCHEMA_FAIL")
            lines = [line.strip() for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            if lines:
                try:
                    last_row = json.loads(lines[-1])
                except Exception:  # noqa: BLE001
                    fail("SCHEMA_FAIL")
                if not isinstance(last_row, dict):
                    fail("SCHEMA_FAIL")
                prev_event_id = ensure_sha256(last_row.get("event_id"), reason="SCHEMA_FAIL")
                no_id = dict(last_row)
                no_id.pop("event_id", None)
                if canon_hash_obj(no_id) != prev_event_id:
                    fail("TRACE_HASH_MISMATCH")
        artifact_hashes: list[str] = []
        emitted_epistemic_capsules: set[str] = set()

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
        if lane_decision_receipt_hash is not None:
            _emit("LANE_DECISION", lane_decision_receipt_hash)
        if mission_goal_receipt_hash is not None:
            _emit("MISSION_GOAL_RECEIPT", mission_goal_receipt_hash)
        if eval_report_hash is not None:
            _emit("EVAL_REPORT", eval_report_hash)
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
        if isinstance(utility_proof_hash, str) and utility_proof_hash:
            _emit("UTILITY_PROOF", utility_proof_hash)
        if activation_hash is not None:
            _emit("ACTIVATION", activation_hash)
        extension_queued_hash = str((activation_receipt or {}).get("extension_queued_receipt_hash", "")).strip()
        if _is_sha256(extension_queued_hash):
            _emit("EXTENSION_QUEUED", extension_queued_hash)
        if rollback_hash is not None:
            _emit("ROLLBACK", rollback_hash)
        if dependency_routing_receipt_hash is not None:
            _emit("DEPENDENCY_ROUTING", dependency_routing_receipt_hash)
        if dependency_debt_snapshot_hash is not None:
            _emit("DEPENDENCY_DEBT_STATE", dependency_debt_snapshot_hash)
        if anti_monopoly_state_hash is not None:
            _emit("ANTI_MONOPOLY_STATE", anti_monopoly_state_hash)
        sip_ingestion_hash = str((sip_ingestion_evidence or {}).get("knowledge_hash") or "").strip()
        if sip_ingestion_hash:
            _emit("SIP_INGESTION_L0", sip_ingestion_hash)
        epistemic_capsule_hash = str((epistemic_capsule_evidence or {}).get("capsule_hash") or "").strip()
        if epistemic_capsule_hash:
            capsule_id = _ensure_sha256_id((epistemic_capsule_evidence or {}).get("capsule_id"))
            if capsule_id not in emitted_epistemic_capsules:
                emitted_epistemic_capsules.add(capsule_id)
                event_payload = {
                    "schema_name": "omega_event_epistemic_capsule_v1",
                    "schema_version": "v19_0",
                    "capsule_id": capsule_id,
                    "world_snapshot_id": _ensure_sha256_id((epistemic_capsule_evidence or {}).get("world_snapshot_id")),
                    "world_root": _ensure_sha256_id((epistemic_capsule_evidence or {}).get("world_root")),
                    "sip_receipt_id": _ensure_sha256_id((epistemic_capsule_evidence or {}).get("sip_receipt_id")),
                    "distillate_graph_id": _ensure_sha256_id((epistemic_capsule_evidence or {}).get("distillate_graph_id")),
                    "episode_id": _ensure_sha256_id((epistemic_capsule_evidence or {}).get("episode_id")),
                }
                validate_schema_v19(event_payload, "omega_event_epistemic_capsule_v1")
                _, _event_obj, event_payload_hash = _write_payload_atomic(
                    state_root / "ledger" / "epistemic",
                    "omega_event_epistemic_capsule_v1.json",
                    event_payload,
                )
                _emit("EPISTEMIC_CAPSULE_V1", event_payload_hash)
        for event_type, key in [
            ("EPISTEMIC_TYPE_REGISTRY_V1", "type_registry_hash"),
            ("EPISTEMIC_TYPE_BINDING_V1", "type_binding_hash"),
            ("EPISTEMIC_ECAC_V1", "epistemic_ecac_hash"),
            ("EPISTEMIC_EUFC_V1", "epistemic_eufc_hash"),
            ("EPISTEMIC_RETENTION_DELETION_PLAN_V1", "retention_deletion_plan_hash"),
            ("EPISTEMIC_RETENTION_SAMPLING_MANIFEST_V1", "retention_sampling_manifest_hash"),
            ("EPISTEMIC_RETENTION_SUMMARY_PROOF_V1", "retention_summary_proof_hash"),
            ("EPISTEMIC_KERNEL_SPEC_V1", "epistemic_kernel_spec_hash"),
        ]:
            artifact_hash = str((epistemic_capsule_evidence or {}).get(key) or "").strip()
            if artifact_hash:
                _emit(event_type, artifact_hash)
        if isinstance(epistemic_action_market_inputs_hash, str) and epistemic_action_market_inputs_hash:
            _emit("EPISTEMIC_ACTION_MARKET_INPUTS_V1", epistemic_action_market_inputs_hash)
        if isinstance(epistemic_market_settlement_hash, str) and epistemic_market_settlement_hash:
            _emit("EPISTEMIC_MARKET_SETTLEMENT_V1", epistemic_market_settlement_hash)

        # Deterministic evidence that hotpaths actually exercised the runtime
        # router (and, when active, the native backend). We emit this into the
        # trace chain so it is covered by the tick snapshot hash.
        try:
            from orchestrator.native.native_router_v1 import drain_runtime_stats

            native_ops = drain_runtime_stats()
        except Exception:
            native_ops = []
        native_ops_rows = [dict(row) for row in native_ops if isinstance(row, dict)]
        fastpath_row = {
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
        fastpath_row["work_units_u64"] = int(derive_work_units_from_row(fastpath_row))
        native_ops_rows.append(fastpath_row)
        stats_payload = {
            "schema_version": "omega_native_runtime_stats_v1",
            "stats_id": "sha256:" + ("0" * 64),
            "tick_u64": int(tick_u64),
            "runtime_stats_source_id": RUNTIME_STATS_SOURCE_ID,
            "work_units_formula_id": WORK_UNITS_FORMULA_ID,
            "total_work_units_u64": int(derive_total_work_units(native_ops_rows)),
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
        from orchestrator.native.wasm_shadow_soak_v1 import emit_shadow_soak_artifacts

        _shadow_summary_obj, shadow_summary_hash, _shadow_receipt_obj, shadow_receipt_hash = emit_shadow_soak_artifacts(
            state_root=state_root,
            tick_u64=int(tick_u64),
        )
        _emit("NATIVE_WASM_SHADOW_SOAK_SUMMARY", shadow_summary_hash)
        _emit("NATIVE_WASM_SHADOW_SOAK_RECEIPT", shadow_receipt_hash)
        if shadow_integrity_report_hash is not None:
            _emit("SHADOW_FS_INTEGRITY", shadow_integrity_report_hash)
        if shadow_tier_a_receipt_hash is not None:
            _emit("SHADOW_TIER_A", shadow_tier_a_receipt_hash)
        if shadow_tier_b_receipt_hash is not None:
            _emit("SHADOW_TIER_B", shadow_tier_b_receipt_hash)
        if shadow_readiness_receipt_hash is not None:
            _emit("SHADOW_READINESS", shadow_readiness_receipt_hash)
        if shadow_corpus_invariance_receipt_hash is not None:
            _emit("SHADOW_CORPUS_INVARIANCE", shadow_corpus_invariance_receipt_hash)

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
                "mission_goal_ingest_receipt_hash": mission_goal_receipt_hash,
                "lane_decision_receipt_hash": lane_decision_receipt_hash,
                "eval_report_hash": eval_report_hash,
                "decision_plan_hash": decision_hash,
                "dispatch_receipt_hash": dispatch_hash,
                "subverifier_receipt_hash": subverifier_hash,
                "promotion_receipt_hash": promotion_hash,
                "utility_proof_hash": utility_proof_hash,
                "dependency_routing_receipt_hash": dependency_routing_receipt_hash,
                "dependency_debt_snapshot_hash": dependency_debt_snapshot_hash,
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
                "policy_vm_proof_fallback_reason_code": policy_vm_proof_fallback_reason_code,
                "policy_market_selection_hash": policy_market_selection_hash,
                "policy_market_selection_commitment_hash": policy_market_selection_commitment_hash,
                "counterfactual_trace_example_hash": counterfactual_trace_example_hash,
                "shadow_fs_integrity_report_hash": shadow_integrity_report_hash,
                "shadow_tier_a_receipt_hash": shadow_tier_a_receipt_hash,
                "shadow_tier_b_receipt_hash": shadow_tier_b_receipt_hash,
                "shadow_readiness_receipt_hash": shadow_readiness_receipt_hash,
                "shadow_corpus_invariance_receipt_hash": shadow_corpus_invariance_receipt_hash,
            }
        )
        _, snapshot, snapshot_hash = write_snapshot(state_root / "snapshot", snapshot)
        _mark("snapshot_write", snapshot_start_ns)
        _emit("SNAPSHOT", snapshot_hash)

        if safe_halt:
            _emit("SAFE_HALT", snapshot_hash)

        tick_total_ns = _DETERMINISTIC_TICK_TOTAL_NS if deterministic_timing else (time.monotonic_ns() - tick_start_ns)

        if (
            orch_bandit_config_payload is not None
            and isinstance(orch_bandit_state_in, dict)
            and isinstance(orch_bandit_context_key, str)
            and _is_sha256(orch_bandit_context_key)
        ):
            try:
                wallclock_ms_u64 = int(max(0, int(tick_total_ns) // 1_000_000))
                promotion_result_kind = _normalize_orch_promotion_result_kind(
                    result_kind=(promotion_receipt or {}).get("result_kind"),
                    status=((promotion_receipt or {}).get("result") or {}).get("status"),
                    activation_kind=(activation_receipt or {}).get("activation_kind"),
                )
                toxic_fail_b = _is_toxic_reason_code(
                    ((promotion_receipt or {}).get("result") or {}).get("reason_code")
                )
                observed_reward_q32 = _compute_orch_reward_q32(
                    promotion_result_kind=promotion_result_kind,
                    toxic_fail_b=bool(toxic_fail_b),
                    lane_kind=str(orch_bandit_context_lane_kind),
                    utility_receipt=utility_proof_receipt,
                )
                observed_cost_q32 = orch_bandit_compute_cost_norm_q32(
                    wallclock_ms_u64=int(wallclock_ms_u64),
                    cost_scale_ms_u64=int(orch_bandit_config_payload.get("cost_scale_ms_u64", 1)),
                )
                orch_bandit_state_out = orch_bandit_update_bandit_state(
                    config=orch_bandit_config_payload,
                    state_in=orch_bandit_state_in,
                    state_in_id=orch_bandit_state_in_id,
                    tick_u64=int(tick_u64),
                    ek_id=_sha256_or_zero((orch_bandit_state_in or {}).get("ek_id")),
                    kernel_ledger_id=_sha256_or_zero((orch_bandit_state_in or {}).get("kernel_ledger_id")),
                    context_key=str(orch_bandit_context_key),
                    lane_kind=str(orch_bandit_context_lane_kind),
                    runaway_band_u32=int(orch_bandit_context_runaway_band_u32),
                    objective_kind=str(orch_bandit_context_objective_kind),
                    selected_capability_id=str(selected_capability_id),
                    observed_reward_q32=int(observed_reward_q32),
                    observed_cost_q32=int(observed_cost_q32),
                )
                validate_schema_v19(orch_bandit_state_out, "orch_bandit_state_v1")
                _state_path, _state_obj, orch_bandit_state_out_id = _write_payload_atomic(
                    _orch_bandit_state_dir(state_root=state_root),
                    "orch_bandit_state_v1.json",
                    orch_bandit_state_out,
                )
                _write_orch_bandit_pointer(
                    state_dir=_orch_bandit_state_dir(state_root=state_root),
                    state_hash=str(orch_bandit_state_out_id),
                )
                orch_bandit_update_receipt = {
                    "schema_version": "orch_bandit_update_receipt_v1",
                    "tick_u64": int(max(0, int(tick_u64))),
                    "state_in_id": str(orch_bandit_state_in_id),
                    "state_out_id": str(orch_bandit_state_out_id),
                    "context_key": str(orch_bandit_context_key),
                    "selected_capability_id": str(selected_capability_id),
                    "observed_reward_q32": int(observed_reward_q32),
                    "observed_cost_q32": int(observed_cost_q32),
                    "status": "OK",
                    "reason_code": "OK",
                }
                validate_schema_v19(orch_bandit_update_receipt, "orch_bandit_update_receipt_v1")
                _update_path, _update_obj, orch_bandit_update_receipt_hash = _write_payload_atomic(
                    state_root / "orch_bandit" / "updates",
                    "orch_bandit_update_receipt_v1.json",
                    orch_bandit_update_receipt,
                )
                _emit("ORCH_BANDIT_UPDATE", orch_bandit_update_receipt_hash)
            except OrchBanditError as exc:
                fail(str(exc))

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
        promotion_status = "SKIPPED"
        promotion_reason_code = "NO_PROMOTION_RECEIPT"
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
        elif isinstance(probe_gate_drop_reason_code, str) and probe_gate_drop_reason_code:
            promotion_reason_code = probe_gate_drop_reason_code

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
            declared_class=declared_class_for_tick,
            effect_class=effect_class_for_tick,
            candidate_bundle_present_b=bool(candidate_bundle_present_b),
            probe_executed_b=bool(probe_executed_b),
            frontier_attempt_counted_b=bool(frontier_attempt_counted_b),
            effective_change_b=bool(effective_change_b),
            activation_success=activation_success,
            activation_reasons=activation_reasons,
            activation_meta_verdict=activation_meta_verdict,
            manifest_changed=manifest_changed,
            safe_halt=safe_halt,
            noop_reason=noop_reason,
            execution_mode=execution_mode,
        )
        write_tick_outcome(state_root / "perf", tick_outcome)
        if long_run_profile is not None:
            shadow_summary_payload = _shadow_summary_obj if isinstance(_shadow_summary_obj, dict) else {}
            next_health_window = _next_health_window(
                prev_window=prev_health_window,
                tick_u64=tick_u64,
                tick_outcome=tick_outcome,
                shadow_summary_payload=shadow_summary_payload,
            )
            _, _health_window_obj, _health_window_hash = _write_payload_atomic(
                state_root / "long_run" / "health",
                "long_run_health_window_v1.json",
                next_health_window,
            )

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
            "lane_name": lane_name,
            "lane_decision_receipt_hash": lane_decision_receipt_hash,
            "mission_goal_ingest_receipt_hash": mission_goal_receipt_hash,
            "eval_report_hash": eval_report_hash,
            "utility_proof_hash": utility_proof_hash,
            "dependency_routing_receipt_hash": dependency_routing_receipt_hash,
            "dependency_debt_snapshot_hash": dependency_debt_snapshot_hash,
            "anti_monopoly_state_hash": anti_monopoly_state_hash,
            "long_run_profile_hash": long_run_profile_hash,
            "runaway_state": "ACTIVE" if runaway_active else "INACTIVE",
            "runaway_level_u64": int(runaway_level_u64),
            "runaway_reason": str(runaway_reason),
            "sip_ingestion_artifact_hash": (sip_ingestion_evidence or {}).get("knowledge_hash"),
            "sip_ingestion_refutation_hash": (sip_ingestion_evidence or {}).get("refutation_hash"),
            "epistemic_capsule_artifact_hash": (epistemic_capsule_evidence or {}).get("capsule_hash"),
            "epistemic_capsule_refutation_hash": (epistemic_capsule_evidence or {}).get("refutation_hash"),
            "policy_vm_stark_proof_hash": policy_vm_stark_proof_hash,
            "policy_vm_proof_runtime_status": policy_vm_proof_runtime_status,
            "policy_vm_proof_profile_id": policy_vm_proof_profile_id,
            "policy_vm_proof_options_hash": policy_vm_proof_options_hash,
            "policy_vm_proof_runtime_reason_code": policy_vm_proof_runtime_reason_code,
            "policy_vm_proof_fallback_reason_code": policy_vm_proof_fallback_reason_code,
            "policy_vm_prove_time_ms": policy_vm_prove_time_ms,
            "policy_vm_proof_size_bytes": policy_vm_proof_size_bytes,
            "policy_market_selection_hash": policy_market_selection_hash,
            "policy_market_selection_commitment_hash": policy_market_selection_commitment_hash,
            "counterfactual_trace_example_hash": counterfactual_trace_example_hash,
            "epistemic_action_market_inputs_hash": epistemic_action_market_inputs_hash,
            "epistemic_action_bid_set_hash": epistemic_action_bid_set_hash,
            "epistemic_action_selection_hash": epistemic_action_selection_hash,
            "epistemic_action_settlement_hash": epistemic_action_settlement_hash,
            "shadow_fs_integrity_report_hash": shadow_integrity_report_hash,
            "shadow_tier_a_receipt_hash": shadow_tier_a_receipt_hash,
            "shadow_tier_b_receipt_hash": shadow_tier_b_receipt_hash,
            "shadow_readiness_receipt_hash": shadow_readiness_receipt_hash,
            "shadow_corpus_invariance_receipt_hash": shadow_corpus_invariance_receipt_hash,
        }


__all__ = [
    "tick_once",
    "_load_axis_gate_failure",
    "_axis_gate_applies_safe_halt",
    "_axis_gate_promotion_reason_code",
]
