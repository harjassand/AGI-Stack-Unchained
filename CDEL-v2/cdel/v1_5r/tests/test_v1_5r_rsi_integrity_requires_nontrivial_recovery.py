from __future__ import annotations

from pathlib import Path

from cdel.v1_5r.canon import load_canon_json, write_canon_json
from cdel.v1_5r.run_rsi_campaign import run_campaign


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def test_v1_5r_rsi_integrity_requires_nontrivial_recovery(tmp_path: Path) -> None:
    base_pack_path = _repo_root() / "campaigns" / "rsi_real_integrity_v1" / "rsi_real_campaign_pack_v1.json"
    pack = load_canon_json(base_pack_path)
    pack["x-family_manifest"] = str(
        _repo_root() / "campaigns" / "rsi_real_integrity_v1" / "family_manifest_v1.json"
    )
    pack["insertion_epochs"] = []
    pack["expected_frontier_events"] = {}
    pack["policy_synthesizer_epochs"] = []
    pack_path = tmp_path / "pack.json"
    write_canon_json(pack_path, pack)

    out_dir = tmp_path / "rsi_integrity_run"
    run_campaign(
        out_dir,
        {},
        strict_rsi=True,
        strict_integrity=True,
        enable_macro_miner=True,
        enable_policy_synthesizer=True,
        enable_family_generalizer=True,
        mode="real",
        campaign_pack=pack,
        pack_path=pack_path,
    )

    reports = sorted(out_dir.glob("epochs/epoch_*/diagnostics/rsi_integrity_window_report_v1.json"))
    assert reports
    report = load_canon_json(reports[-1])
    check = report.get("checks", {}).get("nontrivial_recovery", {})
    assert check.get("ok") is False
    assert "NO_NONTRIVIAL_RECOVERY_WINDOW" in check.get("reason_codes", [])
