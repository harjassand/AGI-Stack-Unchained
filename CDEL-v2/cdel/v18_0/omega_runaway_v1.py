"""Runaway objective mode helpers for omega daemon v18.0."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .omega_common_v1 import Q32_ONE, canon_hash_obj, fail, load_canon_dict, q32_int, q32_mul, validate_schema, write_hashed_json

_ENV_OVERRIDE_ALLOWLIST: dict[str, set[str]] = {
    "rsi_sas_metasearch_v16_1": {"V16_MAX_DEV_EVALS", "V16_BASELINE_MAX_DEV_EVALS", "V16_MIN_CORPUS_CASES"},
    "rsi_sas_science_v13_0": {"V13_MAX_THEORIES"},
    "rsi_sas_val_v17_0": {"V17_MAX_TASKS"},
    "rsi_sas_system_v14_0": {"V14_PERF_GATE_SPEEDUP_X10"},
    "rsi_sas_kernel_v15_0": {"V15_REPLAY_CASES_LIMIT"},
}


def load_runaway_config(path: Path) -> tuple[dict[str, Any], str]:
    obj = load_canon_dict(path)
    if obj.get("schema_version") != "omega_runaway_config_v1":
        fail("SCHEMA_FAIL")
    validate_schema(obj, "omega_runaway_config_v1")
    tighten_q = q32_int(obj.get("tighten_factor_q32"))
    if tighten_q <= 0 or tighten_q >= Q32_ONE:
        fail("SCHEMA_FAIL")
    return obj, canon_hash_obj(obj)


def runaway_enabled(runaway_cfg: dict[str, Any] | None) -> bool:
    return isinstance(runaway_cfg, dict) and bool(runaway_cfg.get("enabled", False))


def _metric_q32(observation_report: dict[str, Any], metric_id: str) -> int:
    metrics = observation_report.get("metrics")
    if not isinstance(metrics, dict):
        fail("SCHEMA_FAIL")
    row = metrics.get(metric_id)
    if not isinstance(row, dict):
        fail("SCHEMA_FAIL")
    return q32_int(row)


def _objective_metrics(objectives: dict[str, Any]) -> list[dict[str, Any]]:
    rows = objectives.get("metrics")
    if not isinstance(rows, list):
        fail("SCHEMA_FAIL")
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        if str(row.get("direction")) != "MINIMIZE":
            fail("SCHEMA_FAIL")
        out.append(row)
    if not out:
        fail("SCHEMA_FAIL")
    return out


def bootstrap_runaway_state(
    *,
    objectives: dict[str, Any],
    objective_set_hash: str,
    observation_report: dict[str, Any],
) -> dict[str, Any]:
    metric_states: dict[str, Any] = {}
    for row in _objective_metrics(objectives):
        metric_id = str(row.get("metric_id"))
        target_q = q32_int(row.get("target_q32"))
        observed_q = _metric_q32(observation_report, metric_id)
        metric_states[metric_id] = {
            "current_target_q32": {"q": int(target_q)},
            "best_value_q32": {"q": int(observed_q)},
            "last_value_q32": {"q": int(observed_q)},
            "last_improve_tick_u64": 0,
            "stall_ticks_u64": 0,
            "escalation_level_u64": 0,
            "tighten_round_u64": 0,
        }

    payload = {
        "schema_version": "omega_runaway_state_v1",
        "state_id": "sha256:" + "0" * 64,
        "tick_u64": 0,
        "objective_set_hash": objective_set_hash,
        "metric_states": metric_states,
        "campaign_intensity_levels": {},
        "version_minor_u64": 0,
    }
    validate_schema(payload, "omega_runaway_state_v1")
    return payload


def _find_intensity_row(runaway_cfg: dict[str, Any], campaign_id: str, level_u64: int) -> dict[str, Any]:
    table = runaway_cfg.get("per_campaign_intensity_table")
    if not isinstance(table, dict):
        fail("SCHEMA_FAIL")
    rows_raw = table.get(campaign_id)
    if not isinstance(rows_raw, list) or not rows_raw:
        return {"level_u64": int(level_u64), "env_overrides": {}}
    rows: list[dict[str, Any]] = []
    for row in rows_raw:
        if isinstance(row, dict):
            rows.append(row)
    if not rows:
        return {"level_u64": int(level_u64), "env_overrides": {}}
    rows.sort(key=lambda row: int(row.get("level_u64", 0)))
    best = rows[0]
    for row in rows:
        if int(row.get("level_u64", 0)) <= int(level_u64):
            best = row
    return best


def resolve_route_campaign(runaway_cfg: dict[str, Any], metric_id: str, escalation_level_u64: int) -> str:
    table = runaway_cfg.get("per_metric_route_table")
    if not isinstance(table, dict):
        fail("SCHEMA_FAIL")
    rows_raw = table.get(metric_id)
    if not isinstance(rows_raw, list) or not rows_raw:
        fail("SCHEMA_FAIL")
    rows = [row for row in rows_raw if isinstance(row, dict)]
    if not rows:
        fail("SCHEMA_FAIL")
    rows.sort(key=lambda row: int(row.get("level_u64", 0)))
    best = rows[0]
    for row in rows:
        if int(row.get("level_u64", 0)) <= int(escalation_level_u64):
            best = row
    campaign_id = str(best.get("campaign_id", "")).strip()
    if not campaign_id:
        fail("SCHEMA_FAIL")
    return campaign_id


def ensure_env_overrides_allowed(campaign_id: str, env_overrides: dict[str, str]) -> None:
    allow = _ENV_OVERRIDE_ALLOWLIST.get(campaign_id, set())
    for key in env_overrides.keys():
        if key not in allow:
            fail("ENV_OVERRIDE_FORBIDDEN")


def resolve_env_overrides(runaway_cfg: dict[str, Any], campaign_id: str, level_u64: int) -> dict[str, str]:
    row = _find_intensity_row(runaway_cfg, campaign_id, level_u64)
    env_raw = row.get("env_overrides")
    if not isinstance(env_raw, dict):
        fail("SCHEMA_FAIL")
    out = {str(k): str(v) for k, v in env_raw.items()}
    ensure_env_overrides_allowed(campaign_id, out)
    return out


def canonicalize_runaway_state(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    no_id = dict(out)
    no_id.pop("state_id", None)
    out["state_id"] = canon_hash_obj(no_id)
    validate_schema(out, "omega_runaway_state_v1")
    return out


def advance_runaway_state(
    *,
    prev_state: dict[str, Any],
    observation_report: dict[str, Any],
    decision_plan: dict[str, Any],
    runaway_cfg: dict[str, Any],
    objectives: dict[str, Any],
    tick_u64: int,
    promoted_and_activated: bool,
    subverifier_invalid_stall: bool = False,
) -> dict[str, Any]:
    if not runaway_enabled(runaway_cfg):
        return canonicalize_runaway_state(
            {
                "schema_version": "omega_runaway_state_v1",
                "state_id": prev_state.get("state_id", "sha256:" + "0" * 64),
                "tick_u64": int(tick_u64),
                "objective_set_hash": prev_state.get("objective_set_hash"),
                "metric_states": prev_state.get("metric_states"),
                "campaign_intensity_levels": prev_state.get("campaign_intensity_levels") or {},
                "version_minor_u64": int(prev_state.get("version_minor_u64", 0)),
            }
        )

    metric_states_prev = prev_state.get("metric_states")
    if not isinstance(metric_states_prev, dict):
        fail("SCHEMA_FAIL")
    tighten_factor_q = q32_int(runaway_cfg.get("tighten_factor_q32"))
    min_improve_map = runaway_cfg.get("min_improve_delta_q32")
    if not isinstance(min_improve_map, dict):
        fail("SCHEMA_FAIL")

    metric_states_next: dict[str, Any] = {}
    improved_metrics = 0
    for row in _objective_metrics(objectives):
        metric_id = str(row.get("metric_id"))
        prev_metric = metric_states_prev.get(metric_id)
        if not isinstance(prev_metric, dict):
            fail("SCHEMA_FAIL")
        observed_q = _metric_q32(observation_report, metric_id)
        best_q = q32_int(prev_metric.get("best_value_q32"))
        min_delta_q = q32_int(min_improve_map.get(metric_id))
        improved = promoted_and_activated and (observed_q < (best_q - min_delta_q))
        if improved:
            best_q = observed_q
            improved_metrics += 1

        current_target_q = q32_int(prev_metric.get("current_target_q32"))
        if improved:
            current_target_q = q32_mul(best_q, tighten_factor_q)

        metric_states_next[metric_id] = {
            "current_target_q32": {"q": int(current_target_q)},
            "best_value_q32": {"q": int(best_q)},
            "last_value_q32": {"q": int(observed_q)},
            "last_improve_tick_u64": int(tick_u64) if improved else int(prev_metric.get("last_improve_tick_u64", 0)),
            "stall_ticks_u64": 0 if improved else int(prev_metric.get("stall_ticks_u64", 0)),
            "escalation_level_u64": 0 if improved else int(prev_metric.get("escalation_level_u64", 0)),
            "tighten_round_u64": int(prev_metric.get("tighten_round_u64", 0)) + (1 if improved else 0),
        }

    if (promoted_and_activated and improved_metrics == 0) or bool(subverifier_invalid_stall):
        metric_id = str(decision_plan.get("runaway_selected_metric_id", "")).strip()
        row = metric_states_next.get(metric_id)
        if isinstance(row, dict):
            row["stall_ticks_u64"] = int(row.get("stall_ticks_u64", 0)) + 1
            stall_window = max(1, int(runaway_cfg.get("stall_window_ticks_u64", 1)))
            stall_after = max(1, int(runaway_cfg.get("stall_escalate_after_u64", 1)))
            escalate_threshold = stall_window * stall_after
            if int(row["stall_ticks_u64"]) >= escalate_threshold:
                row["escalation_level_u64"] = min(
                    int(runaway_cfg.get("max_escalation_level_u64", 0)),
                    int(row.get("escalation_level_u64", 0)) + 1,
                )
                row["stall_ticks_u64"] = 0

    levels = dict(prev_state.get("campaign_intensity_levels") or {})
    action_kind = str(decision_plan.get("action_kind"))
    campaign_id = str(decision_plan.get("campaign_id", "")).strip()
    if action_kind in {"RUN_CAMPAIGN", "RUN_GOAL_TASK"} and campaign_id:
        level_u64 = int(decision_plan.get("runaway_escalation_level_u64", 0))
        levels[campaign_id] = level_u64

    payload = {
        "schema_version": "omega_runaway_state_v1",
        "state_id": "sha256:" + "0" * 64,
        "tick_u64": int(tick_u64),
        "objective_set_hash": prev_state.get("objective_set_hash"),
        "metric_states": metric_states_next,
        "campaign_intensity_levels": levels,
        "version_minor_u64": int(prev_state.get("version_minor_u64", 0)) + int(improved_metrics),
    }
    return canonicalize_runaway_state(payload)


def write_runaway_state(runaway_dir: Path, payload: dict[str, Any]) -> tuple[Path, dict[str, Any], str]:
    path, obj, digest = write_hashed_json(runaway_dir, "omega_runaway_state_v1.json", payload, id_field="state_id")
    validate_schema(obj, "omega_runaway_state_v1")
    return path, obj, digest


def load_runaway_states(runaway_dir: Path) -> list[dict[str, Any]]:
    if not runaway_dir.exists():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(runaway_dir.glob("sha256_*.omega_runaway_state_v1.json")):
        payload = load_canon_dict(path)
        if payload.get("schema_version") != "omega_runaway_state_v1":
            fail("SCHEMA_FAIL")
        validate_schema(payload, "omega_runaway_state_v1")
        out.append(payload)
    return out


def load_latest_runaway_state(runaway_dir: Path) -> dict[str, Any] | None:
    rows = load_runaway_states(runaway_dir)
    if not rows:
        return None
    return max(rows, key=lambda row: int(row.get("tick_u64", -1)))


def load_prev_runaway_state_for_tick(runaway_dir: Path, tick_u64: int) -> dict[str, Any] | None:
    rows = [row for row in load_runaway_states(runaway_dir) if int(row.get("tick_u64", -1)) < int(tick_u64)]
    if not rows:
        return None
    return max(rows, key=lambda row: int(row.get("tick_u64", -1)))


__all__ = [
    "advance_runaway_state",
    "bootstrap_runaway_state",
    "canonicalize_runaway_state",
    "ensure_env_overrides_allowed",
    "load_latest_runaway_state",
    "load_prev_runaway_state_for_tick",
    "load_runaway_config",
    "load_runaway_states",
    "resolve_env_overrides",
    "resolve_route_campaign",
    "runaway_enabled",
    "write_runaway_state",
]
