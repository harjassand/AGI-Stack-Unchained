from __future__ import annotations

from pathlib import Path

from cdel.v1_7r.canon import write_canon_json
from cdel.v18_0 import campaign_polymath_conquer_domain_v1 as conquer_campaign
from cdel.v18_0.omega_common_v1 import load_canon_dict


def _write_registry(path: Path) -> None:
    payload = {
        "schema_version": "polymath_domain_registry_v1",
        "domains": [
            {
                "domain_id": "alpha_domain",
                "domain_name": "Alpha",
                "status": "BLOCKED_POLICY",
                "created_at_utc": "2026-02-10T00:00:00+00:00",
                "topic_ids": ["topic:alpha"],
                "domain_pack_rel": "domains/alpha_domain/domain_pack_v1.json",
                "capability_id": "RSI_DOMAIN_ALPHA",
                "dataset_artifact_sha256s": [],
                "ready_for_conquer": False,
                "ready_for_conquer_reason": "BLOCKED_POLICY",
                "conquered_b": False,
            },
            {
                "domain_id": "beta_domain",
                "domain_name": "Beta",
                "status": "ACTIVE",
                "created_at_utc": "2026-02-10T00:00:00+00:00",
                "topic_ids": ["topic:beta"],
                "domain_pack_rel": "domains/beta_domain/domain_pack_v1.json",
                "capability_id": "RSI_DOMAIN_BETA",
                "dataset_artifact_sha256s": [],
                "ready_for_conquer": False,
                "ready_for_conquer_reason": "BOOTSTRAP_PENDING",
                "conquered_b": False,
            },
        ],
    }
    write_canon_json(path, payload)


def test_conquer_no_ready_domain_diagnostics(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    out_dir = tmp_path / "out"
    pack_path = tmp_path / "conquer_pack.json"

    registry_path = repo / "polymath" / "registry" / "polymath_domain_registry_v1.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    _write_registry(registry_path)

    write_canon_json(
        pack_path,
        {
            "schema_version": "rsi_polymath_conquer_domain_pack_v1",
            "domain_registry_path_rel": "polymath/registry/polymath_domain_registry_v1.json",
            "require_improvement_b": False,
            "target_domain_id": "pubchem_weight300",
        },
    )

    monkeypatch.setattr(conquer_campaign, "repo_root", lambda: repo)
    monkeypatch.setattr(conquer_campaign, "emit_test_plan_receipt", lambda **_kwargs: ({}, {}))
    conquer_campaign.run(campaign_pack=pack_path, out_dir=out_dir)

    report = load_canon_dict(
        out_dir / "daemon" / "rsi_polymath_conquer_domain_v1" / "state" / "reports" / "polymath_conquer_report_v1.json"
    )
    assert str(report.get("status", "")) == "NO_READY_DOMAIN"
    assert int(report.get("domains_seen_u64", 0)) == 2
    skip_reasons = report.get("skip_reasons")
    assert isinstance(skip_reasons, dict)
    assert int(skip_reasons.get("NOT_ACTIVE", 0)) >= 1
    assert int(skip_reasons.get("NOT_READY_FOR_CONQUER", 0)) >= 1
