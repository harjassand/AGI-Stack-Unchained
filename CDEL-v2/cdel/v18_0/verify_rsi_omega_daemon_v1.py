"""Fail-closed verifier for RSI Omega daemon v18.0."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from .omega_allowlists_v1 import is_path_allowed, is_path_forbidden, load_allowlists
from .omega_common_v1 import (
    OmegaV18Error,
    canon_hash_obj,
    collect_single,
    fail,
    find_by_hash,
    hash_file_stream,
    load_jsonl,
    load_canon_dict,
    repo_root,
    require_no_absolute_paths,
    rat_q32,
    schema_dir,
    tree_hash,
    validate_schema,
)
from .omega_diagnoser_v1 import diagnose
from .omega_decider_v1 import decide
from .omega_objectives_v1 import load_objectives
from .omega_observer_index_v1 import load_index
from .omega_policy_ir_v1 import load_policy
from .omega_promotion_bundle_v1 import extract_touched_paths, load_bundle
from .omega_registry_v2 import load_registry
from .omega_test_plan_v1 import campaign_requires_test_plan_receipt, load_test_plan_receipt
from .omega_runaway_v1 import (
    advance_runaway_state,
    load_latest_runaway_state,
    load_prev_runaway_state_for_tick,
    load_runaway_config,
    runaway_enabled,
)
try:
    from orchestrator.omega_bid_market_v1 import (  # type: ignore
        bid_market_enabled,
        build_bid_set_v1,
        build_bid_v1,
        build_decision_plan_from_selection,
        load_optional_bid_market_config,
        resolve_bidder_params,
        select_winner,
        settle_and_advance_market_state,
    )
except Exception:  # pragma: no cover
    # Standalone CDEL-v2 runs vendor the market module under cdel.v18_0.
    from .omega_bid_market_v1 import (
        bid_market_enabled,
        build_bid_set_v1,
        build_bid_v1,
        build_decision_plan_from_selection,
        load_optional_bid_market_config,
        resolve_bidder_params,
        select_winner,
        settle_and_advance_market_state,
    )
from .omega_temperature_v1 import compute_temperature_q32
from .omega_trace_hash_chain_v1 import recompute_head

_SUBVERIFIER_REASON_CODES = {
    "SCHEMA_FAIL",
    "MISSING_STATE_INPUT",
    "NONDETERMINISTIC",
    "MODE_UNSUPPORTED",
    "VERIFY_ERROR",
    "UNKNOWN",
}
_V14_SYSTEM_VERIFIER_MODULE = "cdel.v14_0.verify_rsi_sas_system_v1"
_V16_1_METASEARCH_VERIFIER_MODULE = "cdel.v16_1.verify_rsi_sas_metasearch_v16_1"
_V10_MODEL_GENESIS_VERIFIER_MODULE = "cdel.v10_0.verify_rsi_model_genesis_v1"
_REPLAY_REPO_ROOT_REQUIRED_VERIFIER_MODULES = {
    _V14_SYSTEM_VERIFIER_MODULE,
    _V16_1_METASEARCH_VERIFIER_MODULE,
}
_SUBVERIFIER_STATE_ARG_BY_MODULE = {
    "cdel.v12_0.verify_rsi_sas_code_v1": "--sas_code_state_dir",
    _V10_MODEL_GENESIS_VERIFIER_MODULE: "--smg_state_dir",
}

_OBS_SOURCE_SUFFIX: dict[str, str] = {
    "metasearch_compute_report_v1": "metasearch_compute_report_v1.json",
    "kernel_hotloop_report_v1": "kernel_hotloop_report_v1.json",
    "sas_system_perf_report_v1": "sas_system_perf_report_v1.json",
    "sas_science_promotion_bundle_v1": "sas_science_promotion_bundle_v1.json",
    "sas_code_perf_report_v1": "sas_code_perf_report_v1.json",
    "ccap_receipt_v1": "ccap_receipt_v1.json",
    "omega_tick_perf_v1": "omega_tick_perf_v1.json",
    "omega_tick_stats_v1": "omega_tick_stats_v1.json",
    "omega_run_scorecard_v1": "omega_run_scorecard_v1.json",
    "omega_skill_transfer_report_v1": "omega_skill_report_v1.json",
    "omega_skill_ontology_report_v1": "omega_skill_report_v1.json",
    "omega_skill_eff_flywheel_report_v1": "omega_skill_report_v1.json",
    "omega_skill_thermo_report_v1": "omega_skill_report_v1.json",
    "omega_skill_persistence_report_v1": "omega_skill_report_v1.json",
}

_OBS_SOURCE_FIXED_PATH_REL: dict[str, str] = {
    "polymath_domain_registry_v1": "polymath/registry/polymath_domain_registry_v1.json",
    "polymath_void_report_v1": "polymath/registry/polymath_void_report_v1.jsonl",
    "polymath_scout_status_v1": "polymath/registry/polymath_scout_status_v1.json",
    "polymath_portfolio_v1": "polymath/registry/polymath_portfolio_v1.json",
}

_OBS_SOURCE_CAMPAIGN: dict[str, str] = {
    "metasearch_compute_report_v1": "rsi_sas_metasearch_v16_1",
    "kernel_hotloop_report_v1": "rsi_sas_val_v17_0",
    "sas_system_perf_report_v1": "rsi_sas_system_v14_0",
    "sas_science_promotion_bundle_v1": "rsi_sas_science_v13_0",
    "sas_code_perf_report_v1": "rsi_sas_code_v12_0",
    "ccap_receipt_v1": "rsi_ge_symbiotic_optimizer_sh1_v0_1",
    "omega_tick_perf_v1": "rsi_omega_daemon_v18_0",
    "omega_tick_stats_v1": "rsi_omega_daemon_v18_0",
    "omega_run_scorecard_v1": "rsi_omega_daemon_v18_0",
    "polymath_domain_registry_v1": "rsi_polymath_scout_v1",
    "polymath_void_report_v1": "rsi_polymath_scout_v1",
    "polymath_scout_status_v1": "rsi_polymath_scout_v1",
    "polymath_portfolio_v1": "rsi_polymath_conquer_domain_v1",
    "omega_skill_transfer_report_v1": "rsi_omega_skill_transfer_v1",
    "omega_skill_ontology_report_v1": "rsi_omega_skill_ontology_v1",
    "omega_skill_eff_flywheel_report_v1": "rsi_omega_skill_eff_flywheel_v1",
    "omega_skill_thermo_report_v1": "rsi_omega_skill_thermo_v1",
    "omega_skill_persistence_report_v1": "rsi_omega_skill_persistence_v1",
}

_OBS_SKILL_SOURCE_TO_METRIC: dict[str, str] = {
    "omega_skill_transfer_report_v1": "transfer_gain_q32",
    "omega_skill_ontology_report_v1": "ontology_consistency_q32",
    "omega_skill_eff_flywheel_report_v1": "flywheel_yield_q32",
    "omega_skill_thermo_report_v1": "thermo_efficiency_q32",
    "omega_skill_persistence_report_v1": "persistence_health_q32",
}

_OBS_REQUIRED_SOURCE_IDS: tuple[str, ...] = (
    "metasearch_compute_report_v1",
    "kernel_hotloop_report_v1",
    "sas_system_perf_report_v1",
    "sas_science_promotion_bundle_v1",
)
_POLYMATH_STALE_AGE_U64 = (1 << 63) - 1
_MAX_SERIES_LEN_U64 = 64
_Q32_ONE = 1 << 32
_OBS_NON_CARRY_SERIES_KEYS = {
    "brain_temperature_q32",
    "OBJ_EXPAND_CAPABILITIES",
    "OBJ_MAXIMIZE_SCIENCE",
    "OBJ_MAXIMIZE_SPEED",
    "cap_frontier_u64",
    "cap_enabled_u64",
    "cap_activated_u64",
}
_GE_CAMPAIGN_ID = "rsi_ge_symbiotic_optimizer_sh1_v0_1"
_CAPABILITY_FRONTIER_WINDOW_U64 = 512


def _state_arg_for_verifier(verifier_module: str) -> str:
    return str(_SUBVERIFIER_STATE_ARG_BY_MODULE.get(verifier_module, "--state_dir"))


def _meta_core_root() -> Path:
    override = str(os.environ.get("OMEGA_META_CORE_ROOT", "")).strip()
    if override:
        return Path(override).resolve()
    return _repo_root() / "meta-core"


def _repo_root() -> Path:
    return repo_root()


def _resolve_state_dir(path: Path) -> tuple[Path, Path]:
    root = path.resolve()
    if (root / "state").is_dir() and (root / "config").is_dir():
        return root / "state", root
    if (root / "daemon" / "rsi_omega_daemon_v18_0" / "state").is_dir():
        daemon = root / "daemon" / "rsi_omega_daemon_v18_0"
        return daemon / "state", daemon
    if (root / "daemon" / "rsi_omega_daemon_v19_0" / "state").is_dir():
        daemon = root / "daemon" / "rsi_omega_daemon_v19_0"
        return daemon / "state", daemon
    if root.name == "state" and (root.parent / "config").is_dir():
        return root, root.parent
    fail("SCHEMA_FAIL")
    return root, root


def _observer_runs_roots(*, root: Path, daemon_root: Path) -> list[Path]:
    roots: list[Path] = []

    def _add(path: Path) -> None:
        try:
            resolved = path.resolve()
        except Exception:  # noqa: BLE001
            return
        if not resolved.exists() or not resolved.is_dir():
            return
        if resolved not in roots:
            roots.append(resolved)

    try:
        daemon_root.resolve().relative_to(root.resolve())
    except ValueError:
        daemon_under_repo = False
    else:
        daemon_under_repo = True
    if daemon_under_repo:
        # Prefer the concrete run root over the global runs/ tree to avoid
        # expensive scans on large repos. _read_observer_source_artifact will
        # still consider root/runs as a last resort.
        run_dir = daemon_root.parent.parent
        _add(run_dir)
        _add(run_dir.parent)
    else:
        run_dir = daemon_root.parent.parent
        _add(run_dir)
        _add(run_dir.parent)
        _add(run_dir.parent.parent)
    return roots


def _find_dispatch_hash(state_root: Path, digest: str) -> Path:
    target = f"sha256_{digest.split(':', 1)[1]}.omega_dispatch_receipt_v1.json"
    rows = sorted(state_root.glob(f"dispatch/*/{target}"))
    if len(rows) != 1:
        fail("MISSING_STATE_INPUT")
    return rows[0]


def _find_nested_hash(state_root: Path, digest: str, suffix: str) -> Path:
    target = f"sha256_{digest.split(':', 1)[1]}.{suffix}"
    rows = sorted(state_root.glob(f"dispatch/*/**/{target}"))
    if len(rows) != 1:
        fail("MISSING_STATE_INPUT")
    return rows[0]


def _latest_snapshot_or_fail(snapshot_dir: Path) -> Path:
    rows = sorted(snapshot_dir.glob("sha256_*.omega_tick_snapshot_v1.json"), key=lambda row: row.as_posix())
    if not rows:
        fail("MISSING_STATE_INPUT")
    best_path: Path | None = None
    best_tick = -1
    for row in rows:
        payload = load_canon_dict(row)
        tick_u64 = int(payload.get("tick_u64", -1))
        if tick_u64 < 0:
            fail("SCHEMA_FAIL")
        if tick_u64 > best_tick or (tick_u64 == best_tick and (best_path is None or row.as_posix() > best_path.as_posix())):
            best_tick = tick_u64
            best_path = row
    if best_path is None:
        fail("MISSING_STATE_INPUT")
    return best_path


def _find_prev_observation_report(
    *,
    state_root: Path,
    current_tick_u64: int,
) -> dict[str, Any] | None:
    target_tick_u64 = int(current_tick_u64) - 1
    if target_tick_u64 < 0:
        return None
    observation_dir = state_root / "observations"
    if not observation_dir.exists() or not observation_dir.is_dir():
        return None
    for path in sorted(observation_dir.glob("sha256_*.omega_observation_report_v1.json"), key=lambda p: p.as_posix()):
        payload = load_canon_dict(path)
        if int(payload.get("tick_u64", -1)) == target_tick_u64:
            return payload
    return None


def _derive_prev_observation_from_payload(observation_payload: dict[str, Any]) -> dict[str, Any] | None:
    metric_series = observation_payload.get("metric_series")
    if not isinstance(metric_series, dict):
        fail("SCHEMA_FAIL")
    derived_series: dict[str, list[Any]] = {}
    has_history = False
    for key, rows in metric_series.items():
        if not isinstance(rows, list) or not rows:
            fail("SCHEMA_FAIL")
        if key in _OBS_NON_CARRY_SERIES_KEYS:
            derived_series[str(key)] = []
            continue
        if len(rows) > 1:
            has_history = True
        derived_series[str(key)] = list(rows[:-1])
    if not has_history:
        return None
    return {"metric_series": derived_series}


def _hash_from_hashed_filename(path: Path) -> str:
    name = path.name
    if not name.startswith("sha256_"):
        fail("SCHEMA_FAIL")
    hexd = name[len("sha256_") :].split(".", 1)[0]
    if len(hexd) != 64:
        fail("SCHEMA_FAIL")
    return f"sha256:{hexd}"


def _find_state_payload_by_state_id(state_dir: Path, state_id: str) -> dict[str, Any]:
    for path in sorted(state_dir.glob("sha256_*.omega_state_v1.json")):
        payload = load_canon_dict(path)
        validate_schema(payload, "omega_state_v1")
        if payload.get("state_id") == state_id:
            return payload
    fail("MISSING_STATE_INPUT")
    return {}


def _load_and_hash(path: Path, schema_name: str) -> tuple[dict[str, Any], str]:
    payload = load_canon_dict(path)
    validate_schema(payload, schema_name)
    return payload, canon_hash_obj(payload)


def _verify_hash_binding(path: Path, expected_hash: str, schema_name: str) -> dict[str, Any]:
    payload, digest = _load_and_hash(path, schema_name)
    if digest != expected_hash:
        fail("HASH_MISMATCH")
    return payload


def _validate_goal_queue(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != "omega_goal_queue_v1":
        fail("SCHEMA_FAIL")
    goals = payload.get("goals")
    if not isinstance(goals, list):
        fail("SCHEMA_FAIL")
    for row in goals:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        goal_id = str(row.get("goal_id", "")).strip()
        capability_id = str(row.get("capability_id", "")).strip()
        status = str(row.get("status", "PENDING")).strip()
        if not goal_id or not capability_id or status not in {"PENDING", "DONE", "FAILED"}:
            fail("SCHEMA_FAIL")
    return payload


def _load_goal_queue_from_config(config_dir: Path) -> dict[str, Any]:
    effective_path = config_dir / "goals" / "omega_goal_queue_effective_v1.json"
    if effective_path.exists():
        if not effective_path.is_file():
            fail("SCHEMA_FAIL")
        return _validate_goal_queue(load_canon_dict(effective_path))
    return _validate_goal_queue(load_canon_dict(config_dir / "goals" / "omega_goal_queue_v1.json"))


def _verify_forbidden_paths(
    *,
    state_root: Path,
    promotion_receipt: dict[str, Any] | None,
    allowlists: dict[str, Any],
) -> None:
    if promotion_receipt is None:
        return
    bundle_hash = str(promotion_receipt.get("promotion_bundle_hash", ""))
    if bundle_hash == "sha256:" + "0" * 64:
        return
    hexd = bundle_hash.split(":", 1)[1]
    bundle_paths = sorted(state_root.glob(f"subruns/**/sha256_{hexd}.*.json"))
    if not bundle_paths:
        return
    bundle, _ = load_bundle(bundle_paths[0])
    bundle_schema = str(bundle.get("schema_version", "")).strip()
    touched = extract_touched_paths(bundle)
    if bundle_schema == "omega_promotion_bundle_ccap_v1":
        ccap_rel = str(bundle.get("ccap_relpath", "")).strip()
        patch_rel = str(bundle.get("patch_relpath", "")).strip()
        if ccap_rel not in touched or patch_rel not in touched:
            fail("FORBIDDEN_PATH")
        if any(".omega_cache" in Path(row).parts for row in touched):
            fail("FORBIDDEN_PATH")
        return
    for row in touched:
        if is_path_forbidden(row, allowlists) or not is_path_allowed(row, allowlists):
            fail("FORBIDDEN_PATH")


def _decision_inputs_hash(decision_payload: dict[str, Any]) -> str:
    return canon_hash_obj(
        {
            "tick_u64": decision_payload.get("tick_u64"),
            "observation_report_hash": decision_payload.get("observation_report_hash"),
            "issue_bundle_hash": decision_payload.get("issue_bundle_hash"),
            "policy_hash": decision_payload.get("policy_hash"),
            "registry_hash": decision_payload.get("registry_hash"),
            "budgets_hash": decision_payload.get("budgets_hash"),
            "action_kind": decision_payload.get("action_kind"),
            "campaign_id": decision_payload.get("campaign_id"),
            "capability_id": decision_payload.get("capability_id"),
            "goal_id": decision_payload.get("goal_id"),
            "assigned_capability_id": decision_payload.get("assigned_capability_id"),
            "runaway_selected_metric_id": decision_payload.get("runaway_selected_metric_id"),
            "runaway_escalation_level_u64": decision_payload.get("runaway_escalation_level_u64"),
            "runaway_env_overrides": decision_payload.get("runaway_env_overrides"),
        }
    )


def _binding_id(payload: dict[str, Any]) -> str:
    binding = str(payload.get("binding_id", ""))
    if not binding.startswith("sha256:"):
        fail("BINDING_MISSING_OR_MISMATCH")
    no_id = dict(payload)
    no_id.pop("binding_id", None)
    if canon_hash_obj(no_id) != binding:
        fail("BINDING_MISSING_OR_MISMATCH")
    return binding


def _read_observer_source_from_index(*, root: Path, schema_id: str, artifact_hash: str) -> dict[str, Any] | None:
    entries = load_index(root).get("entries")
    if not isinstance(entries, dict):
        return None
    row = entries.get(schema_id)
    if not isinstance(row, dict):
        return None
    path_rel = row.get("path_rel")
    if not isinstance(path_rel, str) or not path_rel:
        return None
    candidate = root / path_rel
    if not candidate.exists() or not candidate.is_file():
        return None
    try:
        payload = load_canon_dict(candidate)
    except OmegaV18Error:
        return None
    if canon_hash_obj(payload) != artifact_hash:
        return None
    return payload


_RUNS_FILENAME_FIND_CACHE: dict[tuple[str, str], list[Path]] = {}

# Fast-path for locating observer artifacts in repo_root/runs without scanning the
# entire tree: many repos keep canonical "single-campaign run" directories at
# runs/<campaign_id>_tick_XXXX/... which contain the needed artifacts directly.
_OBS_SOURCE_RUNS_DIRECT_STATE_SUBDIR: dict[str, str] = {
    "metasearch_compute_report_v1": "reports",
    "kernel_hotloop_report_v1": "hotloop",
    "sas_system_perf_report_v1": "artifacts",
    "sas_science_promotion_bundle_v1": "promotion",
    "omega_tick_perf_v1": "perf",
    "omega_tick_stats_v1": "perf",
    "omega_run_scorecard_v1": "perf",
}


def _find_ccap_receipt_candidates_in_runs_root(*, runs_root: Path, filename: str) -> list[Path]:
    """Locate CCAP receipts under runs_root without scanning the entire runs tree.

    CCAP receipts are emitted under dispatch/*/verifier/ as `sha256_<hex>.ccap_receipt_v1.json`.
    The observer records them as sources with schema_id=ccap_receipt_v1, but producer_run_id
    may be set to the receipt hash (not the run id), so we cannot rely on directory naming.
    """
    if not runs_root.exists() or not runs_root.is_dir():
        return []
    out: list[Path] = []
    for run_dir in sorted(runs_root.iterdir(), key=lambda p: p.name):
        if not run_dir.is_dir() or run_dir.is_symlink():
            continue
        for daemon_id in ("rsi_omega_daemon_v18_0", "rsi_omega_daemon_v19_0"):
            for path in sorted(
                run_dir.glob(f"daemon/{daemon_id}/state/dispatch/*/verifier/{filename}"),
                key=lambda p: p.as_posix(),
            ):
                if path.exists() and path.is_file():
                    out.append(path)
    dedup: dict[str, Path] = {}
    for row in out:
        dedup[row.as_posix()] = row
    return sorted(dedup.values(), key=lambda p: p.as_posix())


