from __future__ import annotations

from cdel.v18_0.omega_common_v1 import resolve_execution_mode
from cdel.v18_0.omega_tick_outcome_v1 import build_tick_outcome
from cdel.v18_0.omega_tick_snapshot_v1 import build_snapshot


def _hash(ch: str) -> str:
    return "sha256:" + (ch * 64)


def test_execution_mode_resolver_blackbox_truthy_values(monkeypatch) -> None:
    monkeypatch.delenv("OMEGA_BLACKBOX", raising=False)
    assert resolve_execution_mode() == "STRICT"

    for raw in ("1", "true", "yes", "on", "TRUE", "On"):
        monkeypatch.setenv("OMEGA_BLACKBOX", raw)
        assert resolve_execution_mode() == "BLACKBOX"


def test_tick_outcome_and_snapshot_record_execution_mode() -> None:
    strict_outcome = build_tick_outcome(
        tick_u64=1,
        action_kind="RUN_CAMPAIGN",
        campaign_id="rsi_sas_code_v12_0",
        subverifier_status="VALID",
        promotion_status="PROMOTED",
        promotion_reason_code="N/A",
        activation_success=True,
        manifest_changed=True,
        safe_halt=False,
        noop_reason="N/A",
    )
    assert strict_outcome["execution_mode"] == "STRICT"

    blackbox_outcome = build_tick_outcome(
        tick_u64=1,
        action_kind="RUN_CAMPAIGN",
        campaign_id="rsi_sas_code_v12_0",
        subverifier_status="VALID",
        promotion_status="PROMOTED",
        promotion_reason_code="N/A",
        activation_success=True,
        manifest_changed=True,
        safe_halt=False,
        noop_reason="N/A",
        execution_mode="BLACKBOX",
    )
    assert blackbox_outcome["execution_mode"] == "BLACKBOX"

    strict_snapshot = build_snapshot(
        {
            "tick_u64": 1,
            "state_hash": _hash("1"),
            "observation_report_hash": _hash("2"),
            "issue_bundle_hash": _hash("3"),
            "decision_plan_hash": _hash("4"),
            "dispatch_receipt_hash": None,
            "subverifier_receipt_hash": None,
            "promotion_receipt_hash": None,
            "activation_receipt_hash": None,
            "rollback_receipt_hash": None,
            "trace_hash_chain_hash": _hash("5"),
            "budget_remaining": {
                "cpu_cost_q32": {"q": 0},
                "build_cost_q32": {"q": 0},
                "verifier_cost_q32": {"q": 0},
                "disk_bytes_u64": 0,
            },
            "cooldowns": {},
            "goal_queue_hash": _hash("6"),
        }
    )
    assert strict_snapshot["execution_mode"] == "STRICT"

    blackbox_snapshot = build_snapshot(
        {
            "tick_u64": 1,
            "state_hash": _hash("1"),
            "observation_report_hash": _hash("2"),
            "issue_bundle_hash": _hash("3"),
            "decision_plan_hash": _hash("4"),
            "dispatch_receipt_hash": None,
            "subverifier_receipt_hash": None,
            "promotion_receipt_hash": None,
            "activation_receipt_hash": None,
            "rollback_receipt_hash": None,
            "trace_hash_chain_hash": _hash("5"),
            "execution_mode": "BLACKBOX",
            "budget_remaining": {
                "cpu_cost_q32": {"q": 0},
                "build_cost_q32": {"q": 0},
                "verifier_cost_q32": {"q": 0},
                "disk_bytes_u64": 0,
            },
            "cooldowns": {},
            "goal_queue_hash": _hash("6"),
        }
    )
    assert blackbox_snapshot["execution_mode"] == "BLACKBOX"
