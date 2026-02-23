"""Deterministic observer for omega daemon v18.0."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from .omega_common_v1 import (
    OmegaV18Error,
    Q32_ONE,
    canon_hash_obj,
    fail,
    hash_file_stream,
    load_jsonl,
    load_canon_dict,
    rat_q32,
    repo_root,
    require_relpath,
    validate_schema,
)
from .hard_task_suite_v1 import (
    HARD_TASK_METRIC_IDS,
    evaluate_hard_task_suite_v1,
    hard_task_metric_q32_by_id_from_suite,
)
from .omega_observer_index_v1 import load_index, maybe_update_entry, store_index

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_SCIENCE_OMEGA_MARKER = "/rsi_omega_daemon_v18_0"

_INDEX_KEY_METASEARCH = "metasearch_compute_report_v1"
_INDEX_KEY_HOTLOOP = "kernel_hotloop_report_v1"
_INDEX_KEY_BUILD = "sas_system_perf_report_v1"
_INDEX_KEY_SCIENCE = "sas_science_promotion_bundle_v1"
_INDEX_KEY_CODE = "sas_code_perf_report_v1"
_GE_CAMPAIGN_ID = "rsi_ge_symbiotic_optimizer_sh1_v0_1"
_POLYMATH_REGISTRY_REL = "polymath/registry/polymath_domain_registry_v1.json"
_POLYMATH_VOID_REPORT_REL = "polymath/registry/polymath_void_report_v1.jsonl"
_POLYMATH_SCOUT_STATUS_REL = "polymath/registry/polymath_scout_status_v1.json"
_POLYMATH_PORTFOLIO_REL = "polymath/registry/polymath_portfolio_v1.json"
_POLYMATH_STALE_AGE_U64 = (1 << 63) - 1
_CAPABILITY_FRONTIER_WINDOW_U64 = 512
_NON_CARRY_SERIES_KEYS = {
    "OBJ_EXPAND_CAPABILITIES",
    "OBJ_MAXIMIZE_SCIENCE",
    "OBJ_MAXIMIZE_SPEED",
    "cap_frontier_u64",
    "cap_enabled_u64",
    "cap_activated_u64",
}
_HARD_TASK_METRIC_IDS: tuple[str, ...] = tuple(HARD_TASK_METRIC_IDS)
_LEGACY_SKILL_SOURCES: tuple[tuple[str, str, str, str], ...] = (
    (
        "omega_skill_transfer_report_v1",
        "skills/reports/transfer/omega_skill_report_v1.json",
        "rsi_omega_skill_transfer_v1",
        "transfer_gain_q32",
    ),
    (
        "omega_skill_ontology_report_v1",
        "skills/reports/ontology/omega_skill_report_v1.json",
        "rsi_omega_skill_ontology_v1",
        "ontology_consistency_q32",
    ),
    (
        "omega_skill_eff_flywheel_report_v1",
        "skills/reports/eff_flywheel/omega_skill_report_v1.json",
        "rsi_omega_skill_eff_flywheel_v1",
        "flywheel_yield_q32",
    ),
    (
        "omega_skill_thermo_report_v1",
        "skills/reports/thermo/omega_skill_report_v1.json",
        "rsi_omega_skill_thermo_v1",
        "thermo_efficiency_q32",
    ),
    (
        "omega_skill_persistence_report_v1",
        "skills/reports/persistence/omega_skill_report_v1.json",
        "rsi_omega_skill_persistence_v1",
        "persistence_health_q32",
    ),
)


def read_meta_core_active_manifest_hash() -> str:
    active_path = repo_root() / "meta-core" / "active" / "ACTIVE_BUNDLE"
    if not active_path.exists() or not active_path.is_file():
        fail("MISSING_STATE_INPUT")
    raw = active_path.read_text(encoding="utf-8").strip()
    if _HEX64_RE.fullmatch(raw) is None:
        fail("SCHEMA_FAIL")
    return f"sha256:{raw}"


def _read_binding_for_manifest(active_manifest_hash: str) -> dict[str, Any] | None:
    if not isinstance(active_manifest_hash, str) or not active_manifest_hash.startswith("sha256:"):
        fail("SCHEMA_FAIL")
    active_hex = active_manifest_hash.split(":", 1)[1]
    if _HEX64_RE.fullmatch(active_hex) is None:
        fail("SCHEMA_FAIL")
    binding_path = repo_root() / "meta-core" / "store" / "bundles" / active_hex / "omega" / "omega_activation_binding_v1.json"
    if not binding_path.exists() or not binding_path.is_file():
        return None
    payload = load_canon_dict(binding_path)
    validate_schema(payload, "omega_activation_binding_v1")
    return payload


def _sorted_unique(paths: Iterable[Path]) -> list[Path]:
    return sorted(set(paths), key=lambda path: path.as_posix())


def _expand_preferred(preferred: list[Path]) -> list[Path]:
    rows: list[Path] = []
    for path in preferred:
        if "*" in path.name:
            rows.extend(sorted(path.parent.glob(path.name)))
        elif path.exists():
            rows.append(path)
    return _sorted_unique(rows)


def _prefix_scan(*, root: Path, run_prefixes: tuple[str, ...], run_rel_globs: list[str]) -> list[Path]:
    runs_root = root / "runs"
    if not runs_root.exists() or not runs_root.is_dir():
        return []
    rows: list[Path] = []
    for run_dir in sorted(runs_root.iterdir(), key=lambda path: path.name):
        if not run_dir.is_dir():
            continue
        name = run_dir.name
        if not any(name.startswith(prefix) for prefix in run_prefixes):
            continue
        for rel_glob in run_rel_globs:
            rows.extend(sorted(run_dir.glob(rel_glob)))
    return _sorted_unique(rows)


def _select_latest(rows: list[Path], *, prefer_non_omega: bool = False) -> Path | None:
    candidates = _sorted_unique(rows)
    if prefer_non_omega:
        preferred = [row for row in candidates if _SCIENCE_OMEGA_MARKER not in row.as_posix()]
        if preferred:
            candidates = preferred
    if not candidates:
        return None
    return candidates[-1]


def _path_to_runs_rel(root: Path, path: Path) -> str | None:
    try:
        path_rel = path.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return None
    try:
        path_rel = require_relpath(path_rel)
    except Exception:
        return None
    if not path_rel.startswith("runs/"):
        return None
    return path_rel


def _cached_index_path(*, root: Path, index: dict[str, Any], key: str) -> Path | None:
    entries = index.get("entries")
    if not isinstance(entries, dict):
        return None
    row = entries.get(key)
    if not isinstance(row, dict):
        return None
    path_rel_raw = row.get("path_rel")
    try:
        path_rel = require_relpath(path_rel_raw)
    except Exception:
        return None
    if not path_rel.startswith("runs/"):
        return None
    candidate = root / path_rel
    if not candidate.exists() or not candidate.is_file():
        return None
    return candidate


def _maybe_cache_path(*, root: Path, index: dict[str, Any], key: str, path: Path) -> None:
    path_rel = _path_to_runs_rel(root, path)
    if path_rel is None:
        return
    try:
        if maybe_update_entry(index, key, path_rel):
            store_index(root, index)
    except Exception:
        return


def _resolve_artifact_path(
    *,
    root: Path,
    index: dict[str, Any],
    index_key: str,
    preferred_paths: list[Path],
    run_prefixes: tuple[str, ...],
    run_rel_globs: list[str],
    prefer_non_omega: bool = False,
) -> Path:
    cached = _cached_index_path(root=root, index=index, key=index_key)
    if cached is not None:
        return cached

    local_rows = _expand_preferred(preferred_paths)
    candidate = _select_latest(local_rows, prefer_non_omega=prefer_non_omega)
    if candidate is None:
        fallback_rows = _prefix_scan(root=root, run_prefixes=run_prefixes, run_rel_globs=run_rel_globs)
        candidate = _select_latest(fallback_rows, prefer_non_omega=prefer_non_omega)
    if candidate is None:
        fail("MISSING_STATE_INPUT")

    _maybe_cache_path(root=root, index=index, key=index_key, path=candidate)
    return candidate


def _source(schema_id: str, path: Path, campaign_id: str) -> dict[str, str]:
    payload = load_canon_dict(path)
    artifact_hash = canon_hash_obj(payload)
    return {
        "schema_id": schema_id,
        "artifact_hash": artifact_hash,
        "producer_campaign_id": campaign_id,
        "producer_run_id": artifact_hash,
    }


def _fallback_source(*, schema_id: str, campaign_id: str, reason_code: str) -> dict[str, str]:
    payload = {
        "schema_id": str(schema_id),
        "campaign_id": str(campaign_id),
        "reason_code": str(reason_code),
    }
    return {
        "schema_id": str(schema_id),
        "artifact_hash": canon_hash_obj(payload),
        "producer_campaign_id": str(campaign_id),
        "producer_run_id": "observer_fallback",
    }


def _load_metasearch_metric(*, root: Path, index: dict[str, Any]) -> tuple[int, dict[str, str]]:
    try:
        report_path = _resolve_artifact_path(
            root=root,
            index=index,
            index_key=_INDEX_KEY_METASEARCH,
            preferred_paths=[
                root
                / "runs"
                / "rsi_sas_metasearch_v16_1_tick_0001"
                / "daemon"
                / "rsi_sas_metasearch_v16_1"
                / "state"
                / "reports"
                / "*.metasearch_compute_report_v1.json",
            ],
            run_prefixes=("rsi_sas_metasearch_v16_1",),
            run_rel_globs=[
                "daemon/rsi_sas_metasearch_v16_1/state/reports/*.metasearch_compute_report_v1.json",
            ],
        )
    except OmegaV18Error as exc:
        if str(exc) != "INVALID:MISSING_STATE_INPUT":
            raise
        return (
            int(Q32_ONE),
            _fallback_source(
                schema_id="metasearch_compute_report_v1",
                campaign_id="rsi_sas_metasearch_v16_1",
                reason_code="MISSING_STATE_INPUT",
            ),
        )
    report = load_canon_dict(report_path)
    base = int(report.get("c_base_work_cost_total", 0))
    cand = int(report.get("c_cand_work_cost_total", 0))
    if base <= 0 or cand < 0:
        fail("SCHEMA_FAIL")
    ratio_q = rat_q32(base, cand if cand > 0 else 1)
    return ratio_q, _source("metasearch_compute_report_v1", report_path, "rsi_sas_metasearch_v16_1")


def _load_hotloop_metric(*, root: Path, index: dict[str, Any]) -> tuple[int, dict[str, str]]:
    try:
        report_path = _resolve_artifact_path(
            root=root,
            index=index,
            index_key=_INDEX_KEY_HOTLOOP,
            preferred_paths=[
                root
                / "runs"
                / "rsi_sas_val_v17_0_tick_0001"
                / "daemon"
                / "rsi_sas_val_v17_0"
                / "state"
                / "hotloop"
                / "*.kernel_hotloop_report_v1.json",
            ],
            run_prefixes=("rsi_sas_val_v17_0",),
            run_rel_globs=[
                "daemon/rsi_sas_val_v17_0/state/hotloop/*.kernel_hotloop_report_v1.json",
            ],
        )
    except OmegaV18Error as exc:
        if str(exc) != "INVALID:MISSING_STATE_INPUT":
            raise
        return (
            0,
            _fallback_source(
                schema_id="kernel_hotloop_report_v1",
                campaign_id="rsi_sas_val_v17_0",
                reason_code="MISSING_STATE_INPUT",
            ),
        )
    report = load_canon_dict(report_path)
    loops = report.get("top_loops")
    if not isinstance(loops, list) or not loops:
        fail("SCHEMA_FAIL")
    bytes_rows: list[int] = []
    for row in loops:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        bytes_rows.append(int(row.get("bytes", 0)))
    total = sum(max(0, x) for x in bytes_rows)
    top = max(0, bytes_rows[0])
    share_q = rat_q32(top, total if total > 0 else 1)
    return share_q, _source("kernel_hotloop_report_v1", report_path, "rsi_sas_val_v17_0")


def _load_build_metric(*, root: Path, index: dict[str, Any]) -> tuple[int, dict[str, str]]:
    try:
        report_path = _resolve_artifact_path(
            root=root,
            index=index,
            index_key=_INDEX_KEY_BUILD,
            preferred_paths=[
                root
                / "runs"
                / "rsi_sas_system_v14_0_tick_0001"
                / "daemon"
                / "rsi_sas_system_v14_0"
                / "state"
                / "artifacts"
                / "*.sas_system_perf_report_v1.json",
            ],
            run_prefixes=("rsi_sas_system_v14_0",),
            run_rel_globs=[
                "daemon/rsi_sas_system_v14_0/state/artifacts/*.sas_system_perf_report_v1.json",
            ],
        )
    except OmegaV18Error as exc:
        if str(exc) != "INVALID:MISSING_STATE_INPUT":
            raise
        return (
            0,
            _fallback_source(
                schema_id="sas_system_perf_report_v1",
                campaign_id="rsi_sas_system_v14_0",
                reason_code="MISSING_STATE_INPUT",
            ),
        )
    report = load_canon_dict(report_path)
    cand = int(report.get("cand_cost_total", 0))
    ref = int(report.get("ref_cost_total", 0))
    if ref <= 0 or cand < 0:
        fail("SCHEMA_FAIL")
    frac_q = rat_q32(cand, ref)
    return frac_q, _source("sas_system_perf_report_v1", report_path, "rsi_sas_system_v14_0")


def _science_q_from_bundle(bundle: dict[str, Any]) -> int:
    discovery = bundle.get("discovery_bundle")
    if not isinstance(discovery, dict):
        fail("SCHEMA_FAIL")
    heldout = discovery.get("heldout_metrics")
    if not isinstance(heldout, dict):
        fail("SCHEMA_FAIL")
    rmse_obj = heldout.get("rmse_pos1_q32")
    if not isinstance(rmse_obj, dict):
        fail("SCHEMA_FAIL")
    q_raw = rmse_obj.get("q")
    try:
        return int(q_raw)
    except Exception:  # noqa: BLE001
        fail("SCHEMA_FAIL")
    return 0


def _science_bundle_rows(base: Path) -> list[Path]:
    rows: list[Path] = []
    rows.extend(sorted(base.glob("daemon/rsi_sas_science_v13_0/state/promotion/*.sas_science_promotion_bundle_v1.json")))
    rows.extend(
        sorted(
            base.glob(
                "daemon/rsi_omega_daemon_v18_0/state/subruns/*/daemon/rsi_sas_science_v13_0/state/promotion/*.sas_science_promotion_bundle_v1.json"
            )
        )
    )
    rows.extend(
        sorted(
            base.glob(
                "daemon/rsi_omega_daemon_v18_0/state/subruns/*/rsi_sas_science_v13_0*/state/promotion/*.sas_science_promotion_bundle_v1.json"
            )
        )
    )
    # Compatibility fallback for legacy v13 run layout under runs/<run>/state/.
    rows.extend(sorted(base.glob("rsi_sas_science_v13_0*/state/promotion/*.sas_science_promotion_bundle_v1.json")))
    return _sorted_unique(rows)


def _load_science_metric_global(
    *,
    root: Path | None = None,
    index: dict[str, Any] | None = None,
) -> tuple[int, dict[str, str]]:
    if root is None:
        root = repo_root()
    if index is None:
        index = load_index(root)
    try:
        bundle_path = _resolve_artifact_path(
            root=root,
            index=index,
            index_key=_INDEX_KEY_SCIENCE,
            preferred_paths=[
                root
                / "runs"
                / "rsi_sas_science_v13_0_tick_0001"
                / "daemon"
                / "rsi_sas_science_v13_0"
                / "state"
                / "promotion"
                / "*.sas_science_promotion_bundle_v1.json",
            ],
            run_prefixes=("rsi_sas_science_v13_0",),
            run_rel_globs=[
                "daemon/rsi_sas_science_v13_0/state/promotion/*.sas_science_promotion_bundle_v1.json",
                "rsi_sas_science_v13_0*/state/promotion/*.sas_science_promotion_bundle_v1.json",
            ],
            prefer_non_omega=True,
        )
    except OmegaV18Error as exc:
        if str(exc) != "INVALID:MISSING_STATE_INPUT":
            raise
        return (
            0,
            _fallback_source(
                schema_id="sas_science_promotion_bundle_v1",
                campaign_id="rsi_sas_science_v13_0",
                reason_code="MISSING_STATE_INPUT",
            ),
        )
    bundle = load_canon_dict(bundle_path)
    science_q = _science_q_from_bundle(bundle)
    return science_q, _source("sas_science_promotion_bundle_v1", bundle_path, "rsi_sas_science_v13_0")


def _load_science_metric(
    *,
    active_binding: dict[str, Any] | None,
    allow_unbound_fallback: bool,
    root: Path,
    index: dict[str, Any],
) -> tuple[int, dict[str, str]]:
    _ = allow_unbound_fallback
    if active_binding is None:
        return _load_science_metric_global(root=root, index=index)

    source_run_root_rel = require_relpath(active_binding.get("source_run_root_rel"))
    run_root = root / "runs" / source_run_root_rel
    if run_root.exists() and run_root.is_dir():
        rows = _science_bundle_rows(run_root)
        bundle_path = _select_latest(rows, prefer_non_omega=True)
        if bundle_path is not None:
            _maybe_cache_path(root=root, index=index, key=_INDEX_KEY_SCIENCE, path=bundle_path)
            bundle = load_canon_dict(bundle_path)
            science_q = _science_q_from_bundle(bundle)
            return science_q, _source("sas_science_promotion_bundle_v1", bundle_path, "rsi_sas_science_v13_0")

    # If the bound run does not expose a science promotion artifact, use stable global science history.
    return _load_science_metric_global(root=root, index=index)


def _rate_from_stats(payload: dict[str, Any], key: str) -> dict[str, int]:
    value = payload.get(key)
    if not isinstance(value, dict):
        fail("SCHEMA_FAIL")
    num_u64 = max(0, int(value.get("num_u64", 0)))
    den_u64 = max(1, int(value.get("den_u64", 1)))
    return {"num_u64": num_u64, "den_u64": den_u64}


def _recent_runaway_blocked_streak_u64(payload: dict[str, Any]) -> int:
    rows = payload.get("recent_noop_reasons")
    if not isinstance(rows, list):
        fail("SCHEMA_FAIL")
    streak = 0
    for row in reversed(rows):
        if str(row) == "RUNAWAY_BLOCKED":
            streak += 1
        else:
            break
        if streak >= 3:
            return 3
    return streak


def _polymath_source(
    *,
    schema_id: str,
    artifact_hash: str,
    producer_campaign_id: str = "rsi_polymath_scout_v1",
) -> dict[str, str]:
    return {
        "schema_id": schema_id,
        "artifact_hash": artifact_hash,
        "producer_campaign_id": producer_campaign_id,
        "producer_run_id": artifact_hash,
    }


def _load_polymath_metrics(*, root: Path, tick_u64: int) -> tuple[dict[str, Any], list[dict[str, str]]]:
    metrics: dict[str, Any] = {
        "domain_coverage_ratio": {"q": 0},
        "top_void_score_q32": {"q": 0},
        "domains_bootstrapped_u64": 0,
        "domains_blocked_license_u64": 0,
        "domains_blocked_policy_u64": 0,
        "domains_blocked_size_u64": 0,
        "domains_ready_for_conquer_u64": 0,
        "polymath_last_scout_tick_u64": 0,
        "polymath_scout_age_ticks_u64": int(_POLYMATH_STALE_AGE_U64),
        "polymath_portfolio_score_q32": {"q": 0},
        "polymath_portfolio_domains_u64": 0,
        "polymath_portfolio_cache_hit_rate_q32": {"q": 0},
    }
    sources: list[dict[str, str]] = []

    registry_path = root / _POLYMATH_REGISTRY_REL
    if registry_path.exists() and registry_path.is_file():
        registry = load_canon_dict(registry_path)
        validate_schema(registry, "polymath_domain_registry_v1")
        rows = registry.get("domains")
        if not isinstance(rows, list):
            fail("SCHEMA_FAIL")

        active_u64 = 0
        blocked_license_u64 = 0
        blocked_policy_u64 = 0
        blocked_size_u64 = 0
        ready_for_conquer_u64 = 0
        for row in rows:
            if not isinstance(row, dict):
                fail("SCHEMA_FAIL")
            status = str(row.get("status", "")).strip()
            if status == "ACTIVE":
                active_u64 += 1
                if bool(row.get("ready_for_conquer", False)) and not bool(row.get("conquered_b", False)):
                    ready_for_conquer_u64 += 1
            elif status == "BLOCKED_LICENSE":
                blocked_license_u64 += 1
            elif status == "BLOCKED_POLICY":
                blocked_policy_u64 += 1
            elif status == "BLOCKED_SIZE":
                blocked_size_u64 += 1

        metrics["domains_bootstrapped_u64"] = int(active_u64)
        metrics["domains_blocked_license_u64"] = int(blocked_license_u64)
        metrics["domains_blocked_policy_u64"] = int(blocked_policy_u64)
        metrics["domains_blocked_size_u64"] = int(blocked_size_u64)
        metrics["domains_ready_for_conquer_u64"] = int(ready_for_conquer_u64)
        sources.append(
            _polymath_source(
                schema_id="polymath_domain_registry_v1",
                artifact_hash=canon_hash_obj(registry),
            )
        )

    void_path = root / _POLYMATH_VOID_REPORT_REL
    if void_path.exists() and void_path.is_file():
        rows = load_jsonl(void_path)
        top_void_q = 0
        topics: set[str] = set()
        for row in rows:
            if str(row.get("schema_version", "")) != "polymath_void_report_v1":
                fail("SCHEMA_FAIL")
            validate_schema(row, "polymath_void_report_v1")
            topic_id = str(row.get("topic_id", "")).strip()
            if topic_id:
                topics.add(topic_id)
            void_obj = row.get("void_score_q32")
            if isinstance(void_obj, dict):
                top_void_q = max(top_void_q, int(void_obj.get("q", 0)))

        den = max(1, len(topics))
        active = int(metrics["domains_bootstrapped_u64"])
        metrics["domain_coverage_ratio"] = {"q": rat_q32(min(active, den), den)}
        metrics["top_void_score_q32"] = {"q": int(top_void_q)}
        sources.append(
            _polymath_source(
                schema_id="polymath_void_report_v1",
                artifact_hash=hash_file_stream(void_path),
            )
        )

    status_path = root / _POLYMATH_SCOUT_STATUS_REL
    if status_path.exists() and status_path.is_file():
        status = load_canon_dict(status_path)
        validate_schema(status, "polymath_scout_status_v1")
        last_tick = max(0, int(status.get("tick_u64", 0)))
        if last_tick > int(tick_u64):
            fail("SCHEMA_FAIL")
        metrics["polymath_last_scout_tick_u64"] = int(last_tick)
        metrics["polymath_scout_age_ticks_u64"] = int(max(0, int(tick_u64) - int(last_tick)))
        sources.append(
            _polymath_source(
                schema_id="polymath_scout_status_v1",
                artifact_hash=canon_hash_obj(status),
            )
        )

    portfolio_path = root / _POLYMATH_PORTFOLIO_REL
    if portfolio_path.exists() and portfolio_path.is_file():
        portfolio = load_canon_dict(portfolio_path)
        validate_schema(portfolio, "polymath_portfolio_v1")
        score_obj = portfolio.get("portfolio_score_q32")
        if isinstance(score_obj, dict):
            metrics["polymath_portfolio_score_q32"] = {"q": int(score_obj.get("q", 0))}
        domains_rows = portfolio.get("domains")
        if isinstance(domains_rows, list):
            rows = [row for row in domains_rows if isinstance(row, dict)]
            metrics["polymath_portfolio_domains_u64"] = int(len(rows))
            if rows:
                cache_mean = sum(int(row.get("cache_hit_rate_q32", 0)) for row in rows) // len(rows)
            else:
                cache_mean = 0
            metrics["polymath_portfolio_cache_hit_rate_q32"] = {"q": int(cache_mean)}
        sources.append(
            _polymath_source(
                schema_id="polymath_portfolio_v1",
                artifact_hash=canon_hash_obj(portfolio),
                producer_campaign_id="rsi_polymath_conquer_domain_v1",
            )
        )

    return metrics, sources


def _ge_stps_delta_q32(receipt: dict[str, Any]) -> int:
    delta = receipt.get("score_delta_summary")
    if isinstance(delta, dict):
        return int(delta.get("median_stps_non_noop_q32", 0))
    base = receipt.get("score_base_summary")
    cand = receipt.get("score_cand_summary")
    if isinstance(base, dict) and isinstance(cand, dict):
        return int(cand.get("median_stps_non_noop_q32", 0)) - int(base.get("median_stps_non_noop_q32", 0))
    return 0


def _load_ge_metrics(*, root: Path) -> tuple[dict[str, Any], list[dict[str, str]]]:
    metrics = {
        "ge_promote_rate_rat": {"num_u64": 0, "den_u64": 1},
        "ge_mean_stps_delta_q32": {"q": 0},
    }
    runs_root = root / "runs"
    if not runs_root.exists() or not runs_root.is_dir():
        return metrics, []

    records_by_ccap_id: dict[str, dict[str, Any]] = {}
    pattern = "*/daemon/rsi_omega_daemon_v18_0/state/dispatch/*/verifier/*.ccap_receipt_v1.json"
    for path in sorted(runs_root.glob(pattern), key=lambda row: row.as_posix()):
        if not path.exists() or not path.is_file():
            continue
        try:
            receipt = load_canon_dict(path)
            validate_schema(receipt, "ccap_receipt_v1")
        except Exception:  # noqa: BLE001
            continue
        ccap_id = str(receipt.get("ccap_id", "")).strip()
        if not ccap_id.startswith("sha256:"):
            continue

        dispatch_dir = path.parent.parent
        dispatch_receipts = sorted(dispatch_dir.glob("*.omega_dispatch_receipt_v1.json"), key=lambda row: row.as_posix())
        ge_dispatch_payload: dict[str, Any] | None = None
        for dispatch_path in dispatch_receipts:
            try:
                dispatch_payload = load_canon_dict(dispatch_path)
            except Exception:  # noqa: BLE001
                continue
            if str(dispatch_payload.get("campaign_id", "")).strip() == _GE_CAMPAIGN_ID:
                ge_dispatch_payload = dispatch_payload
                break
        if ge_dispatch_payload is None:
            continue

        tick_u64 = int(ge_dispatch_payload.get("tick_u64", 0))
        record = {
            "tick_u64": tick_u64,
            "path": path,
            "receipt": receipt,
            "artifact_hash": canon_hash_obj(receipt),
            "producer_run_id": canon_hash_obj(receipt),
        }
        prev = records_by_ccap_id.get(ccap_id)
        if prev is None:
            records_by_ccap_id[ccap_id] = record
            continue
        prev_tick = int(prev.get("tick_u64", 0))
        prev_path = Path(prev.get("path")) if isinstance(prev.get("path"), Path) else Path(str(prev.get("path", "")))
        if tick_u64 > prev_tick or (tick_u64 == prev_tick and path.as_posix() > prev_path.as_posix()):
            records_by_ccap_id[ccap_id] = record

    records = sorted(
        records_by_ccap_id.values(),
        key=lambda row: (int(row.get("tick_u64", 0)), Path(row.get("path")).as_posix()),
    )[-64:]
    if not records:
        return metrics, []

    promote_u64 = 0
    stps_delta_total_q32 = 0
    for row in records:
        receipt = row.get("receipt")
        if not isinstance(receipt, dict):
            continue
        if str(receipt.get("decision", "")).strip() == "PROMOTE":
            promote_u64 += 1
        stps_delta_total_q32 += int(_ge_stps_delta_q32(receipt))

    total_u64 = len(records)
    metrics["ge_promote_rate_rat"] = {
        "num_u64": int(promote_u64),
        "den_u64": int(max(1, total_u64)),
    }
    metrics["ge_mean_stps_delta_q32"] = {
        "q": int(stps_delta_total_q32 // max(1, total_u64)),
    }
    sources: list[dict[str, str]] = []
    for row in records:
        sources.append(
            {
                "schema_id": "ccap_receipt_v1",
                "artifact_hash": str(row.get("artifact_hash", "")),
                "producer_campaign_id": _GE_CAMPAIGN_ID,
                "producer_run_id": str(row.get("producer_run_id", "")),
            }
        )
    return metrics, sources


def _load_code_metrics(*, root: Path, index: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    metrics = {
        "code_success_rate_rat": {"num_u64": 0, "den_u64": 1},
    }
    try:
        report_path = _resolve_artifact_path(
            root=root,
            index=index,
            index_key=_INDEX_KEY_CODE,
            preferred_paths=[
                root
                / "runs"
                / "rsi_sas_code_v12_0_tick_0001"
                / "daemon"
                / "rsi_sas_code_v12_0"
                / "state"
                / "eval"
                / "perf"
                / "*.sas_code_perf_report_v1.json",
            ],
            run_prefixes=("rsi_sas_code_v12_0",),
            run_rel_globs=[
                "daemon/rsi_sas_code_v12_0/state/eval/perf/*.sas_code_perf_report_v1.json",
                "rsi_sas_code_v12_0*/state/eval/perf/*.sas_code_perf_report_v1.json",
            ],
        )
    except OmegaV18Error as exc:
        if str(exc) != "INVALID:MISSING_STATE_INPUT":
            raise
        return metrics, []

    report = load_canon_dict(report_path)
    if str(report.get("schema_version", "")).strip() != _INDEX_KEY_CODE:
        fail("SCHEMA_FAIL")
    gate = report.get("gate")
    if not isinstance(gate, dict):
        fail("SCHEMA_FAIL")
    passed_u64 = 1 if bool(gate.get("passed", False)) else 0
    metrics["code_success_rate_rat"] = {
        "num_u64": int(passed_u64),
        "den_u64": 1,
    }
    sources: list[dict[str, str]] = [
        {
            "schema_id": _INDEX_KEY_CODE,
            "artifact_hash": canon_hash_obj(report),
            "producer_campaign_id": "rsi_sas_code_v12_0",
            "producer_run_id": canon_hash_obj(report),
        }
    ]
    return metrics, sources


def _load_legacy_skill_metrics(*, root: Path) -> tuple[dict[str, Any], list[dict[str, str]]]:
    metrics: dict[str, Any] = {
        "transfer_gain_q32": {"q": 0},
        "ontology_consistency_q32": {"q": 0},
        "flywheel_yield_q32": {"q": 0},
        "thermo_efficiency_q32": {"q": 0},
        "persistence_health_q32": {"q": 0},
        "persistence_flags_u64": 0,
    }
    sources: list[dict[str, str]] = []

    for schema_id, relpath, campaign_id, metric_key in _LEGACY_SKILL_SOURCES:
        report_path = root / relpath
        if not report_path.exists() or not report_path.is_file():
            continue
        report = load_canon_dict(report_path)
        validate_schema(report, "omega_skill_report_v1")
        report_metrics = report.get("metrics")
        if not isinstance(report_metrics, dict):
            fail("SCHEMA_FAIL")
        metric_obj = report_metrics.get(metric_key)
        if not isinstance(metric_obj, dict):
            fail("SCHEMA_FAIL")
        metrics[metric_key] = {"q": int(metric_obj.get("q", 0))}
        if schema_id == "omega_skill_persistence_report_v1":
            flags = report.get("flags")
            if not isinstance(flags, list):
                fail("SCHEMA_FAIL")
            metrics["persistence_flags_u64"] = int(len(flags))
        sources.append(
            {
                "schema_id": schema_id,
                "artifact_hash": canon_hash_obj(report),
                "producer_campaign_id": campaign_id,
                "producer_run_id": canon_hash_obj(report),
            }
        )

    return metrics, sources


def _count_enabled_capabilities(registry: dict[str, Any] | None) -> int:
    if not isinstance(registry, dict):
        return 0
    rows = registry.get("capabilities")
    if not isinstance(rows, list):
        return 0
    return int(sum(1 for row in rows if isinstance(row, dict) and bool(row.get("enabled", False))))


def _latest_valid_receipt(*, rows: Iterable[Path], schema_version: str) -> tuple[dict[str, Any], int] | None:
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
    registry: dict[str, Any] | None,
    window_ticks_u64: int = _CAPABILITY_FRONTIER_WINDOW_U64,
) -> dict[str, int]:
    records: list[dict[str, Any]] = []
    for dispatch_dir in sorted(root.glob("runs/*/daemon/rsi_omega_daemon_v*/state/dispatch/*"), key=lambda row: row.as_posix()):
        if not dispatch_dir.is_dir():
            continue
        dispatch_row = _latest_valid_receipt(
            rows=dispatch_dir.glob("*.omega_dispatch_receipt_v1.json"),
            schema_version="omega_dispatch_receipt_v1",
        )
        activation_row = _latest_valid_receipt(
            rows=dispatch_dir.glob("activation/*.omega_activation_receipt_v1.json"),
            schema_version="omega_activation_receipt_v1",
        )
        if dispatch_row is None or activation_row is None:
            continue

        dispatch_payload, dispatch_tick_u64 = dispatch_row
        activation_payload, activation_tick_u64 = activation_row
        capability_id = str(dispatch_payload.get("capability_id", "")).strip()
        if not capability_id:
            continue

        try:
            dispatch_rel = dispatch_dir.resolve().relative_to(root.resolve()).as_posix()
        except Exception:
            dispatch_rel = dispatch_dir.as_posix()

        before_hash = str(activation_payload.get("before_active_manifest_hash", ""))
        after_hash = str(activation_payload.get("after_active_manifest_hash", ""))
        records.append(
            {
                "tick_u64": int(max(dispatch_tick_u64, activation_tick_u64)),
                "dispatch_rel": dispatch_rel,
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
    rmse_q = max(0, min(int(science_rmse_q32), int(Q32_ONE)))
    return int(Q32_ONE - rmse_q)


def _maximize_speed_q32(previous_tick_total_ns_u64: int) -> int:
    total_ns = int(previous_tick_total_ns_u64)
    if total_ns <= 0:
        return 0
    return int(rat_q32(1_000_000_000, total_ns))


def _metric_q32(metrics: dict[str, Any], metric_id: str) -> int:
    raw = metrics.get(metric_id)
    if not isinstance(raw, dict):
        return 0
    if set(raw.keys()) != {"q"}:
        return 0
    return max(0, int(raw.get("q", 0)))


def observe(
    *,
    tick_u64: int,
    active_manifest_hash: str,
    policy_hash: str,
    registry_hash: str,
    objectives_hash: str,
    allow_unbound_fallback: bool = False,
    previous_tick_perf: dict[str, Any] | None = None,
    previous_tick_perf_source: dict[str, str] | None = None,
    previous_tick_stats: dict[str, Any] | None = None,
    previous_tick_stats_source: dict[str, str] | None = None,
    previous_run_scorecard: dict[str, Any] | None = None,
    previous_run_scorecard_source: dict[str, str] | None = None,
    previous_observation_report: dict[str, Any] | None = None,
    registry: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    root = repo_root()
    index = load_index(root)
    metasearch_q, src_meta = _load_metasearch_metric(root=root, index=index)
    hotloop_q, src_hotloop = _load_hotloop_metric(root=root, index=index)
    build_q, src_build = _load_build_metric(root=root, index=index)
    active_binding = _read_binding_for_manifest(active_manifest_hash)
    science_q, src_science = _load_science_metric(
        active_binding=active_binding,
        allow_unbound_fallback=bool(allow_unbound_fallback),
        root=root,
        index=index,
    )
    has_prev_perf_source = (
        isinstance(previous_tick_perf_source, dict)
        and all(
            str(previous_tick_perf_source.get(key, ""))
            for key in ("schema_id", "artifact_hash", "producer_campaign_id", "producer_run_id")
        )
    )
    previous_tick_total_ns_u64 = 0
    verifier_overhead_q32 = 0
    if previous_tick_perf is not None and has_prev_perf_source:
        validate_schema(previous_tick_perf, "omega_tick_perf_v1")
        previous_tick_total_ns_u64 = max(0, int(previous_tick_perf.get("total_ns", 0)))
        stage_ns = previous_tick_perf.get("stage_ns")
        if isinstance(stage_ns, dict) and previous_tick_total_ns_u64 > 0:
            run_subverifier_ns = max(0, int(stage_ns.get("run_subverifier", 0)))
            run_promotion_ns = max(0, int(stage_ns.get("run_promotion", 0)))
            verifier_overhead_q32 = rat_q32(run_subverifier_ns + run_promotion_ns, previous_tick_total_ns_u64)

    has_prev_stats_source = (
        isinstance(previous_tick_stats_source, dict)
        and all(
            str(previous_tick_stats_source.get(key, ""))
            for key in ("schema_id", "artifact_hash", "producer_campaign_id", "producer_run_id")
        )
    )
    promotion_reject_rate_rat = {"num_u64": 0, "den_u64": 1}
    subverifier_invalid_rate_rat = {"num_u64": 0, "den_u64": 1}
    runaway_blocked_noop_rate_rat = {"num_u64": 0, "den_u64": 1}
    runaway_blocked_recent3_u64 = 0
    if previous_tick_stats is not None and has_prev_stats_source:
        validate_schema(previous_tick_stats, "omega_tick_stats_v1")
        promotion_reject_rate_rat = _rate_from_stats(previous_tick_stats, "promotion_reject_rate_rat")
        subverifier_invalid_rate_rat = _rate_from_stats(previous_tick_stats, "invalid_rate_rat")
        runaway_blocked_noop_rate_rat = _rate_from_stats(previous_tick_stats, "runaway_blocked_noop_rate_rat")
        runaway_blocked_recent3_u64 = _recent_runaway_blocked_streak_u64(previous_tick_stats)
    has_prev_scorecard_source = (
        isinstance(previous_run_scorecard_source, dict)
        and all(
            str(previous_run_scorecard_source.get(key, ""))
            for key in ("schema_id", "artifact_hash", "producer_campaign_id", "producer_run_id")
        )
    )
    if previous_run_scorecard is not None and has_prev_scorecard_source:
        validate_schema(previous_run_scorecard, "omega_run_scorecard_v1")

    polymath_metrics, polymath_sources = _load_polymath_metrics(root=root, tick_u64=int(tick_u64))
    ge_metrics, ge_sources = _load_ge_metrics(root=root)
    code_metrics, code_sources = _load_code_metrics(root=root, index=index)
    legacy_skill_metrics, legacy_skill_sources = _load_legacy_skill_metrics(root=root)
    capability_frontier = _capability_frontier_metrics(root=root, registry=registry)
    capability_expansion_q32 = int(int(capability_frontier["cap_frontier_u64"]) << 32)
    maximize_science_q32 = _maximize_science_q32(science_q)
    maximize_speed_q32 = _maximize_speed_q32(previous_tick_total_ns_u64)
    code_success_rate_rat = dict(code_metrics["code_success_rate_rat"])
    hard_task_suite_v1 = evaluate_hard_task_suite_v1(repo_root=root)
    hard_task_metric_q32_by_id = hard_task_metric_q32_by_id_from_suite(suite_eval=hard_task_suite_v1)
    hard_task_code_correctness_q32 = int(hard_task_metric_q32_by_id.get(_HARD_TASK_METRIC_IDS[0], 0))
    hard_task_performance_q32 = int(hard_task_metric_q32_by_id.get(_HARD_TASK_METRIC_IDS[1], 0))
    hard_task_reasoning_q32 = int(hard_task_metric_q32_by_id.get(_HARD_TASK_METRIC_IDS[2], 0))
    hard_task_suite_score_q32 = int(hard_task_metric_q32_by_id.get(_HARD_TASK_METRIC_IDS[3], 0))
    hard_task_score_q32 = int(hard_task_suite_score_q32)
    hard_task_now_q32_by_metric = {
        _HARD_TASK_METRIC_IDS[0]: int(hard_task_code_correctness_q32),
        _HARD_TASK_METRIC_IDS[1]: int(hard_task_performance_q32),
        _HARD_TASK_METRIC_IDS[2]: int(hard_task_reasoning_q32),
        _HARD_TASK_METRIC_IDS[3]: int(hard_task_suite_score_q32),
    }
    hard_task_delta_q32 = 0
    hard_task_gain_count_u64 = 0
    hard_task_prev_score_q32 = 0
    hard_task_baseline_init_u64 = 1
    if isinstance(previous_observation_report, dict):
        prev_metrics = previous_observation_report.get("metrics")
        if isinstance(prev_metrics, dict):
            previous_hard_task_score_q32 = int(_metric_q32(prev_metrics, "hard_task_score_q32"))
            if previous_hard_task_score_q32 == 0:
                previous_hard_task_score_q32 = int(_metric_q32(prev_metrics, _HARD_TASK_METRIC_IDS[3]))
            hard_task_prev_score_q32 = int(previous_hard_task_score_q32)
            hard_task_delta_q32 = int(hard_task_score_q32) - int(previous_hard_task_score_q32)
            for metric_id, now_q32 in sorted(hard_task_now_q32_by_metric.items()):
                if int(now_q32) > int(_metric_q32(prev_metrics, metric_id)):
                    hard_task_gain_count_u64 += 1
            hard_task_baseline_init_u64 = 0
    elif int(tick_u64) > 1:
        # Previous observation can be unavailable in some replay/fastpath ticks.
        # Keep baseline initialization one-shot and deterministic after tick 1.
        hard_task_prev_score_q32 = int(hard_task_score_q32)
        hard_task_delta_q32 = 0
        hard_task_gain_count_u64 = 0
        hard_task_baseline_init_u64 = 0

    sources: list[dict[str, str]] = [src_meta, src_hotloop, src_build, src_science]
    sources.extend(polymath_sources)
    sources.extend(ge_sources)
    sources.extend(code_sources)
    sources.extend(legacy_skill_sources)
    if has_prev_perf_source:
        row = {
            "schema_id": str(previous_tick_perf_source.get("schema_id", "")),
            "artifact_hash": str(previous_tick_perf_source.get("artifact_hash", "")),
            "producer_campaign_id": str(previous_tick_perf_source.get("producer_campaign_id", "")),
            "producer_run_id": str(previous_tick_perf_source.get("producer_run_id", "")),
        }
        sources.append(row)
    if has_prev_stats_source:
        row = {
            "schema_id": str(previous_tick_stats_source.get("schema_id", "")),
            "artifact_hash": str(previous_tick_stats_source.get("artifact_hash", "")),
            "producer_campaign_id": str(previous_tick_stats_source.get("producer_campaign_id", "")),
            "producer_run_id": str(previous_tick_stats_source.get("producer_run_id", "")),
        }
        sources.append(row)
    if has_prev_scorecard_source:
        row = {
            "schema_id": str(previous_run_scorecard_source.get("schema_id", "")),
            "artifact_hash": str(previous_run_scorecard_source.get("artifact_hash", "")),
            "producer_campaign_id": str(previous_run_scorecard_source.get("producer_campaign_id", "")),
            "producer_run_id": str(previous_run_scorecard_source.get("producer_run_id", "")),
        }
        sources.append(row)

    payload: dict[str, Any] = {
        "schema_version": "omega_observation_report_v1",
        "report_id": "sha256:" + "0" * 64,
        "tick_u64": int(tick_u64),
        "active_manifest_hash": active_manifest_hash,
        "metrics": {
            "metasearch_cost_ratio_q32": {"q": metasearch_q},
            "hotloop_top_share_q32": {"q": hotloop_q},
            "val_hotloop_top_share_q32": {"q": hotloop_q},
            "build_link_fraction_q32": {"q": build_q},
            "system_build_link_fraction_q32": {"q": build_q},
            "science_rmse_q32": {"q": science_q},
            "code_success_rate_rat": code_success_rate_rat,
            "hard_task_code_correctness_q32": {"q": int(hard_task_code_correctness_q32)},
            "hard_task_performance_q32": {"q": int(hard_task_performance_q32)},
            "hard_task_reasoning_q32": {"q": int(hard_task_reasoning_q32)},
            "hard_task_suite_score_q32": {"q": int(hard_task_suite_score_q32)},
            "hard_task_score_q32": {"q": int(hard_task_score_q32)},
            "hard_task_prev_score_q32": {"q": int(hard_task_prev_score_q32)},
            "hard_task_delta_q32": {"q": int(hard_task_delta_q32)},
            "hard_task_baseline_init_u64": int(hard_task_baseline_init_u64),
            "hard_task_gain_count_u64": int(hard_task_gain_count_u64),
            "promotion_reject_rate_rat": promotion_reject_rate_rat,
            "subverifier_invalid_rate_rat": subverifier_invalid_rate_rat,
            "runaway_blocked_noop_rate_rat": runaway_blocked_noop_rate_rat,
            "runaway_blocked_recent3_u64": int(runaway_blocked_recent3_u64),
            "verifier_overhead_q32": {"q": verifier_overhead_q32},
            "previous_tick_total_ns_u64": previous_tick_total_ns_u64,
            "OBJ_EXPAND_CAPABILITIES": {"q": int(capability_expansion_q32)},
            "OBJ_MAXIMIZE_SCIENCE": {"q": int(maximize_science_q32)},
            "OBJ_MAXIMIZE_SPEED": {"q": int(maximize_speed_q32)},
            "cap_frontier_u64": int(capability_frontier["cap_frontier_u64"]),
            "cap_enabled_u64": int(capability_frontier["cap_enabled_u64"]),
            "cap_activated_u64": int(capability_frontier["cap_activated_u64"]),
            "domain_coverage_ratio": dict(polymath_metrics["domain_coverage_ratio"]),
            "top_void_score_q32": dict(polymath_metrics["top_void_score_q32"]),
            "domains_bootstrapped_u64": int(polymath_metrics["domains_bootstrapped_u64"]),
            "domains_blocked_license_u64": int(polymath_metrics["domains_blocked_license_u64"]),
            "domains_blocked_policy_u64": int(polymath_metrics["domains_blocked_policy_u64"]),
            "domains_blocked_size_u64": int(polymath_metrics["domains_blocked_size_u64"]),
            "domains_ready_for_conquer_u64": int(polymath_metrics["domains_ready_for_conquer_u64"]),
            "polymath_last_scout_tick_u64": int(polymath_metrics["polymath_last_scout_tick_u64"]),
            "polymath_scout_age_ticks_u64": int(polymath_metrics["polymath_scout_age_ticks_u64"]),
            "polymath_portfolio_score_q32": dict(polymath_metrics["polymath_portfolio_score_q32"]),
            "polymath_portfolio_domains_u64": int(polymath_metrics["polymath_portfolio_domains_u64"]),
            "polymath_portfolio_cache_hit_rate_q32": dict(polymath_metrics["polymath_portfolio_cache_hit_rate_q32"]),
            "ge_promote_rate_rat": dict(ge_metrics["ge_promote_rate_rat"]),
            "ge_mean_stps_delta_q32": dict(ge_metrics["ge_mean_stps_delta_q32"]),
            "transfer_gain_q32": dict(legacy_skill_metrics["transfer_gain_q32"]),
            "ontology_consistency_q32": dict(legacy_skill_metrics["ontology_consistency_q32"]),
            "flywheel_yield_q32": dict(legacy_skill_metrics["flywheel_yield_q32"]),
            "thermo_efficiency_q32": dict(legacy_skill_metrics["thermo_efficiency_q32"]),
            "persistence_health_q32": dict(legacy_skill_metrics["persistence_health_q32"]),
            "persistence_flags_u64": int(legacy_skill_metrics["persistence_flags_u64"]),
        },
        "metric_series": {
            "metasearch_cost_ratio_q32": [{"q": metasearch_q}],
            "hotloop_top_share_q32": [{"q": hotloop_q}],
            "val_hotloop_top_share_q32": [{"q": hotloop_q}],
            "build_link_fraction_q32": [{"q": build_q}],
            "system_build_link_fraction_q32": [{"q": build_q}],
            "science_rmse_q32": [{"q": science_q}],
            "code_success_rate_rat": [code_success_rate_rat],
            "hard_task_code_correctness_q32": [{"q": int(hard_task_code_correctness_q32)}],
            "hard_task_performance_q32": [{"q": int(hard_task_performance_q32)}],
            "hard_task_reasoning_q32": [{"q": int(hard_task_reasoning_q32)}],
            "hard_task_suite_score_q32": [{"q": int(hard_task_suite_score_q32)}],
            "hard_task_score_q32": [{"q": int(hard_task_score_q32)}],
            "hard_task_prev_score_q32": [{"q": int(hard_task_prev_score_q32)}],
            "hard_task_delta_q32": [{"q": int(hard_task_delta_q32)}],
            "hard_task_baseline_init_u64": [int(hard_task_baseline_init_u64)],
            "hard_task_gain_count_u64": [int(hard_task_gain_count_u64)],
            "promotion_reject_rate_rat": [promotion_reject_rate_rat],
            "subverifier_invalid_rate_rat": [subverifier_invalid_rate_rat],
            "runaway_blocked_noop_rate_rat": [runaway_blocked_noop_rate_rat],
            "runaway_blocked_recent3_u64": [int(runaway_blocked_recent3_u64)],
            "previous_tick_total_ns_u64": [previous_tick_total_ns_u64],
            "OBJ_EXPAND_CAPABILITIES": [{"q": int(capability_expansion_q32)}],
            "OBJ_MAXIMIZE_SCIENCE": [{"q": int(maximize_science_q32)}],
            "OBJ_MAXIMIZE_SPEED": [{"q": int(maximize_speed_q32)}],
            "cap_frontier_u64": [int(capability_frontier["cap_frontier_u64"])],
            "cap_enabled_u64": [int(capability_frontier["cap_enabled_u64"])],
            "cap_activated_u64": [int(capability_frontier["cap_activated_u64"])],
            "domain_coverage_ratio": [dict(polymath_metrics["domain_coverage_ratio"])],
            "top_void_score_q32": [dict(polymath_metrics["top_void_score_q32"])],
            "domains_bootstrapped_u64": [int(polymath_metrics["domains_bootstrapped_u64"])],
            "domains_blocked_license_u64": [int(polymath_metrics["domains_blocked_license_u64"])],
            "domains_blocked_policy_u64": [int(polymath_metrics["domains_blocked_policy_u64"])],
            "domains_blocked_size_u64": [int(polymath_metrics["domains_blocked_size_u64"])],
            "domains_ready_for_conquer_u64": [int(polymath_metrics["domains_ready_for_conquer_u64"])],
            "polymath_last_scout_tick_u64": [int(polymath_metrics["polymath_last_scout_tick_u64"])],
            "polymath_scout_age_ticks_u64": [int(polymath_metrics["polymath_scout_age_ticks_u64"])],
            "polymath_portfolio_score_q32": [dict(polymath_metrics["polymath_portfolio_score_q32"])],
            "polymath_portfolio_domains_u64": [int(polymath_metrics["polymath_portfolio_domains_u64"])],
            "polymath_portfolio_cache_hit_rate_q32": [dict(polymath_metrics["polymath_portfolio_cache_hit_rate_q32"])],
            "ge_promote_rate_rat": [dict(ge_metrics["ge_promote_rate_rat"])],
            "ge_mean_stps_delta_q32": [dict(ge_metrics["ge_mean_stps_delta_q32"])],
            "transfer_gain_q32": [dict(legacy_skill_metrics["transfer_gain_q32"])],
            "ontology_consistency_q32": [dict(legacy_skill_metrics["ontology_consistency_q32"])],
            "flywheel_yield_q32": [dict(legacy_skill_metrics["flywheel_yield_q32"])],
            "thermo_efficiency_q32": [dict(legacy_skill_metrics["thermo_efficiency_q32"])],
            "persistence_health_q32": [dict(legacy_skill_metrics["persistence_health_q32"])],
            "persistence_flags_u64": [int(legacy_skill_metrics["persistence_flags_u64"])],
        },
        "hard_task_suite_v1": {
            "schema_name": str(hard_task_suite_v1.get("schema_name", "")),
            "schema_version": str(hard_task_suite_v1.get("schema_version", "")),
            "suite_hash": str(hard_task_suite_v1.get("suite_hash", "")),
            "target_relpath": str(hard_task_suite_v1.get("target_relpath", "")),
            "status": str(hard_task_suite_v1.get("status", "")),
            "error_code": (
                str(hard_task_suite_v1.get("error_code"))
                if hard_task_suite_v1.get("error_code") is not None
                else None
            ),
            "task_count_u32": int(max(0, int(hard_task_suite_v1.get("task_count_u32", 0)))),
            "tasks": [
                {
                    "task_id": str(row.get("task_id", "")),
                    "score_q32": int(max(0, int(row.get("score_q32", 0)))),
                    "passed_u64": int(max(0, int(row.get("passed_u64", 0)))),
                    "total_u64": int(max(0, int(row.get("total_u64", 0)))),
                    "error_code": (str(row.get("error_code")) if row.get("error_code") is not None else None),
                }
                for row in (hard_task_suite_v1.get("tasks") if isinstance(hard_task_suite_v1.get("tasks"), list) else [])
                if isinstance(row, dict)
            ],
            "total_score_q32": int(max(0, int(hard_task_suite_v1.get("total_score_q32", 0)))),
        },
        "sources": sources,
        "inputs_hashes": {
            "policy_hash": policy_hash,
            "registry_hash": registry_hash,
            "objectives_hash": objectives_hash,
        },
    }

    if previous_observation_report is not None:
        prev_series = previous_observation_report.get("metric_series")
        cur_series = payload.get("metric_series")
        if isinstance(prev_series, dict) and isinstance(cur_series, dict):
            for key, rows in cur_series.items():
                if not isinstance(rows, list) or not rows:
                    continue
                prev_rows = prev_series.get(key)
                if not isinstance(prev_rows, list):
                    continue
                if key in _NON_CARRY_SERIES_KEYS:
                    continue
                cur_series[key] = [*prev_rows, rows[-1]][-64:]

    no_id = dict(payload)
    no_id.pop("report_id", None)
    payload["report_id"] = canon_hash_obj(no_id)
    validate_schema(payload, "omega_observation_report_v1")
    return payload, canon_hash_obj(payload)


__all__ = ["observe", "read_meta_core_active_manifest_hash"]
