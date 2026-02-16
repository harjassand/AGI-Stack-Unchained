from __future__ import annotations

import json
from pathlib import Path

from cdel.v18_0 import campaign_omega_skill_eff_flywheel_v1 as eff_campaign
from cdel.v18_0 import campaign_omega_skill_persistence_v1 as persistence_campaign
from cdel.v18_0 import campaign_omega_skill_transfer_v1 as transfer_campaign
from cdel.v18_0 import omega_observer_v1


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _write_pack(path: Path, schema_version: str) -> None:
    _write_json(
        path,
        {
            "schema_version": schema_version,
            "authoritative_state_root_rel": "daemon/rsi_omega_daemon_v18_0/state",
        },
    )


def test_legacy_skill_reports_produced_and_observable(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    schema_dir = repo_root / "Genesis" / "schema" / "v18_0"
    schema_dir.mkdir(parents=True, exist_ok=True)
    source_schema = (
        Path(__file__).resolve().parents[4] / "Genesis" / "schema" / "v18_0" / "omega_skill_report_v1.jsonschema"
    )
    schema_dir.joinpath("omega_skill_report_v1.jsonschema").write_text(source_schema.read_text(encoding="utf-8"), encoding="utf-8")

    (repo_root / "daemon" / "rsi_omega_daemon_v18_0" / "state").mkdir(parents=True, exist_ok=True)
    (repo_root / "daemon" / "rsi_omega_daemon_v18_0" / "config").mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("OMEGA_DEV_BENCHMARK_MODE", "1")
    monkeypatch.setenv("OMEGA_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("OMEGA_DAEMON_STATE_ROOT_REL", "daemon/rsi_omega_daemon_v18_0/state")

    transfer_pack = tmp_path / "transfer_pack.json"
    eff_pack = tmp_path / "eff_pack.json"
    persistence_pack = tmp_path / "persistence_pack.json"
    _write_pack(transfer_pack, "rsi_omega_skill_transfer_pack_v1")
    _write_pack(eff_pack, "rsi_omega_skill_eff_flywheel_pack_v1")
    _write_pack(persistence_pack, "rsi_omega_skill_persistence_pack_v1")

    transfer_campaign.run(campaign_pack=transfer_pack, out_dir=tmp_path / "out_transfer")
    eff_campaign.run(campaign_pack=eff_pack, out_dir=tmp_path / "out_eff")
    persistence_campaign.run(campaign_pack=persistence_pack, out_dir=tmp_path / "out_persistence")

    transfer_report = repo_root / "skills" / "reports" / "transfer" / "omega_skill_report_v1.json"
    eff_report = repo_root / "skills" / "reports" / "eff_flywheel" / "omega_skill_report_v1.json"
    persistence_report = repo_root / "skills" / "reports" / "persistence" / "omega_skill_report_v1.json"
    assert transfer_report.exists()
    assert eff_report.exists()
    assert persistence_report.exists()

    metrics, sources = omega_observer_v1._load_legacy_skill_metrics(root=repo_root)  # noqa: SLF001
    assert len(sources) >= 3
    assert "transfer_gain_q32" in metrics
    assert "flywheel_yield_q32" in metrics
    assert "persistence_health_q32" in metrics