def _find_daemon_perf_candidates_in_runs_root(*, runs_root: Path, filename: str) -> list[Path]:
    """Locate daemon perf artifacts under runs_root without a full recursive scan.

    Many runs are stored as runs/<run_id>/tick_XXXX/daemon/<daemon_id>/state/perf/<filename>.
    """
    if not runs_root.exists() or not runs_root.is_dir():
        return []
    out: list[Path] = []
    for run_dir in sorted(runs_root.iterdir(), key=lambda p: p.name):
        if not run_dir.is_dir() or run_dir.is_symlink():
            continue
        for daemon_id in ("rsi_omega_daemon_v18_0", "rsi_omega_daemon_v19_0"):
            # Common layout: per-tick subdirectories.
            for path in sorted(
                run_dir.glob(f"tick_*/daemon/{daemon_id}/state/perf/{filename}"),
                key=lambda p: p.as_posix(),
            ):
                if path.exists() and path.is_file():
                    out.append(path)
            # Legacy/single-tick layout: direct daemon/ subdir.
            for path in sorted(
                run_dir.glob(f"daemon/{daemon_id}/state/perf/{filename}"),
                key=lambda p: p.as_posix(),
            ):
                if path.exists() and path.is_file():
                    out.append(path)
    dedup: dict[str, Path] = {}
    for row in out:
        dedup[row.as_posix()] = row
    return sorted(dedup.values(), key=lambda p: p.as_posix())


def _find_direct_observer_artifacts_in_runs_root(
    *,
    runs_root: Path,
    schema_id: str,
    expected_campaign: str,
    filename: str,
) -> list[Path]:
    subdir = _OBS_SOURCE_RUNS_DIRECT_STATE_SUBDIR.get(str(schema_id))
    if subdir is None:
        return []
    if not runs_root.exists() or not runs_root.is_dir():
        return []
    if not expected_campaign:
        return []
    candidates: list[Path] = []
    campaign_candidates: list[str] = [expected_campaign]
    # v19 runs keep state under rsi_omega_daemon_v19_0, but some sources still
    # label the producer as v18. Accept either on disk.
    if expected_campaign.endswith("_v18_0"):
        campaign_candidates.append(expected_campaign[: -len("_v18_0")] + "_v19_0")
    elif expected_campaign.endswith("_v19_0"):
        campaign_candidates.append(expected_campaign[: -len("_v19_0")] + "_v18_0")
    for run_dir in sorted(runs_root.iterdir(), key=lambda p: p.name):
        if not run_dir.is_dir() or run_dir.is_symlink():
            continue
        for camp in campaign_candidates:
            candidate = run_dir / "daemon" / camp / "state" / subdir / filename
            if candidate.exists() and candidate.is_file():
                candidates.append(candidate)
    return candidates


