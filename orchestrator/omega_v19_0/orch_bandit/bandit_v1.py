"""Deterministic contextual bandit v1 for orchestration routing."""

from __future__ import annotations

from typing import Any, Mapping

from cdel.v18_0.omega_common_v1 import canon_hash_obj


Q32_ONE = 1 << 32
_LANE_KINDS = {"BASELINE", "FRONTIER_HEAVY", "UNKNOWN"}


class BanditError(RuntimeError):
    """Deterministic bandit failure with an explicit reason code."""


def _bandit_fail(reason_code: str) -> None:
    raise BanditError(str(reason_code))


def _as_nonneg_int(value: Any) -> int:
    return int(max(0, int(value)))


def _state_limits(config: Mapping[str, Any]) -> tuple[int, int]:
    max_contexts_u32 = max(1, int(config.get("max_contexts_u32", 1)))
    max_arms_u32 = max(1, int(config.get("max_arms_per_context_u32", 1)))
    return int(max_contexts_u32), int(max_arms_u32)


def _normalize_lane_kind(lane_kind: Any) -> str:
    lane = str(lane_kind).strip().upper()
    if lane not in _LANE_KINDS:
        return "UNKNOWN"
    return lane


def _runaway_band_u32(runaway_level_u32: Any) -> int:
    return int(min(_as_nonneg_int(runaway_level_u32), 5))


