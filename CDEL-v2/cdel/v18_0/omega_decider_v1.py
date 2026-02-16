"""Deterministic policy decider for omega daemon v18.0."""

from __future__ import annotations

from typing import Any

from .omega_budgets_v1 import has_budget
from .omega_common_v1 import canon_hash_obj, cmp_q32, fail, q32_int, q32_mul, rat_q32, validate_schema
from .omega_runaway_v1 import check_runaway_condition, resolve_env_overrides, resolve_route_campaign, runaway_enabled
from .omega_temperature_v1 import temperature_band_from_q32


def _metric_as_q32(value: Any) -> int:
    if isinstance(value, dict):
        if set(value.keys()) == {"q"}:
            return q32_int(value)
        if set(value.keys()) == {"num_u64", "den_u64"}:
            return rat_q32(int(value.get("num_u64", 0)), int(value.get("den_u64", 0)))
    if isinstance(value, int):
        return value
    fail("SCHEMA_FAIL")
    return 0


def _temperature_band(observation_report: dict[str, Any]) -> str:
    metrics = observation_report.get("metrics")
    if not isinstance(metrics, dict):
        fail("SCHEMA_FAIL")
    temp_metric = metrics.get("brain_temperature_q32")
    if temp_metric is None:
        return "MID"
    return temperature_band_from_q32(_metric_as_q32(temp_metric))


def _goal_class(goal_id: str) -> str:
    value = str(goal_id)
    if value.startswith("goal_self_optimize_core_00_"):
        return "CORE_SELF_OPT"
    if value.startswith("goal_auto_00_") or value.startswith("goal_auto_10_"):
        return "SAFE"
    if value.startswith("goal_explore_20_"):
        return "EXPLORE"
    if value.startswith("goal_auto_90_"):
        return "FLOOR"
    return "SAFE"


def _goal_class_rank(goal_class: str, temp_band: str) -> int:
    if temp_band == "LOW":
        ranks = {"CORE_SELF_OPT": 0, "SAFE": 1, "FLOOR": 2, "EXPLORE": 3}
        return int(ranks.get(goal_class, 3))
    if temp_band == "HIGH":
        ranks = {"CORE_SELF_OPT": 0, "SAFE": 1, "EXPLORE": 2, "FLOOR": 3}
        return int(ranks.get(goal_class, 3))
    ranks = {"CORE_SELF_OPT": 0, "SAFE": 1, "EXPLORE": 2, "FLOOR": 3}
    return int(ranks.get(goal_class, 3))


def _match_rule(
    *,
    rule: dict[str, Any],
    issue: dict[str, Any],
    metrics: dict[str, Any],
) -> bool:
    when = rule.get("when")
    if not isinstance(when, dict):
        fail("SCHEMA_FAIL")
    if issue.get("issue_type") != when.get("issue_type"):
        return False
    metric_id = str(when.get("metric_id"))
    metric = metrics.get(metric_id)
    if metric is None:
        return False
    lhs_q = _metric_as_q32(metric)
    rhs_q = q32_int(when.get("threshold_q32"))
    if not cmp_q32(lhs_q, str(when.get("comparator")), rhs_q):
        return False
    persistence = int(issue.get("persistence_ticks_u64", 0))
    required = int(when.get("persistence_min_ticks_u64", 0))
    return persistence >= required


