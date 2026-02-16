from __future__ import annotations

import hashlib
from typing import Any

from ...v1_7r.canon import canon_bytes
from .brain_branch_sig_v1 import branch_signature_v1
from .brain_context_v1 import validate_brain_context_v1


def _seeded_rank(seed_u64: int, campaign_id: str, capability_id: str) -> str:
    raw = f"{seed_u64}:{campaign_id}:{capability_id}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _stable_sort_candidates(candidates: list[dict[str, Any]], seed_u64: int, tie_break_rule: str) -> list[dict[str, Any]]:
    if tie_break_rule == "LOWEST_CAMPAIGN_ID":
        tie_key = lambda c: (c["campaign_id"], c["capability_id"])
    else:
        tie_key = lambda c: (_seeded_rank(seed_u64, c["campaign_id"], c["capability_id"]), c["campaign_id"], c["capability_id"])

    return sorted(
        candidates,
        key=lambda c: (
            -int(c["priority_i32"]),
            int(c["last_run_tick_u64"]),
            int(c["estimated_cost_u64"]),
            tie_key(c),
        ),
    )


def _stable_decision_hash_payload(decision: dict[str, Any]) -> dict[str, Any]:
    payload = dict(decision)
    payload.pop("explain_hash", None)
    return payload


def stable_decision_bytes(decision: dict[str, Any]) -> bytes:
    return canon_bytes(decision)


def brain_decide_v15_1(ctx: dict[str, Any]) -> dict[str, Any]:
    ctx = validate_brain_context_v1(dict(ctx))
    budget = dict(ctx["budget"])
    policy = dict(ctx["policy"])
    candidates = [dict(c) for c in ctx["candidates"]]

    selection_rules = list(policy["selection_rules"])
    max_cost = int(policy["max_cost_u64"])
    min_remaining = int(policy["min_remaining_budget_u64"])
    remaining = int(budget["remaining_budget_u64"])
    seed_u64 = int(ctx["seed_u64"])
    tie_break_rule = str(policy["tie_break_rule"])

    rule_path: list[dict[str, str]] = []

    budget_verdict = "OK"
    verdict = "SKIP"
    selected_campaign_id: str | None = None
    selected_capability_id: str | None = None

    working = candidates

    for rule_id in selection_rules:
        if rule_id == "R0_FILTER_ENABLED":
            before = len(working)
            working = [c for c in working if bool(c["enabled"])]
            rule_path.append({"rule_id": rule_id, "outcome": f"kept={len(working)};dropped={before-len(working)}"})
            continue

        if rule_id == "R1_FILTER_COOLDOWN":
            before = len(working)
            working = [c for c in working if int(c["cooldown_remaining_u64"]) == 0]
            rule_path.append({"rule_id": rule_id, "outcome": f"kept={len(working)};dropped={before-len(working)}"})
            continue

        if rule_id == "R2_BUDGET_HARD_STOP":
            if bool(budget["hard_stop"]):
                budget_verdict = "HARD_STOP"
                verdict = "STOP"
                rule_path.append({"rule_id": rule_id, "outcome": "hard_stop=true"})
                break
            rule_path.append({"rule_id": rule_id, "outcome": "hard_stop=false"})
            continue

        if rule_id == "R3_BUDGET_MIN_REMAINING":
            if remaining < min_remaining:
                budget_verdict = "INSUFFICIENT"
                verdict = "STOP"
                rule_path.append({"rule_id": rule_id, "outcome": f"remaining={remaining}<min={min_remaining}"})
                break
            rule_path.append({"rule_id": rule_id, "outcome": f"remaining={remaining}>=min={min_remaining}"})
            continue

        if rule_id == "R4_FILTER_COST_MAX":
            before = len(working)
            working = [c for c in working if int(c["estimated_cost_u64"]) <= max_cost]
            rule_path.append({"rule_id": rule_id, "outcome": f"kept={len(working)};dropped={before-len(working)}"})
            continue

        if rule_id == "R5_SCORE_PRIORITY":
            working = _stable_sort_candidates(working, seed_u64=seed_u64, tie_break_rule=tie_break_rule)
            top = working[0]["priority_i32"] if working else "NONE"
            rule_path.append({"rule_id": rule_id, "outcome": f"top_priority={top}"})
            continue

        if rule_id == "R6_TIEBREAK":
            if not working:
                rule_path.append({"rule_id": rule_id, "outcome": "no_candidates"})
                continue
            selected = working[0]
            selected_campaign_id = str(selected["campaign_id"])
            selected_capability_id = str(selected["capability_id"])
            cost = int(selected["estimated_cost_u64"])
            if cost > remaining:
                budget_verdict = "INSUFFICIENT"
                verdict = "SKIP"
                rule_path.append({
                    "rule_id": rule_id,
                    "outcome": f"selected={selected_campaign_id};cost={cost};remaining={remaining};budget=insufficient",
                })
            else:
                verdict = "RUN"
                rule_path.append({
                    "rule_id": rule_id,
                    "outcome": f"selected={selected_campaign_id};cost={cost};remaining={remaining};budget=ok",
                })
            continue

        rule_path.append({"rule_id": rule_id, "outcome": "unknown_rule_ignored"})

    if verdict != "RUN":
        selected_campaign_id = None
        selected_capability_id = None

    if verdict == "STOP" and budget_verdict == "OK":
        budget_verdict = "INSUFFICIENT"

    decision = {
        "schema_version": "brain_decision_v1",
        "case_id": ctx["case_id"],
        "verdict": verdict,
        "selected_campaign_id": selected_campaign_id,
        "selected_capability_id": selected_capability_id,
        "budget_verdict": budget_verdict,
        "rule_path": rule_path,
        "branch_signature": branch_signature_v1(rule_path),
        "explain_hash": "",
    }
    explain_payload = {
        "case_id": ctx["case_id"],
        "decision": _stable_decision_hash_payload(decision),
        "candidate_count": len(candidates),
    }
    decision["explain_hash"] = f"sha256:{hashlib.sha256(canon_bytes(explain_payload)).hexdigest()}"
    return decision


__all__ = ["brain_decide_v15_1", "stable_decision_bytes"]