def _q32_mul(a_q32: int, b_q32: int) -> int:
    prod = int(a_q32) * int(b_q32)
    if prod >= 0:
        return int(prod // Q32_ONE)
    return int(-((-prod) // Q32_ONE))


def _q32_add(a_q32: int, b_q32: int) -> int:
    return int(int(a_q32) + int(b_q32))


def _context_rows_with_bounds(*, state: Mapping[str, Any], max_contexts_u32: int, max_arms_u32: int) -> list[dict[str, Any]]:
    contexts_raw = state.get("contexts")
    if not isinstance(contexts_raw, list):
        return []
    if len(contexts_raw) > int(max_contexts_u32):
        _bandit_fail("BANDIT_FAIL:CONTEXT_LIMIT")
    contexts: list[dict[str, Any]] = []
    scanned = 0
    for row in contexts_raw:
        scanned += 1
        if scanned > int(max_contexts_u32):
            _bandit_fail("BANDIT_FAIL:CONTEXT_LIMIT")
        if not isinstance(row, dict):
            continue
        arms_raw = row.get("arms")
        if not isinstance(arms_raw, list):
            _bandit_fail("BANDIT_FAIL:ARM_LIMIT")
        if len(arms_raw) > int(max_arms_u32):
            _bandit_fail("BANDIT_FAIL:ARM_LIMIT")
        arm_scanned = 0
        for arm_row in arms_raw:
            arm_scanned += 1
            if arm_scanned > int(max_arms_u32):
                _bandit_fail("BANDIT_FAIL:ARM_LIMIT")
            if not isinstance(arm_row, dict):
                _bandit_fail("BANDIT_FAIL:ARM_LIMIT")
        contexts.append(dict(row))
    return contexts


def compute_context_key(*, lane_kind: str, runaway_level_u32: int, objective_kind: str) -> str:
    lane = _normalize_lane_kind(lane_kind)
    runaway_band_u32 = _runaway_band_u32(runaway_level_u32)
    payload = {
        "lane_kind": lane,
        "runaway_band_u32": int(runaway_band_u32),
        "objective_kind": str(objective_kind),
    }
    return canon_hash_obj(payload)


def compute_cost_norm_q32(*, wallclock_ms_u64: int, cost_scale_ms_u64: int) -> int:
    scale = int(cost_scale_ms_u64)
    if scale <= 0:
        raise ValueError("cost_scale_ms_u64 must be > 0")
    wallclock_ms = _as_nonneg_int(wallclock_ms_u64)
    value = (wallclock_ms * Q32_ONE) // scale
    return int(min(Q32_ONE, int(value)))


def _eligible_capability_ids_with_bounds(*, eligible_capability_ids: list[str], max_arms_u32: int) -> list[str]:
    eligible_sorted = sorted({str(row).strip() for row in eligible_capability_ids if str(row).strip()})
    if not eligible_sorted:
        _bandit_fail("BANDIT_FAIL:NO_ELIGIBLE_ARMS")
    if len(eligible_sorted) > int(max_arms_u32):
        _bandit_fail("BANDIT_FAIL:ARM_LIMIT")
    return eligible_sorted


def _arms_by_capability_for_context(
    *,
    contexts: list[dict[str, Any]],
    context_key: str,
    max_arms_u32: int,
) -> dict[str, dict[str, Any]]:
    context_row: dict[str, Any] | None = None
    for row in contexts:
        if str(row.get("context_key", "")).strip() == str(context_key).strip():
            context_row = row
            break

    arms_by_capability: dict[str, dict[str, Any]] = {}
    if not isinstance(context_row, dict):
        return arms_by_capability
    arms_raw = context_row.get("arms")
    if not isinstance(arms_raw, list):
        _bandit_fail("BANDIT_FAIL:ARM_LIMIT")
    if len(arms_raw) > int(max_arms_u32):
        _bandit_fail("BANDIT_FAIL:ARM_LIMIT")
    scanned = 0
    for arm in arms_raw:
        scanned += 1
        if scanned > int(max_arms_u32):
            _bandit_fail("BANDIT_FAIL:ARM_LIMIT")
        if not isinstance(arm, dict):
            _bandit_fail("BANDIT_FAIL:ARM_LIMIT")
        capability_id = str(arm.get("capability_id", "")).strip()
        if not capability_id:
            continue
        arms_by_capability[capability_id] = dict(arm)
    return arms_by_capability


def compute_arm_scores_q32(
    *,
    config: Mapping[str, Any],
    state: Mapping[str, Any],
    context_key: str,
    eligible_capability_ids: list[str],
) -> dict[str, int]:
    max_contexts_u32, max_arms_u32 = _state_limits(config)
    contexts = _context_rows_with_bounds(state=state, max_contexts_u32=max_contexts_u32, max_arms_u32=max_arms_u32)
    eligible_sorted = _eligible_capability_ids_with_bounds(
        eligible_capability_ids=list(eligible_capability_ids),
        max_arms_u32=max_arms_u32,
    )
    arms_by_capability = _arms_by_capability_for_context(
        contexts=contexts,
        context_key=context_key,
        max_arms_u32=max_arms_u32,
    )

    min_trials_before_exploit_u32 = _as_nonneg_int(config.get("min_trials_before_exploit_u32", 0))
    explore_weight_q32 = int(config.get("explore_weight_q32", 0))
    cost_weight_q32 = int(config.get("cost_weight_q32", 0))

    scores_by_capability: dict[str, int] = {}
    for capability_id in eligible_sorted:
        arm_row = arms_by_capability.get(str(capability_id), {})
        n_u64 = _as_nonneg_int(arm_row.get("n_u64", 0))
        reward_ewma_q32 = int(arm_row.get("reward_ewma_q32", 0))
        cost_ewma_q32 = _as_nonneg_int(arm_row.get("cost_ewma_q32", 0))

        if n_u64 < int(min_trials_before_exploit_u32):
            explore_bonus_q32 = int(Q32_ONE)
        else:
            explore_bonus_q32 = int(explore_weight_q32 // (n_u64 + 1))

        score_q32 = int(reward_ewma_q32) - int(_q32_mul(int(cost_weight_q32), int(cost_ewma_q32))) + int(explore_bonus_q32)
        scores_by_capability[str(capability_id)] = int(score_q32)
    return scores_by_capability


def _select_from_scores(*, scores_by_capability: Mapping[str, int]) -> str:
    selected: str | None = None
    best_score_q32: int | None = None
    for capability_id in sorted(str(key) for key in scores_by_capability.keys()):
        score_q32 = int(scores_by_capability.get(capability_id, 0))
        if best_score_q32 is None or score_q32 > int(best_score_q32):
            best_score_q32 = int(score_q32)
            selected = str(capability_id)
    if not isinstance(selected, str) or not selected:
        _bandit_fail("BANDIT_FAIL:NO_ELIGIBLE_ARMS")
    return selected


def select_capability_id(
    *,
    config: Mapping[str, Any],
    state: Mapping[str, Any],
    context_key: str,
    eligible_capability_ids: list[str],
) -> str:
    scores_by_capability = compute_arm_scores_q32(
        config=config,
        state=state,
        context_key=context_key,
        eligible_capability_ids=list(eligible_capability_ids),
    )
    return _select_from_scores(scores_by_capability=scores_by_capability)


def select_capability_id_with_bonus(
    *,
    config: Mapping[str, Any],
    state: Mapping[str, Any],
    context_key: str,
    eligible_capability_ids: list[str],
    bonus_by_capability_q32: Mapping[str, int],
) -> str:
    scores_by_capability = compute_arm_scores_q32(
        config=config,
        state=state,
        context_key=context_key,
        eligible_capability_ids=list(eligible_capability_ids),
    )
    adjusted_scores: dict[str, int] = {}
    for capability_id, score_q32 in sorted(scores_by_capability.items(), key=lambda row: str(row[0])):
        bonus_q32 = int(bonus_by_capability_q32.get(str(capability_id), 0))
        adjusted_scores[str(capability_id)] = int(score_q32) + int(bonus_q32)
    return _select_from_scores(scores_by_capability=adjusted_scores)


def update_bandit_state(
    *,
    config: Mapping[str, Any],
    state_in: Mapping[str, Any],
    state_in_id: str,
    tick_u64: int,
    ek_id: str,
    kernel_ledger_id: str,
    context_key: str,
    lane_kind: str,
    runaway_band_u32: int,
    objective_kind: str,
    selected_capability_id: str,
    observed_reward_q32: int,
    observed_cost_q32: int,
) -> dict[str, Any]:
    max_contexts_u32, max_arms_u32 = _state_limits(config)
    contexts = _context_rows_with_bounds(state=state_in, max_contexts_u32=max_contexts_u32, max_arms_u32=max_arms_u32)

    context_key_norm = str(context_key).strip()
    if not context_key_norm:
        _bandit_fail("BANDIT_FAIL:CONTEXT_LIMIT")
    capability_id_norm = str(selected_capability_id).strip()
    if not capability_id_norm:
        _bandit_fail("BANDIT_FAIL:NO_ELIGIBLE_ARMS")

    lane_kind_norm = _normalize_lane_kind(lane_kind)
    runaway_band_norm = _runaway_band_u32(runaway_band_u32)
    objective_kind_norm = str(objective_kind)

    context_row: dict[str, Any] | None = None
    for row in contexts:
        if str(row.get("context_key", "")).strip() == context_key_norm:
            context_row = row
            break

    if context_row is None:
        if len(contexts) >= int(max_contexts_u32):
            _bandit_fail("BANDIT_FAIL:CONTEXT_LIMIT")
        context_row = {
            "context_key": context_key_norm,
            "lane_kind": lane_kind_norm,
            "runaway_band_u32": int(runaway_band_norm),
            "objective_kind": objective_kind_norm,
            "arms": [],
        }
        contexts.append(context_row)

    context_row["context_key"] = context_key_norm
    context_row["lane_kind"] = lane_kind_norm
    context_row["runaway_band_u32"] = int(runaway_band_norm)
    context_row["objective_kind"] = objective_kind_norm

    arms_raw = context_row.get("arms")
    if not isinstance(arms_raw, list):
        _bandit_fail("BANDIT_FAIL:ARM_LIMIT")
    if len(arms_raw) > int(max_arms_u32):
        _bandit_fail("BANDIT_FAIL:ARM_LIMIT")

    arms: list[dict[str, Any]] = [dict(row) for row in arms_raw if isinstance(row, dict)]
    arm_row: dict[str, Any] | None = None
    scanned = 0
    for row in arms:
        scanned += 1
        if scanned > int(max_arms_u32):
            _bandit_fail("BANDIT_FAIL:ARM_LIMIT")
        if str(row.get("capability_id", "")).strip() == capability_id_norm:
            arm_row = row
            break

    if arm_row is None:
        if len(arms) >= int(max_arms_u32):
            _bandit_fail("BANDIT_FAIL:ARM_LIMIT")
        arm_row = {
            "capability_id": capability_id_norm,
            "n_u64": 0,
            "reward_ewma_q32": 0,
            "cost_ewma_q32": 0,
            "last_update_tick_u64": 0,
        }
        arms.append(arm_row)

    alpha_q32 = _as_nonneg_int(config.get("alpha_q32", 0))
    if alpha_q32 > int(Q32_ONE):
        alpha_q32 = int(Q32_ONE)
    one_minus_alpha_q32 = int(Q32_ONE - int(alpha_q32))

    old_reward_q32 = int(arm_row.get("reward_ewma_q32", 0))
    old_cost_q32 = _as_nonneg_int(arm_row.get("cost_ewma_q32", 0))
    reward_q32 = int(observed_reward_q32)
    cost_q32 = _as_nonneg_int(observed_cost_q32)

    new_reward_q32 = _q32_add(
        _q32_mul(one_minus_alpha_q32, old_reward_q32),
        _q32_mul(int(alpha_q32), reward_q32),
    )
    new_cost_q32 = _q32_add(
        _q32_mul(one_minus_alpha_q32, old_cost_q32),
        _q32_mul(int(alpha_q32), cost_q32),
    )

    arm_row["capability_id"] = capability_id_norm
    arm_row["n_u64"] = int(_as_nonneg_int(arm_row.get("n_u64", 0)) + 1)
    arm_row["reward_ewma_q32"] = int(new_reward_q32)
    arm_row["cost_ewma_q32"] = int(max(0, int(new_cost_q32)))
    arm_row["last_update_tick_u64"] = int(_as_nonneg_int(tick_u64))

    context_row["arms"] = sorted(
        [dict(row) for row in arms],
        key=lambda row: str(row.get("capability_id", "")),
    )

    state_out = {
        "schema_version": "orch_bandit_state_v1",
        "tick_u64": int(_as_nonneg_int(tick_u64)),
        "parent_state_hash": str(state_in_id),
        "ek_id": str(ek_id),
        "kernel_ledger_id": str(kernel_ledger_id),
        "contexts": sorted(
            [
                {
                    "context_key": str(row.get("context_key", "")).strip(),
                    "lane_kind": _normalize_lane_kind(row.get("lane_kind")),
                    "runaway_band_u32": _runaway_band_u32(row.get("runaway_band_u32", 0)),
                    "objective_kind": str(row.get("objective_kind", "")),
                    "arms": [dict(arm) for arm in list(row.get("arms") or [])],
                }
                for row in contexts
            ],
            key=lambda row: str(row.get("context_key", "")),
        ),
    }
    return state_out


__all__ = [
    "BanditError",
    "Q32_ONE",
    "compute_arm_scores_q32",
    "compute_context_key",
    "compute_cost_norm_q32",
    "select_capability_id",
    "select_capability_id_with_bonus",
    "update_bandit_state",
]
