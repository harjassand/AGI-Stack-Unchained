"""Deterministic goal synthesis for omega daemon v18.0."""

from __future__ import annotations

import os
import re
from typing import Any

from cdel.v18_0.omega_budgets_v1 import has_budget
from cdel.v18_0.omega_common_v1 import Q32_ONE, fail, load_canon_dict, load_jsonl, rat_q32, repo_root
from cdel.v18_0.omega_runaway_v1 import runaway_enabled


_MAX_GOALS_U64 = 300
_MIN_PENDING_GOALS_U64 = 24
_PER_CAP_PENDING_FLOOR_U64 = 2
_ISSUE_PENDING_CAP_SOFT_LIMIT_U64 = 4
_NOOP_STREAK_TRIGGER_U64 = 3
_RUNAWAY_BLOCKED_RATE_TRIGGER_Q32 = int(0.20 * Q32_ONE)
_CORE_SELF_OPT_PENDING_FLOOR_U64 = 6
_STPS_REGRESSION_TRIGGER_NUM = 85
_STPS_REGRESSION_TRIGGER_DEN = 100
_HOTSPOT_STAGE_SHARE_TRIGGER_Q32 = int(0.40 * Q32_ONE)
_CORE_SELF_OPT_CAPABILITY_ID = "RSI_OMEGA_SELF_OPTIMIZE_CORE"
_POLYMATH_SCOUT_CAPABILITY_ID = "RSI_POLYMATH_SCOUT"
_POLYMATH_BOOTSTRAP_CAPABILITY_ID = "RSI_POLYMATH_BOOTSTRAP_DOMAIN"
_POLYMATH_CONQUER_CAPABILITY_ID = "RSI_POLYMATH_CONQUER_DOMAIN"
_POLYMATH_VOID_TRIGGER_Q32 = int(0.30 * Q32_ONE)
_POLYMATH_SCOUT_TTL_TICKS_U64 = 50
_ALREADY_ACTIVE_TAIL_U64 = 3
_ALREADY_ACTIVE_SUPPRESS_TICKS_U64 = 25
_NO_PROMOTION_BUNDLE_TAIL_U64 = 5
_NO_PROMOTION_BUNDLE_SUPPRESS_TICKS_U64 = 15
_CHURN_CONTEXT_MUST_MATCH_B = True
_GOAL_ID_TOKEN_RE = re.compile(r"[^a-z0-9_]+")
_PROMO_FOCUS_ENV_VAR = "OMEGA_PROMO_FOCUS"
_PROMO_FOCUS_MIN_PENDING_GOALS_U64 = 32
_PROMO_FOCUS_PROMOTION_PENDING_FLOOR_U64 = 4
_PROMO_FOCUS_POLYMATH_PENDING_FLOOR_U64 = 2
_PROMO_FOCUS_SKILL_PENDING_FLOOR_U64 = 1
_PROMO_FOCUS_REQUIRED_CAPABILITIES: tuple[str, ...] = (
    "RSI_SAS_CODE",
    "RSI_SAS_SYSTEM",
    "RSI_SAS_KERNEL",
    "RSI_SAS_METASEARCH",
    "RSI_SAS_VAL",
    "RSI_SAS_SCIENCE",
    _POLYMATH_SCOUT_CAPABILITY_ID,
    _POLYMATH_BOOTSTRAP_CAPABILITY_ID,
    _POLYMATH_CONQUER_CAPABILITY_ID,
    "RSI_GE_SH1_OPTIMIZER",
    "RSI_MODEL_GENESIS_V10",
    "RSI_OMEGA_SKILL_ONTOLOGY",
    "RSI_OMEGA_SKILL_SWARM",
)
_PROMO_FOCUS_NO_BUNDLE_EXEMPT_CAPABILITIES = frozenset(
    {
        "RSI_SAS_CODE",
        "RSI_SAS_SYSTEM",
        "RSI_SAS_KERNEL",
        "RSI_SAS_METASEARCH",
        "RSI_SAS_VAL",
        "RSI_SAS_SCIENCE",
    }
)
_PROMO_FOCUS_PROMOTION_CAPABILITIES = frozenset(
    {
        "RSI_SAS_CODE",
        "RSI_SAS_SYSTEM",
        "RSI_SAS_KERNEL",
        "RSI_SAS_METASEARCH",
        "RSI_SAS_VAL",
        "RSI_SAS_SCIENCE",
        "RSI_GE_SH1_OPTIMIZER",
        "RSI_MODEL_GENESIS_V10",
    }
)
_PROMO_FOCUS_POLYMATH_CAPABILITIES = frozenset(
    {
        _POLYMATH_SCOUT_CAPABILITY_ID,
        _POLYMATH_BOOTSTRAP_CAPABILITY_ID,
        _POLYMATH_CONQUER_CAPABILITY_ID,
    }
)

