from __future__ import annotations

import json
from pathlib import Path

from tools.omega import omega_overnight_runner_v1 as runner


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def test_capability_usage_artifact_d6_counts_and_sorting(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    state_dir = run_dir / "daemon" / "rsi_omega_daemon_v18_0" / "state"

    # CODE dispatch with promoted+activated success.
    _write_json(
        state_dir / "dispatch" / "d0" / ("sha256_" + ("1" * 64) + ".omega_dispatch_receipt_v1.json"),
        {
            "schema_version": "omega_dispatch_receipt_v1",
            "campaign_id": "rsi_sas_code_v12_0",
            "capability_id": "RSI_SAS_CODE",
            "subrun": {"subrun_root_rel": "subruns/d0_code"},
        },
    )
    _write_json(
        state_dir / "dispatch" / "d0" / "promotion" / "omega_activation_binding_v1.json",
        {
            "schema_version": "omega_activation_binding_v1",
            "campaign_id": "rsi_sas_code_v12_0",
            "capability_id": "RSI_SAS_CODE",
        },
    )
    _write_json(
        state_dir / "dispatch" / "d0" / "promotion" / ("sha256_" + ("2" * 64) + ".omega_promotion_receipt_v1.json"),
        {
            "schema_version": "omega_promotion_receipt_v1",
            "result": {"status": "PROMOTED", "reason_code": None},
        },
    )
    _write_json(
        state_dir / "dispatch" / "d0" / "activation" / ("sha256_" + ("3" * 64) + ".omega_activation_receipt_v1.json"),
        {
            "schema_version": "omega_activation_receipt_v1",
            "activation_success": True,
            "reasons": ["HEALTHCHECK_PASS"],
        },
    )

    # ONTOLOGY skill dispatch with rejected promotion and denied activation.
    _write_json(
        state_dir / "dispatch" / "d1" / ("sha256_" + ("4" * 64) + ".omega_dispatch_receipt_v1.json"),
        {
            "schema_version": "omega_dispatch_receipt_v1",
            "campaign_id": "rsi_omega_skill_ontology_v1",
            "capability_id": "RSI_OMEGA_SKILL_ONTOLOGY",
            "subrun": {"subrun_root_rel": "subruns/d1_ontology"},
        },
    )
    _write_json(
        state_dir / "dispatch" / "d1" / "promotion" / "omega_activation_binding_v1.json",
        {
            "schema_version": "omega_activation_binding_v1",
            "campaign_id": "rsi_omega_skill_ontology_v1",
            "capability_id": "RSI_OMEGA_SKILL_ONTOLOGY",
        },
    )
    _write_json(
        state_dir / "dispatch" / "d1" / "promotion" / ("sha256_" + ("5" * 64) + ".omega_promotion_receipt_v1.json"),
        {
            "schema_version": "omega_promotion_receipt_v1",
            "result": {"status": "REJECTED", "reason_code": "NO_PROMOTION_BUNDLE"},
        },
    )
    _write_json(
        state_dir / "dispatch" / "d1" / "activation" / ("sha256_" + ("6" * 64) + ".omega_activation_receipt_v1.json"),
        {
            "schema_version": "omega_activation_receipt_v1",
            "activation_success": False,
            "reasons": ["META_CORE_DENIED"],
        },
    )
    _write_json(
        state_dir
        / "subruns"
        / "d1_ontology"
        / "daemon"
        / "rsi_omega_skill_ontology_v1"
        / "state"
        / "reports"
        / "omega_skill_report_v1.json",
        {
            "schema_version": "omega_skill_report_v1",
            "skill_id": "ontology",
            "tick_u64": 1,
            "inputs_hash": "sha256:" + ("a" * 64),
            "metrics": {},
            "flags": [],
            "recommendations": [],
        },
    )

    # Polymath scout dispatch with skipped promotion.
    _write_json(
        state_dir / "dispatch" / "d2" / ("sha256_" + ("7" * 64) + ".omega_dispatch_receipt_v1.json"),
        {
            "schema_version": "omega_dispatch_receipt_v1",
            "campaign_id": "rsi_polymath_scout_v1",
            "capability_id": "RSI_POLYMATH_SCOUT",
            "subrun": {"subrun_root_rel": "subruns/d2_scout"},
        },
    )
    _write_json(
        state_dir / "dispatch" / "d2" / "promotion" / "omega_activation_binding_v1.json",
        {
            "schema_version": "omega_activation_binding_v1",
            "campaign_id": "rsi_polymath_scout_v1",
            "capability_id": "RSI_POLYMATH_SCOUT",
        },
    )
    _write_json(
        state_dir / "dispatch" / "d2" / "promotion" / ("sha256_" + ("8" * 64) + ".omega_promotion_receipt_v1.json"),
        {
            "schema_version": "omega_promotion_receipt_v1",
            "result": {"status": "SKIPPED", "reason_code": "ALREADY_ACTIVE"},
        },
    )

    # Malformed dispatch receipt should not crash artifact writing.
    malformed_path = state_dir / "dispatch" / "zz" / "sha256_bad.omega_dispatch_receipt_v1.json"
    malformed_path.parent.mkdir(parents=True, exist_ok=True)
    malformed_path.write_text("{", encoding="utf-8")

    # Polymath progress snapshot deltas.
    _write_json(
        state_dir / "observations" / ("sha256_" + ("9" * 64) + ".omega_observation_report_v1.json"),
        {
            "schema_version": "omega_observation_report_v1",
            "tick_u64": 1,
            "metrics": {
                "top_void_score_q32": {"q": 100},
                "domain_coverage_ratio": {"q": 20},
                "domains_bootstrapped_u64": 1,
            },
        },
    )
    _write_json(
        state_dir / "observations" / ("sha256_" + ("b" * 64) + ".omega_observation_report_v1.json"),
        {
            "schema_version": "omega_observation_report_v1",
            "tick_u64": 2,
            "metrics": {
                "top_void_score_q32": {"q": 90},
                "domain_coverage_ratio": {"q": 30},
                "domains_bootstrapped_u64": 4,
            },
        },
    )

    out_path = runner._write_capability_usage_artifact(run_dir=run_dir)
    payload = json.loads(out_path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "OMEGA_CAPABILITY_USAGE_v1"
    assert bool(payload["ok_b"]) is False
    errors = payload.get("evidence_errors")
    assert isinstance(errors, list)
    assert any(str(row).startswith("INVALID_JSON:dispatch_receipt:") for row in errors)

    dispatch_caps = payload.get("dispatch_counts_by_capability")
    assert isinstance(dispatch_caps, list)
    cap_ids = [str(row.get("capability_id", "")) for row in dispatch_caps if isinstance(row, dict)]
    assert cap_ids == sorted(cap_ids)

    dispatch_campaigns = payload.get("dispatch_counts_by_campaign")
    assert isinstance(dispatch_campaigns, list)
    campaign_ids = [str(row.get("campaign_id", "")) for row in dispatch_campaigns if isinstance(row, dict)]
    assert campaign_ids == sorted(campaign_ids)

    promotion_by_cap = {
        str(row.get("capability_id", "")): row
        for row in (payload.get("promotion_counts_by_capability") or [])
        if isinstance(row, dict)
    }
    assert int((promotion_by_cap["RSI_SAS_CODE"]).get("promoted_u64", 0)) == 1
    assert int((promotion_by_cap["RSI_OMEGA_SKILL_ONTOLOGY"]).get("rejected_u64", 0)) == 1
    assert int((promotion_by_cap["RSI_POLYMATH_SCOUT"]).get("skipped_u64", 0)) == 1

    activation_by_cap = {
        str(row.get("capability_id", "")): row
        for row in (payload.get("activation_counts_by_capability") or [])
        if isinstance(row, dict)
    }
    assert int((activation_by_cap["RSI_SAS_CODE"]).get("activation_success_u64", 0)) == 1
    assert int((activation_by_cap["RSI_OMEGA_SKILL_ONTOLOGY"]).get("activation_denied_u64", 0)) == 1
    assert int((activation_by_cap["RSI_OMEGA_SKILL_ONTOLOGY"]).get("activation_other_fail_u64", 0)) == 0

    skill_reports = {
        str(row.get("capability_id", "")): row
        for row in (payload.get("observed_skill_reports") or [])
        if isinstance(row, dict)
    }
    ontology_row = skill_reports["RSI_OMEGA_SKILL_ONTOLOGY"]
    assert bool(ontology_row.get("report_present_b", False)) is True
    assert ontology_row.get("report_paths") == [
        "daemon/rsi_omega_daemon_v18_0/state/subruns/d1_ontology/daemon/rsi_omega_skill_ontology_v1/state/reports/omega_skill_report_v1.json"
    ]
    assert "RSI_OMEGA_SKILL_SWARM" not in skill_reports

    polymath_snapshot = payload.get("polymath_progress_snapshot")
    assert isinstance(polymath_snapshot, dict)
    assert int(polymath_snapshot.get("top_void_score_delta_q32", 0)) == -10
    assert int(polymath_snapshot.get("coverage_ratio_delta_q32", 0)) == 10
    assert int(polymath_snapshot.get("domains_bootstrapped_delta_u64", 0)) == 3

    ge_snapshot = payload.get("ge_sh1_snapshot")
    assert isinstance(ge_snapshot, dict)
    assert int(ge_snapshot.get("ge_dispatch_u64", 0)) == 0
    assert int(ge_snapshot.get("ccap_receipts_u64", 0)) == 0
