"""Deterministic construction helpers for dependency routing receipts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from cdel.v18_0.omega_common_v1 import canon_hash_obj


def _utc_now_rfc3339() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _is_sha256(value: Any) -> bool:
    raw = str(value).strip()
    return raw.startswith("sha256:") and len(raw) == 71 and all(ch in "0123456789abcdef" for ch in raw.split(":", 1)[1])


def make_dependency_routing_receipt_v1(
    *,
    tick_u64: int,
    routing_selector_id: str,
    hard_lock_active_b: bool,
    hard_lock_keys: list[str],
    forced_heavy_b: bool,
    forced_heavy_reason_code: str | None,
    forced_heavy_target_debt_keys: list[str],
    anti_monopoly_gate_applied_b: bool,
    anti_monopoly_reason_code: str | None,
    selected_route: dict[str, Any],
    blocked_candidates: list[dict[str, str]],
    selected_declared_class: str,
    reason_codes: list[str],
    frontier_goals_pending_b: bool,
    blocks_goal_id: str | None,
    blocks_debt_key: str | None,
    dependency_debt_delta_i64: int,
    forced_frontier_attempt_b: bool,
    forced_frontier_debt_key: str | None,
    context_key: str | None,
    orch_policy_bundle_id_used: str | None,
    orch_policy_row_hit_b: bool,
    orch_policy_selected_bonus_q32: int,
    market_frozen_b: bool,
    market_used_for_selection_b: bool,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    route = dict(selected_route)
    campaign_id = str(route.get("campaign_id", "")).strip()
    capability_id = str(route.get("capability_id", "")).strip()
    lane_id = str(route.get("lane_id", "")).strip()
    if not campaign_id or not capability_id or not lane_id:
        raise ValueError("selected_route requires campaign_id/capability_id/lane_id")

    payload = {
        "schema_id": "dependency_routing_receipt_v1",
        "id": "sha256:" + ("0" * 64),
        "schema_name": "dependency_routing_receipt_v1",
        "schema_version": "v19_0",
        "receipt_id": "sha256:" + ("0" * 64),
        "tick_u64": int(max(0, int(tick_u64))),
        "routing_selector_id": str(routing_selector_id),
        "hard_lock_active_b": bool(hard_lock_active_b),
        "hard_lock_keys": sorted({str(key).strip() for key in hard_lock_keys if str(key).strip()}),
        "forced_heavy_b": bool(forced_heavy_b),
        "forced_heavy_reason_code": (
            str(forced_heavy_reason_code).strip() if isinstance(forced_heavy_reason_code, str) and str(forced_heavy_reason_code).strip() else None
        ),
        "forced_heavy_target_debt_keys": sorted(
            {str(key).strip() for key in forced_heavy_target_debt_keys if str(key).strip()}
        ),
        "anti_monopoly_gate_applied_b": bool(anti_monopoly_gate_applied_b),
        "anti_monopoly_reason_code": (
            str(anti_monopoly_reason_code).strip() if isinstance(anti_monopoly_reason_code, str) and str(anti_monopoly_reason_code).strip() else None
        ),
        "selected_route": {
            "campaign_id": campaign_id,
            "capability_id": capability_id,
            "lane_id": lane_id,
        },
        "blocked_candidates": [
            {
                "candidate_id": str(row.get("candidate_id", "")),
                "blocked_reason_code": str(row.get("blocked_reason_code", "")),
                "blocked_detail": str(row.get("blocked_detail", "")),
            }
            for row in blocked_candidates
            if isinstance(row, dict)
        ],
        "created_at_utc": str(created_at_utc or _utc_now_rfc3339()),
        "selected_capability_id": capability_id,
        "selected_declared_class": str(selected_declared_class),
        "frontier_goals_pending_b": bool(frontier_goals_pending_b),
        "blocks_goal_id": str(blocks_goal_id) if isinstance(blocks_goal_id, str) and blocks_goal_id.strip() else None,
        "blocks_debt_key": str(blocks_debt_key) if isinstance(blocks_debt_key, str) and blocks_debt_key.strip() else None,
        "dependency_debt_delta_i64": int(dependency_debt_delta_i64),
        "forced_frontier_attempt_b": bool(forced_frontier_attempt_b),
        "forced_frontier_debt_key": (
            str(forced_frontier_debt_key)
            if isinstance(forced_frontier_debt_key, str) and forced_frontier_debt_key.strip()
            else None
        ),
        "context_key": str(context_key) if _is_sha256(context_key) else None,
        "orch_policy_bundle_id_used": str(orch_policy_bundle_id_used) if _is_sha256(orch_policy_bundle_id_used) else None,
        "orch_policy_row_hit_b": bool(orch_policy_row_hit_b),
        "orch_policy_selected_bonus_q32": int(orch_policy_selected_bonus_q32),
        "market_frozen_b": bool(market_frozen_b),
        "market_used_for_selection_b": bool(market_used_for_selection_b),
        "reason_codes": [str(row) for row in reason_codes if str(row).strip()],
    }
    no_ids = dict(payload)
    no_ids.pop("id", None)
    no_ids.pop("receipt_id", None)
    digest = canon_hash_obj(no_ids)
    payload["id"] = digest
    payload["receipt_id"] = digest
    return payload


__all__ = ["make_dependency_routing_receipt_v1"]
