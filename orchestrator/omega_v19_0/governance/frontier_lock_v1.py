"""Deterministic hard-lock and unlock contract helpers for v19 governance."""

from __future__ import annotations

from typing import Any


Q32_ONE = 1 << 32
DEBT_KEYS: tuple[str, ...] = (
    "TDL",
    "KDL",
    "EDL",
    "CDL",
    "CoDL",
    "IDL",
    "FRONTIER_STALL",
    "UTILITY_FAIL",
    "DIVERSITY_VIOLATION",
)
DEBT_KEY_SET = set(DEBT_KEYS)
FORCED_HEAVY_REASON_CODES: tuple[str, ...] = (
    "HARD_LOCK_ACTIVE",
    "DEBT_THRESHOLD_EXCEEDED",
    "NO_FRONTIER_ATTEMPT_TIMEOUT",
    "UTILITY_POLICY_MANDATE",
    "UTILITY_PROOF_INSUFFICIENT",
)


def _u64(value: Any) -> int:
    return int(max(0, int(value)))


def _debt_key(value: Any) -> str | None:
    key = str(value).strip()
    return key if key in DEBT_KEY_SET else None


def _normalize_debt_key(value: Any) -> str:
    key = str(value).strip()
    if key in DEBT_KEY_SET:
        return key
    if key.startswith("frontier:"):
        return "FRONTIER_STALL"
    return "UTILITY_FAIL"


def _sorted_unique_debt_keys(values: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    if isinstance(values, list):
        for row in values:
            key = _debt_key(row)
            if key is None or key in seen:
                continue
            out.append(key)
            seen.add(key)
    out.sort()
    return out


def _coerce_debt_counter_map(raw: Any) -> dict[str, int]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int] = {}
    for key, value in raw.items():
        k = _normalize_debt_key(key)
        out[k] = int(max(_u64(value), int(out.get(k, 0))))
    return {str(k): int(v) for k, v in sorted(out.items(), key=lambda kv: str(kv[0]))}


def debt_counters_by_key_v1(debt_state: dict[str, Any]) -> dict[str, int]:
    counters = _coerce_debt_counter_map(debt_state.get("debt_counters_by_key"))
    if counters:
        return counters
    return _coerce_debt_counter_map(debt_state.get("debt_by_key"))


def ticks_without_frontier_attempt_by_key_v1(debt_state: dict[str, Any]) -> dict[str, int]:
    return _coerce_debt_counter_map(debt_state.get("ticks_without_frontier_attempt_by_key"))


def _thresholds_by_key(utility_policy: dict[str, Any] | None) -> dict[str, int]:
    raw = (utility_policy or {}).get("debt_threshold_u64_by_key")
    out = {key: 1 for key in DEBT_KEYS}
    if isinstance(raw, dict):
        for key, value in raw.items():
            norm = _debt_key(key)
            if norm is None:
                continue
            out[norm] = int(max(1, _u64(value)))
    return out


def _debt_pressure_threshold_u64(utility_policy: dict[str, Any] | None) -> int:
    raw = (utility_policy or {}).get("debt_pressure_threshold_u64")
    if raw is None:
        return 1
    return int(max(1, _u64(raw)))


def _no_frontier_attempt_timeout_u64(utility_policy: dict[str, Any] | None) -> int:
    raw = (utility_policy or {}).get("no_frontier_attempt_timeout_u64")
    if raw is None:
        return 40
    return int(max(1, _u64(raw)))