_ISSUE_CAPABILITY_PRIORITY: dict[str, tuple[str, ...]] = {
    "SEARCH_SLOW": ("RSI_SAS_METASEARCH",),
    "SEARCH_STALL": ("RSI_SAS_METASEARCH",),
    "HOTLOOP_BOTTLENECK": ("RSI_SAS_VAL", "RSI_SAS_KERNEL"),
    "BUILD_BOTTLENECK": ("RSI_SAS_SYSTEM", "RSI_SAS_CODE"),
    "SCIENCE_ACCURACY_STALL": ("RSI_SAS_SCIENCE",),
    "VERIFIER_OVERHEAD": ("RSI_SAS_VAL", "RSI_OMEGA_DAEMON"),
    "PROMOTION_REJECT_RATE": ("RSI_SAS_CODE", "RSI_OMEGA_DAEMON"),
    "DOMAIN_VOID_DETECTED": (_POLYMATH_SCOUT_CAPABILITY_ID, _POLYMATH_BOOTSTRAP_CAPABILITY_ID),
    "POLYMATH_SCOUT_STALE": (_POLYMATH_SCOUT_CAPABILITY_ID,),
    "DOMAIN_READY_FOR_CONQUER": (_POLYMATH_CONQUER_CAPABILITY_ID,),
    "DOMAIN_BLOCKED_LICENSE": (_POLYMATH_BOOTSTRAP_CAPABILITY_ID,),
    "DOMAIN_BLOCKED_POLICY": (_POLYMATH_BOOTSTRAP_CAPABILITY_ID,),
    "DOMAIN_BLOCKED_SIZE": (_POLYMATH_BOOTSTRAP_CAPABILITY_ID,),
}
_FAMILY_TO_CAPABILITY: dict[str, str] = {
    "CODE": "RSI_SAS_CODE",
    "SYSTEM": "RSI_SAS_SYSTEM",
    "KERNEL": "RSI_SAS_KERNEL",
    "METASEARCH": "RSI_SAS_METASEARCH",
    "VAL": "RSI_SAS_VAL",
    "SCIENCE": "RSI_SAS_SCIENCE",
}


def _slug(value: str) -> str:
    out = _GOAL_ID_TOKEN_RE.sub("_", str(value).strip().lower()).strip("_")
    return out or "x"


