from __future__ import annotations

import hashlib
from pathlib import Path

from cdel.v18_0 import omega_observer_v1 as observer
from cdel.v18_0.omega_tick_outcome_v1 import build_tick_outcome
from cdel.v18_0.omega_tick_stats_v1 import build_tick_stats


def _hash(ch: str) -> str:
    return "sha256:" + (ch * 64)


def _source(schema_id: str, campaign_id: str) -> dict[str, str]:
    return {
        "schema_id": schema_id,
        "artifact_hash": "sha256:" + hashlib.sha256(schema_id.encode("utf-8")).hexdigest(),
        "producer_campaign_id": campaign_id,
        "producer_run_id": "rsi_test_0001",
    }


def _stats_with_rejects() -> dict[str, object]:
    stats = None
    statuses = ["REJECTED", "REJECTED", "REJECTED", "PROMOTED"]
    for idx, status in enumerate(statuses, start=1):
        outcome = build_tick_outcome(
            tick_u64=idx,
            action_kind="RUN_CAMPAIGN",
            campaign_id="rsi_sas_code_v12_0",
            subverifier_status="VALID",
            promotion_status=status,
            promotion_reason_code="TEST",
            activation_success=False,
            manifest_changed=False,
            safe_halt=False,
            noop_reason="N/A",
        )
        stats = build_tick_stats(
            tick_u64=idx,
            tick_outcome=outcome,
            previous_tick_stats=stats,
        )
    assert stats is not None
    return stats


def test_observer_reports_real_promotion_reject_rate(monkeypatch) -> None:
    monkeypatch.setattr(observer, "repo_root", lambda: Path("/tmp"))
    monkeypatch.setattr(observer, "load_index", lambda _root: {"schema_version": "omega_observer_index_v1", "entries": {}})
    monkeypatch.setattr(observer, "_read_binding_for_manifest", lambda _hash: None)
    monkeypatch.setattr(
        observer,
        "_load_metasearch_metric",
        lambda **kwargs: (1, _source("metasearch_compute_report_v1", "rsi_sas_metasearch_v16_1")),
    )
    monkeypatch.setattr(
        observer,
        "_load_hotloop_metric",
        lambda **kwargs: (1, _source("kernel_hotloop_report_v1", "rsi_sas_val_v17_0")),
    )
    monkeypatch.setattr(
        observer,
        "_load_build_metric",
        lambda **kwargs: (1, _source("sas_system_perf_report_v1", "rsi_sas_system_v14_0")),
    )
    monkeypatch.setattr(
        observer,
        "_load_science_metric",
        lambda **kwargs: (1, _source("sas_science_promotion_bundle_v1", "rsi_sas_science_v13_0")),
    )

    previous_stats = _stats_with_rejects()
    report, _ = observer.observe(
        tick_u64=10,
        active_manifest_hash=_hash("a"),
        policy_hash=_hash("b"),
        registry_hash=_hash("c"),
        objectives_hash=_hash("d"),
        previous_tick_stats=previous_stats,
        previous_tick_stats_source=_source("omega_tick_stats_v1", "rsi_omega_daemon_v18_0"),
    )

    metrics = report["metrics"]
    assert metrics["promotion_reject_rate_rat"] == {"num_u64": 3, "den_u64": 4}
    assert metrics["subverifier_invalid_rate_rat"] == {"num_u64": 0, "den_u64": 4}
    assert metrics["runaway_blocked_noop_rate_rat"] == {"num_u64": 0, "den_u64": 4}
