"""RE2 verifier for deterministic orchestration bandit v1."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...v18_0.omega_common_v1 import canon_hash_obj, fail as fail_v18, load_canon_dict
from ..common_v1 import validate_schema as validate_schema_v19
from orchestrator.omega_v19_0.governance.frontier_lock_v1 import (
    compute_debt_pressure_v1 as compute_governance_debt_pressure_v1,
)
from orchestrator.omega_v19_0.orch_bandit.bandit_v1 import (
    BanditError as OrchBanditError,
    compute_context_key,
    compute_cost_norm_q32,
    select_capability_id,
    select_capability_id_with_bonus,
    update_bandit_state,
)


_HEAVY_DECLARED_CLASSES = {"FRONTIER_HEAVY", "CANARY_HEAVY"}
_PROMOTION_RESULT_KINDS = {
    "PROMOTED_COMMIT",
    "PROMOTED_EXT_QUEUED",
    "PROMOTED_POLICY_UPDATE",
    "REJECTED",
}
_TOXIC_REASON_PREFIXES = (
    "HOLDOUT_",
    "PHASE1_PUBLIC_ONLY_VIOLATION",
    "SANDBOX_",
)
_TOXIC_REASON_EXACT = {
    "CCAP_ALLOWLIST_VIOLATION",
    "CCAP_PATCH_ALLOWLIST_VIOLATION",
    "BUDGET_EXHAUSTED",
}
_Q32_ONE = 1 << 32
_ORCH_REWARD_COMMIT_Q32 = _Q32_ONE
_ORCH_REWARD_EXT_Q32 = _Q32_ONE // 2
_ORCH_REWARD_TOXIC_Q32 = -(_Q32_ONE // 2)
_ORCH_REWARD_HEAVY_UTILITY_BONUS_Q32 = _Q32_ONE // 4
_ORCH_POLICY_BONUS_ABS_Q32 = _Q32_ONE // 4


def _is_sha256(value: Any) -> bool:
    raw = str(value).strip()
    return raw.startswith("sha256:") and len(raw) == 71 and all(ch in "0123456789abcdef" for ch in raw.split(":", 1)[1])


def _require_sha256(value: Any, *, reason: str = "SCHEMA_FAIL") -> str:
    raw = str(value).strip()
    if not _is_sha256(raw):
        fail_v18(reason)
    return raw


def _load_canon_json(path: Path) -> dict[str, Any]:
    payload = load_canon_dict(path)
    if not isinstance(payload, dict):
        fail_v18("SCHEMA_FAIL")
    return payload


def _path_for_hash(*, dir_path: Path, digest: str, suffix: str) -> Path:
    if not _is_sha256(digest):
        fail_v18("SCHEMA_FAIL")
    hexd = str(digest).split(":", 1)[1]
    path = dir_path / f"sha256_{hexd}.{suffix}"
    if not path.exists() or not path.is_file():
        fail_v18("MISSING_STATE_INPUT")
    return path


def _load_hash_bound_payload(*, dir_path: Path, digest: str, suffix: str, schema_name: str) -> dict[str, Any]:
    path = _path_for_hash(dir_path=dir_path, digest=digest, suffix=suffix)
    payload = _load_canon_json(path)
    if canon_hash_obj(payload) != str(digest):
        fail_v18("NONDETERMINISTIC")
    validate_schema_v19(payload, schema_name)
    return payload


def _find_nested_hash(*, state_root: Path, digest: str, suffix: str) -> Path:
    if not _is_sha256(digest):
        fail_v18("SCHEMA_FAIL")
    hexd = digest.split(":", 1)[1]
    target = f"sha256_{hexd}.{suffix}"
    rows = sorted(state_root.glob(f"dispatch/*/**/{target}"), key=lambda row: row.as_posix())
    if len(rows) != 1:
        fail_v18("MISSING_STATE_INPUT")
    return rows[0]


def _normalize_lane_kind(*, state_root: Path, snapshot: dict[str, Any]) -> str:
    lane_hash = snapshot.get("lane_decision_receipt_hash")
    if not _is_sha256(lane_hash):
        return "UNKNOWN"
    lane_payload = _load_hash_bound_payload(
        dir_path=state_root / "long_run" / "lane",
        digest=str(lane_hash),
        suffix="lane_decision_receipt_v1.json",
        schema_name="lane_decision_receipt_v1",
    )
    lane_name = str(lane_payload.get("lane_name", "")).strip().upper()
    if lane_name == "FRONTIER":
        return "FRONTIER_HEAVY"
    if lane_name in {"BASELINE", "CANARY"}:
        return "BASELINE"
    return "UNKNOWN"


def _load_decision_plan(*, state_root: Path, snapshot: dict[str, Any]) -> dict[str, Any]:
    decision_hash = str(snapshot.get("decision_plan_hash", "")).strip()
    path = _path_for_hash(
        dir_path=state_root / "decisions",
        digest=decision_hash,
        suffix="omega_decision_plan_v1.json",
    )
    payload = _load_canon_json(path)
    if canon_hash_obj(payload) != decision_hash:
        fail_v18("NONDETERMINISTIC")
    return payload


def _load_tick_perf(*, state_root: Path, tick_u64: int) -> dict[str, Any]:
    rows = sorted((state_root / "perf").glob("sha256_*.omega_tick_perf_v1.json"), key=lambda row: row.as_posix())
    for row in rows:
        payload = _load_canon_json(row)
        if int(payload.get("tick_u64", -1)) != int(tick_u64):
            continue
        if canon_hash_obj(payload) != "sha256:" + row.name.split(".", 1)[0].split("_", 1)[1]:
            fail_v18("NONDETERMINISTIC")
        return payload
    fail_v18("MISSING_STATE_INPUT")
    return {}


def _load_optional_utility_policy(*, config_dir: Path) -> dict[str, Any] | None:
    profile_path = config_dir / "long_run_profile_v1.json"
    if not profile_path.exists() or not profile_path.is_file():
        return None
    profile_payload = _load_canon_json(profile_path)
    try:
        validate_schema_v19(profile_payload, "long_run_profile_v1")
    except Exception:
        return None
    rel = str(profile_payload.get("utility_policy_rel", "")).strip()
    if not rel:
        return None
    rel_path = Path(rel)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        fail_v18("SCHEMA_FAIL")
    path = config_dir / rel_path
    if not path.exists() or not path.is_file():
        fail_v18("MISSING_STATE_INPUT")
    payload = _load_canon_json(path)
    validate_schema_v19(payload, "utility_policy_v1")
    return payload


def _orch_policy_root(*, state_root: Path) -> Path:
    try:
        daemon_root = state_root.parents[1]
    except Exception:
        fail_v18("MISSING_STATE_INPUT")
    return daemon_root / "orch_policy"


def _clamp_orch_policy_bonus_q32(value_q32: int) -> int:
    if int(value_q32) < -int(_ORCH_POLICY_BONUS_ABS_Q32):
        return -int(_ORCH_POLICY_BONUS_ABS_Q32)
    if int(value_q32) > int(_ORCH_POLICY_BONUS_ABS_Q32):
        return int(_ORCH_POLICY_BONUS_ABS_Q32)
    return int(value_q32)


def _policy_lookup_from_bundle(bundle_payload: dict[str, Any]) -> dict[str, dict[str, int]]:
    validate_schema_v19(bundle_payload, "orch_policy_bundle_v1")
    bundle_id = _require_sha256(bundle_payload.get("policy_bundle_id"), reason="SCHEMA_FAIL")
    bundle_no_id = dict(bundle_payload)
    bundle_no_id.pop("policy_bundle_id", None)
    if canon_hash_obj(bundle_no_id) != bundle_id:
        fail_v18("NONDETERMINISTIC")

    table_raw = bundle_payload.get("policy_table")
    if not isinstance(table_raw, dict):
        fail_v18("SCHEMA_FAIL")
    table_payload = dict(table_raw)
    validate_schema_v19(table_payload, "orch_policy_table_v1")
    declared_table_id = _require_sha256(bundle_payload.get("policy_table_id"), reason="SCHEMA_FAIL")
    observed_table_id = _require_sha256(table_payload.get("policy_table_id"), reason="SCHEMA_FAIL")
    if observed_table_id != declared_table_id:
        fail_v18("NONDETERMINISTIC")
    table_no_id = dict(table_payload)
    table_no_id.pop("policy_table_id", None)
    if canon_hash_obj(table_no_id) != observed_table_id:
        fail_v18("NONDETERMINISTIC")

    rows_raw = table_payload.get("rows")
    if not isinstance(rows_raw, list):
        fail_v18("SCHEMA_FAIL")
    out: dict[str, dict[str, int]] = {}
    for row in rows_raw:
        if not isinstance(row, dict):
            fail_v18("SCHEMA_FAIL")
        context_key = _require_sha256(row.get("context_key"), reason="SCHEMA_FAIL")
        ranked_raw = row.get("ranked_capabilities")
        if not isinstance(ranked_raw, list):
            fail_v18("SCHEMA_FAIL")
        scores: dict[str, int] = {}
        for ranked in ranked_raw:
            if not isinstance(ranked, dict):
                fail_v18("SCHEMA_FAIL")
            capability_id = str(ranked.get("capability_id", "")).strip()
            if not capability_id:
                fail_v18("SCHEMA_FAIL")
            score_q32 = ranked.get("score_q32")
            if not isinstance(score_q32, int):
                fail_v18("SCHEMA_FAIL")
            if capability_id in scores:
                continue
            scores[capability_id] = int(score_q32)
        if not scores:
            fail_v18("SCHEMA_FAIL")
        if context_key in out:
            fail_v18("NONDETERMINISTIC")
        out[context_key] = scores
    return out


def _load_active_orch_policy_lookup(*, state_root: Path) -> tuple[str | None, dict[str, dict[str, int]] | None]:
    pointer_path = _orch_policy_root(state_root=state_root) / "active" / "ORCH_POLICY_V1.json"
    if not pointer_path.exists() or not pointer_path.is_file():
        return None, None
    pointer_payload = _load_canon_json(pointer_path)
    validate_schema_v19(pointer_payload, "orch_policy_pointer_v1")
    bundle_id = _require_sha256(pointer_payload.get("active_policy_bundle_id"), reason="SCHEMA_FAIL")
    bundle_path = _orch_policy_root(state_root=state_root) / "store" / f"sha256_{bundle_id.split(':', 1)[1]}.orch_policy_bundle_v1.json"
    if not bundle_path.exists() or not bundle_path.is_file():
        fail_v18("MISSING_STATE_INPUT")
    bundle_payload = _load_canon_json(bundle_path)
    observed_bundle_id = _require_sha256(bundle_payload.get("policy_bundle_id"), reason="SCHEMA_FAIL")
    if observed_bundle_id != bundle_id:
        fail_v18("NONDETERMINISTIC")
    lookup = _policy_lookup_from_bundle(bundle_payload)
    return bundle_id, lookup


def _declared_class_for_capability_id(*, utility_policy: dict[str, Any] | None, capability_id: str) -> str:
    if not isinstance(utility_policy, dict):
        return "UNCLASSIFIED"
    mapping = utility_policy.get("declared_class_by_capability")
    if not isinstance(mapping, dict):
        return "UNCLASSIFIED"
    mapped = str(mapping.get(str(capability_id), "")).strip().upper()
    if mapped in {"FRONTIER_HEAVY", "CANARY_HEAVY", "BASELINE_CORE", "MAINTENANCE"}:
        return mapped
    return "UNCLASSIFIED"


def _derive_eligible_capability_ids(
    *,
    config_payload: dict[str, Any],
    registry_payload: dict[str, Any],
    utility_policy: dict[str, Any] | None,
    lane_kind: str,
    hard_lock_active_b: bool,
    selected_capability_id: str,
) -> list[str]:
    max_arms = int(max(1, int(config_payload.get("max_arms_per_context_u32", 1))))
    selected = str(selected_capability_id).strip()
    if bool(hard_lock_active_b):
        if not selected:
            fail_v18("BANDIT_FAIL:HARD_LOCK_EMPTY")
        return [selected]

    caps = registry_payload.get("capabilities")
    if not isinstance(caps, list):
        fail_v18("SCHEMA_FAIL")
    heavy_lane = str(lane_kind).strip() == "FRONTIER_HEAVY"
    out: list[str] = []
    seen: set[str] = set()
    scanned = 0
    for row in sorted([entry for entry in caps if isinstance(entry, dict)], key=lambda entry: str(entry.get("capability_id", ""))):
        scanned += 1
        if scanned > int(max_arms):
            fail_v18("BANDIT_FAIL:ARM_LIMIT")
        capability_id = str(row.get("capability_id", "")).strip()
        if not capability_id or capability_id in seen:
            continue
        if not bool(row.get("enabled", False)):
            continue
        declared_class = _declared_class_for_capability_id(
            utility_policy=utility_policy,
            capability_id=capability_id,
        )
        is_heavy = declared_class in _HEAVY_DECLARED_CLASSES
        if heavy_lane and not is_heavy:
            continue
        if (not heavy_lane) and is_heavy:
            continue
        out.append(capability_id)
        seen.add(capability_id)
        if len(out) > int(max_arms):
            fail_v18("BANDIT_FAIL:ARM_LIMIT")
    out = sorted(out)
    if not out:
        fail_v18("BANDIT_FAIL:NO_ELIGIBLE_ARMS")
    return out


def _normalize_promotion_result_kind(*, result_kind: Any, status: Any, activation_kind: Any) -> str:
    kind = str(result_kind).strip()
    if kind in _PROMOTION_RESULT_KINDS:
        return kind
    normalized_status = str(status).strip().upper()
    if normalized_status == "PROMOTED":
        normalized_activation_kind = str(activation_kind).strip()
        if normalized_activation_kind == "ACTIVATION_KIND_EXT_QUEUED":
            return "PROMOTED_EXT_QUEUED"
        if normalized_activation_kind == "ACTIVATION_KIND_ORCH_POLICY_UPDATE":
            return "PROMOTED_POLICY_UPDATE"
        return "PROMOTED_COMMIT"
    return "REJECTED"


def _is_toxic_reason_code(reason_code: Any) -> bool:
    code = str(reason_code).strip()
    if not code:
        return False
    for prefix in _TOXIC_REASON_PREFIXES:
        if code.startswith(prefix):
            return True
    return code in _TOXIC_REASON_EXACT


def _utility_indicates_effect_heavy_ok(utility_receipt: dict[str, Any] | None) -> bool:
    if not isinstance(utility_receipt, dict):
        return False
    return str(utility_receipt.get("effect_class", "")).strip() == "EFFECT_HEAVY_OK"


def _clamp_reward_q32(value: int) -> int:
    if int(value) < -_Q32_ONE:
        return -_Q32_ONE
    if int(value) > _Q32_ONE:
        return _Q32_ONE
    return int(value)


def _compute_reward_q32(
    *,
    promotion_result_kind: str,
    toxic_fail_b: bool,
    lane_kind: str,
    utility_receipt: dict[str, Any] | None,
) -> int:
    if promotion_result_kind in {"PROMOTED_COMMIT", "PROMOTED_POLICY_UPDATE"}:
        r_commit_q32 = int(_ORCH_REWARD_COMMIT_Q32)
        r_ext_q32 = 0
    elif promotion_result_kind == "PROMOTED_EXT_QUEUED":
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
    return int(_clamp_reward_q32(reward_q32))


def _enforce_bounds(*, config_payload: dict[str, Any], state_payload: dict[str, Any]) -> None:
    max_contexts = int(max(1, int(config_payload.get("max_contexts_u32", 1))))
    max_arms = int(max(1, int(config_payload.get("max_arms_per_context_u32", 1))))
    contexts = state_payload.get("contexts")
    if not isinstance(contexts, list):
        fail_v18("SCHEMA_FAIL")
    if len(contexts) > int(max_contexts):
        fail_v18("BANDIT_FAIL:CONTEXT_LIMIT")
    scanned = 0
    for row in contexts:
        scanned += 1
        if scanned > int(max_contexts):
            fail_v18("BANDIT_FAIL:CONTEXT_LIMIT")
        if not isinstance(row, dict):
            fail_v18("SCHEMA_FAIL")
        arms = row.get("arms")
        if not isinstance(arms, list):
            fail_v18("SCHEMA_FAIL")
        if len(arms) > int(max_arms):
            fail_v18("BANDIT_FAIL:ARM_LIMIT")


def verify_orch_bandit_v1(
    *,
    state_root: Path,
    config_dir: Path,
    snapshot: dict[str, Any],
    pack_payload: dict[str, Any],
) -> str:
    bandit_rel = str(pack_payload.get("orch_bandit_config_rel", "")).strip()
    if not bandit_rel:
        return "VALID"
    rel = Path(bandit_rel)
    if rel.is_absolute() or ".." in rel.parts:
        fail_v18("SCHEMA_FAIL")
    config_path = config_dir / rel
    if not config_path.exists() or not config_path.is_file():
        fail_v18("MISSING_STATE_INPUT")
    config_payload = _load_canon_json(config_path)
    validate_schema_v19(config_payload, "orch_bandit_config_v1")
    config_hash = canon_hash_obj(config_payload)

    tick_u64 = int(max(0, int(snapshot.get("tick_u64", 0))))
    decision_plan = _load_decision_plan(state_root=state_root, snapshot=snapshot)
    objective_kind = str(decision_plan.get("action_kind", "")).strip() or "UNKNOWN"
    if objective_kind not in {"RUN_CAMPAIGN", "RUN_GOAL_TASK"}:
        return "VALID"

    update_rows = sorted((state_root / "orch_bandit" / "updates").glob("sha256_*.orch_bandit_update_receipt_v1.json"), key=lambda row: row.as_posix())
    tick_updates: list[dict[str, Any]] = []
    for row in update_rows:
        payload = _load_canon_json(row)
        validate_schema_v19(payload, "orch_bandit_update_receipt_v1")
        digest = canon_hash_obj(payload)
        if digest != "sha256:" + row.name.split(".", 1)[0].split("_", 1)[1]:
            fail_v18("NONDETERMINISTIC")
        if int(max(0, int(payload.get("tick_u64", -1)))) == int(tick_u64):
            tick_updates.append(dict(payload))
    if not tick_updates:
        fail_v18("MISSING_STATE_INPUT")
    if len(tick_updates) != 1:
        fail_v18("NONDETERMINISTIC")
    update_receipt = tick_updates[0]
    if str(update_receipt.get("status", "")).strip() != "OK":
        fail_v18("NONDETERMINISTIC")
    if not str(update_receipt.get("reason_code", "")).strip():
        fail_v18("SCHEMA_FAIL")

    state_in_id = str(update_receipt.get("state_in_id", "")).strip()
    state_out_id = str(update_receipt.get("state_out_id", "")).strip()
    state_in = _load_hash_bound_payload(
        dir_path=state_root / "orch_bandit" / "state",
        digest=state_in_id,
        suffix="orch_bandit_state_v1.json",
        schema_name="orch_bandit_state_v1",
    )
    state_out = _load_hash_bound_payload(
        dir_path=state_root / "orch_bandit" / "state",
        digest=state_out_id,
        suffix="orch_bandit_state_v1.json",
        schema_name="orch_bandit_state_v1",
    )

    _enforce_bounds(config_payload=config_payload, state_payload=state_in)
    _enforce_bounds(config_payload=config_payload, state_payload=state_out)

    routing_hash = str(snapshot.get("dependency_routing_receipt_hash", "")).strip()
    routing_payload = _load_hash_bound_payload(
        dir_path=state_root / "long_run" / "debt",
        digest=routing_hash,
        suffix="dependency_routing_receipt_v1.json",
        schema_name="dependency_routing_receipt_v1",
    )
    if str(routing_payload.get("routing_selector_id", "")).strip() != str(config_hash):
        fail_v18("NONDETERMINISTIC")

    lane_kind = _normalize_lane_kind(state_root=state_root, snapshot=snapshot)
    runaway_level_u32 = int(max(0, int(decision_plan.get("runaway_escalation_level_u64", 0))))
    expected_context_key = compute_context_key(
        lane_kind=lane_kind,
        runaway_level_u32=runaway_level_u32,
        objective_kind=objective_kind,
    )

    if str(update_receipt.get("context_key", "")).strip() != str(expected_context_key):
        fail_v18("NONDETERMINISTIC")
    if str(routing_payload.get("context_key", "")).strip() != str(expected_context_key):
        fail_v18("NONDETERMINISTIC")

    debt_hash = snapshot.get("dependency_debt_snapshot_hash")
    hard_lock_active_b = bool(
        routing_payload.get(
            "hard_lock_active_b",
            routing_payload.get("forced_frontier_attempt_b", False),
        )
    )
    if objective_kind == "RUN_GOAL_TASK":
        hard_lock_active_b = True
    debt_payload: dict[str, Any] | None = None
    debt_pressure_b = False
    if _is_sha256(debt_hash):
        debt_payload = _load_hash_bound_payload(
            dir_path=state_root / "long_run" / "debt",
            digest=str(debt_hash),
            suffix="dependency_debt_state_v1.json",
            schema_name="dependency_debt_state_v1",
        )
        hard_lock_active_b = bool(hard_lock_active_b or bool(debt_payload.get("hard_lock_active_b", False)))
        debt_pressure_b = compute_governance_debt_pressure_v1(
            debt_state=dict(debt_payload),
            utility_policy=_load_optional_utility_policy(config_dir=config_dir),
            tick_u64=int(tick_u64),
        )

    expected_exploration_allowed_b = bool((not hard_lock_active_b) and (not debt_pressure_b))
    if hard_lock_active_b:
        expected_exploration_reason_code = "HARD_LOCK_ACTIVE"
    elif debt_pressure_b:
        expected_exploration_reason_code = "DEBT_PRESSURE_ACTIVE"
    else:
        expected_exploration_reason_code = "EXPLORATION_ALLOWED"
    if bool(update_receipt.get("exploration_allowed_b", False)) != bool(expected_exploration_allowed_b):
        fail_v18("NONDETERMINISTIC")
    if str(update_receipt.get("exploration_reason_code", "")).strip() != str(expected_exploration_reason_code):
        fail_v18("NONDETERMINISTIC")

    registry_payload = _load_canon_json(config_dir / "omega_capability_registry_v2.json")
    utility_policy = _load_optional_utility_policy(config_dir=config_dir)
    eligible_capability_ids = _derive_eligible_capability_ids(
        config_payload=config_payload,
        registry_payload=registry_payload,
        utility_policy=utility_policy,
        lane_kind=lane_kind,
        hard_lock_active_b=hard_lock_active_b,
        selected_capability_id=str(routing_payload.get("selected_capability_id", "")),
    )

    try:
        expected_selected = select_capability_id(
            config=config_payload,
            state=state_in,
            context_key=expected_context_key,
            eligible_capability_ids=list(eligible_capability_ids),
            exploration_allowed_b=bool(expected_exploration_allowed_b),
            exploration_reason_code=str(expected_exploration_reason_code),
        )
    except OrchBanditError as exc:
        fail_v18(str(exc))

    observed_selected_routing = str(routing_payload.get("selected_capability_id", "")).strip()
    observed_selected_update = str(update_receipt.get("selected_capability_id", "")).strip()
    if observed_selected_routing != observed_selected_update:
        fail_v18("NONDETERMINISTIC")

    orch_policy_use_b = bool(pack_payload.get("orch_policy_use_b", False))
    if orch_policy_use_b:
        if str(pack_payload.get("orch_policy_mode", "")).strip().upper() != "ADD_BONUS_V1":
            fail_v18("SCHEMA_FAIL")
        observed_bundle_id_raw = routing_payload.get("orch_policy_bundle_id_used")
        observed_bundle_id: str | None
        if observed_bundle_id_raw is None:
            observed_bundle_id = None
        else:
            text = str(observed_bundle_id_raw).strip()
            observed_bundle_id = _require_sha256(text, reason="SCHEMA_FAIL") if text else None
        observed_row_hit_b = bool(routing_payload.get("orch_policy_row_hit_b", False))
        observed_bonus_q32 = int(routing_payload.get("orch_policy_selected_bonus_q32", 0))

        active_bundle_id, policy_lookup = _load_active_orch_policy_lookup(state_root=state_root)
        if active_bundle_id is None:
            if observed_bundle_id is not None or observed_row_hit_b or observed_bonus_q32 != 0:
                fail_v18("NONDETERMINISTIC")
            expected_selected_with_bonus = str(expected_selected)
            expected_row_hit_b = False
            expected_bonus_q32 = 0
        else:
            if observed_bundle_id != str(active_bundle_id):
                fail_v18("NONDETERMINISTIC")
            context_scores = (policy_lookup or {}).get(str(expected_context_key)) if isinstance(policy_lookup, dict) else None
            if isinstance(context_scores, dict):
                expected_row_hit_b = True
                bonus_by_capability_q32: dict[str, int] = {}
                for capability_id in eligible_capability_ids:
                    score_q32 = int(context_scores.get(str(capability_id), 0))
                    bonus_by_capability_q32[str(capability_id)] = _clamp_orch_policy_bonus_q32(score_q32)
                try:
                    expected_selected_with_bonus = select_capability_id_with_bonus(
                        config=config_payload,
                        state=state_in,
                        context_key=expected_context_key,
                        eligible_capability_ids=list(eligible_capability_ids),
                        bonus_by_capability_q32=bonus_by_capability_q32,
                        exploration_allowed_b=bool(expected_exploration_allowed_b),
                        exploration_reason_code=str(expected_exploration_reason_code),
                    )
                except OrchBanditError as exc:
                    fail_v18(str(exc))
                expected_bonus_q32 = int(bonus_by_capability_q32.get(str(expected_selected_with_bonus), 0))
            else:
                expected_selected_with_bonus = str(expected_selected)
                expected_row_hit_b = False
                expected_bonus_q32 = 0
        if observed_row_hit_b != bool(expected_row_hit_b):
            fail_v18("NONDETERMINISTIC")
        if int(observed_bonus_q32) != int(expected_bonus_q32):
            fail_v18("NONDETERMINISTIC")
        if str(observed_selected_routing) != str(expected_selected_with_bonus):
            fail_v18("NONDETERMINISTIC")
        selected_for_update = observed_selected_update
        if not selected_for_update:
            fail_v18("SCHEMA_FAIL")
        if selected_for_update not in set(eligible_capability_ids):
            fail_v18("NONDETERMINISTIC")
    else:
        if routing_payload.get("orch_policy_bundle_id_used") is not None:
            fail_v18("NONDETERMINISTIC")
        if bool(routing_payload.get("orch_policy_row_hit_b", False)):
            fail_v18("NONDETERMINISTIC")
        if int(routing_payload.get("orch_policy_selected_bonus_q32", 0)) != 0:
            fail_v18("NONDETERMINISTIC")
        if str(expected_selected) != observed_selected_routing:
            fail_v18("NONDETERMINISTIC")
        selected_for_update = str(expected_selected)

    promotion_receipt: dict[str, Any] | None = None
    utility_receipt: dict[str, Any] | None = None
    activation_receipt: dict[str, Any] | None = None

    promotion_hash = snapshot.get("promotion_receipt_hash")
    if _is_sha256(promotion_hash):
        promotion_path = _find_nested_hash(state_root=state_root, digest=str(promotion_hash), suffix="omega_promotion_receipt_v1.json")
        promotion_receipt = _load_canon_json(promotion_path)
        if canon_hash_obj(promotion_receipt) != str(promotion_hash):
            fail_v18("NONDETERMINISTIC")

    utility_hash = snapshot.get("utility_proof_hash")
    if _is_sha256(utility_hash):
        utility_path = _find_nested_hash(state_root=state_root, digest=str(utility_hash), suffix="utility_proof_receipt_v1.json")
        utility_receipt = _load_canon_json(utility_path)
        if canon_hash_obj(utility_receipt) != str(utility_hash):
            fail_v18("NONDETERMINISTIC")

    activation_hash = snapshot.get("activation_receipt_hash")
    if _is_sha256(activation_hash):
        activation_path = _find_nested_hash(state_root=state_root, digest=str(activation_hash), suffix="omega_activation_receipt_v1.json")
        activation_receipt = _load_canon_json(activation_path)
        if canon_hash_obj(activation_receipt) != str(activation_hash):
            fail_v18("NONDETERMINISTIC")

    promotion_result_kind = _normalize_promotion_result_kind(
        result_kind=(promotion_receipt or {}).get("result_kind"),
        status=((promotion_receipt or {}).get("result") or {}).get("status"),
        activation_kind=(activation_receipt or {}).get("activation_kind"),
    )
    toxic_fail_b = _is_toxic_reason_code(((promotion_receipt or {}).get("result") or {}).get("reason_code"))
    expected_reward_q32 = _compute_reward_q32(
        promotion_result_kind=promotion_result_kind,
        toxic_fail_b=bool(toxic_fail_b),
        lane_kind=lane_kind,
        utility_receipt=utility_receipt,
    )

    perf_payload = _load_tick_perf(state_root=state_root, tick_u64=tick_u64)
    wallclock_ms_u64 = int(max(0, int(perf_payload.get("total_ns", 0)) // 1_000_000))
    expected_cost_q32 = compute_cost_norm_q32(
        wallclock_ms_u64=wallclock_ms_u64,
        cost_scale_ms_u64=int(config_payload.get("cost_scale_ms_u64", 1)),
    )

    if int(update_receipt.get("observed_reward_q32", 0)) != int(expected_reward_q32):
        fail_v18("NONDETERMINISTIC")
    if int(update_receipt.get("observed_cost_q32", -1)) != int(expected_cost_q32):
        fail_v18("NONDETERMINISTIC")

    try:
        recomputed_state_out = update_bandit_state(
            config=config_payload,
            state_in=state_in,
            state_in_id=state_in_id,
            tick_u64=int(tick_u64),
            ek_id=str(state_in.get("ek_id", "")),
            kernel_ledger_id=str(state_in.get("kernel_ledger_id", "")),
            context_key=expected_context_key,
            lane_kind=lane_kind,
            runaway_band_u32=int(min(runaway_level_u32, 5)),
            objective_kind=objective_kind,
            selected_capability_id=str(selected_for_update),
            observed_reward_q32=int(expected_reward_q32),
            observed_cost_q32=int(expected_cost_q32),
        )
    except OrchBanditError as exc:
        fail_v18(str(exc))

    recomputed_state_out_id = canon_hash_obj(recomputed_state_out)
    if recomputed_state_out_id != str(state_out_id):
        fail_v18("NONDETERMINISTIC")
    if canon_hash_obj(state_out) != str(state_out_id):
        fail_v18("NONDETERMINISTIC")
    if recomputed_state_out != state_out:
        fail_v18("NONDETERMINISTIC")

    pointer_path = state_root / "orch_bandit" / "state" / "ACTIVE_ORCH_BANDIT_STATE"
    if pointer_path.exists() and pointer_path.is_file():
        pointer = pointer_path.read_text(encoding="utf-8").strip()
        if pointer != str(state_out_id):
            fail_v18("NONDETERMINISTIC")

    return "VALID"


__all__ = ["verify_orch_bandit_v1"]