def _find_named_files_under_root(*, root: Path, filename: str) -> list[Path]:
    """Return absolute paths matching filename under root.

    Used to avoid Path.glob("**/...") on large runs trees, which is slow in Python.
    """
    key = (root.as_posix(), str(filename))
    cached = _RUNS_FILENAME_FIND_CACHE.get(key)
    if cached is not None:
        return list(cached)

    if not root.exists() or not root.is_dir():
        _RUNS_FILENAME_FIND_CACHE[key] = []
        return []

    try:
        rc = subprocess.run(
            ["find", str(root), "-type", "f", "-name", str(filename), "-print"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:  # noqa: BLE001
        _RUNS_FILENAME_FIND_CACHE[key] = []
        return []

    if int(rc.returncode) != 0:
        _RUNS_FILENAME_FIND_CACHE[key] = []
        return []

    rows: list[Path] = []
    for line in str(rc.stdout).splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(Path(line))

    # Deterministic ordering: match the verifier's "lexicographically smallest path" tie-break.
    dedup: dict[str, Path] = {}
    for row in rows:
        dedup[row.as_posix()] = row
    out = sorted(dedup.values(), key=lambda p: p.as_posix())
    _RUNS_FILENAME_FIND_CACHE[key] = out
    return list(out)


def _read_observer_source_artifact(
    *,
    root: Path,
    source: dict[str, Any],
    runs_roots: list[Path] | None = None,
) -> tuple[str, dict[str, Any]]:
    schema_id = str(source.get("schema_id", ""))
    expected_campaign = _OBS_SOURCE_CAMPAIGN.get(schema_id)
    if str(source.get("producer_campaign_id", "")) != str(expected_campaign):
        fail("SCHEMA_FAIL")
    artifact_hash = str(source.get("artifact_hash", ""))
    if not artifact_hash.startswith("sha256:") or len(artifact_hash.split(":", 1)[1]) != 64:
        fail("SCHEMA_FAIL")
    producer_run_id = str(source.get("producer_run_id", ""))

    if producer_run_id == "observer_fallback":
        expected_hash = canon_hash_obj(
            {
                "schema_id": schema_id,
                "campaign_id": str(expected_campaign),
                "reason_code": "MISSING_STATE_INPUT",
            }
        )
        if artifact_hash != expected_hash:
            fail("NONDETERMINISTIC")
        if schema_id == "metasearch_compute_report_v1":
            return schema_id, {
                "schema_version": "metasearch_compute_report_v1",
                "c_base_work_cost_total": 1,
                "c_cand_work_cost_total": 1,
            }
        if schema_id == "kernel_hotloop_report_v1":
            return schema_id, {
                "schema_version": "kernel_hotloop_report_v1",
                "top_loops": [{"bytes": 0}],
            }
        if schema_id == "sas_system_perf_report_v1":
            return schema_id, {
                "schema_version": "sas_system_perf_report_v1",
                "cand_cost_total": 0,
                "ref_cost_total": 1,
            }
        if schema_id == "sas_science_promotion_bundle_v1":
            return schema_id, {
                "schema_version": "sas_science_promotion_bundle_v1",
                "discovery_bundle": {
                    "heldout_metrics": {
                        "rmse_pos1_q32": {"q": 0},
                    }
                },
            }
        fail("SCHEMA_FAIL")

    fixed_rel = _OBS_SOURCE_FIXED_PATH_REL.get(schema_id)
    if fixed_rel is not None:
        fixed_path = root / fixed_rel
        if not fixed_path.exists() or not fixed_path.is_file():
            fail("MISSING_STATE_INPUT")
        if schema_id == "polymath_domain_registry_v1":
            payload = load_canon_dict(fixed_path)
            validate_schema(payload, "polymath_domain_registry_v1")
            if canon_hash_obj(payload) != artifact_hash:
                fail("NONDETERMINISTIC")
            return schema_id, payload
        if schema_id == "polymath_void_report_v1":
            if hash_file_stream(fixed_path) != artifact_hash:
                fail("NONDETERMINISTIC")
            rows = load_jsonl(fixed_path)
            for row in rows:
                if str(row.get("schema_version", "")) != "polymath_void_report_v1":
                    fail("SCHEMA_FAIL")
                validate_schema(row, "polymath_void_report_v1")
            return schema_id, {"schema_version": "polymath_void_report_v1_rows", "rows": rows}
        if schema_id == "polymath_scout_status_v1":
            payload = load_canon_dict(fixed_path)
            validate_schema(payload, "polymath_scout_status_v1")
            if canon_hash_obj(payload) != artifact_hash:
                fail("NONDETERMINISTIC")
            return schema_id, payload
        if schema_id == "polymath_portfolio_v1":
            payload = load_canon_dict(fixed_path)
            validate_schema(payload, "polymath_portfolio_v1")
            if canon_hash_obj(payload) != artifact_hash:
                fail("NONDETERMINISTIC")
            return schema_id, payload
        if schema_id in _OBS_SKILL_SOURCE_TO_METRIC:
            payload = load_canon_dict(fixed_path)
            validate_schema(payload, "omega_skill_report_v1")
            if canon_hash_obj(payload) != artifact_hash:
                fail("NONDETERMINISTIC")
            return schema_id, payload
        fail("SCHEMA_FAIL")

    suffix = _OBS_SOURCE_SUFFIX.get(schema_id)
    if suffix is None:
        fail("SCHEMA_FAIL")
    artifact_hex = artifact_hash.split(":", 1)[1]
    filename = f"sha256_{artifact_hex}.{suffix}"

    indexed_payload = _read_observer_source_from_index(root=root, schema_id=schema_id, artifact_hash=artifact_hash)
    if indexed_payload is not None:
        return schema_id, indexed_payload

    search_roots: list[Path] = []
    raw_search_roots = list(runs_roots or [])
    raw_search_roots.append(root / "runs")
    for path in raw_search_roots:
        try:
            resolved = path.resolve()
        except Exception:  # noqa: BLE001
            continue
        if not resolved.exists() or not resolved.is_dir():
            continue
        if resolved not in search_roots:
            search_roots.append(resolved)

    preferred_roots: list[Path] = []
    candidates: list[Path] = []
    runs_root: Path | None = None
    try:
        resolved_runs = (root / "runs").resolve()
    except Exception:  # noqa: BLE001
        resolved_runs = None
    if resolved_runs is not None and resolved_runs.exists() and resolved_runs.is_dir():
        runs_root = resolved_runs
    if producer_run_id:
        for search_root in search_roots:
            if search_root.name == producer_run_id:
                preferred_roots.append(search_root)
            preferred_roots.append(search_root / producer_run_id)
        normalized_preferred_roots: list[Path] = []
        for path in preferred_roots:
            try:
                resolved = path.resolve()
            except Exception:  # noqa: BLE001
                continue
            if not resolved.exists() or not resolved.is_dir():
                continue
            if resolved not in normalized_preferred_roots:
                normalized_preferred_roots.append(resolved)
        preferred_roots = normalized_preferred_roots
        for preferred_root in preferred_roots:
            candidates.extend(sorted(preferred_root.glob(f"**/{filename}")))
        if not candidates:
            for search_root in search_roots:
                if runs_root is not None and search_root == runs_root:
                    if schema_id == "ccap_receipt_v1":
                        candidates.extend(_find_ccap_receipt_candidates_in_runs_root(runs_root=search_root, filename=filename))
                    elif schema_id in {"omega_tick_perf_v1", "omega_tick_stats_v1", "omega_run_scorecard_v1"}:
                        candidates.extend(_find_daemon_perf_candidates_in_runs_root(runs_root=search_root, filename=filename))
                    else:
                        for row in _find_named_files_under_root(root=search_root, filename=filename):
                            if f"/{producer_run_id}/" in row.as_posix():
                                candidates.append(row)
                    continue
                candidates.extend(sorted(search_root.glob(f"**/{producer_run_id}/**/{filename}")))
    if not candidates:
        for search_root in search_roots:
            if runs_root is not None and search_root == runs_root:
                direct = _find_direct_observer_artifacts_in_runs_root(
                    runs_root=search_root,
                    schema_id=schema_id,
                    expected_campaign=str(expected_campaign or ""),
                    filename=filename,
                )
                if direct:
                    candidates.extend(direct)
                else:
                    if schema_id == "ccap_receipt_v1":
                        candidates.extend(_find_ccap_receipt_candidates_in_runs_root(runs_root=search_root, filename=filename))
                    elif schema_id in {"omega_tick_perf_v1", "omega_tick_stats_v1", "omega_run_scorecard_v1"}:
                        candidates.extend(_find_daemon_perf_candidates_in_runs_root(runs_root=search_root, filename=filename))
                    else:
                        candidates.extend(_find_named_files_under_root(root=search_root, filename=filename))
                continue
            candidates.extend(sorted(search_root.glob(f"**/{filename}")))
    if candidates:
        chosen = sorted(set(candidates), key=lambda p: p.as_posix())[0]
        payload = load_canon_dict(chosen)
        if canon_hash_obj(payload) != artifact_hash:
            fail("NONDETERMINISTIC")
        return schema_id, payload

    # Fallback for legacy artifacts where filename digest and canonical hash diverge.
    # We still require an exact content-hash match against artifact_hash.
    content_match_candidates: list[Path] = []
    scan_roots = preferred_roots if preferred_roots else search_roots
    pattern = f"*.{suffix}"
    for scan_root in scan_roots:
        if not scan_root.exists() or not scan_root.is_dir():
            continue
        for path in sorted(scan_root.glob(f"**/{pattern}"), key=lambda p: p.as_posix()):
            try:
                payload = load_canon_dict(path)
            except OmegaV18Error:
                continue
            if canon_hash_obj(payload) == artifact_hash:
                content_match_candidates.append(path)
    if not content_match_candidates and preferred_roots:
        for fallback_root in search_roots:
            if fallback_root in scan_roots:
                continue
            if not fallback_root.exists() or not fallback_root.is_dir():
                continue
            for path in sorted(fallback_root.glob(f"**/{pattern}"), key=lambda p: p.as_posix()):
                try:
                    payload = load_canon_dict(path)
                except OmegaV18Error:
                    continue
                if canon_hash_obj(payload) == artifact_hash:
                    content_match_candidates.append(path)
    if not content_match_candidates:
        fail("MISSING_STATE_INPUT")

    chosen = sorted(set(content_match_candidates), key=lambda p: p.as_posix())[0]
    payload = load_canon_dict(chosen)
    if canon_hash_obj(payload) != artifact_hash:
        fail("NONDETERMINISTIC")
    return schema_id, payload


def _metric_from_observer_source(schema_id: str, payload: dict[str, Any]) -> int:
    if schema_id == "metasearch_compute_report_v1":
        base = int(payload.get("c_base_work_cost_total", 0))
        cand = int(payload.get("c_cand_work_cost_total", 0))
        if base <= 0 or cand < 0:
            fail("SCHEMA_FAIL")
        return rat_q32(base, cand if cand > 0 else 1)
    if schema_id == "kernel_hotloop_report_v1":
        loops = payload.get("top_loops")
        if not isinstance(loops, list) or not loops:
            fail("SCHEMA_FAIL")
        bytes_rows: list[int] = []
        for row in loops:
            if not isinstance(row, dict):
                fail("SCHEMA_FAIL")
            bytes_rows.append(int(row.get("bytes", 0)))
        total = sum(max(0, x) for x in bytes_rows)
        top = max(0, bytes_rows[0])
        return rat_q32(top, total if total > 0 else 1)
    if schema_id == "sas_system_perf_report_v1":
        cand = int(payload.get("cand_cost_total", 0))
        ref = int(payload.get("ref_cost_total", 0))
        if ref <= 0 or cand < 0:
            fail("SCHEMA_FAIL")
        return rat_q32(cand, ref)
    if schema_id == "sas_science_promotion_bundle_v1":
        discovery = payload.get("discovery_bundle")
        if not isinstance(discovery, dict):
            fail("SCHEMA_FAIL")
        heldout = discovery.get("heldout_metrics")
        if not isinstance(heldout, dict):
            fail("SCHEMA_FAIL")
        rmse = heldout.get("rmse_pos1_q32")
        if not isinstance(rmse, dict):
            fail("SCHEMA_FAIL")
        q_raw = rmse.get("q")
        try:
            return int(q_raw)
        except Exception:  # noqa: BLE001
            fail("SCHEMA_FAIL")
    fail("SCHEMA_FAIL")
    return 0


def _ge_stps_delta_q32(receipt: dict[str, Any]) -> int:
    delta = receipt.get("score_delta_summary")
    if isinstance(delta, dict):
        return int(delta.get("median_stps_non_noop_q32", 0))
    base = receipt.get("score_base_summary")
    cand = receipt.get("score_cand_summary")
    if isinstance(base, dict) and isinstance(cand, dict):
        return int(cand.get("median_stps_non_noop_q32", 0)) - int(base.get("median_stps_non_noop_q32", 0))
    return 0


def _count_enabled_capabilities(registry: dict[str, Any]) -> int:
    caps = registry.get("capabilities")
    if not isinstance(caps, list):
        fail("SCHEMA_FAIL")
    return int(sum(1 for row in caps if isinstance(row, dict) and bool(row.get("enabled", False))))


def _latest_valid_receipt(*, rows: list[Path], schema_version: str) -> tuple[dict[str, Any], int] | None:
    best_payload: dict[str, Any] | None = None
    best_tick_u64 = -1
    best_path = ""
    for path in sorted(rows, key=lambda row: row.as_posix()):
        if not path.exists() or not path.is_file():
            continue
        try:
            payload = load_canon_dict(path)
        except Exception:  # noqa: BLE001
            continue
        if str(payload.get("schema_version", "")).strip() != schema_version:
            continue
        try:
            tick_u64 = int(payload.get("tick_u64", 0))
        except Exception:  # noqa: BLE001
            continue
        path_key = path.as_posix()
        if tick_u64 > best_tick_u64 or (tick_u64 == best_tick_u64 and path_key > best_path):
            best_payload = payload
            best_tick_u64 = tick_u64
            best_path = path_key
    if best_payload is None:
        return None
    return best_payload, int(best_tick_u64)


def _capability_frontier_metrics(
    *,
    root: Path,
    registry: dict[str, Any],
    exclude_run_dir: Path | None = None,
    exclude_after_or_equal_tick_u64: int | None = None,
    window_ticks_u64: int = _CAPABILITY_FRONTIER_WINDOW_U64,
) -> dict[str, int]:
    records: list[dict[str, Any]] = []
    exclude_root: Path | None = None
    if exclude_run_dir is not None:
        try:
            exclude_root = exclude_run_dir.resolve()
        except Exception:  # noqa: BLE001
            exclude_root = exclude_run_dir
    exclude_tick_u64: int | None = None
    if exclude_after_or_equal_tick_u64 is not None:
        try:
            exclude_tick_u64 = int(exclude_after_or_equal_tick_u64)
        except Exception:  # noqa: BLE001
            exclude_tick_u64 = None
    for dispatch_dir in sorted(root.glob("runs/*/daemon/rsi_omega_daemon_v*/state/dispatch/*"), key=lambda row: row.as_posix()):
        if not dispatch_dir.is_dir():
            continue
        dispatch_row = _latest_valid_receipt(
            rows=list(dispatch_dir.glob("*.omega_dispatch_receipt_v1.json")),
            schema_version="omega_dispatch_receipt_v1",
        )
        activation_row = _latest_valid_receipt(
            rows=list(dispatch_dir.glob("activation/*.omega_activation_receipt_v1.json")),
            schema_version="omega_activation_receipt_v1",
        )
        if dispatch_row is None or activation_row is None:
            continue
        dispatch_payload, dispatch_tick_u64 = dispatch_row
        activation_payload, activation_tick_u64 = activation_row
        record_tick_u64 = int(max(dispatch_tick_u64, activation_tick_u64))
        if exclude_root is not None and exclude_tick_u64 is not None and record_tick_u64 >= exclude_tick_u64:
            try:
                dispatch_dir.resolve().relative_to(exclude_root)
            except Exception:  # noqa: BLE001
                pass
            else:
                # Observation is computed at the start of the tick; exclude receipts from the
                # current run that are generated later in the same tick (and therefore would not
                # have been visible during the original observation scan).
                continue
        capability_id = str(dispatch_payload.get("capability_id", "")).strip()
        if not capability_id:
            continue
        before_hash = str(activation_payload.get("before_active_manifest_hash", ""))
        after_hash = str(activation_payload.get("after_active_manifest_hash", ""))
        records.append(
            {
                "tick_u64": record_tick_u64,
                "capability_id": capability_id,
                "activation_success": bool(activation_payload.get("activation_success", False)),
                "manifest_changed": before_hash != after_hash,
            }
        )

    enabled_u64 = _count_enabled_capabilities(registry)
    if not records:
        return {
            "cap_frontier_u64": 0,
            "cap_enabled_u64": int(enabled_u64),
            "cap_activated_u64": 0,
            "cap_manifest_changed_u64": 0,
        }

    window = max(1, int(window_ticks_u64))
    latest_tick_u64 = max(int(row["tick_u64"]) for row in records)
    min_tick_u64 = max(0, int(latest_tick_u64 - window + 1))
    rows_window = [row for row in records if int(row["tick_u64"]) >= min_tick_u64]
    frontier_ids = sorted(
        {str(row["capability_id"]) for row in rows_window if bool(row["activation_success"])}
    )
    activated_u64 = sum(1 for row in rows_window if bool(row["activation_success"]))
    manifest_changed_u64 = sum(
        1 for row in rows_window if bool(row["activation_success"]) and bool(row["manifest_changed"])
    )
    return {
        "cap_frontier_u64": int(len(frontier_ids)),
        "cap_enabled_u64": int(enabled_u64),
        "cap_activated_u64": int(activated_u64),
        "cap_manifest_changed_u64": int(manifest_changed_u64),
    }


def _maximize_science_q32(science_rmse_q32: int) -> int:
    rmse_q = max(0, min(int(science_rmse_q32), int(_Q32_ONE)))
    return int(_Q32_ONE - rmse_q)


def _maximize_speed_q32(previous_tick_total_ns_u64: int) -> int:
    total_ns = int(previous_tick_total_ns_u64)
    if total_ns <= 0:
        return 0
    return int(rat_q32(1_000_000_000, total_ns))


def _recompute_observation_from_sources(
    *,
    root: Path,
    runs_roots: list[Path] | None,
    observation_payload: dict[str, Any],
    registry: dict[str, Any],
    policy_hash: str,
    registry_hash: str,
    objectives_hash: str,
    prev_observation: dict[str, Any] | None,
    exclude_run_dir: Path | None = None,
    exclude_after_or_equal_tick_u64: int | None = None,
) -> dict[str, Any]:
    sources = observation_payload.get("sources")
    if not isinstance(sources, list):
        fail("SCHEMA_FAIL")
    by_schema: dict[str, int] = {}
    seen_sources: set[tuple[str, str]] = set()
    previous_tick_total_ns_u64 = 0
    verifier_overhead_q32 = 0
    promotion_reject_rate_rat = {"num_u64": 0, "den_u64": 1}
    subverifier_invalid_rate_rat = {"num_u64": 0, "den_u64": 1}
    runaway_blocked_noop_rate_rat = {"num_u64": 0, "den_u64": 1}
    runaway_blocked_recent3_u64 = 0
    promotion_success_rate_rat = {"num_u64": 0, "den_u64": 1}
    activation_denied_rate_rat = {"num_u64": 0, "den_u64": 1}
    domains_bootstrapped_u64 = 0
    domains_blocked_license_u64 = 0
    domains_blocked_policy_u64 = 0
    domains_blocked_size_u64 = 0
    domains_ready_for_conquer_u64 = 0
    domain_topics_u64 = 0
    top_void_score_q32 = 0
    observation_tick_u64 = max(0, int(observation_payload.get("tick_u64", 0)))
    polymath_last_scout_tick_u64 = 0
    polymath_scout_age_ticks_u64 = int(_POLYMATH_STALE_AGE_U64)
    polymath_portfolio_score_q32 = 0
    polymath_portfolio_domains_u64 = 0
    polymath_portfolio_cache_hit_rate_q32 = 0
    code_pass_u64 = 0
    code_reports_u64 = 0
    ge_promote_u64 = 0
    ge_receipts_u64 = 0
    ge_stps_delta_total_q32 = 0
    transfer_gain_q32 = 0
    ontology_consistency_q32 = 0
    flywheel_yield_q32 = 0
    thermo_efficiency_q32 = 0
    persistence_health_q32 = 0
    persistence_flags_u64 = 0
    for source in sources:
        if not isinstance(source, dict):
            fail("SCHEMA_FAIL")
        schema_id, artifact_payload = _read_observer_source_artifact(root=root, source=source, runs_roots=runs_roots)
        artifact_hash = str(source.get("artifact_hash", "")).strip()
        if not artifact_hash.startswith("sha256:"):
            fail("SCHEMA_FAIL")
        seen_key = (schema_id, artifact_hash)
        if seen_key in seen_sources:
            fail("SCHEMA_FAIL")
        seen_sources.add(seen_key)
        if schema_id == "omega_tick_perf_v1":
            stage_ns = artifact_payload.get("stage_ns")
            if not isinstance(stage_ns, dict):
                fail("SCHEMA_FAIL")
            total_ns = int(artifact_payload.get("total_ns", 0))
            if total_ns < 0:
                fail("SCHEMA_FAIL")
            previous_tick_total_ns_u64 = max(0, total_ns)
            if previous_tick_total_ns_u64 > 0:
                run_subverifier_ns = max(0, int(stage_ns.get("run_subverifier", 0)))
                run_promotion_ns = max(0, int(stage_ns.get("run_promotion", 0)))
                verifier_overhead_q32 = rat_q32(run_subverifier_ns + run_promotion_ns, previous_tick_total_ns_u64)
            continue
        if schema_id == "omega_tick_stats_v1":
            validate_schema(artifact_payload, "omega_tick_stats_v1")
            for key, target in [
                ("promotion_reject_rate_rat", promotion_reject_rate_rat),
                ("invalid_rate_rat", subverifier_invalid_rate_rat),
                ("runaway_blocked_noop_rate_rat", runaway_blocked_noop_rate_rat),
            ]:
                row = artifact_payload.get(key)
                if not isinstance(row, dict):
                    fail("SCHEMA_FAIL")
                target["num_u64"] = max(0, int(row.get("num_u64", 0)))
                target["den_u64"] = max(1, int(row.get("den_u64", 1)))
            run_ticks_u64 = max(1, int(artifact_payload.get("run_ticks_u64", 1)))
            activation_denied_rate_rat = {
                "num_u64": max(0, int(artifact_payload.get("activation_denied_u64", 0))),
                "den_u64": run_ticks_u64,
            }
            recent_noop_reasons = artifact_payload.get("recent_noop_reasons")
            if not isinstance(recent_noop_reasons, list):
                fail("SCHEMA_FAIL")
            streak = 0
            for row in reversed(recent_noop_reasons):
                if str(row) == "RUNAWAY_BLOCKED":
                    streak += 1
                else:
                    break
                if streak >= 3:
                    break
            runaway_blocked_recent3_u64 = int(min(3, streak))
            continue
        if schema_id == "omega_run_scorecard_v1":
            validate_schema(artifact_payload, "omega_run_scorecard_v1")
            row = artifact_payload.get("promotion_success_rate_rat")
            if not isinstance(row, dict):
                fail("SCHEMA_FAIL")
            promotion_success_rate_rat = {
                "num_u64": max(0, int(row.get("num_u64", 0))),
                "den_u64": max(1, int(row.get("den_u64", 1))),
            }
            continue
        if schema_id == "polymath_domain_registry_v1":
            validate_schema(artifact_payload, "polymath_domain_registry_v1")
            domains = artifact_payload.get("domains")
            if not isinstance(domains, list):
                fail("SCHEMA_FAIL")
            for row in domains:
                if not isinstance(row, dict):
                    fail("SCHEMA_FAIL")
                status = str(row.get("status", "")).strip()
                if status == "ACTIVE":
                    domains_bootstrapped_u64 += 1
                    if bool(row.get("ready_for_conquer", False)) and not bool(row.get("conquered_b", False)):
                        domains_ready_for_conquer_u64 += 1
                elif status == "BLOCKED_LICENSE":
                    domains_blocked_license_u64 += 1
                elif status == "BLOCKED_POLICY":
                    domains_blocked_policy_u64 += 1
                elif status == "BLOCKED_SIZE":
                    domains_blocked_size_u64 += 1
            continue
        if schema_id == "polymath_void_report_v1":
            rows = artifact_payload.get("rows")
            if not isinstance(rows, list):
                fail("SCHEMA_FAIL")
            topics: set[str] = set()
            for row in rows:
                if not isinstance(row, dict):
                    fail("SCHEMA_FAIL")
                topic_id = str(row.get("topic_id", "")).strip()
                if topic_id:
                    topics.add(topic_id)
                void_obj = row.get("void_score_q32")
                if isinstance(void_obj, dict):
                    top_void_score_q32 = max(top_void_score_q32, int(void_obj.get("q", 0)))
            domain_topics_u64 = max(domain_topics_u64, len(topics))
            continue
        if schema_id == "polymath_scout_status_v1":
            validate_schema(artifact_payload, "polymath_scout_status_v1")
            last_tick = max(0, int(artifact_payload.get("tick_u64", 0)))
            if last_tick > int(observation_tick_u64):
                fail("SCHEMA_FAIL")
            polymath_last_scout_tick_u64 = int(last_tick)
            polymath_scout_age_ticks_u64 = int(max(0, int(observation_tick_u64) - int(last_tick)))
            continue
        if schema_id == "polymath_portfolio_v1":
            validate_schema(artifact_payload, "polymath_portfolio_v1")
            score_obj = artifact_payload.get("portfolio_score_q32")
            if isinstance(score_obj, dict):
                polymath_portfolio_score_q32 = int(score_obj.get("q", 0))
            domains_rows = artifact_payload.get("domains")
            if isinstance(domains_rows, list):
                rows = [row for row in domains_rows if isinstance(row, dict)]
                polymath_portfolio_domains_u64 = int(len(rows))
                polymath_portfolio_cache_hit_rate_q32 = (
                    int(sum(int(row.get("cache_hit_rate_q32", 0)) for row in rows) // len(rows))
                    if rows
                    else 0
                )
            continue
        if schema_id == "sas_code_perf_report_v1":
            if str(artifact_payload.get("schema_version", "")).strip() != "sas_code_perf_report_v1":
                fail("SCHEMA_FAIL")
            gate = artifact_payload.get("gate")
            if not isinstance(gate, dict):
                fail("SCHEMA_FAIL")
            if bool(gate.get("passed", False)):
                code_pass_u64 += 1
            code_reports_u64 += 1
            continue
        if schema_id == "ccap_receipt_v1":
            if str(source.get("producer_campaign_id", "")).strip() != _GE_CAMPAIGN_ID:
                fail("SCHEMA_FAIL")
            validate_schema(artifact_payload, "ccap_receipt_v1")
            if str(artifact_payload.get("decision", "")).strip() == "PROMOTE":
                ge_promote_u64 += 1
            ge_stps_delta_total_q32 += int(_ge_stps_delta_q32(artifact_payload))
            ge_receipts_u64 += 1
            continue
        if schema_id in _OBS_SKILL_SOURCE_TO_METRIC:
            validate_schema(artifact_payload, "omega_skill_report_v1")
            metric_key = _OBS_SKILL_SOURCE_TO_METRIC[schema_id]
            metrics_obj = artifact_payload.get("metrics")
            if not isinstance(metrics_obj, dict):
                fail("SCHEMA_FAIL")
            metric_obj = metrics_obj.get(metric_key)
            if not isinstance(metric_obj, dict):
                fail("SCHEMA_FAIL")
            metric_q32 = int(metric_obj.get("q", 0))
            if schema_id == "omega_skill_transfer_report_v1":
                transfer_gain_q32 = metric_q32
            elif schema_id == "omega_skill_ontology_report_v1":
                ontology_consistency_q32 = metric_q32
            elif schema_id == "omega_skill_eff_flywheel_report_v1":
                flywheel_yield_q32 = metric_q32
            elif schema_id == "omega_skill_thermo_report_v1":
                thermo_efficiency_q32 = metric_q32
            elif schema_id == "omega_skill_persistence_report_v1":
                persistence_health_q32 = metric_q32
                flags = artifact_payload.get("flags")
                if not isinstance(flags, list):
                    fail("SCHEMA_FAIL")
                persistence_flags_u64 = len(flags)
            continue
        by_schema[schema_id] = _metric_from_observer_source(schema_id, artifact_payload)

    for required in sorted(_OBS_REQUIRED_SOURCE_IDS):
        if required not in by_schema:
            fail("SCHEMA_FAIL")
    brain_temperature_q32 = int(
        compute_temperature_q32(
            promotion_success_rate=promotion_success_rate_rat,
            invalid_rate=subverifier_invalid_rate_rat,
            activation_denied_rate=activation_denied_rate_rat,
        )
    )
    domain_coverage_ratio_q32 = rat_q32(min(domains_bootstrapped_u64, max(1, domain_topics_u64)), max(1, domain_topics_u64))
    ge_promote_rate_rat = {
        "num_u64": int(ge_promote_u64),
        "den_u64": int(max(1, ge_receipts_u64)),
    }
    ge_mean_stps_delta_q32 = int(ge_stps_delta_total_q32 // max(1, ge_receipts_u64))
    code_success_rate_rat = {
        "num_u64": int(code_pass_u64),
        "den_u64": int(max(1, code_reports_u64)),
    }
    capability_frontier = _capability_frontier_metrics(
        root=root,
        registry=registry,
        exclude_run_dir=exclude_run_dir,
        exclude_after_or_equal_tick_u64=exclude_after_or_equal_tick_u64,
    )
    capability_expansion_q32 = int(int(capability_frontier["cap_frontier_u64"]) << 32)
    maximize_science_q32 = _maximize_science_q32(int(by_schema["sas_science_promotion_bundle_v1"]))
    maximize_speed_q32 = _maximize_speed_q32(int(previous_tick_total_ns_u64))

    payload: dict[str, Any] = {
        "schema_version": "omega_observation_report_v1",
        "report_id": "sha256:" + "0" * 64,
        "tick_u64": int(observation_payload.get("tick_u64", 0)),
        "active_manifest_hash": str(observation_payload.get("active_manifest_hash", "")),
        "metrics": {
            "metasearch_cost_ratio_q32": {"q": int(by_schema["metasearch_compute_report_v1"])},
            "hotloop_top_share_q32": {"q": int(by_schema["kernel_hotloop_report_v1"])},
            "val_hotloop_top_share_q32": {"q": int(by_schema["kernel_hotloop_report_v1"])},
            "build_link_fraction_q32": {"q": int(by_schema["sas_system_perf_report_v1"])},
            "system_build_link_fraction_q32": {"q": int(by_schema["sas_system_perf_report_v1"])},
            "science_rmse_q32": {"q": int(by_schema["sas_science_promotion_bundle_v1"])},
            "code_success_rate_rat": code_success_rate_rat,
            "promotion_reject_rate_rat": promotion_reject_rate_rat,
            "subverifier_invalid_rate_rat": subverifier_invalid_rate_rat,
            "runaway_blocked_noop_rate_rat": runaway_blocked_noop_rate_rat,
            "runaway_blocked_recent3_u64": int(runaway_blocked_recent3_u64),
            "verifier_overhead_q32": {"q": verifier_overhead_q32},
            "previous_tick_total_ns_u64": int(previous_tick_total_ns_u64),
            "OBJ_EXPAND_CAPABILITIES": {"q": int(capability_expansion_q32)},
            "OBJ_MAXIMIZE_SCIENCE": {"q": int(maximize_science_q32)},
            "OBJ_MAXIMIZE_SPEED": {"q": int(maximize_speed_q32)},
            "cap_frontier_u64": int(capability_frontier["cap_frontier_u64"]),
            "cap_enabled_u64": int(capability_frontier["cap_enabled_u64"]),
            "cap_activated_u64": int(capability_frontier["cap_activated_u64"]),
            "brain_temperature_q32": {"q": int(brain_temperature_q32)},
            "domain_coverage_ratio": {"q": int(domain_coverage_ratio_q32)},
            "top_void_score_q32": {"q": int(top_void_score_q32)},
            "domains_bootstrapped_u64": int(domains_bootstrapped_u64),
            "domains_blocked_license_u64": int(domains_blocked_license_u64),
            "domains_blocked_policy_u64": int(domains_blocked_policy_u64),
            "domains_blocked_size_u64": int(domains_blocked_size_u64),
            "domains_ready_for_conquer_u64": int(domains_ready_for_conquer_u64),
            "polymath_last_scout_tick_u64": int(polymath_last_scout_tick_u64),
            "polymath_scout_age_ticks_u64": int(polymath_scout_age_ticks_u64),
            "polymath_portfolio_score_q32": {"q": int(polymath_portfolio_score_q32)},
            "polymath_portfolio_domains_u64": int(polymath_portfolio_domains_u64),
            "polymath_portfolio_cache_hit_rate_q32": {"q": int(polymath_portfolio_cache_hit_rate_q32)},
            "ge_promote_rate_rat": ge_promote_rate_rat,
            "ge_mean_stps_delta_q32": {"q": int(ge_mean_stps_delta_q32)},
            "transfer_gain_q32": {"q": int(transfer_gain_q32)},
            "ontology_consistency_q32": {"q": int(ontology_consistency_q32)},
            "flywheel_yield_q32": {"q": int(flywheel_yield_q32)},
            "thermo_efficiency_q32": {"q": int(thermo_efficiency_q32)},
            "persistence_health_q32": {"q": int(persistence_health_q32)},
            "persistence_flags_u64": int(persistence_flags_u64),
        },
        "metric_series": {
            "metasearch_cost_ratio_q32": [{"q": int(by_schema["metasearch_compute_report_v1"])}],
            "hotloop_top_share_q32": [{"q": int(by_schema["kernel_hotloop_report_v1"])}],
            "val_hotloop_top_share_q32": [{"q": int(by_schema["kernel_hotloop_report_v1"])}],
            "build_link_fraction_q32": [{"q": int(by_schema["sas_system_perf_report_v1"])}],
            "system_build_link_fraction_q32": [{"q": int(by_schema["sas_system_perf_report_v1"])}],
            "science_rmse_q32": [{"q": int(by_schema["sas_science_promotion_bundle_v1"])}],
            "code_success_rate_rat": [code_success_rate_rat],
            "promotion_reject_rate_rat": [promotion_reject_rate_rat],
            "subverifier_invalid_rate_rat": [subverifier_invalid_rate_rat],
            "runaway_blocked_noop_rate_rat": [runaway_blocked_noop_rate_rat],
            "runaway_blocked_recent3_u64": [int(runaway_blocked_recent3_u64)],
            "previous_tick_total_ns_u64": [int(previous_tick_total_ns_u64)],
            "OBJ_EXPAND_CAPABILITIES": [{"q": int(capability_expansion_q32)}],
            "OBJ_MAXIMIZE_SCIENCE": [{"q": int(maximize_science_q32)}],
            "OBJ_MAXIMIZE_SPEED": [{"q": int(maximize_speed_q32)}],
            "cap_frontier_u64": [int(capability_frontier["cap_frontier_u64"])],
            "cap_enabled_u64": [int(capability_frontier["cap_enabled_u64"])],
            "cap_activated_u64": [int(capability_frontier["cap_activated_u64"])],
            "brain_temperature_q32": [{"q": int(brain_temperature_q32)}],
            "domain_coverage_ratio": [{"q": int(domain_coverage_ratio_q32)}],
            "top_void_score_q32": [{"q": int(top_void_score_q32)}],
            "domains_bootstrapped_u64": [int(domains_bootstrapped_u64)],
            "domains_blocked_license_u64": [int(domains_blocked_license_u64)],
            "domains_blocked_policy_u64": [int(domains_blocked_policy_u64)],
            "domains_blocked_size_u64": [int(domains_blocked_size_u64)],
            "domains_ready_for_conquer_u64": [int(domains_ready_for_conquer_u64)],
            "polymath_last_scout_tick_u64": [int(polymath_last_scout_tick_u64)],
            "polymath_scout_age_ticks_u64": [int(polymath_scout_age_ticks_u64)],
            "polymath_portfolio_score_q32": [{"q": int(polymath_portfolio_score_q32)}],
            "polymath_portfolio_domains_u64": [int(polymath_portfolio_domains_u64)],
            "polymath_portfolio_cache_hit_rate_q32": [{"q": int(polymath_portfolio_cache_hit_rate_q32)}],
            "ge_promote_rate_rat": [ge_promote_rate_rat],
            "ge_mean_stps_delta_q32": [{"q": int(ge_mean_stps_delta_q32)}],
            "transfer_gain_q32": [{"q": int(transfer_gain_q32)}],
            "ontology_consistency_q32": [{"q": int(ontology_consistency_q32)}],
            "flywheel_yield_q32": [{"q": int(flywheel_yield_q32)}],
            "thermo_efficiency_q32": [{"q": int(thermo_efficiency_q32)}],
            "persistence_health_q32": [{"q": int(persistence_health_q32)}],
            "persistence_flags_u64": [int(persistence_flags_u64)],
        },
        "sources": list(sources),
        "inputs_hashes": {
            "policy_hash": policy_hash,
            "registry_hash": registry_hash,
            "objectives_hash": objectives_hash,
        },
    }
    if prev_observation is not None:
        prev_metric_series = prev_observation.get("metric_series")
        cur_metric_series = payload.get("metric_series")
        if not isinstance(prev_metric_series, dict) or not isinstance(cur_metric_series, dict):
            fail("SCHEMA_FAIL")
        for key, cur_rows in cur_metric_series.items():
            if not isinstance(cur_rows, list) or not cur_rows:
                fail("SCHEMA_FAIL")
            if key in _OBS_NON_CARRY_SERIES_KEYS:
                continue
            prev_rows = prev_metric_series.get(key)
            if not isinstance(prev_rows, list):
                fail("SCHEMA_FAIL")
            if len(prev_rows) >= _MAX_SERIES_LEN_U64:
                prev_rows = prev_rows[-(_MAX_SERIES_LEN_U64 - 1) :]
            cur_metric_series[key] = [*prev_rows, cur_rows[-1]]
    no_id = dict(payload)
    no_id.pop("report_id", None)
    payload["report_id"] = canon_hash_obj(no_id)
    validate_schema(payload, "omega_observation_report_v1")
    return payload


def _run_subverifier_replay_cmd(
    *,
    state_root: Path,
    verifier_module: str,
    state_arg: str,
    replay_state_dir: str,
    replay_repo_root: Path | None = None,
    env_overrides: dict[str, str] | None = None,
    replay_argv: list[str] | None = None,
) -> tuple[int, str, str]:
    if replay_argv is None:
        cmd = [sys.executable, "-m", verifier_module, "--mode", "full", state_arg, replay_state_dir]
    else:
        cmd = [sys.executable, "-m", verifier_module, *list(replay_argv)]
    env = dict(os.environ)
    existing_pythonpath = str(env.get("PYTHONPATH", "")).strip()

    def _run_with_roots(*, pythonpath_root: Path, cwd_root: Path) -> tuple[int, str, str]:
        base_pythonpath = f"{pythonpath_root}/CDEL-v2:{pythonpath_root}"
        local_env = dict(env)
        local_env["PYTHONPATH"] = f"{base_pythonpath}:{existing_pythonpath}" if existing_pythonpath else base_pythonpath
        for key, value in (env_overrides or {}).items():
            local_env[str(key)] = str(value)
        rc = subprocess.run(
            cmd,
            cwd=cwd_root,
            capture_output=True,
            text=True,
            check=False,
            env=local_env,
        )
        stdout_text = rc.stdout.strip()
        stdout_lines = rc.stdout.splitlines()
        last_line = stdout_lines[-1].strip() if stdout_lines else ""
        return int(rc.returncode), last_line, stdout_text

    if replay_repo_root is None:
        root = _repo_root()
        # Some verifiers resolve repo-relative paths from CWD (Path(".").resolve()).
        # Use repo root here to match orchestrator execution, while still passing
        # an explicit replay_state_dir argument.
        return _run_with_roots(pythonpath_root=root, cwd_root=root)
    if verifier_module == _V16_1_METASEARCH_VERIFIER_MODULE:
        with tempfile.TemporaryDirectory(prefix="omega_v16_replay_") as tmp:
            tmp_root = Path(tmp) / "repo_root"
            shutil.copytree(replay_repo_root, tmp_root)
            # Avoid Path.rglob here: some verifier tests enforce that replay paths
            # never fall back to rglob-based discovery.
            if not tmp_root.is_symlink():
                tmp_root.chmod(tmp_root.stat().st_mode | 0o200)
            for root_dir, dir_names, file_names in os.walk(tmp_root):
                dir_names.sort()
                file_names.sort()
                for name in [*dir_names, *file_names]:
                    path = Path(root_dir) / name
                    if path.is_symlink():
                        continue
                    path.chmod(path.stat().st_mode | 0o200)
            return _run_with_roots(pythonpath_root=tmp_root, cwd_root=tmp_root)
    return _run_with_roots(pythonpath_root=replay_repo_root, cwd_root=replay_repo_root)


def _has_valid_line(stdout_text: str) -> bool:
    return any("VALID" in str(line).strip() for line in str(stdout_text).splitlines())


def _resolve_replay_repo_root(
    *,
    state_root: Path,
    verifier_module: str,
    subverifier_payload: dict[str, Any],
) -> Path | None:
    rel_raw = subverifier_payload.get("replay_repo_root_rel")
    hash_raw = subverifier_payload.get("replay_repo_root_hash")
    if rel_raw is None and hash_raw is None:
        if verifier_module in _REPLAY_REPO_ROOT_REQUIRED_VERIFIER_MODULES:
            fail("SUBVERIFIER_REPLAY_FAIL")
        return None
    if not isinstance(rel_raw, str) or not rel_raw.strip():
        fail("SUBVERIFIER_REPLAY_FAIL")
    if not isinstance(hash_raw, str) or not hash_raw.startswith("sha256:"):
        fail("SUBVERIFIER_REPLAY_FAIL")
    replay_root = (state_root / rel_raw).resolve()
    state_root_abs = state_root.resolve()
    try:
        replay_root.relative_to(state_root_abs)
    except ValueError:
        fail("SUBVERIFIER_REPLAY_FAIL")
    if not replay_root.exists() or not replay_root.is_dir():
        fail("SUBVERIFIER_REPLAY_FAIL")
    if tree_hash(replay_root) != hash_raw:
        fail("SUBVERIFIER_REPLAY_FAIL")
    return replay_root


def _v12_replay_fallback_state_dir(subrun_state_dir: Path) -> str | None:
    health_dir = subrun_state_dir / "health"
    manifest_paths = sorted(health_dir.glob("sha256_*.sas_root_manifest_v1.json"))
    if not manifest_paths:
        return None
    manifest = load_canon_dict(manifest_paths[-1])
    sas_root_canon = str(manifest.get("sas_root_canon", "")).strip()
    if not sas_root_canon:
        return None
    return str((Path(sas_root_canon) / "state").resolve())


def _discover_ccap_relpath(subrun_root: Path) -> str | None:
    rows = sorted((subrun_root / "ccap").glob("sha256_*.ccap_v1.json"), key=lambda row: row.as_posix())
    if not rows:
        return None
    return rows[0].relative_to(subrun_root).as_posix()


def _replay_promoted_subverifier(
    *,
    state_root: Path,
    dispatch_payload: dict[str, Any] | None,
    subverifier_payload: dict[str, Any] | None,
) -> None:
    if dispatch_payload is None or subverifier_payload is None:
        fail("SUBVERIFIER_REPLAY_FAIL")

    verifier_module = str(subverifier_payload.get("verifier_module", "")).strip()
    if not verifier_module:
        fail("SUBVERIFIER_REPLAY_FAIL")

    subrun = dispatch_payload.get("subrun")
    if not isinstance(subrun, dict):
        fail("SUBVERIFIER_REPLAY_FAIL")
    subrun_root_rel = str(subrun.get("subrun_root_rel", "")).strip()
    subrun_state_rel = str(subrun.get("state_dir_rel", "")).strip()
    if not subrun_root_rel or not subrun_state_rel:
        fail("SUBVERIFIER_REPLAY_FAIL")
    replay_state_rel = f"{subrun_root_rel}/{subrun_state_rel}"
    replay_state_abs = (state_root / replay_state_rel).resolve()
    if not replay_state_abs.exists() or not replay_state_abs.is_dir():
        fail("SUBVERIFIER_REPLAY_FAIL")

    expected_state_hash = str(subverifier_payload.get("state_dir_hash", "")).strip()
    if expected_state_hash != tree_hash(replay_state_abs):
        fail("SUBVERIFIER_REPLAY_FAIL")

    replay_repo_root = _resolve_replay_repo_root(
        state_root=state_root,
        verifier_module=verifier_module,
        subverifier_payload=subverifier_payload,
    )
    invocation = dispatch_payload.get("invocation")
    if not isinstance(invocation, dict):
        fail("SUBVERIFIER_REPLAY_FAIL")
    raw_overrides = invocation.get("env_overrides")
    env_overrides: dict[str, str] | None = None
    if raw_overrides is not None:
        if not isinstance(raw_overrides, dict):
            fail("SUBVERIFIER_REPLAY_FAIL")
        env_overrides = {str(k): str(v) for k, v in raw_overrides.items()}

    state_arg = _state_arg_for_verifier(verifier_module)

    replay_argv: list[str] | None = None
    if verifier_module == "cdel.v18_0.verify_ccap_v1":
        replay_subrun_root_abs = (state_root / subrun_root_rel).resolve()
        replay_receipt_out_dir = state_root / "_replay_subverifier" / replay_subrun_root_abs.name / "verifier"
        replay_receipt_out_dir.mkdir(parents=True, exist_ok=True)
        replay_argv = [
            "--mode",
            "full",
            "--subrun_root",
            str(replay_subrun_root_abs),
            "--repo_root",
            str(_repo_root()),
            "--receipt_out_dir",
            str(replay_receipt_out_dir),
            "--enable_ccap",
            "1",
        ]
        ccap_relpath = _discover_ccap_relpath(replay_subrun_root_abs)
        if ccap_relpath is not None:
            replay_argv.extend(["--ccap_relpath", ccap_relpath])

    return_code, last_line, stdout_text = _run_subverifier_replay_cmd(
        state_root=state_root,
        verifier_module=verifier_module,
        state_arg=state_arg,
        replay_state_dir=str(replay_state_abs),
        replay_repo_root=replay_repo_root,
        env_overrides=env_overrides,
        replay_argv=replay_argv,
    )
    if return_code == 0 and _has_valid_line(stdout_text):
        return
    if verifier_module == "cdel.v12_0.verify_rsi_sas_code_v1":
        fallback_state_dir = _v12_replay_fallback_state_dir(replay_state_abs)
        if fallback_state_dir:
            return_code, last_line, stdout_text = _run_subverifier_replay_cmd(
                state_root=state_root,
                verifier_module=verifier_module,
                state_arg=state_arg,
                replay_state_dir=fallback_state_dir,
                replay_repo_root=replay_repo_root,
                env_overrides=env_overrides,
            )
            if return_code == 0 and _has_valid_line(stdout_text):
                return

    if return_code != 0 or not _has_valid_line(stdout_text):
        fail("SUBVERIFIER_REPLAY_FAIL")


def verify(state_dir: Path, *, mode: str = "full") -> str:
    if mode != "full":
        fail("MODE_UNSUPPORTED")

    state_root, daemon_root = _resolve_state_dir(state_dir)
    config_dir = daemon_root / "config"

    pack, pack_hash = _load_and_hash(config_dir / "rsi_omega_daemon_pack_v1.json", "rsi_omega_daemon_pack_v1")
    policy, policy_hash = load_policy(config_dir / "omega_policy_ir_v1.json")
    registry, registry_hash = load_registry(config_dir / "omega_capability_registry_v2.json")
    objectives, objectives_hash = load_objectives(config_dir / "omega_objectives_v1.json")
    runaway_cfg, _runaway_cfg_hash = load_runaway_config(config_dir / "omega_runaway_config_v1.json")
    _budgets, budgets_hash = _load_and_hash(config_dir / "omega_budgets_v1.json", "omega_budgets_v1")
    allowlists, _allowlists_hash = load_allowlists(config_dir / "omega_allowlists_v1.json")
    healthcheck_suite, healthcheck_suite_hash = _load_and_hash(config_dir / "healthcheck_suitepack_v1.json", "healthcheck_suitepack_v1")
    goal_queue = _load_goal_queue_from_config(config_dir)

    bid_market_cfg, bid_market_cfg_hash = load_optional_bid_market_config(config_dir)
    market_enabled = bid_market_enabled(bid_market_cfg)

    snapshot_path = _latest_snapshot_or_fail(state_root / "snapshot")
    snapshot = _verify_hash_binding(snapshot_path, canon_hash_obj(load_canon_dict(snapshot_path)), "omega_tick_snapshot_v1")

    state_payload = _verify_hash_binding(
        find_by_hash(state_root / "state", "omega_state_v1.json", str(snapshot.get("state_hash"))),
        str(snapshot.get("state_hash")),
        "omega_state_v1",
    )
    obs_payload = _verify_hash_binding(
        find_by_hash(state_root / "observations", "omega_observation_report_v1.json", str(snapshot.get("observation_report_hash"))),
        str(snapshot.get("observation_report_hash")),
        "omega_observation_report_v1",
    )
    issue_payload = _verify_hash_binding(
        find_by_hash(state_root / "issues", "omega_issue_bundle_v1.json", str(snapshot.get("issue_bundle_hash"))),
        str(snapshot.get("issue_bundle_hash")),
        "omega_issue_bundle_v1",
    )
    decision_payload = _verify_hash_binding(
        find_by_hash(state_root / "decisions", "omega_decision_plan_v1.json", str(snapshot.get("decision_plan_hash"))),
        str(snapshot.get("decision_plan_hash")),
        "omega_decision_plan_v1",
    )

    dispatch_payload = None
    if snapshot.get("dispatch_receipt_hash") is not None:
        digest = str(snapshot.get("dispatch_receipt_hash"))
        dispatch_payload = _verify_hash_binding(
            _find_dispatch_hash(state_root, digest),
            digest,
            "omega_dispatch_receipt_v1",
        )

    subverifier_payload = None
    if snapshot.get("subverifier_receipt_hash") is not None:
        digest = str(snapshot.get("subverifier_receipt_hash"))
        subverifier_payload = _verify_hash_binding(
            _find_nested_hash(state_root, digest, "omega_subverifier_receipt_v1.json"),
            digest,
            "omega_subverifier_receipt_v1",
        )

    promotion_payload = None
    promotion_path: Path | None = None
    if snapshot.get("promotion_receipt_hash") is not None:
        digest = str(snapshot.get("promotion_receipt_hash"))
        promotion_path = _find_nested_hash(state_root, digest, "omega_promotion_receipt_v1.json")
        promotion_payload = _verify_hash_binding(
            promotion_path,
            digest,
            "omega_promotion_receipt_v1",
        )

    activation_payload = None
    if snapshot.get("activation_receipt_hash") is not None:
        digest = str(snapshot.get("activation_receipt_hash"))
        activation_payload = _verify_hash_binding(
            _find_nested_hash(state_root, digest, "omega_activation_receipt_v1.json"),
            digest,
            "omega_activation_receipt_v1",
        )

    rollback_payload = None
    if snapshot.get("rollback_receipt_hash") is not None:
        digest = str(snapshot.get("rollback_receipt_hash"))
        rollback_payload = _verify_hash_binding(
            _find_nested_hash(state_root, digest, "omega_rollback_receipt_v1.json"),
            digest,
            "omega_rollback_receipt_v1",
        )

    dispatch_occurred = dispatch_payload is not None
    subverifier_status = str((subverifier_payload or {}).get("result", {}).get("status", "")).strip()
    subverifier_reason = (subverifier_payload or {}).get("result", {}).get("reason_code")
    promotion_status = str((promotion_payload or {}).get("result", {}).get("status", "")).strip()

    # Keep verifier behavior aligned with orchestrator/omega_v18_0/coordinator_v1.py:
    # SAFE_HALT suppresses runaway stall escalation.
    safe_halt = str((decision_payload or {}).get("action_kind")) == "SAFE_HALT"
    if subverifier_payload is not None and subverifier_status != "VALID":
        safe_halt = True
    if str((promotion_payload or {}).get("result", {}).get("reason_code")) == "FORBIDDEN_PATH":
        safe_halt = True

    subverifier_invalid_stall = dispatch_occurred and subverifier_status == "INVALID" and not safe_halt

    trace_payload = _verify_hash_binding(
        find_by_hash(state_root / "ledger", "omega_trace_hash_chain_v1.json", str(snapshot.get("trace_hash_chain_hash"))),
        str(snapshot.get("trace_hash_chain_hash")),
        "omega_trace_hash_chain_v1",
    )

    if state_payload.get("policy_hash") != policy_hash:
        fail("POLICY_HASH_MISMATCH")
    if state_payload.get("registry_hash") != registry_hash:
        fail("REGISTRY_HASH_MISMATCH")
    if state_payload.get("objectives_hash") != objectives_hash:
        fail("OBJECTIVES_HASH_MISMATCH")
    if state_payload.get("budgets_hash") != budgets_hash:
        fail("BUDGETS_HASH_MISMATCH")

    prev_state_id = state_payload.get("prev_state_id")
    if not isinstance(prev_state_id, str):
        fail("NONDETERMINISTIC")
    prev_state_payload = _find_state_payload_by_state_id(state_root / "state", prev_state_id)

    prev_runaway_payload = None
    current_runaway_payload = None
    if runaway_enabled(runaway_cfg):
        prev_runaway_payload = load_prev_runaway_state_for_tick(
            state_root / "runaway",
            int(decision_payload.get("tick_u64", 0)),
        )
        if prev_runaway_payload is None:
            fail("MISSING_STATE_INPUT")
        current_runaway_payload = load_latest_runaway_state(state_root / "runaway")
        if current_runaway_payload is None:
            fail("MISSING_STATE_INPUT")
        if int(current_runaway_payload.get("tick_u64", -1)) != int(state_payload.get("tick_u64", -2)):
            fail("NONDETERMINISTIC")

    prev_observation = _find_prev_observation_report(
        state_root=state_root,
        current_tick_u64=int(obs_payload.get("tick_u64", 0)),
    )
    if prev_observation is None:
        prev_observation = _derive_prev_observation_from_payload(obs_payload)
    prev_observation_full = _find_prev_observation_report(
        state_root=state_root,
        current_tick_u64=int(obs_payload.get("tick_u64", 0)),
    )
    prev_observation_full_hash = canon_hash_obj(prev_observation_full) if isinstance(prev_observation_full, dict) else None
    exclude_run_dir: Path | None = None
    if daemon_root.parent.name == "daemon":
        exclude_run_dir = daemon_root.parent.parent
    recomputed_obs = _recompute_observation_from_sources(
        root=_repo_root(),
        runs_roots=_observer_runs_roots(root=_repo_root(), daemon_root=daemon_root),
        observation_payload=obs_payload,
        registry=registry,
        policy_hash=policy_hash,
        registry_hash=registry_hash,
        objectives_hash=objectives_hash,
        prev_observation=prev_observation,
        exclude_run_dir=exclude_run_dir,
        exclude_after_or_equal_tick_u64=int(obs_payload.get("tick_u64", 0)),
    )
    if canon_hash_obj(recomputed_obs) != canon_hash_obj(obs_payload):
        fail("NONDETERMINISTIC")

    recomputed_issue, recomputed_issue_hash = diagnose(
        tick_u64=int(issue_payload.get("tick_u64", 0)),
        observation_report=obs_payload,
        objectives=objectives,
    )
    if recomputed_issue_hash != canon_hash_obj(issue_payload):
        fail("NONDETERMINISTIC")

    recomputed_inputs_hash = _decision_inputs_hash(decision_payload)
    proof = decision_payload.get("recompute_proof")
    if not isinstance(proof, dict):
        fail("NONDETERMINISTIC")
    if proof.get("inputs_hash") != recomputed_inputs_hash:
        fail("NONDETERMINISTIC")
    if proof.get("plan_hash") != decision_payload.get("plan_id"):
        fail("NONDETERMINISTIC")

    if not market_enabled:
        recomputed_decision, _ = decide(
            tick_u64=int(decision_payload.get("tick_u64", 0)),
            state=prev_state_payload,
            observation_report_hash=str(decision_payload.get("observation_report_hash")),
            issue_bundle_hash=str(decision_payload.get("issue_bundle_hash")),
            observation_report=obs_payload,
            issue_bundle=issue_payload,
            policy=policy,
            policy_hash=policy_hash,
            registry=registry,
            registry_hash=registry_hash,
            budgets_hash=budgets_hash,
            goal_queue=goal_queue,
            objectives=objectives,
            runaway_cfg=runaway_cfg,
            runaway_state=prev_runaway_payload,
        )
        if canon_hash_obj(recomputed_decision) != canon_hash_obj(decision_payload):
            fail("NONDETERMINISTIC")
    else:
        if bid_market_cfg is None or bid_market_cfg_hash is None:
            fail("MISSING_STATE_INPUT")

        snap_state_hash = snapshot.get("bid_market_state_hash")
        snap_settlement_hash = snapshot.get("bid_settlement_receipt_hash")
        snap_bid_set_hash = snapshot.get("bid_set_hash")
        snap_selection_hash = snapshot.get("bid_selection_receipt_hash")
        for value in [snap_state_hash, snap_settlement_hash, snap_bid_set_hash, snap_selection_hash]:
            if not isinstance(value, str) or not value.startswith("sha256:") or len(value.split(":", 1)[1]) != 64:
                fail("MISSING_STATE_INPUT")

        market_state_payload = _verify_hash_binding(
            find_by_hash(state_root / "market" / "state", "bid_market_state_v1.json", str(snap_state_hash)),
            str(snap_state_hash),
            "bid_market_state_v1",
        )
        settlement_payload = _verify_hash_binding(
            find_by_hash(state_root / "market" / "settlement", "bid_settlement_receipt_v1.json", str(snap_settlement_hash)),
            str(snap_settlement_hash),
            "bid_settlement_receipt_v1",
        )
        bid_set_payload = _verify_hash_binding(
            find_by_hash(state_root / "market" / "bid_sets", "bid_set_v1.json", str(snap_bid_set_hash)),
            str(snap_bid_set_hash),
            "bid_set_v1",
        )
        selection_payload = _verify_hash_binding(
            find_by_hash(state_root / "market" / "selection", "bid_selection_receipt_v1.json", str(snap_selection_hash)),
            str(snap_selection_hash),
            "bid_selection_receipt_v1",
        )

        # Load referenced bids from the current tick's bid set.
        bids_by_campaign: dict[str, dict[str, Any]] = {}
        bid_refs = bid_set_payload.get("bids")
        if not isinstance(bid_refs, list):
            fail("SCHEMA_FAIL")
        for ref in bid_refs:
            if not isinstance(ref, dict):
                fail("SCHEMA_FAIL")
            cid = str(ref.get("campaign_id", "")).strip()
            bh = str(ref.get("bid_hash", "")).strip()
            if not cid or not bh:
                fail("SCHEMA_FAIL")
            bids_by_campaign[cid] = _verify_hash_binding(
                find_by_hash(state_root / "market" / "bids", "bid_v1.json", bh),
                bh,
                "bid_v1",
            )

        # Load prior tick state/selection receipts referenced by settlement.
        prev_market_state = None
        prev_market_state_hash = settlement_payload.get("market_state_before_hash")
        if prev_market_state_hash is not None:
            prev_market_state = _verify_hash_binding(
                find_by_hash(state_root / "market" / "state", "bid_market_state_v1.json", str(prev_market_state_hash)),
                str(prev_market_state_hash),
                "bid_market_state_v1",
            )
            prev_market_state_hash = str(prev_market_state_hash)
        else:
            prev_market_state_hash = None

        prev_selection = None
        prev_selection_hash = settlement_payload.get("selection_receipt_hash")
        if prev_selection_hash is not None:
            prev_selection = _verify_hash_binding(
                find_by_hash(state_root / "market" / "selection", "bid_selection_receipt_v1.json", str(prev_selection_hash)),
                str(prev_selection_hash),
                "bid_selection_receipt_v1",
            )
            prev_selection_hash = str(prev_selection_hash)
        else:
            prev_selection_hash = None

        expected_settlement, expected_market_state = settle_and_advance_market_state(
            tick_u64=int(state_payload.get("tick_u64", 0)),
            config_hash=bid_market_cfg_hash,
            registry_hash=registry_hash,
            cfg=bid_market_cfg,
            registry=registry,
            objectives=objectives,
            prev_market_state=prev_market_state,
            prev_market_state_hash=prev_market_state_hash,
            prev_selection_receipt=prev_selection,
            prev_selection_hash=prev_selection_hash,
            prev_observation_report=prev_observation_full,
            prev_observation_hash=prev_observation_full_hash,
            cur_observation_report=obs_payload,
            cur_observation_hash=str(snapshot.get("observation_report_hash")),
        )
        if canon_hash_obj(expected_settlement) != canon_hash_obj(settlement_payload):
            fail("NONDETERMINISTIC")
        if canon_hash_obj(expected_market_state) != canon_hash_obj(market_state_payload):
            fail("NONDETERMINISTIC")

        # Recompute bid emission and set aggregation.
        market_state_map = {
            str(row.get("campaign_id")): row
            for row in (market_state_payload.get("campaign_states") or [])
            if isinstance(row, dict) and str(row.get("campaign_id", "")).strip()
        }
        caps = registry.get("capabilities")
        if not isinstance(caps, list):
            fail("SCHEMA_FAIL")
        expected_bids: dict[str, dict[str, Any]] = {}
        expected_bid_hash_by_campaign: dict[str, str] = {}
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
                tick_u64=int(state_payload.get("tick_u64", 0)),
                campaign_id=campaign_id,
                capability_id=str(cap.get("capability_id", "")).strip(),
                observation_report_hash=str(snapshot.get("observation_report_hash")),
                market_state_hash=str(snap_state_hash),
                config_hash=bid_market_cfg_hash,
                registry_hash=registry_hash,
                roi_q32=roi_q32,
                confidence_q32=conf_q32,
                horizon_ticks_u64=horizon_u64,
                predicted_cost_q32=cost_q32,
            )
            expected_bids[campaign_id] = bid
            expected_bid_hash_by_campaign[campaign_id] = canon_hash_obj(bid)

        expected_bid_set = build_bid_set_v1(
            tick_u64=int(state_payload.get("tick_u64", 0)),
            observation_report_hash=str(snapshot.get("observation_report_hash")),
            market_state_hash=str(snap_state_hash),
            config_hash=bid_market_cfg_hash,
            registry_hash=registry_hash,
            bids_by_campaign=expected_bid_hash_by_campaign,
        )
        if canon_hash_obj(expected_bid_set) != canon_hash_obj(bid_set_payload):
            fail("NONDETERMINISTIC")
        for cid, expected_hash in expected_bid_hash_by_campaign.items():
            got = bids_by_campaign.get(cid)
            if got is None or canon_hash_obj(got) != expected_hash:
                fail("NONDETERMINISTIC")

        expected_selection = select_winner(
            tick_u64=int(state_payload.get("tick_u64", 0)),
            observation_report_hash=str(snapshot.get("observation_report_hash")),
            market_state=market_state_payload,
            market_state_hash=str(snap_state_hash),
            config_hash=bid_market_cfg_hash,
            registry_hash=registry_hash,
            bid_set_hash=str(snap_bid_set_hash),
            bids=expected_bids,
            prev_state=prev_state_payload,
        )
        if canon_hash_obj(expected_selection) != canon_hash_obj(selection_payload):
            fail("NONDETERMINISTIC")

        expected_decision = build_decision_plan_from_selection(
            tick_u64=int(state_payload.get("tick_u64", 0)),
            observation_report_hash=str(snapshot.get("observation_report_hash")),
            issue_bundle_hash=str(snapshot.get("issue_bundle_hash")),
            policy_hash=policy_hash,
            registry_hash=registry_hash,
            budgets_hash=budgets_hash,
            registry=registry,
            selection_receipt=selection_payload,
        )
        if canon_hash_obj(expected_decision) != canon_hash_obj(decision_payload):
            fail("NONDETERMINISTIC")
        # Downstream verifier checks (e.g. runaway env bindings) refer to the
        # recomputed decision plan in both market/non-market modes.
        recomputed_decision = expected_decision

    if runaway_enabled(runaway_cfg):
        if current_runaway_payload is None or prev_runaway_payload is None:
            fail("MISSING_STATE_INPUT")
        if str(prev_runaway_payload.get("objective_set_hash")) != objectives_hash:
            fail("OBJECTIVE_SET_HASH_MISMATCH")
        action_kind = str(decision_payload.get("action_kind"))
        if action_kind in {"RUN_CAMPAIGN", "RUN_GOAL_TASK"}:
            if dispatch_payload is None:
                fail("MISSING_STATE_INPUT")
            invocation = dispatch_payload.get("invocation")
            if not isinstance(invocation, dict):
                fail("SCHEMA_FAIL")
            got_env = invocation.get("env_overrides")
            if not isinstance(got_env, dict):
                fail("NONDETERMINISTIC")
            expected_env = recomputed_decision.get("runaway_env_overrides")
            # Goal-mode dispatches can occur even when runaway config is present but the
            # runaway condition is inactive (for example via an explicit env gate used
            # for acceptance runs). In that case the decision plan intentionally omits
            # runaway env overrides, and dispatch should run with no overrides.
            if expected_env is None:
                expected_env = {}
            if not isinstance(expected_env, dict):
                fail("NONDETERMINISTIC")
            if {str(k): str(v) for k, v in got_env.items()} != {str(k): str(v) for k, v in expected_env.items()}:
                fail("NONDETERMINISTIC")

        promoted_and_activated = (
            not safe_halt
            and str((promotion_payload or {}).get("result", {}).get("status")) == "PROMOTED"
            and bool((activation_payload or {}).get("activation_success", False))
            and (
                str((activation_payload or {}).get("before_active_manifest_hash", ""))
                != str((activation_payload or {}).get("after_active_manifest_hash", ""))
            )
        )
        expected_next_runaway = advance_runaway_state(
            prev_state=prev_runaway_payload,
            observation_report=obs_payload,
            decision_plan=decision_payload,
            runaway_cfg=runaway_cfg,
            objectives=objectives,
            tick_u64=int(state_payload.get("tick_u64", 0)),
            promoted_and_activated=promoted_and_activated,
            subverifier_invalid_stall=subverifier_invalid_stall,
        )
        if canon_hash_obj(expected_next_runaway) != canon_hash_obj(current_runaway_payload):
            fail("NONDETERMINISTIC")

    if activation_payload is not None and promotion_payload is None:
        fail("ACTIVATION_REQUIRES_PROMOTION")

    if dispatch_occurred:
        if subverifier_payload is None:
            fail("SUBVERIFIER_REQUIRED")
        if subverifier_status not in {"VALID", "INVALID"}:
            fail("SCHEMA_FAIL")
        if subverifier_status == "INVALID":
            if (
                not isinstance(subverifier_reason, str)
                or not subverifier_reason.strip()
                or subverifier_reason not in _SUBVERIFIER_REASON_CODES
            ):
                fail("SCHEMA_FAIL")

    promotion_reason = (promotion_payload or {}).get("result", {}).get("reason_code")
    if promotion_payload is not None:
        if subverifier_payload is None:
            fail("SUBVERIFIER_REQUIRED")
        if subverifier_status == "INVALID":
            if promotion_status not in {"REJECTED", "SKIPPED"} or str(promotion_reason) != "SUBVERIFIER_INVALID":
                fail("PROMOTION_INCONSISTENT_WITH_SUBVERIFIER")
        elif subverifier_status == "VALID":
            if promotion_status not in {"PROMOTED", "REJECTED", "SKIPPED"}:
                fail("SCHEMA_FAIL")
        else:
            fail("SCHEMA_FAIL")

    meta_core_promo_payload = None
    if promotion_payload is not None and promotion_status == "PROMOTED":
        if subverifier_status != "VALID":
            fail("SUBVERIFIER_REQUIRED")
        _replay_promoted_subverifier(
            state_root=state_root,
            dispatch_payload=dispatch_payload,
            subverifier_payload=subverifier_payload,
        )
        if promotion_path is None:
            fail("DOWNSTREAM_META_CORE_FAIL")
        promo_dir = promotion_path.parent
        tick_binding_path = promo_dir / "omega_activation_binding_v1.json"
        if not tick_binding_path.exists() or not tick_binding_path.is_file():
            fail("BINDING_MISSING_OR_MISMATCH")
        tick_binding_payload = load_canon_dict(tick_binding_path)
        validate_schema(tick_binding_payload, "omega_activation_binding_v1")
        tick_binding_id = _binding_id(tick_binding_payload)

        plain_receipt = promo_dir / "meta_core_promo_verify_receipt_v1.json"
        if not plain_receipt.exists():
            fail("DOWNSTREAM_META_CORE_FAIL")
        meta_receipt_path = collect_single(
            promo_dir,
            "sha256_*.meta_core_promo_verify_receipt_v1.json",
            reason="DOWNSTREAM_META_CORE_FAIL",
        )
        meta_core_promo_payload = _verify_hash_binding(
            meta_receipt_path,
            _hash_from_hashed_filename(meta_receipt_path),
            "meta_core_promo_verify_receipt_v1",
        )
        if not bool(meta_core_promo_payload.get("pass")):
            fail("DOWNSTREAM_META_CORE_FAIL")
        if activation_payload is None:
            fail("DOWNSTREAM_META_CORE_FAIL")
        if not bool(activation_payload.get("activation_success", False)):
            fail("DOWNSTREAM_META_CORE_FAIL")
        if activation_payload.get("before_active_manifest_hash") == activation_payload.get("after_active_manifest_hash"):
            fail("ACTIVATION_NO_MANIFEST_CHANGE")

        after_hash = str(activation_payload.get("after_active_manifest_hash", ""))
        if not after_hash.startswith("sha256:"):
            fail("BINDING_MISSING_OR_MISMATCH")
        after_hex = after_hash.split(":", 1)[1]
        if len(after_hex) != 64:
            fail("BINDING_MISSING_OR_MISMATCH")
        active_binding_path = _meta_core_root() / "store" / "bundles" / after_hex / "omega" / "omega_activation_binding_v1.json"
        if not active_binding_path.exists() or not active_binding_path.is_file():
            # Simulated activation does not mutate meta-core pointer/store; verify against tick-local activation bundle.
            active_binding_path = promo_dir / "meta_core_activation_bundle_v1" / "omega" / "omega_activation_binding_v1.json"
            if not active_binding_path.exists() or not active_binding_path.is_file():
                fail("BINDING_MISSING_OR_MISMATCH")
        active_binding_payload = load_canon_dict(active_binding_path)
        validate_schema(active_binding_payload, "omega_activation_binding_v1")
        if _binding_id(active_binding_payload) != tick_binding_id:
            fail("BINDING_MISSING_OR_MISMATCH")
        if canon_hash_obj(active_binding_payload) != canon_hash_obj(tick_binding_payload):
            fail("BINDING_MISSING_OR_MISMATCH")

    if promotion_payload is not None and promotion_status in {"REJECTED", "SKIPPED"}:
        if activation_payload is not None:
            fail("ACTIVATION_REQUIRES_PROMOTION")
        if promotion_path is None:
            fail("MISSING_STATE_INPUT")
        promo_dir = promotion_path.parent
        if (promo_dir / "meta_core_promo_verify_receipt_v1.json").exists():
            fail("PROMOTION_INCONSISTENT_WITH_SUBVERIFIER")
        if any(promo_dir.glob("sha256_*.meta_core_promo_verify_receipt_v1.json")):
            fail("PROMOTION_INCONSISTENT_WITH_SUBVERIFIER")

    if activation_payload is not None and bool(activation_payload.get("activation_success", False)):
        if activation_payload.get("before_active_manifest_hash") == activation_payload.get("after_active_manifest_hash"):
            fail("ACTIVATION_NO_MANIFEST_CHANGE")

    if promotion_payload is not None and promotion_path is not None:
        bundle_hash = str(promotion_payload.get("promotion_bundle_hash", "")).strip()
        if bundle_hash.startswith("sha256:") and len(bundle_hash.split(":", 1)[1]) == 64:
            bundle_hex = bundle_hash.split(":", 1)[1]
            bundle_paths = sorted(state_root.glob(f"subruns/**/sha256_{bundle_hex}.*.json"))
            if bundle_paths:
                bundle_payload, _ = load_bundle(bundle_paths[0])
                touched_paths = extract_touched_paths(bundle_payload)
                campaign_id = str((dispatch_payload or {}).get("campaign_id", "")).strip()
                load_test_plan_receipt(
                    promotion_dir=bundle_paths[0].parent,
                    touched_paths=touched_paths,
                    required=campaign_requires_test_plan_receipt(campaign_id),
                )

    _verify_forbidden_paths(state_root=state_root, promotion_receipt=promotion_payload, allowlists=allowlists)

    artifact_hashes = trace_payload.get("artifact_hashes")
    if not isinstance(artifact_hashes, list):
        fail("TRACE_HASH_MISMATCH")
    recomputed_head = recompute_head(str(trace_payload.get("H0")), [str(x) for x in artifact_hashes])
    if recomputed_head != trace_payload.get("H_final"):
        fail("TRACE_HASH_MISMATCH")

    for payload in [
        obs_payload,
        issue_payload,
        decision_payload,
        prev_runaway_payload,
        current_runaway_payload,
        dispatch_payload,
        subverifier_payload,
        promotion_payload,
        meta_core_promo_payload,
        activation_payload,
        rollback_payload,
    ]:
        if payload is None:
            continue
        require_no_absolute_paths(payload)

    return "VALID"


def main() -> None:
    parser = argparse.ArgumentParser(prog="verify_rsi_omega_daemon_v1")
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