def compute_hard_lock_v1(
    *,
    debt_state: dict[str, Any],
    utility_policy: dict[str, Any] | None,
    tick_u64: int,
) -> tuple[bool, list[str], str]:
    del tick_u64
    counters = debt_counters_by_key_v1(debt_state)
    ticks_by_key = ticks_without_frontier_attempt_by_key_v1(debt_state)
    thresholds = _thresholds_by_key(utility_policy)
    timeout_u64 = _no_frontier_attempt_timeout_u64(utility_policy)

    explicit_keys = _sorted_unique_debt_keys(debt_state.get("hard_lock_keys"))
    computed_keys: set[str] = set(explicit_keys)
    reason_candidates: list[str] = []

    for key in DEBT_KEYS:
        if int(counters.get(key, 0)) >= int(thresholds.get(key, 1)):
            computed_keys.add(key)
            if "DEBT_THRESHOLD_EXCEEDED" not in reason_candidates:
                reason_candidates.append("DEBT_THRESHOLD_EXCEEDED")

    if int(ticks_by_key.get("FRONTIER_STALL", 0)) >= int(timeout_u64):
        computed_keys.add("FRONTIER_STALL")
        if "NO_FRONTIER_ATTEMPT_TIMEOUT" not in reason_candidates:
            reason_candidates.append("NO_FRONTIER_ATTEMPT_TIMEOUT")

    if bool(debt_state.get("hard_lock_active_b", False)) and explicit_keys:
        if "HARD_LOCK_ACTIVE" not in reason_candidates:
            reason_candidates.insert(0, "HARD_LOCK_ACTIVE")

    lock_keys = sorted(computed_keys)
    if not lock_keys:
        return False, [], "NONE"

    for preferred in FORCED_HEAVY_REASON_CODES:
        if preferred in reason_candidates:
            return True, lock_keys, preferred
    return True, lock_keys, "DEBT_THRESHOLD_EXCEEDED"


def compute_debt_pressure_v1(
    *,
    debt_state: dict[str, Any],
    utility_policy: dict[str, Any] | None,
    tick_u64: int,
) -> bool:
    lock_active, _lock_keys, _reason = compute_hard_lock_v1(
        debt_state=debt_state,
        utility_policy=utility_policy,
        tick_u64=tick_u64,
    )
    if lock_active:
        return True
    counters = debt_counters_by_key_v1(debt_state)
    threshold = _debt_pressure_threshold_u64(utility_policy)
    return any(int(value) >= int(threshold) for value in counters.values())


def choose_forced_heavy_route_v1(
    *,
    gated_routes: list[dict[str, Any]],
    utility_policy: dict[str, Any] | None,
    required_debt_keys: list[str],
    tick_u64: int,
) -> dict[str, Any] | None:
    del utility_policy
    del tick_u64
    required = set(_sorted_unique_debt_keys(required_debt_keys))
    ordered = sorted(
        [dict(row) for row in gated_routes if isinstance(row, dict)],
        key=lambda row: (
            str(row.get("campaign_id", "")),
            str(row.get("capability_id", "")),
            str(row.get("lane_id", "")),
        ),
    )
    for row in ordered:
        declared_class = str(row.get("declared_class", "")).strip().upper()
        if declared_class not in {"FRONTIER_HEAVY", "CANARY_HEAVY"}:
            continue
        route_keys = {
            _debt_key(item)
            for item in (row.get("target_debt_keys") if isinstance(row.get("target_debt_keys"), list) else [])
        }
        route_keys = {item for item in route_keys if isinstance(item, str)}
        if required and not route_keys.issuperset(required):
            continue
        return row
    return None


def bump_debt_key(
    *,
    debt_state: dict[str, Any],
    debt_key: str,
    delta_i64: int,
) -> dict[str, Any]:
    out = dict(debt_state)
    counters = debt_counters_by_key_v1(out)
    norm = _debt_key(debt_key)
    if norm is None:
        norm = "UTILITY_FAIL"
    next_value = int(counters.get(norm, 0)) + int(delta_i64)
    counters[norm] = int(max(0, next_value))
    out["debt_counters_by_key"] = {str(k): int(v) for k, v in sorted(counters.items(), key=lambda kv: str(kv[0]))}
    return out