def _pending_goals_and_caps(
    *,
    state: dict[str, Any],
    goal_queue: dict[str, Any],
    registry: dict[str, Any],
    tie_break_path: list[str],
) -> tuple[list[tuple[str, str]], dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    caps = registry.get("capabilities")
    goals = goal_queue.get("goals")
    state_goals = state.get("goals") or {}
    if not isinstance(caps, list) or not isinstance(goals, list) or not isinstance(state_goals, dict):
        fail("SCHEMA_FAIL")

    cap_map: dict[str, dict[str, Any]] = {}
    cap_by_id: dict[str, list[dict[str, Any]]] = {}
    for row in caps:
        if isinstance(row, dict):
            campaign_id = str(row.get("campaign_id"))
            cap_map[campaign_id] = row
            capability_id = str(row.get("capability_id"))
            cap_by_id.setdefault(capability_id, []).append(row)

    pending_goals: list[tuple[str, str]] = []
    for row in goals:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        goal_id = str(row.get("goal_id", "")).strip()
        capability_id = str(row.get("capability_id", "")).strip()
        if not goal_id or not capability_id:
            fail("SCHEMA_FAIL")
        state_row = state_goals.get(goal_id)
        status = str(row.get("status", "PENDING"))
        if isinstance(state_row, dict):
            status = str(state_row.get("status", status))
        if status not in {"PENDING", "DONE", "FAILED"}:
            fail("SCHEMA_FAIL")
        if status == "PENDING":
            pending_goals.append((goal_id, capability_id))
        else:
            tie_break_path.append(f"GOAL_SKIP:{goal_id}:{status}")

    return pending_goals, cap_map, cap_by_id


def _goal_plan_candidate(
    *,
    tick_u64: int,
    state: dict[str, Any],
    pending_goals: list[tuple[str, str]],
    cap_by_id: dict[str, list[dict[str, Any]]],
    tie_break_path: list[str],
    tie_break_prefix: str = "",
) -> dict[str, Any] | None:
    prefix = f"{tie_break_prefix}:" if tie_break_prefix else ""
    for goal_id, capability_id in pending_goals:
        cap_rows = sorted(
            [row for row in cap_by_id.get(capability_id, []) if bool(row.get("enabled", False))],
            key=lambda row: str(row.get("campaign_id")),
        )
        if not cap_rows:
            tie_break_path.append(f"{prefix}GOAL_SKIP:{goal_id}:CAPABILITY_DISABLED")
            continue

        winner_cap: dict[str, Any] | None = None
        for cap in cap_rows:
            campaign_id = str(cap.get("campaign_id"))
            cooldown = ((state.get("cooldowns") or {}).get(campaign_id) or {}).get("next_tick_allowed_u64", 0)
            if int(cooldown) > int(tick_u64):
                tie_break_path.append(f"{prefix}GOAL_SKIP:{goal_id}:{campaign_id}:COOLDOWN")
                continue
            cost_q = int(((cap.get("budget_cost_hint_q32") or {}).get("q", 0)))
            if not has_budget(state.get("budget_remaining") or {}, cost_q32=cost_q):
                tie_break_path.append(f"{prefix}GOAL_SKIP:{goal_id}:{campaign_id}:BUDGET")
                continue
            winner_cap = cap
            break

        if winner_cap is None:
            continue

        campaign_id = str(winner_cap.get("campaign_id"))
        tie_break_path.append(f"{prefix}GOAL:{goal_id}:capability={capability_id}:campaign={campaign_id}")
        return {
            "goal_id": goal_id,
            "assigned_capability_id": capability_id,
            "campaign_id": campaign_id,
            "capability_id": str(winner_cap.get("capability_id")),
            "campaign_pack_hash": canon_hash_obj({"campaign_pack_rel": winner_cap.get("campaign_pack_rel")}),
            "expected_verifier_module": str(winner_cap.get("verifier_module")),
            "priority_q32": {"q": 1 << 32},
        }
    return None


def _rule_candidates(
    *,
    tick_u64: int,
    state: dict[str, Any],
    issues: list[dict[str, Any]],
    rules: list[dict[str, Any]],
    metrics: dict[str, Any],
    cap_map: dict[str, dict[str, Any]],
    tie_break_path: list[str],
    tie_break_prefix: str = "",
) -> list[dict[str, Any]]:
    prefix = f"{tie_break_prefix}:" if tie_break_prefix else ""
    candidates: list[dict[str, Any]] = []
    for issue in issues:
        if not isinstance(issue, dict):
            fail("SCHEMA_FAIL")
        for rule in rules:
            if not isinstance(rule, dict) or not bool(rule.get("enabled", False)):
                continue
            if not _match_rule(rule=rule, issue=issue, metrics=metrics):
                continue
            then = rule.get("then")
            if not isinstance(then, dict):
                fail("SCHEMA_FAIL")
            campaign_id = str(then.get("campaign_id"))
            cap = cap_map.get(campaign_id)
            if cap is None or not bool(cap.get("enabled", False)):
                tie_break_path.append(f"{prefix}SKIP:{campaign_id}:DISABLED")
                continue
            cooldown = ((state.get("cooldowns") or {}).get(campaign_id) or {}).get("next_tick_allowed_u64", 0)
            if int(cooldown) > int(tick_u64):
                tie_break_path.append(f"{prefix}SKIP:{campaign_id}:COOLDOWN")
                continue
            cost_q = int(((cap.get("budget_cost_hint_q32") or {}).get("q", 0)))
            if not has_budget(state.get("budget_remaining") or {}, cost_q32=cost_q):
                tie_break_path.append(f"{prefix}SKIP:{campaign_id}:BUDGET")
                continue
            candidates.append(
                {
                    "campaign_id": campaign_id,
                    "capability_id": str(cap.get("capability_id")),
                    "campaign_pack_hash": canon_hash_obj({"campaign_pack_rel": cap.get("campaign_pack_rel")}),
                    "expected_verifier_module": str(cap.get("verifier_module")),
                    "priority_q": q32_int(then.get("priority_q32")),
                    "severity_q": q32_int(issue.get("severity_q32")),
                    "rule_id": str(rule.get("rule_id")),
                    "issue_type": str(issue.get("issue_type")),
                }
            )
    return candidates


def _runaway_decision(
    *,
    tick_u64: int,
    state: dict[str, Any],
    observation_report_hash: str,
    issue_bundle_hash: str,
    observation_report: dict[str, Any],
    policy_hash: str,
    registry_hash: str,
    budgets_hash: str,
    goals: list[tuple[str, str]],
    cap_map: dict[str, dict[str, Any]],
    cap_by_id: dict[str, list[dict[str, Any]]],
    runaway_cfg: dict[str, Any],
    runaway_state: dict[str, Any],
    objectives: dict[str, Any],
    issues: list[dict[str, Any]],
    rules: list[dict[str, Any]],
    tie_break_path: list[str],
) -> tuple[dict[str, Any], str]:
    metrics = observation_report.get("metrics")
    objective_rows = objectives.get("metrics")
    metric_states = runaway_state.get("metric_states")
    if not isinstance(metrics, dict) or not isinstance(objective_rows, list) or not isinstance(metric_states, dict):
        fail("SCHEMA_FAIL")
    runaway_active, forced_escalation_level, runaway_reason = check_runaway_condition(
        observation_report=observation_report,
        runaway_cfg=runaway_cfg,
        runaway_state=runaway_state,
    )
    if not runaway_active:
        fail("SCHEMA_FAIL")
    tie_break_path.append(f"RUNAWAY_REASON:{runaway_reason}")

    candidates: list[dict[str, Any]] = []
    for row in objective_rows:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        metric_id = str(row.get("metric_id", "")).strip()
        direction = str(row.get("direction", "")).strip()
        if not metric_id or direction not in {"MINIMIZE", "MAXIMIZE"}:
            fail("SCHEMA_FAIL")
        metric_state = metric_states.get(metric_id)
        metric_obs = metrics.get(metric_id)
        if not isinstance(metric_state, dict) or metric_obs is None:
            fail("SCHEMA_FAIL")
        last_q = q32_int(metric_state.get("last_value_q32"))
        current_target_q = q32_int(metric_state.get("current_target_q32"))
        gap_q = 0
        if direction == "MINIMIZE":
            gap_q = max(0, int(last_q) - int(current_target_q))
        else:
            gap_q = max(0, int(current_target_q) - int(last_q))
        score_q = q32_mul(gap_q, q32_int(row.get("weight_q32")))
        escalation_level = int(forced_escalation_level)
        campaign_id = resolve_route_campaign(runaway_cfg, metric_id, escalation_level)
        cap = cap_map.get(campaign_id)
        if cap is None or not bool(cap.get("enabled", False)):
            tie_break_path.append(f"RUNAWAY_SKIP:{metric_id}:{campaign_id}:DISABLED")
            continue
        env_overrides = resolve_env_overrides(runaway_cfg, campaign_id, escalation_level)
        candidates.append(
            {
                "metric_id": metric_id,
                "score_q": int(score_q),
                "objective_rank": 0 if metric_id == "OBJ_EXPAND_CAPABILITIES" else 1,
                "campaign_id": campaign_id,
                "capability_id": str(cap.get("capability_id")),
                "campaign_pack_hash": canon_hash_obj({"campaign_pack_rel": cap.get("campaign_pack_rel")}),
                "expected_verifier_module": str(cap.get("verifier_module")),
                "escalation_level_u64": int(escalation_level),
                "env_overrides": env_overrides,
            }
        )

    if not candidates:
        tie_break_path.append("RUNAWAY_NO_CANDIDATE")
        goal_candidate = _goal_plan_candidate(
            tick_u64=tick_u64,
            state=state,
            pending_goals=goals,
            cap_by_id=cap_by_id,
            tie_break_path=tie_break_path,
            tie_break_prefix="RUNAWAY_NO_CANDIDATE_FALLBACK",
        )
        if goal_candidate is not None:
            tie_break_path.append("RUNAWAY_NO_CANDIDATE_FALLBACK:GOAL_SELECTED")
            fallback_escalation_level = int(forced_escalation_level)
            fallback_env_overrides = resolve_env_overrides(
                runaway_cfg, str(goal_candidate["campaign_id"]), fallback_escalation_level
            )
            return _finalize_plan(
                {
                    "schema_version": "omega_decision_plan_v1",
                    "plan_id": "sha256:" + "0" * 64,
                    "tick_u64": int(tick_u64),
                    "observation_report_hash": observation_report_hash,
                    "issue_bundle_hash": issue_bundle_hash,
                    "policy_hash": policy_hash,
                    "registry_hash": registry_hash,
                    "budgets_hash": budgets_hash,
                    "action_kind": "RUN_GOAL_TASK",
                    "goal_id": goal_candidate["goal_id"],
                    "assigned_capability_id": goal_candidate["assigned_capability_id"],
                    "campaign_id": goal_candidate["campaign_id"],
                    "capability_id": goal_candidate["capability_id"],
                    "campaign_pack_hash": goal_candidate["campaign_pack_hash"],
                    "expected_verifier_module": goal_candidate["expected_verifier_module"],
                    "priority_q32": goal_candidate["priority_q32"],
                    "runaway_selected_metric_id": "RUNAWAY_NO_CANDIDATE",
                    "runaway_escalation_level_u64": int(fallback_escalation_level),
                    "runaway_env_overrides": fallback_env_overrides,
                    "tie_break_path": tie_break_path,
                    "recompute_proof": {"inputs_hash": "sha256:" + "0" * 64, "plan_hash": "sha256:" + "0" * 64},
                }
            )
        return _finalize_plan(
            {
                "schema_version": "omega_decision_plan_v1",
                "plan_id": "sha256:" + "0" * 64,
                "tick_u64": int(tick_u64),
                "observation_report_hash": observation_report_hash,
                "issue_bundle_hash": issue_bundle_hash,
                "policy_hash": policy_hash,
                "registry_hash": registry_hash,
                "budgets_hash": budgets_hash,
                "action_kind": "NOOP",
                "tie_break_path": tie_break_path,
                "recompute_proof": {"inputs_hash": "sha256:" + "0" * 64, "plan_hash": "sha256:" + "0" * 64},
            }
        )

    candidates.sort(
        key=lambda row: (
            int(row.get("objective_rank", 1)),
            -int(row["score_q"]),
            str(row["metric_id"]),
            str(row["campaign_id"]),
        )
    )
    for row in candidates:
        tie_break_path.append(
            f"RUNAWAY_CAND:{row['metric_id']}:{row['campaign_id']}:score={row['score_q']}:lvl={row['escalation_level_u64']}"
        )

    winner: dict[str, Any] | None = None
    for row in candidates:
        campaign_id = str(row["campaign_id"])
        cap = cap_map[campaign_id]
        cooldown = ((state.get("cooldowns") or {}).get(campaign_id) or {}).get("next_tick_allowed_u64", 0)
        if int(cooldown) > int(tick_u64):
            tie_break_path.append(f"RUNAWAY_SKIP:{campaign_id}:COOLDOWN")
            continue
        cost_q = int(((cap.get("budget_cost_hint_q32") or {}).get("q", 0)))
        if not has_budget(state.get("budget_remaining") or {}, cost_q32=cost_q):
            tie_break_path.append(f"RUNAWAY_SKIP:{campaign_id}:BUDGET")
            continue
        winner = row
        break

    if winner is None:
        tie_break_path.append("RUNAWAY_BLOCKED")
        goal_candidate = _goal_plan_candidate(
            tick_u64=tick_u64,
            state=state,
            pending_goals=goals,
            cap_by_id=cap_by_id,
            tie_break_path=tie_break_path,
            tie_break_prefix="RUNAWAY_FALLBACK",
        )
        if goal_candidate is not None:
            tie_break_path.append("RUNAWAY_FALLBACK:GOAL_SELECTED")
            fallback_escalation_level = int(forced_escalation_level)
            fallback_env_overrides = resolve_env_overrides(
                runaway_cfg, str(goal_candidate["campaign_id"]), fallback_escalation_level
            )
            return _finalize_plan(
                {
                    "schema_version": "omega_decision_plan_v1",
                    "plan_id": "sha256:" + "0" * 64,
                    "tick_u64": int(tick_u64),
                    "observation_report_hash": observation_report_hash,
                    "issue_bundle_hash": issue_bundle_hash,
                    "policy_hash": policy_hash,
                    "registry_hash": registry_hash,
                    "budgets_hash": budgets_hash,
                    "action_kind": "RUN_GOAL_TASK",
                    "goal_id": goal_candidate["goal_id"],
                    "assigned_capability_id": goal_candidate["assigned_capability_id"],
                    "campaign_id": goal_candidate["campaign_id"],
                    "capability_id": goal_candidate["capability_id"],
                    "campaign_pack_hash": goal_candidate["campaign_pack_hash"],
                    "expected_verifier_module": goal_candidate["expected_verifier_module"],
                    "priority_q32": goal_candidate["priority_q32"],
                    "runaway_selected_metric_id": "RUNAWAY_BLOCKED",
                    "runaway_escalation_level_u64": int(fallback_escalation_level),
                    "runaway_env_overrides": fallback_env_overrides,
                    "tie_break_path": tie_break_path,
                    "recompute_proof": {"inputs_hash": "sha256:" + "0" * 64, "plan_hash": "sha256:" + "0" * 64},
                }
            )

        fallback_candidates = _rule_candidates(
            tick_u64=tick_u64,
            state=state,
            issues=issues,
            rules=rules,
            metrics=metrics,
            cap_map=cap_map,
            tie_break_path=tie_break_path,
            tie_break_prefix="RUNAWAY_FALLBACK",
        )
        if fallback_candidates:
            fallback_candidates.sort(
                key=lambda row: (
                    -int(row["priority_q"]),
                    -int(row["severity_q"]),
                    str(row["rule_id"]),
                    str(row["campaign_id"]),
                )
            )
            for row in fallback_candidates:
                tie_break_path.append(
                    f"RUNAWAY_FALLBACK:CAND:{row['campaign_id']}:priority={row['priority_q']}:"
                    f"severity={row['severity_q']}:rule={row['rule_id']}"
                )
            winner_fallback = fallback_candidates[0]
            tie_break_path.append("RUNAWAY_FALLBACK:RULE_SELECTED")
            return _finalize_plan(
                {
                    "schema_version": "omega_decision_plan_v1",
                    "plan_id": "sha256:" + "0" * 64,
                    "tick_u64": int(tick_u64),
                    "observation_report_hash": observation_report_hash,
                    "issue_bundle_hash": issue_bundle_hash,
                    "policy_hash": policy_hash,
                    "registry_hash": registry_hash,
                    "budgets_hash": budgets_hash,
                    "action_kind": "RUN_CAMPAIGN",
                    "campaign_id": winner_fallback["campaign_id"],
                    "capability_id": winner_fallback["capability_id"],
                    "campaign_pack_hash": winner_fallback["campaign_pack_hash"],
                    "expected_verifier_module": winner_fallback["expected_verifier_module"],
                    "priority_q32": {"q": int(winner_fallback["priority_q"])},
                    "tie_break_path": tie_break_path,
                    "recompute_proof": {"inputs_hash": "sha256:" + "0" * 64, "plan_hash": "sha256:" + "0" * 64},
                }
            )

        tie_break_path.append("RUNAWAY_FALLBACK:NO_MATCH")
        return _finalize_plan(
            {
                "schema_version": "omega_decision_plan_v1",
                "plan_id": "sha256:" + "0" * 64,
                "tick_u64": int(tick_u64),
                "observation_report_hash": observation_report_hash,
                "issue_bundle_hash": issue_bundle_hash,
                "policy_hash": policy_hash,
                "registry_hash": registry_hash,
                "budgets_hash": budgets_hash,
                "action_kind": "NOOP",
                "tie_break_path": tie_break_path,
                "recompute_proof": {"inputs_hash": "sha256:" + "0" * 64, "plan_hash": "sha256:" + "0" * 64},
            }
        )

    goal_id = ""
    for pending_goal_id, capability_id in goals:
        if capability_id == winner["capability_id"]:
            goal_id = pending_goal_id
            break

    action_kind = "RUN_GOAL_TASK" if goal_id else "RUN_CAMPAIGN"
    plan = {
        "schema_version": "omega_decision_plan_v1",
        "plan_id": "sha256:" + "0" * 64,
        "tick_u64": int(tick_u64),
        "observation_report_hash": observation_report_hash,
        "issue_bundle_hash": issue_bundle_hash,
        "policy_hash": policy_hash,
        "registry_hash": registry_hash,
        "budgets_hash": budgets_hash,
        "action_kind": action_kind,
        "campaign_id": winner["campaign_id"],
        "capability_id": winner["capability_id"],
        "campaign_pack_hash": winner["campaign_pack_hash"],
        "expected_verifier_module": winner["expected_verifier_module"],
        "priority_q32": {"q": int(winner["score_q"])},
        "runaway_selected_metric_id": winner["metric_id"],
        "runaway_escalation_level_u64": int(winner["escalation_level_u64"]),
        "runaway_env_overrides": dict(winner["env_overrides"]),
        "tie_break_path": tie_break_path,
        "recompute_proof": {"inputs_hash": "sha256:" + "0" * 64, "plan_hash": "sha256:" + "0" * 64},
    }
    if goal_id:
        plan["goal_id"] = goal_id
        plan["assigned_capability_id"] = winner["capability_id"]
        tie_break_path.append(f"RUNAWAY_GOAL:{goal_id}")
    return _finalize_plan(plan)


def decide(
    *,
    tick_u64: int,
    state: dict[str, Any],
    observation_report_hash: str,
    issue_bundle_hash: str,
    observation_report: dict[str, Any],
    issue_bundle: dict[str, Any],
    policy: dict[str, Any],
    policy_hash: str,
    registry: dict[str, Any],
    registry_hash: str,
    budgets_hash: str,
    goal_queue: dict[str, Any],
    objectives: dict[str, Any] | None = None,
    runaway_cfg: dict[str, Any] | None = None,
    runaway_state: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    tie_break_path: list[str] = []

    if state.get("policy_hash") != policy_hash:
        tie_break_path.append("SAFE_HALT:POLICY_HASH_MISMATCH")
        return _safe_halt_plan(
            tick_u64=tick_u64,
            observation_report_hash=observation_report_hash,
            issue_bundle_hash=issue_bundle_hash,
            policy_hash=policy_hash,
            registry_hash=registry_hash,
            budgets_hash=budgets_hash,
            tie_break_path=tie_break_path,
        )
    if state.get("registry_hash") != registry_hash:
        tie_break_path.append("SAFE_HALT:REGISTRY_HASH_MISMATCH")
        return _safe_halt_plan(
            tick_u64=tick_u64,
            observation_report_hash=observation_report_hash,
            issue_bundle_hash=issue_bundle_hash,
            policy_hash=policy_hash,
            registry_hash=registry_hash,
            budgets_hash=budgets_hash,
            tie_break_path=tie_break_path,
        )

    rules = policy.get("rules")
    issues = issue_bundle.get("issues")
    metrics = observation_report.get("metrics")
    if not isinstance(rules, list) or not isinstance(issues, list) or not isinstance(metrics, dict):
        fail("SCHEMA_FAIL")

    temp_band = _temperature_band(observation_report)
    tie_break_path.append(f"TEMP:{temp_band}")

    pending_goals, cap_map, cap_by_id = _pending_goals_and_caps(
        state=state,
        goal_queue=goal_queue,
        registry=registry,
        tie_break_path=tie_break_path,
    )
    pending_goals.sort(key=lambda item: (_goal_class_rank(_goal_class(item[0]), temp_band), item[0]))
    for goal_id, _capability_id in pending_goals:
        tie_break_path.append(f"GOAL_CLASS:{_goal_class(goal_id)}:{goal_id}")

    if runaway_enabled(runaway_cfg):
        if not isinstance(runaway_cfg, dict) or not isinstance(runaway_state, dict) or not isinstance(objectives, dict):
            fail("SCHEMA_FAIL")
        return _runaway_decision(
            tick_u64=tick_u64,
            state=state,
            observation_report_hash=observation_report_hash,
            issue_bundle_hash=issue_bundle_hash,
            observation_report=observation_report,
            policy_hash=policy_hash,
            registry_hash=registry_hash,
            budgets_hash=budgets_hash,
            goals=pending_goals,
            cap_map=cap_map,
            cap_by_id=cap_by_id,
            runaway_cfg=runaway_cfg,
            runaway_state=runaway_state,
            objectives=objectives,
            issues=issues,
            rules=rules,
            tie_break_path=tie_break_path,
        )

    goal_candidate = _goal_plan_candidate(
        tick_u64=tick_u64,
        state=state,
        pending_goals=pending_goals,
        cap_by_id=cap_by_id,
        tie_break_path=tie_break_path,
    )
    if goal_candidate is not None:
        plan = {
            "schema_version": "omega_decision_plan_v1",
            "plan_id": "sha256:" + "0" * 64,
            "tick_u64": int(tick_u64),
            "observation_report_hash": observation_report_hash,
            "issue_bundle_hash": issue_bundle_hash,
            "policy_hash": policy_hash,
            "registry_hash": registry_hash,
            "budgets_hash": budgets_hash,
            "action_kind": "RUN_GOAL_TASK",
            "goal_id": goal_candidate["goal_id"],
            "assigned_capability_id": goal_candidate["assigned_capability_id"],
            "campaign_id": goal_candidate["campaign_id"],
            "capability_id": goal_candidate["capability_id"],
            "campaign_pack_hash": goal_candidate["campaign_pack_hash"],
            "expected_verifier_module": goal_candidate["expected_verifier_module"],
            "priority_q32": goal_candidate["priority_q32"],
            "tie_break_path": tie_break_path,
            "recompute_proof": {"inputs_hash": "sha256:" + "0" * 64, "plan_hash": "sha256:" + "0" * 64},
        }
        return _finalize_plan(plan)

    candidates = _rule_candidates(
        tick_u64=tick_u64,
        state=state,
        issues=issues,
        rules=rules,
        metrics=metrics,
        cap_map=cap_map,
        tie_break_path=tie_break_path,
    )

    if goal_queue.get("goals") and not pending_goals:
        tie_break_path.append("GOALS_COMPLETE:NOOP")
        return _finalize_plan(
            {
                "schema_version": "omega_decision_plan_v1",
                "plan_id": "sha256:" + "0" * 64,
                "tick_u64": int(tick_u64),
                "observation_report_hash": observation_report_hash,
                "issue_bundle_hash": issue_bundle_hash,
                "policy_hash": policy_hash,
                "registry_hash": registry_hash,
                "budgets_hash": budgets_hash,
                "action_kind": "NOOP",
                "tie_break_path": tie_break_path,
                "recompute_proof": {"inputs_hash": "sha256:" + "0" * 64, "plan_hash": "sha256:" + "0" * 64},
            }
        )

    if not candidates:
        tie_break_path.append("NO_MATCH")
        return _finalize_plan(
            {
                "schema_version": "omega_decision_plan_v1",
                "plan_id": "sha256:" + "0" * 64,
                "tick_u64": int(tick_u64),
                "observation_report_hash": observation_report_hash,
                "issue_bundle_hash": issue_bundle_hash,
                "policy_hash": policy_hash,
                "registry_hash": registry_hash,
                "budgets_hash": budgets_hash,
                "action_kind": "NOOP",
                "tie_break_path": tie_break_path,
                "recompute_proof": {"inputs_hash": "sha256:" + "0" * 64, "plan_hash": "sha256:" + "0" * 64},
            }
        )

    candidates.sort(
        key=lambda row: (
            -int(row["priority_q"]),
            -int(row["severity_q"]),
            str(row["rule_id"]),
            str(row["campaign_id"]),
        )
    )
    winner = candidates[0]
    for row in candidates:
        tie_break_path.append(
            f"CAND:{row['campaign_id']}:priority={row['priority_q']}:severity={row['severity_q']}:rule={row['rule_id']}"
        )

    plan = {
        "schema_version": "omega_decision_plan_v1",
        "plan_id": "sha256:" + "0" * 64,
        "tick_u64": int(tick_u64),
        "observation_report_hash": observation_report_hash,
        "issue_bundle_hash": issue_bundle_hash,
        "policy_hash": policy_hash,
        "registry_hash": registry_hash,
        "budgets_hash": budgets_hash,
        "action_kind": "RUN_CAMPAIGN",
        "campaign_id": winner["campaign_id"],
        "capability_id": winner["capability_id"],
        "campaign_pack_hash": winner["campaign_pack_hash"],
        "expected_verifier_module": winner["expected_verifier_module"],
        "priority_q32": {"q": int(winner["priority_q"])},
        "tie_break_path": tie_break_path,
        "recompute_proof": {"inputs_hash": "sha256:" + "0" * 64, "plan_hash": "sha256:" + "0" * 64},
    }
    return _finalize_plan(plan)


def _finalize_plan(plan: dict[str, Any]) -> tuple[dict[str, Any], str]:
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
    plan["recompute_proof"] = {"inputs_hash": inputs_hash, "plan_hash": "sha256:" + "0" * 64}
    no_id = dict(plan)
    no_id.pop("plan_id", None)
    plan_id = canon_hash_obj(no_id)
    plan["plan_id"] = plan_id
    plan["recompute_proof"] = {"inputs_hash": inputs_hash, "plan_hash": plan_id}
    validate_schema(plan, "omega_decision_plan_v1")
    return plan, canon_hash_obj(plan)


def _safe_halt_plan(
    *,
    tick_u64: int,
    observation_report_hash: str,
    issue_bundle_hash: str,
    policy_hash: str,
    registry_hash: str,
    budgets_hash: str,
    tie_break_path: list[str],
) -> tuple[dict[str, Any], str]:
    plan = {
        "schema_version": "omega_decision_plan_v1",
        "plan_id": "sha256:" + "0" * 64,
        "tick_u64": int(tick_u64),
        "observation_report_hash": observation_report_hash,
        "issue_bundle_hash": issue_bundle_hash,
        "policy_hash": policy_hash,
        "registry_hash": registry_hash,
        "budgets_hash": budgets_hash,
        "action_kind": "SAFE_HALT",
        "tie_break_path": tie_break_path,
        "recompute_proof": {"inputs_hash": "sha256:" + "0" * 64, "plan_hash": "sha256:" + "0" * 64},
    }
    return _finalize_plan(plan)


__all__ = ["decide"]
