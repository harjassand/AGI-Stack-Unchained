from __future__ import annotations

from cdel.v19_0.common_v1 import canon_hash_obj
from cdel.v19_0.shadow_airlock_v1 import evaluate_shadow_regime_proposal


def _proposal() -> dict[str, object]:
    payload = {
        "schema_name": "shadow_regime_proposal_v1",
        "schema_version": "v19_0",
        "proposal_id": "sha256:" + ("0" * 64),
        "proposer_campaign_id": "rsi_knowledge_transpiler_v1",
        "target_regime_id": "rsi_omega_daemon_v20_0",
        "mode": "OUTBOX_ONLY_SHADOW",
        "activation_intent": "NO_SWAP",
        "candidate_bundle_ref": {
            "bundle_hash": "sha256:" + ("1" * 64),
            "state_dir_rel": "daemon/rsi_omega_daemon_v20_0/state",
        },
        "safety_invariants": [
            "NON_WEAKENING_J",
            "CORPUS_REPLAY",
            "DETERMINISTIC_FUZZ",
        ],
        "determinism_contract_hash": "sha256:" + ("2" * 64),
        "corpus_replay_suite_ref": "sha256:" + ("3" * 64),
        "deterministic_fuzz_suite_ref": "sha256:" + ("4" * 64),
        "shadow_evaluation_tiers_profile_id": "sha256:" + ("5" * 64),
        "shadow_protected_roots_profile_id": "sha256:" + ("6" * 64),
        "corpus_descriptor_id": "sha256:" + ("7" * 64),
        "witnessed_determinism_profile_id": "sha256:" + ("8" * 64),
        "j_comparison_profile_id": "sha256:" + ("9" * 64),
    }
    payload["proposal_id"] = canon_hash_obj({k: v for k, v in payload.items() if k != "proposal_id"})
    return payload


def test_shadow_airlock_ready_receipt_is_outbox_only() -> None:
    receipt = evaluate_shadow_regime_proposal(
        _proposal(),
        tier_a_pass_b=True,
        tier_b_pass_b=True,
        integrity_guard_verified_b=True,
        static_protected_roots_verified_b=True,
        dynamic_protected_roots_verified_b=True,
        j_window_rule_verified_b=True,
        j_per_tick_floor_verified_b=True,
        corpus_replay_verified_b=True,
        deterministic_fuzz_verified_b=True,
        rollback_plan_bound_b=True,
        auto_swap_b=False,
    )
    assert receipt["verdict"] == "READY"
    assert receipt["swap_execution_performed_b"] is False
    assert receipt["tier_a_pass_b"] is True
    assert receipt["tier_b_pass_b"] is True


def test_shadow_airlock_not_ready_when_non_weakening_fails() -> None:
    receipt = evaluate_shadow_regime_proposal(
        _proposal(),
        tier_a_pass_b=True,
        tier_b_pass_b=False,
        integrity_guard_verified_b=True,
        static_protected_roots_verified_b=True,
        dynamic_protected_roots_verified_b=True,
        j_window_rule_verified_b=False,
        j_per_tick_floor_verified_b=False,
        non_weakening_j_verified_b=False,
        corpus_replay_verified_b=True,
        deterministic_fuzz_verified_b=True,
        rollback_plan_bound_b=True,
        auto_swap_b=True,
    )
    assert receipt["verdict"] == "NOT_READY"
    assert "NON_WEAKENING_J_FAIL" in receipt["reasons"]
    assert "TIER_B_REQUIRED_FOR_SWAP" in receipt["reasons"]