def recompute_lock_fields_from_counters_v1(
    *,
    debt_state: dict[str, Any],
    utility_policy: dict[str, Any] | None,
    tick_u64: int,
) -> dict[str, Any]:
    lock_active, lock_keys, _reason_code = compute_hard_lock_v1(
        debt_state=debt_state,
        utility_policy=utility_policy,
        tick_u64=tick_u64,
    )
    out = dict(debt_state)
    out["hard_lock_active_b"] = bool(lock_active)
    out["hard_lock_keys"] = list(lock_keys)
    out["hard_lock_debt_key"] = str(lock_keys[0]) if lock_keys else None
    return out


def utility_proof_unlock_contract_satisfied_v1(
    *,
    hard_lock_keys: list[str],
    utility_proof_receipt: dict[str, Any] | None,
) -> bool:
    if not isinstance(utility_proof_receipt, dict):
        return False
    if str(utility_proof_receipt.get("utility_class", "")).strip() != "HEAVY":
        return False
    targeted = set(_sorted_unique_debt_keys(utility_proof_receipt.get("targeted_debt_keys")))
    required = set(_sorted_unique_debt_keys(hard_lock_keys))
    if not targeted.issuperset(required):
        return False
    if bool(utility_proof_receipt.get("reduced_specific_trigger_keys_b", False)) is not True:
        return False
    deltas = utility_proof_receipt.get("debt_delta_by_key")
    if not isinstance(deltas, dict):
        return False
    for key in sorted(required):
        if int(deltas.get(key, 0)) >= 0:
            return False
    return True


def append_unlock_reason_codes_v1(
    *,
    reason_codes: list[str],
    hard_lock_keys: list[str],
    utility_proof_receipt: dict[str, Any] | None,
) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for row in reason_codes:
        code = str(row).strip()
        if not code or code in seen:
            continue
        out.append(code)
        seen.add(code)
    required = _sorted_unique_debt_keys(hard_lock_keys)
    if required and not utility_proof_unlock_contract_satisfied_v1(
        hard_lock_keys=required,
        utility_proof_receipt=utility_proof_receipt,
    ):
        code = "UTILITY_PROOF_INSUFFICIENT"
        if code not in seen:
            out.append(code)
    return out


def enforce_unlock_contract_v1(
    *,
    tick_u64: int,
    debt_state_before: dict[str, Any],
    debt_state_after: dict[str, Any],
    routing_receipt: dict[str, Any],
    utility_proof_receipt: dict[str, Any] | None,
    utility_policy: dict[str, Any] | None,
) -> dict[str, Any]:
    del debt_state_before
    if not bool(routing_receipt.get("hard_lock_active_b", False)):
        return recompute_lock_fields_from_counters_v1(
            debt_state=debt_state_after,
            utility_policy=utility_policy,
            tick_u64=tick_u64,
        )

    out = dict(debt_state_after)
    hard_lock_keys = _sorted_unique_debt_keys(routing_receipt.get("hard_lock_keys"))
    out["hard_lock_active_b"] = True
    out["hard_lock_keys"] = list(hard_lock_keys)
    out["hard_lock_debt_key"] = str(hard_lock_keys[0]) if hard_lock_keys else None

    if not utility_proof_unlock_contract_satisfied_v1(
        hard_lock_keys=hard_lock_keys,
        utility_proof_receipt=utility_proof_receipt,
    ):
        out = bump_debt_key(debt_state=out, debt_key="UTILITY_FAIL", delta_i64=1)
        return out

    return recompute_lock_fields_from_counters_v1(
        debt_state=out,
        utility_policy=utility_policy,
        tick_u64=tick_u64,
    )


__all__ = [
    "DEBT_KEYS",
    "FORCED_HEAVY_REASON_CODES",
    "bump_debt_key",
    "choose_forced_heavy_route_v1",
    "compute_debt_pressure_v1",
    "compute_hard_lock_v1",
    "debt_counters_by_key_v1",
    "append_unlock_reason_codes_v1",
    "enforce_unlock_contract_v1",
    "recompute_lock_fields_from_counters_v1",
    "ticks_without_frontier_attempt_by_key_v1",
    "utility_proof_unlock_contract_satisfied_v1",
]
