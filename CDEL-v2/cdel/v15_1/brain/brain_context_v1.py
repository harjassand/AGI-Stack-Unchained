from __future__ import annotations

from typing import Any

from ...v1_7r.canon import canon_bytes, sha256_prefixed


class BrainContextError(RuntimeError):
    pass


def _fail(reason: str) -> None:
    raise BrainContextError(reason)


def _require_keys(obj: dict[str, Any], keys: set[str], reason: str) -> None:
    if set(obj.keys()) != keys:
        _fail(reason)


def _require_u64(value: Any, reason: str) -> int:
    if not isinstance(value, int):
        _fail(reason)
    if value < 0 or value > (2**64 - 1):
        _fail(reason)
    return value


def _require_i32(value: Any, reason: str) -> int:
    if not isinstance(value, int):
        _fail(reason)
    if value < -(2**31) or value > (2**31 - 1):
        _fail(reason)
    return value


def _require_str(value: Any, reason: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(reason)
    return value


def _validate_budget(obj: dict[str, Any]) -> None:
    _require_keys(
        obj,
        {
            "schema_version",
            "total_budget_u64",
            "spent_budget_u64",
            "remaining_budget_u64",
            "per_bucket",
            "hard_stop",
        },
        "INVALID:BRAIN_CONTEXT_BUDGET_KEYS",
    )
    if obj["schema_version"] != "brain_budget_state_v1":
        _fail("INVALID:BRAIN_CONTEXT_BUDGET_SCHEMA")
    total = _require_u64(obj["total_budget_u64"], "INVALID:BRAIN_CONTEXT_BUDGET")
    spent = _require_u64(obj["spent_budget_u64"], "INVALID:BRAIN_CONTEXT_BUDGET")
    remaining = _require_u64(obj["remaining_budget_u64"], "INVALID:BRAIN_CONTEXT_BUDGET")
    if total < spent or remaining != (total - spent):
        _fail("INVALID:BRAIN_CONTEXT_BUDGET_MATH")
    if not isinstance(obj["hard_stop"], bool):
        _fail("INVALID:BRAIN_CONTEXT_BUDGET")

    buckets = obj["per_bucket"]
    if not isinstance(buckets, list):
        _fail("INVALID:BRAIN_CONTEXT_BUDGET")
    for bucket in buckets:
        if not isinstance(bucket, dict):
            _fail("INVALID:BRAIN_CONTEXT_BUDGET")
        _require_keys(
            bucket,
            {"bucket_id", "total_u64", "spent_u64", "remaining_u64"},
            "INVALID:BRAIN_CONTEXT_BUDGET_BUCKET_KEYS",
        )
        _require_str(bucket["bucket_id"], "INVALID:BRAIN_CONTEXT_BUDGET")
        b_total = _require_u64(bucket["total_u64"], "INVALID:BRAIN_CONTEXT_BUDGET")
        b_spent = _require_u64(bucket["spent_u64"], "INVALID:BRAIN_CONTEXT_BUDGET")
        b_remaining = _require_u64(bucket["remaining_u64"], "INVALID:BRAIN_CONTEXT_BUDGET")
        if b_total < b_spent or b_remaining != (b_total - b_spent):
            _fail("INVALID:BRAIN_CONTEXT_BUDGET_MATH")


def _validate_candidates(rows: Any) -> None:
    if not isinstance(rows, list) or not rows:
        _fail("INVALID:BRAIN_CONTEXT_CANDIDATES")
    for row in rows:
        if not isinstance(row, dict):
            _fail("INVALID:BRAIN_CONTEXT_CANDIDATES")
        _require_keys(
            row,
            {
                "campaign_id",
                "capability_id",
                "enabled",
                "estimated_cost_u64",
                "priority_i32",
                "last_run_tick_u64",
                "cooldown_remaining_u64",
                "tags",
            },
            "INVALID:BRAIN_CONTEXT_CANDIDATE_KEYS",
        )
        _require_str(row["campaign_id"], "INVALID:BRAIN_CONTEXT_CANDIDATES")
        _require_str(row["capability_id"], "INVALID:BRAIN_CONTEXT_CANDIDATES")
        if not isinstance(row["enabled"], bool):
            _fail("INVALID:BRAIN_CONTEXT_CANDIDATES")
        _require_u64(row["estimated_cost_u64"], "INVALID:BRAIN_CONTEXT_CANDIDATES")
        _require_i32(row["priority_i32"], "INVALID:BRAIN_CONTEXT_CANDIDATES")
        _require_u64(row["last_run_tick_u64"], "INVALID:BRAIN_CONTEXT_CANDIDATES")
        _require_u64(row["cooldown_remaining_u64"], "INVALID:BRAIN_CONTEXT_CANDIDATES")
        tags = row["tags"]
        if not isinstance(tags, list) or any((not isinstance(t, str)) for t in tags):
            _fail("INVALID:BRAIN_CONTEXT_CANDIDATES")


def _validate_history(obj: dict[str, Any]) -> None:
    _require_keys(
        obj,
        {
            "schema_version",
            "current_tick_u64",
            "source_run_root_rel",
            "recent_choices",
            "recent_failures",
        },
        "INVALID:BRAIN_CONTEXT_HISTORY_KEYS",
    )
    if obj["schema_version"] != "brain_history_v1":
        _fail("INVALID:BRAIN_CONTEXT_HISTORY_SCHEMA")
    _require_u64(obj["current_tick_u64"], "INVALID:BRAIN_CONTEXT_HISTORY")
    _require_str(obj["source_run_root_rel"], "INVALID:BRAIN_CONTEXT_HISTORY")

    choices = obj["recent_choices"]
    failures = obj["recent_failures"]
    if not isinstance(choices, list) or not isinstance(failures, list):
        _fail("INVALID:BRAIN_CONTEXT_HISTORY")
    for row in choices:
        if not isinstance(row, dict):
            _fail("INVALID:BRAIN_CONTEXT_HISTORY")
        _require_keys(row, {"tick_u64", "campaign_id"}, "INVALID:BRAIN_CONTEXT_HISTORY_CHOICE_KEYS")
        _require_u64(row["tick_u64"], "INVALID:BRAIN_CONTEXT_HISTORY")
        _require_str(row["campaign_id"], "INVALID:BRAIN_CONTEXT_HISTORY")
    for row in failures:
        if not isinstance(row, dict):
            _fail("INVALID:BRAIN_CONTEXT_HISTORY")
        _require_keys(
            row,
            {"tick_u64", "campaign_id", "fail_code"},
            "INVALID:BRAIN_CONTEXT_HISTORY_FAIL_KEYS",
        )
        _require_u64(row["tick_u64"], "INVALID:BRAIN_CONTEXT_HISTORY")
        _require_str(row["campaign_id"], "INVALID:BRAIN_CONTEXT_HISTORY")
        _require_str(row["fail_code"], "INVALID:BRAIN_CONTEXT_HISTORY")


def _validate_policy(obj: dict[str, Any]) -> None:
    _require_keys(
        obj,
        {
            "schema_version",
            "max_cost_u64",
            "min_remaining_budget_u64",
            "tie_break_rule",
            "selection_rules",
        },
        "INVALID:BRAIN_CONTEXT_POLICY_KEYS",
    )
    if obj["schema_version"] != "brain_policy_v1":
        _fail("INVALID:BRAIN_CONTEXT_POLICY_SCHEMA")
    _require_u64(obj["max_cost_u64"], "INVALID:BRAIN_CONTEXT_POLICY")
    _require_u64(obj["min_remaining_budget_u64"], "INVALID:BRAIN_CONTEXT_POLICY")
    tie_break = obj["tie_break_rule"]
    if tie_break not in {"LOWEST_CAMPAIGN_ID", "SEEDED_HASH_ORDER_V1"}:
        _fail("INVALID:BRAIN_CONTEXT_POLICY")
    rules = obj["selection_rules"]
    if not isinstance(rules, list) or any((not isinstance(r, str) or not r) for r in rules):
        _fail("INVALID:BRAIN_CONTEXT_POLICY")


def validate_brain_context_v1(obj: dict[str, Any]) -> dict[str, Any]:
    _require_keys(
        obj,
        {
            "schema_version",
            "case_id",
            "seed_u64",
            "budget",
            "candidates",
            "history",
            "policy",
        },
        "INVALID:BRAIN_CONTEXT_KEYS",
    )
    if obj["schema_version"] != "brain_context_v1":
        _fail("INVALID:BRAIN_CONTEXT_SCHEMA")
    _require_str(obj["case_id"], "INVALID:BRAIN_CONTEXT")
    _require_u64(obj["seed_u64"], "INVALID:BRAIN_CONTEXT")

    budget = obj["budget"]
    if not isinstance(budget, dict):
        _fail("INVALID:BRAIN_CONTEXT_BUDGET")
    _validate_budget(budget)

    _validate_candidates(obj["candidates"])

    history = obj["history"]
    if not isinstance(history, dict):
        _fail("INVALID:BRAIN_CONTEXT_HISTORY")
    _validate_history(history)

    policy = obj["policy"]
    if not isinstance(policy, dict):
        _fail("INVALID:BRAIN_CONTEXT_POLICY")
    _validate_policy(policy)

    return obj


def build_case_id_v1(*, run_root_rel: str, context_tick: int, seed_u64: int) -> str:
    payload = {
        "run_root_rel": run_root_rel,
        "context_tick": context_tick,
        "seed_u64": seed_u64,
    }
    return sha256_prefixed(canon_bytes(payload))


__all__ = ["BrainContextError", "validate_brain_context_v1", "build_case_id_v1"]
