"""Phase 4C shadow-airlock: tiered readiness gate before any RE1 swap."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .common_v1 import canon_hash_obj, load_canon_dict, validate_schema
from ..v1_7r.canon import write_canon_json


def _require_bool(value: Any, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise RuntimeError(f"SCHEMA_FAIL:{field}")
    return value


def evaluate_shadow_regime_proposal(
    proposal: dict[str, Any],
    *,
    tier_a_pass_b: bool = True,
    tier_b_pass_b: bool = True,
    integrity_guard_verified_b: bool = True,
    static_protected_roots_verified_b: bool = True,
    dynamic_protected_roots_verified_b: bool = True,
    j_window_rule_verified_b: bool = True,
    j_per_tick_floor_verified_b: bool = True,
    non_weakening_j_verified_b: bool | None = None,
    corpus_replay_verified_b: bool = True,
    deterministic_fuzz_verified_b: bool = True,
    corpus_invariance_verified_b: bool = True,
    corpus_invariance_receipt_id: str | None = None,
    rollback_plan_bound_b: bool = True,
    rollback_evidence_hash: str | None = None,
    auto_swap_b: bool = False,
) -> dict[str, Any]:
    validate_schema(proposal, "shadow_regime_proposal_v1")
    expected_proposal_id = canon_hash_obj({k: v for k, v in proposal.items() if k != "proposal_id"})
    if str(proposal.get("proposal_id", "")) != expected_proposal_id:
        raise RuntimeError("NONDETERMINISTIC")

    outbox_only_verified_b = (
        str(proposal.get("mode", "")) == "OUTBOX_ONLY_SHADOW"
        and str(proposal.get("activation_intent", "")) == "NO_SWAP"
    )

    tier_a_pass_b = _require_bool(tier_a_pass_b, field="tier_a_pass_b")
    tier_b_pass_b = _require_bool(tier_b_pass_b, field="tier_b_pass_b")
    integrity_guard_verified_b = _require_bool(integrity_guard_verified_b, field="integrity_guard_verified_b")
    static_protected_roots_verified_b = _require_bool(
        static_protected_roots_verified_b,
        field="static_protected_roots_verified_b",
    )
    dynamic_protected_roots_verified_b = _require_bool(
        dynamic_protected_roots_verified_b,
        field="dynamic_protected_roots_verified_b",
    )
    j_window_rule_verified_b = _require_bool(j_window_rule_verified_b, field="j_window_rule_verified_b")
    j_per_tick_floor_verified_b = _require_bool(j_per_tick_floor_verified_b, field="j_per_tick_floor_verified_b")
    corpus_replay_verified_b = _require_bool(corpus_replay_verified_b, field="corpus_replay_verified_b")
    deterministic_fuzz_verified_b = _require_bool(deterministic_fuzz_verified_b, field="deterministic_fuzz_verified_b")
    corpus_invariance_verified_b = _require_bool(corpus_invariance_verified_b, field="corpus_invariance_verified_b")
    rollback_plan_bound_b = _require_bool(rollback_plan_bound_b, field="rollback_plan_bound_b")
    auto_swap_b = _require_bool(auto_swap_b, field="auto_swap_b")
    if corpus_invariance_receipt_id is not None:
        corpus_invariance_receipt_id = str(corpus_invariance_receipt_id).strip()
        if not corpus_invariance_receipt_id:
            corpus_invariance_receipt_id = None
    if corpus_invariance_receipt_id is None:
        raise RuntimeError("SCHEMA_FAIL:corpus_invariance_receipt_id")
    if rollback_evidence_hash is None:
        rollback_evidence_hash = canon_hash_obj(
            {
                "schema_version": "shadow_rollback_evidence_binding_v1",
                "proposal_id": str(proposal.get("proposal_id", "")),
            }
        )
    rollback_evidence_hash = str(rollback_evidence_hash).strip()
    if not rollback_evidence_hash.startswith("sha256:") or len(rollback_evidence_hash) != 71:
        raise RuntimeError("SCHEMA_FAIL:rollback_evidence_hash")

    if non_weakening_j_verified_b is None:
        non_weakening_j_verified_b = bool(j_window_rule_verified_b and j_per_tick_floor_verified_b)
    non_weakening_j_verified_b = _require_bool(non_weakening_j_verified_b, field="non_weakening_j_verified_b")

    reasons: list[str] = []
    if not outbox_only_verified_b:
        reasons.append("OUTBOX_ONLY_REQUIRED")
    if not tier_a_pass_b:
        reasons.append("TIER_A_FAIL")
    if not tier_b_pass_b:
        reasons.append("TIER_B_FAIL")
    if not integrity_guard_verified_b:
        reasons.append("SHADOW_PROTECTED_ROOT_MUTATION")
    if not static_protected_roots_verified_b:
        reasons.append("STATIC_ROOTS_UNVERIFIED")
    if not dynamic_protected_roots_verified_b:
        reasons.append("DYNAMIC_ROOTS_UNVERIFIED")
    if not j_window_rule_verified_b:
        reasons.append("SHADOW_J_WINDOW_RULE_FAIL")
    if not j_per_tick_floor_verified_b:
        reasons.append("SHADOW_J_PER_TICK_FLOOR_FAIL")
    if not non_weakening_j_verified_b:
        reasons.append("NON_WEAKENING_J_FAIL")
    if not corpus_replay_verified_b:
        reasons.append("CORPUS_REPLAY_FAIL")
    if not deterministic_fuzz_verified_b:
        reasons.append("DETERMINISTIC_FUZZ_FAIL")
    if not corpus_invariance_verified_b:
        reasons.append("CORPUS_INVARIANCE_FAIL")
    if not rollback_plan_bound_b:
        reasons.append("ROLLBACK_PLAN_MISSING")
    if auto_swap_b and not tier_b_pass_b:
        reasons.append("TIER_B_REQUIRED_FOR_SWAP")
    if not reasons:
        reasons.append("READY")

    ready = bool(
        outbox_only_verified_b
        and tier_a_pass_b
        and tier_b_pass_b
        and integrity_guard_verified_b
        and static_protected_roots_verified_b
        and dynamic_protected_roots_verified_b
        and j_window_rule_verified_b
        and j_per_tick_floor_verified_b
        and non_weakening_j_verified_b
        and corpus_replay_verified_b
        and deterministic_fuzz_verified_b
        and corpus_invariance_verified_b
        and rollback_plan_bound_b
    )

    receipt_without_id = {
        "schema_name": "shadow_regime_readiness_receipt_v1",
        "schema_version": "v19_0",
        "proposal_id": str(proposal.get("proposal_id", "")),
        "verdict": "READY" if ready else "NOT_READY",
        "outbox_only_verified_b": bool(outbox_only_verified_b),
        "non_weakening_j_verified_b": bool(non_weakening_j_verified_b),
        "corpus_replay_verified_b": bool(corpus_replay_verified_b),
        "deterministic_fuzz_verified_b": bool(deterministic_fuzz_verified_b),
        "tier_a_pass_b": bool(tier_a_pass_b),
        "tier_b_pass_b": bool(tier_b_pass_b),
        "runtime_tier_b_pass_b": bool(tier_b_pass_b),
        "integrity_guard_verified_b": bool(integrity_guard_verified_b),
        "static_protected_roots_verified_b": bool(static_protected_roots_verified_b),
        "dynamic_protected_roots_verified_b": bool(dynamic_protected_roots_verified_b),
        "j_window_rule_verified_b": bool(j_window_rule_verified_b),
        "j_per_tick_floor_verified_b": bool(j_per_tick_floor_verified_b),
        "corpus_invariance_verified_b": bool(corpus_invariance_verified_b),
        "corpus_invariance_receipt_id": corpus_invariance_receipt_id,
        "auto_swap_b": bool(auto_swap_b),
        "swap_execution_performed_b": False,
        "rollback_plan_bound_b": bool(rollback_plan_bound_b),
        "rollback_evidence_hash": rollback_evidence_hash,
        "reasons": sorted(set(reasons)),
    }
    receipt = dict(receipt_without_id)
    receipt["receipt_id"] = canon_hash_obj(receipt_without_id)
    validate_schema(receipt, "shadow_regime_readiness_receipt_v1")
    return receipt


def _as_bool(raw: str) -> bool:
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="shadow_airlock_v1")
    ap.add_argument("--proposal", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tier_a_pass_b", default="1")
    ap.add_argument("--tier_b_pass_b", default="1")
    ap.add_argument("--integrity_guard_verified_b", default="1")
    ap.add_argument("--static_protected_roots_verified_b", default="1")
    ap.add_argument("--dynamic_protected_roots_verified_b", default="1")
    ap.add_argument("--j_window_rule_verified_b", default="1")
    ap.add_argument("--j_per_tick_floor_verified_b", default="1")
    ap.add_argument("--non_weakening_j_verified_b", default="")
    ap.add_argument("--corpus_replay_verified_b", default="1")
    ap.add_argument("--deterministic_fuzz_verified_b", default="1")
    ap.add_argument("--rollback_plan_bound_b", default="1")
    ap.add_argument("--rollback_evidence_hash", default="")
    ap.add_argument("--auto_swap_b", default="0")
    return ap.parse_args()


def main() -> None:
    args = _parse_args()
    proposal_path = Path(args.proposal).resolve()
    out_path = Path(args.out).resolve()

    proposal = load_canon_dict(proposal_path)
    non_weakening_arg = str(args.non_weakening_j_verified_b).strip()
    non_weakening_value = None if non_weakening_arg == "" else _as_bool(non_weakening_arg)
    receipt = evaluate_shadow_regime_proposal(
        proposal,
        tier_a_pass_b=_as_bool(args.tier_a_pass_b),
        tier_b_pass_b=_as_bool(args.tier_b_pass_b),
        integrity_guard_verified_b=_as_bool(args.integrity_guard_verified_b),
        static_protected_roots_verified_b=_as_bool(args.static_protected_roots_verified_b),
        dynamic_protected_roots_verified_b=_as_bool(args.dynamic_protected_roots_verified_b),
        j_window_rule_verified_b=_as_bool(args.j_window_rule_verified_b),
        j_per_tick_floor_verified_b=_as_bool(args.j_per_tick_floor_verified_b),
        non_weakening_j_verified_b=non_weakening_value,
        corpus_replay_verified_b=_as_bool(args.corpus_replay_verified_b),
        deterministic_fuzz_verified_b=_as_bool(args.deterministic_fuzz_verified_b),
        rollback_plan_bound_b=_as_bool(args.rollback_plan_bound_b),
        rollback_evidence_hash=(str(args.rollback_evidence_hash).strip() or None),
        auto_swap_b=_as_bool(args.auto_swap_b),
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(out_path, receipt)
    print(receipt["verdict"])


if __name__ == "__main__":
    main()
