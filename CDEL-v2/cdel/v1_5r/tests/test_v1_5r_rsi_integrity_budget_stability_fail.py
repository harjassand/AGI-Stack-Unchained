from __future__ import annotations

import json
from pathlib import Path

from cdel.v1_5r.canon import load_canon_json, write_canon_json
from cdel.v1_5r.run_rsi_campaign import run_campaign
from cdel.v1_5r.verify_rsi_integrity import verify as verify_integrity


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def test_v1_5r_rsi_integrity_budget_stability_fail(tmp_path: Path) -> None:
    pack_path = _repo_root() / "campaigns" / "rsi_real_integrity_v1" / "rsi_real_campaign_pack_v1.json"
    campaign_pack = load_canon_json(pack_path)
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
        campaign_pack=campaign_pack,
        pack_path=pack_path,
    )

    ledger_path = out_dir / "current" / "barrier_ledger_v1.jsonl"
    assert ledger_path.exists()
    lines = [line for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines
    last_entry = json.loads(lines[-1])
    recovery_epoch = last_entry.get("recovery_epoch") or last_entry.get("end_epoch")
    assert isinstance(recovery_epoch, str)
    report_path = out_dir / "epochs" / recovery_epoch / "diagnostics" / "eval_budget_report_v1.json"
    assert report_path.exists()
    report = load_canon_json(report_path)
    budgets = report.get("budgets", {})
    budgets["budget_env_steps_total"] = int(budgets.get("budget_env_steps_total", 0)) + 1
    report["budgets"] = budgets
    write_canon_json(report_path, report)

    ok, reason = verify_integrity(out_dir)
    assert not ok
    assert "BUDGET_NOT_STABLE" in reason