def _enabled_campaigns_by_capability(registry: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    caps = registry.get("capabilities")
    if not isinstance(caps, list):
        fail("SCHEMA_FAIL")
    out: dict[str, list[dict[str, Any]]] = {}
    for row in caps:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        if not bool(row.get("enabled", False)):
            continue
        capability_id = str(row.get("capability_id", "")).strip()
        campaign_id = str(row.get("campaign_id", "")).strip()
        if not capability_id or not campaign_id:
            fail("SCHEMA_FAIL")
        out.setdefault(capability_id, []).append(dict(row))
    for capability_id in sorted(out.keys()):
        out[capability_id] = sorted(out[capability_id], key=lambda row: str(row.get("campaign_id", "")))
    return {key: out[key] for key in sorted(out.keys())}


def _metric_as_q32(value: Any) -> int:
    if isinstance(value, dict):
        if set(value.keys()) == {"q"}:
            return int(value.get("q", 0))
        if set(value.keys()) == {"num_u64", "den_u64"}:
            return rat_q32(int(value.get("num_u64", 0)), int(value.get("den_u64", 0)))
    if isinstance(value, int):
        return value
    fail("SCHEMA_FAIL")
    return 0


def _runaway_blocked_recent3_u64(observation_report: dict[str, Any]) -> int:
    metrics = observation_report.get("metrics")
    if not isinstance(metrics, dict):
        fail("SCHEMA_FAIL")
    value = metrics.get("runaway_blocked_recent3_u64", 0)
    if isinstance(value, int):
        return max(0, min(3, int(value)))
    fail("SCHEMA_FAIL")
    return 0


def _runaway_blocked_rate_q32(observation_report: dict[str, Any]) -> int:
    metrics = observation_report.get("metrics")
    if not isinstance(metrics, dict):
        fail("SCHEMA_FAIL")
    value = metrics.get("runaway_blocked_noop_rate_rat")
    if value is None:
        return 0
    return _metric_as_q32(value)


def _tail_noop_streak(state: dict[str, Any]) -> int:
    rows = state.get("last_actions")
    if not isinstance(rows, list):
        return 0
    streak = 0
    for row in reversed(rows):
        if not isinstance(row, dict):
            break
        if str(row.get("action_kind", "")) != "NOOP":
            break
        streak += 1
    return streak


def _is_core_self_opt_goal(goal_id: str) -> bool:
    return str(goal_id).startswith("goal_self_optimize_core_00_")


def _scorecard_stps_regressed(run_scorecard: dict[str, Any] | None) -> bool:
    if run_scorecard is None:
        return False
    if run_scorecard.get("schema_version") != "omega_run_scorecard_v1":
        fail("SCHEMA_FAIL")
    median_q32 = max(0, int(run_scorecard.get("median_stps_non_noop_q32", 0)))
    window_rows = run_scorecard.get("window_rows")
    if not isinstance(window_rows, list):
        fail("SCHEMA_FAIL")
    latest_q32 = 0
    for row in reversed(window_rows):
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        value = max(0, int(row.get("stps_non_noop_q32", 0)))
        if value > 0:
            latest_q32 = value
            break
    if median_q32 <= 0 or latest_q32 <= 0:
        return False
    return int(latest_q32) * _STPS_REGRESSION_TRIGGER_DEN < int(median_q32) * _STPS_REGRESSION_TRIGGER_NUM


def _hotspot_trigger(hotspots: dict[str, Any] | None) -> tuple[bool, str]:
    if hotspots is None:
        return False, "core"
    if hotspots.get("schema_version") != "omega_hotspots_v1":
        fail("SCHEMA_FAIL")
    rows = hotspots.get("top_hotspots")
    if not isinstance(rows, list):
        fail("SCHEMA_FAIL")
    fallback_stage = "core"
    for row in rows:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        stage_id = str(row.get("stage_id", "")).strip()
        if stage_id and fallback_stage == "core":
            fallback_stage = stage_id
        pct = row.get("pct_of_total_q32")
        if isinstance(pct, dict):
            pct_q = int(pct.get("q", 0))
            if stage_id and pct_q > _HOTSPOT_STAGE_SHARE_TRIGGER_Q32:
                return True, stage_id
    return False, fallback_stage


def _goal_status(state_goals: dict[str, Any], goal_row: dict[str, Any]) -> str:
    goal_id = str(goal_row.get("goal_id", "")).strip()
    status = str(goal_row.get("status", "PENDING"))
    state_row = state_goals.get(goal_id)
    if isinstance(state_row, dict):
        status = str(state_row.get("status", status))
    if status not in {"PENDING", "DONE", "FAILED"}:
        fail("SCHEMA_FAIL")
    return status


def _normalize_goal_rows(goal_queue_base: dict[str, Any]) -> list[dict[str, str]]:
    goals = goal_queue_base.get("goals")
    if not isinstance(goals, list):
        fail("SCHEMA_FAIL")
    out: list[dict[str, str]] = []
    for row in goals:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        goal_id = str(row.get("goal_id", "")).strip()
        capability_id = str(row.get("capability_id", "")).strip()
        status = str(row.get("status", "PENDING"))
        if not goal_id or not capability_id or status not in {"PENDING", "DONE", "FAILED"}:
            fail("SCHEMA_FAIL")
        out.append(
            {
                "goal_id": goal_id,
                "capability_id": capability_id,
                "status": status,
            }
        )
    return out


def _eligible_capability_ids(
    *,
    tick_u64: int,
    state: dict[str, Any],
    campaigns_by_capability: dict[str, list[dict[str, Any]]],
) -> list[str]:
    cooldowns = state.get("cooldowns") or {}
    budget_remaining = state.get("budget_remaining") or {}
    if not isinstance(cooldowns, dict) or not isinstance(budget_remaining, dict):
        fail("SCHEMA_FAIL")
    out: list[str] = []
    for capability_id in sorted(campaigns_by_capability.keys()):
        eligible = False
        for campaign in campaigns_by_capability[capability_id]:
            campaign_id = str(campaign.get("campaign_id", "")).strip()
            if not campaign_id:
                fail("SCHEMA_FAIL")
            next_tick_allowed_u64 = int(((cooldowns.get(campaign_id) or {}).get("next_tick_allowed_u64", 0)))
            if next_tick_allowed_u64 > int(tick_u64):
                continue
            cost_q = int(((campaign.get("budget_cost_hint_q32") or {}).get("q", 0)))
            if not has_budget(budget_remaining, cost_q32=cost_q):
                continue
            eligible = True
            break
        if eligible:
            out.append(capability_id)
    return out


def _goal_id_for(
    *,
    priority_prefix: str,
    reason_slug: str,
    capability_id: str,
    tick_u64: int,
    suffix_u64: int = 0,
) -> str:
    cap_slug = _slug(capability_id)
    if priority_prefix == "CORE":
        base = f"goal_self_optimize_core_00_{_slug(reason_slug)}_{int(tick_u64):06d}"
    elif priority_prefix == "00":
        base = f"goal_auto_00_issue_{_slug(reason_slug)}_{cap_slug}_{int(tick_u64):06d}"
    elif priority_prefix == "10":
        base = f"goal_auto_10_runaway_blocked_{cap_slug}_{int(tick_u64):06d}"
    elif priority_prefix == "20":
        base = f"goal_explore_20_family_{_slug(reason_slug)}_{cap_slug}_{int(tick_u64):06d}"
    else:
        base = f"goal_auto_90_queue_floor_{cap_slug}_{int(tick_u64):06d}"
    if suffix_u64 <= 0:
        return base
    return f"{base}_{int(suffix_u64):02d}"


def _recent_family_counts(tick_stats: dict[str, Any] | None) -> dict[str, int]:
    if tick_stats is None:
        return {}
    if tick_stats.get("schema_version") != "omega_tick_stats_v1":
        fail("SCHEMA_FAIL")
    counts_raw = tick_stats.get("recent_family_counts")
    if not isinstance(counts_raw, dict):
        fail("SCHEMA_FAIL")
    out: dict[str, int] = {}
    for family in sorted(_FAMILY_TO_CAPABILITY.keys()):
        value = counts_raw.get(family)
        if value is None:
            continue
        out[family] = max(0, int(value))
    return out


def _tail_has_rejected_reason(
    rows: list[dict[str, Any]],
    *,
    reason_code: str,
    tail_u64: int,
) -> tuple[bool, int]:
    if len(rows) < int(tail_u64):
        return False, 0
    tail = rows[-int(tail_u64) :]
    if not all(str(row.get("outcome", "")) == "REJECTED" for row in tail):
        return False, 0
    context_hashes: set[str] = set()
    for row in tail:
        reasons = row.get("reason_codes")
        if not isinstance(reasons, list):
            fail("SCHEMA_FAIL")
        reason_set = {str(code).strip() for code in reasons}
        if reason_code not in reason_set:
            return False, 0
        if _CHURN_CONTEXT_MUST_MATCH_B:
            context_hashes.add(str(row.get("context_hash", "")).strip())
    if _CHURN_CONTEXT_MUST_MATCH_B and len(context_hashes) != 1:
        return False, 0
    last_tick = max(int(row.get("tick_u64", 0)) for row in tail)
    return True, int(last_tick)


def _suppressed_caps_from_episodic_memory(tick_u64: int, episodic_memory: dict[str, Any] | None) -> set[str]:
    if episodic_memory is None:
        return set()
    if episodic_memory.get("schema_version") != "omega_episodic_memory_v1":
        fail("SCHEMA_FAIL")
    episodes = episodic_memory.get("episodes")
    if not isinstance(episodes, list):
        fail("SCHEMA_FAIL")

    by_capability: dict[str, list[dict[str, Any]]] = {}
    promo_focus_enabled = _promo_focus_enabled()
    for row in episodes:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        capability_id = str(row.get("capability_id", "")).strip()
        if not capability_id:
            continue
        by_capability.setdefault(capability_id, []).append(row)

    out: set[str] = set()
    for capability_id in sorted(by_capability.keys()):
        if capability_id == "RSI_POLYMATH_SCOUT":
            continue
        rows = sorted(by_capability[capability_id], key=lambda row: int(row.get("tick_u64", 0)))
        if len(rows) < 3:
            pass
        else:
            tail = rows[-3:]
            if all(str(row.get("outcome", "")) == "INVALID" for row in tail):
                reason_sets = []
                for row in tail:
                    reasons = row.get("reason_codes")
                    if not isinstance(reasons, list):
                        fail("SCHEMA_FAIL")
                    reason_sets.append({str(code).strip() for code in reasons})
                if all("SUBVERIFIER_INVALID" in reasons for reasons in reason_sets):
                    last_tick = max(int(row.get("tick_u64", 0)) for row in tail)
                    if int(tick_u64) <= last_tick + 10:
                        out.add(capability_id)

        already_active_match, already_active_last_tick = _tail_has_rejected_reason(
            rows,
            reason_code="ALREADY_ACTIVE",
            tail_u64=_ALREADY_ACTIVE_TAIL_U64,
        )
        if already_active_match and int(tick_u64) <= int(already_active_last_tick) + _ALREADY_ACTIVE_SUPPRESS_TICKS_U64:
            out.add(capability_id)
            continue

        no_bundle_match, no_bundle_last_tick = _tail_has_rejected_reason(
            rows,
            reason_code="NO_PROMOTION_BUNDLE",
            tail_u64=_NO_PROMOTION_BUNDLE_TAIL_U64,
        )
        if promo_focus_enabled and capability_id in _PROMO_FOCUS_NO_BUNDLE_EXEMPT_CAPABILITIES:
            no_bundle_match = False
        if no_bundle_match and int(tick_u64) <= int(no_bundle_last_tick) + _NO_PROMOTION_BUNDLE_SUPPRESS_TICKS_U64:
            out.add(capability_id)
    return out


def _demote_suppressed_pending_goals(
    goals: list[dict[str, str]],
    *,
    suppressed_caps: set[str],
) -> list[dict[str, str]]:
    if not suppressed_caps:
        return list(goals)
    demote_prefixes = ("goal_auto_", "goal_explore_", "goal_auto_90_")
    front: list[dict[str, str]] = []
    back: list[dict[str, str]] = []
    for row in goals:
        if (
            str(row["status"]) == "PENDING"
            and str(row["capability_id"]) in suppressed_caps
            and any(str(row["goal_id"]).startswith(prefix) for prefix in demote_prefixes)
        ):
            back.append(row)
        else:
            front.append(row)
    return front + back


def _activation_denied_repeat(episodic_memory: dict[str, Any] | None) -> tuple[bool, str | None]:
    if episodic_memory is None:
        return False, None
    episodes = episodic_memory.get("episodes")
    if not isinstance(episodes, list):
        fail("SCHEMA_FAIL")
    denied_rows: list[dict[str, Any]] = []
    for row in episodes:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        reasons = row.get("reason_codes")
        if not isinstance(reasons, list):
            fail("SCHEMA_FAIL")
        if "META_CORE_DENIED" in {str(code).strip() for code in reasons}:
            denied_rows.append(row)
    if len(denied_rows) < 2:
        return False, None
    denied_rows = sorted(denied_rows, key=lambda row: int(row.get("tick_u64", 0)))
    latest = denied_rows[-1]
    return True, str(latest.get("capability_id", "")).strip() or None


def _optional_metric_q32(observation_report: dict[str, Any], metric_id: str) -> int:
    metrics = observation_report.get("metrics")
    if not isinstance(metrics, dict):
        fail("SCHEMA_FAIL")
    value = metrics.get(metric_id)
    if value is None:
        return 0
    return _metric_as_q32(value)


def _optional_metric_u64(observation_report: dict[str, Any], metric_id: str) -> int:
    metrics = observation_report.get("metrics")
    if not isinstance(metrics, dict):
        fail("SCHEMA_FAIL")
    value = metrics.get(metric_id)
    if value is None:
        return 0
    if isinstance(value, int):
        return max(0, int(value))
    fail("SCHEMA_FAIL")
    return 0


def _latest_goal_tick_with_prefix(state_goals: dict[str, Any], prefix: str) -> int:
    best = 0
    for goal_id, row in state_goals.items():
        if not str(goal_id).startswith(prefix):
            continue
        if not isinstance(row, dict):
            continue
        best = max(best, max(0, int(row.get("last_tick_u64", 0))))
    return best


def _top_void_candidate_domain_id() -> str | None:
    path = repo_root() / "polymath" / "registry" / "polymath_void_report_v1.jsonl"
    if not path.exists() or not path.is_file():
        return None
    try:
        rows = load_jsonl(path)
    except Exception:  # noqa: BLE001
        return None
    best_id: str | None = None
    best_q = -1
    for row in rows:
        if not isinstance(row, dict):
            continue
        domain_id = str(row.get("candidate_domain_id", "")).strip()
        if not domain_id:
            continue
        value = row.get("void_score_q32")
        q = int(value.get("q", 0)) if isinstance(value, dict) else 0
        if q > best_q or (q == best_q and (best_id is None or domain_id < best_id)):
            best_q = q
            best_id = domain_id
    return best_id


def _latest_ready_domain_id() -> str | None:
    path = repo_root() / "polymath" / "registry" / "polymath_domain_registry_v1.json"
    if not path.exists() or not path.is_file():
        return None
    try:
        payload = load_canon_dict(path)
    except Exception:  # noqa: BLE001
        return None
    rows = payload.get("domains")
    if not isinstance(rows, list):
        return None
    active_ids = sorted(
        {
            str(row.get("domain_id", "")).strip()
            for row in rows
            if isinstance(row, dict)
            and str(row.get("status", "")) == "ACTIVE"
            and bool(row.get("ready_for_conquer", False))
            and not bool(row.get("conquered_b", False))
            and str(row.get("domain_id", "")).strip()
        }
    )
    if not active_ids:
        return None
    return active_ids[-1]


def _promo_focus_enabled() -> bool:
    return str(os.environ.get(_PROMO_FOCUS_ENV_VAR, "")).strip() == "1"


def _pending_floor_for_capability(*, capability_id: str, promo_focus_enabled: bool) -> int:
    if not promo_focus_enabled:
        return int(_PER_CAP_PENDING_FLOOR_U64)
    value = str(capability_id).strip()
    if value in _PROMO_FOCUS_PROMOTION_CAPABILITIES:
        return int(_PROMO_FOCUS_PROMOTION_PENDING_FLOOR_U64)
    if value in _PROMO_FOCUS_POLYMATH_CAPABILITIES:
        return int(_PROMO_FOCUS_POLYMATH_PENDING_FLOOR_U64)
    if value.startswith("RSI_OMEGA_SKILL_"):
        return int(_PROMO_FOCUS_SKILL_PENDING_FLOOR_U64)
    return int(_PER_CAP_PENDING_FLOOR_U64)


def synthesize_goal_queue(
    *,
    tick_u64: int,
    goal_queue_base: dict[str, Any],
    state: dict[str, Any],
    issue_bundle: dict[str, Any],
    observation_report: dict[str, Any],
    registry: dict[str, Any],
    runaway_cfg: dict[str, Any] | None = None,
    run_scorecard: dict[str, Any] | None = None,
    tick_stats: dict[str, Any] | None = None,
    tick_outcome: dict[str, Any] | None = None,
    hotspots: dict[str, Any] | None = None,
    episodic_memory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if goal_queue_base.get("schema_version") != "omega_goal_queue_v1":
        fail("SCHEMA_FAIL")
    state_goals = state.get("goals") or {}
    if not isinstance(state_goals, dict):
        fail("SCHEMA_FAIL")
    issues = issue_bundle.get("issues")
    if not isinstance(issues, list):
        fail("SCHEMA_FAIL")
    if tick_outcome is not None and tick_outcome.get("schema_version") != "omega_tick_outcome_v1":
        fail("SCHEMA_FAIL")

    campaigns_by_capability = _enabled_campaigns_by_capability(registry)
    enabled_caps = sorted(campaigns_by_capability.keys())
    goals = _normalize_goal_rows(goal_queue_base)
    suppressed_caps = _suppressed_caps_from_episodic_memory(int(tick_u64), episodic_memory)
    activation_denied_repeat, denied_capability = _activation_denied_repeat(episodic_memory)
    if denied_capability:
        suppressed_caps.add(denied_capability)
    goals = _demote_suppressed_pending_goals(goals, suppressed_caps=suppressed_caps)
    existing_ids = {str(row["goal_id"]) for row in goals}

    pending_count = 0
    pending_count_by_cap: dict[str, int] = {}
    for row in goals:
        capability_id = str(row["capability_id"])
        status = _goal_status(state_goals, row)
        if status != "PENDING":
            continue
        pending_count += 1
        pending_count_by_cap[capability_id] = int(pending_count_by_cap.get(capability_id, 0)) + 1
    # Keep explicit pending goals from the base queue as the immediate focus.
    # Auto SAFE goals can preempt manual goals in decider ordering.
    preexisting_pending_count = int(pending_count)

    family_counts = _recent_family_counts(tick_stats)
    missing_families = [
        family
        for family in sorted(_FAMILY_TO_CAPABILITY.keys())
        if int(family_counts.get(family, 0)) <= 0
    ]
    promo_focus_enabled = _promo_focus_enabled()
    min_pending_goals_u64 = (
        int(_PROMO_FOCUS_MIN_PENDING_GOALS_U64)
        if promo_focus_enabled
        else int(_MIN_PENDING_GOALS_U64)
    )

    if len(goals) >= _MAX_GOALS_U64 or not enabled_caps:
        return {
            "schema_version": "omega_goal_queue_v1",
            "goals": goals[:_MAX_GOALS_U64],
        }

    eligible_caps = _eligible_capability_ids(
        tick_u64=tick_u64,
        state=state,
        campaigns_by_capability=campaigns_by_capability,
    )
    eligible_cap_set = set(eligible_caps)

    def add_goal(priority_prefix: str, reason_slug: str, capability_id: str) -> bool:
        nonlocal pending_count
        if capability_id in suppressed_caps:
            return False
        if capability_id not in eligible_cap_set:
            return False
        if len(goals) >= _MAX_GOALS_U64:
            return False
        candidate_goal_id = _goal_id_for(
            priority_prefix=priority_prefix,
            reason_slug=reason_slug,
            capability_id=capability_id,
            tick_u64=tick_u64,
        )
        suffix = 0
        while candidate_goal_id in existing_ids:
            suffix += 1
            candidate_goal_id = _goal_id_for(
                priority_prefix=priority_prefix,
                reason_slug=reason_slug,
                capability_id=capability_id,
                tick_u64=tick_u64,
                suffix_u64=suffix,
            )
        goals.append(
            {
                "goal_id": candidate_goal_id,
                "capability_id": capability_id,
                "status": "PENDING",
            }
        )
        existing_ids.add(candidate_goal_id)
        pending_count += 1
        pending_count_by_cap[capability_id] = int(pending_count_by_cap.get(capability_id, 0)) + 1
        return True

    def add_named_goal(goal_id_base: str, capability_id: str, *, require_eligible: bool = True) -> bool:
        nonlocal pending_count
        if require_eligible and capability_id not in eligible_cap_set:
            return False
        if len(goals) >= _MAX_GOALS_U64:
            return False
        candidate_goal_id = str(goal_id_base).strip()
        if not candidate_goal_id:
            return False
        suffix = 0
        while candidate_goal_id in existing_ids:
            suffix += 1
            candidate_goal_id = f"{goal_id_base}_{suffix:02d}"
        goals.append(
            {
                "goal_id": candidate_goal_id,
                "capability_id": capability_id,
                "status": "PENDING",
            }
        )
        existing_ids.add(candidate_goal_id)
        pending_count += 1
        pending_count_by_cap[capability_id] = int(pending_count_by_cap.get(capability_id, 0)) + 1
        return True

    top_void_score_q32 = _optional_metric_q32(observation_report, "top_void_score_q32")
    polymath_scout_age_ticks_u64 = _optional_metric_u64(observation_report, "polymath_scout_age_ticks_u64")
    domains_ready_for_conquer_u64 = _optional_metric_u64(observation_report, "domains_ready_for_conquer_u64")

    if (
        top_void_score_q32 > _POLYMATH_VOID_TRIGGER_Q32
        and preexisting_pending_count <= 0
    ):
        domain_id = _top_void_candidate_domain_id() or "unknown"
        if (
            polymath_scout_age_ticks_u64 > _POLYMATH_SCOUT_TTL_TICKS_U64
            and _POLYMATH_SCOUT_CAPABILITY_ID in eligible_cap_set
        ):
            add_named_goal(
                f"goal_polymath_scout_{_slug(domain_id)}_{int(tick_u64):06d}",
                _POLYMATH_SCOUT_CAPABILITY_ID,
            )
        elif (
            polymath_scout_age_ticks_u64 <= _POLYMATH_SCOUT_TTL_TICKS_U64
            and _POLYMATH_BOOTSTRAP_CAPABILITY_ID in eligible_cap_set
        ):
            add_named_goal(
                f"goal_polymath_bootstrap_{_slug(domain_id)}_{int(tick_u64):06d}",
                _POLYMATH_BOOTSTRAP_CAPABILITY_ID,
            )

    if domains_ready_for_conquer_u64 > 0 and _POLYMATH_CONQUER_CAPABILITY_ID in eligible_cap_set and preexisting_pending_count <= 0:
        domain_id = _latest_ready_domain_id() or "unknown"
        add_named_goal(
            f"goal_polymath_conquer_{_slug(domain_id)}_{int(tick_u64):06d}",
            _POLYMATH_CONQUER_CAPABILITY_ID,
        )

    stps_regression_triggered = _scorecard_stps_regressed(run_scorecard)
    hotspot_triggered, hotspot_stage_slug = _hotspot_trigger(hotspots)
    core_self_opt_triggered = bool(stps_regression_triggered or hotspot_triggered)
    if core_self_opt_triggered and _CORE_SELF_OPT_CAPABILITY_ID in eligible_cap_set:
        core_pending = 0
        for row in goals:
            if not isinstance(row, dict):
                fail("SCHEMA_FAIL")
            if not _is_core_self_opt_goal(str(row.get("goal_id", ""))):
                continue
            if _goal_status(state_goals, row) != "PENDING":
                continue
            core_pending += 1
        while core_pending < _CORE_SELF_OPT_PENDING_FLOOR_U64 and len(goals) < _MAX_GOALS_U64:
            if not add_goal("CORE", hotspot_stage_slug, _CORE_SELF_OPT_CAPABILITY_ID):
                break
            core_pending += 1

    if preexisting_pending_count <= 0:
        sorted_issues_rows: list[dict[str, Any]] = []
        for row in issues:
            if not isinstance(row, dict):
                fail("SCHEMA_FAIL")
            sorted_issues_rows.append(row)
        sorted_issues = sorted(
            sorted_issues_rows,
            key=lambda row: (str(row.get("issue_type", "")), str(row.get("issue_id", ""))),
        )
        for issue in sorted_issues:
            issue_type = str(issue.get("issue_type", "")).strip()
            if issue_type in {"DOMAIN_VOID_DETECTED", "POLYMATH_SCOUT_STALE", "DOMAIN_READY_FOR_CONQUER"}:
                continue
            targets = _ISSUE_CAPABILITY_PRIORITY.get(issue_type, ())
            for capability_id in targets:
                if int(pending_count_by_cap.get(capability_id, 0)) >= _ISSUE_PENDING_CAP_SOFT_LIMIT_U64:
                    continue
                add_goal("00", issue_type, capability_id)

    tail_noop_streak_u64 = _tail_noop_streak(state)
    runaway_blocked_rate_q32 = _runaway_blocked_rate_q32(observation_report)
    runaway_blocked_recent3 = _runaway_blocked_recent3_u64(observation_report)
    scorecard_force_quality_shift = False
    scorecard_force_all_eligible = False
    if run_scorecard is not None:
        if run_scorecard.get("schema_version") != "omega_run_scorecard_v1":
            fail("SCHEMA_FAIL")
        run_ticks_u64 = int(run_scorecard.get("run_ticks_u64", 0))
        non_noop_ticks_u64 = int(run_scorecard.get("non_noop_ticks_u64", 0))
        promotion_success_rate_q32 = _metric_as_q32(run_scorecard.get("promotion_success_rate_rat"))
        high_non_noop = non_noop_ticks_u64 * 2 >= max(1, run_ticks_u64)
        low_non_noop = non_noop_ticks_u64 * 4 < max(1, run_ticks_u64)
        scorecard_force_quality_shift = high_non_noop and promotion_success_rate_q32 < int(0.35 * Q32_ONE)
        scorecard_force_all_eligible = low_non_noop and runaway_blocked_rate_q32 >= _RUNAWAY_BLOCKED_RATE_TRIGGER_Q32

    if preexisting_pending_count <= 0:
        if scorecard_force_quality_shift:
            for capability_id in ("RSI_SAS_CODE", "RSI_SAS_SYSTEM"):
                add_goal("00", "scorecard_quality_shift", capability_id)
        if activation_denied_repeat:
            for capability_id in ("RSI_SAS_CODE", "RSI_SAS_SYSTEM"):
                add_goal("00", "activation_pipeline_fix", capability_id)

    runaway_recovery_triggered = (
        runaway_enabled(runaway_cfg)
        and tail_noop_streak_u64 >= _NOOP_STREAK_TRIGGER_U64
        and (runaway_blocked_rate_q32 > 0 or runaway_blocked_recent3 > 0)
    )
    runaway_recovery_all_caps = (
        runaway_enabled(runaway_cfg)
        and (
            runaway_blocked_rate_q32 >= _RUNAWAY_BLOCKED_RATE_TRIGGER_Q32
            or runaway_blocked_recent3 >= 3
        )
    )
    if scorecard_force_all_eligible:
        runaway_recovery_triggered = True
        runaway_recovery_all_caps = True
    if preexisting_pending_count <= 0 and runaway_recovery_triggered and eligible_caps:
        if runaway_recovery_all_caps:
            recovery_caps = list(eligible_caps)
        else:
            recovery_caps = [eligible_caps[0]]
        for capability_id in recovery_caps:
            add_goal("10", "runaway_blocked", capability_id)

    boredom_triggered = pending_count < 4
    if boredom_triggered:
        for family in missing_families:
            capability_id = _FAMILY_TO_CAPABILITY[family]
            add_goal("20", family, capability_id)

    if promo_focus_enabled:
        for capability_id in _PROMO_FOCUS_REQUIRED_CAPABILITIES:
            if capability_id not in enabled_caps:
                continue
            if int(pending_count_by_cap.get(capability_id, 0)) > 0:
                continue
            add_named_goal(
                f"goal_auto_00_00promo_{_slug(capability_id)}_{int(tick_u64):06d}",
                capability_id,
                require_eligible=False,
            )

    floor_caps = [capability_id for capability_id in eligible_caps if capability_id not in suppressed_caps]
    if not floor_caps and pending_count <= 0:
        floor_caps = list(eligible_caps)

    for capability_id in floor_caps:
        floor_u64 = _pending_floor_for_capability(
            capability_id=capability_id,
            promo_focus_enabled=promo_focus_enabled,
        )
        while int(pending_count_by_cap.get(capability_id, 0)) < int(floor_u64) and len(goals) < _MAX_GOALS_U64:
            if not add_goal("90", "queue_floor", capability_id):
                break

    if floor_caps:
        cap_idx = 0
        no_progress_rounds = 0
        while pending_count < int(min_pending_goals_u64) and len(goals) < _MAX_GOALS_U64:
            capability_id = floor_caps[cap_idx % len(floor_caps)]
            cap_idx += 1
            if add_goal("90", "queue_floor", capability_id):
                no_progress_rounds = 0
            else:
                no_progress_rounds += 1
                if no_progress_rounds >= len(floor_caps):
                    break

    return {
        "schema_version": "omega_goal_queue_v1",
        "goals": goals[:_MAX_GOALS_U64],
    }


__all__ = ["synthesize_goal_queue"]
