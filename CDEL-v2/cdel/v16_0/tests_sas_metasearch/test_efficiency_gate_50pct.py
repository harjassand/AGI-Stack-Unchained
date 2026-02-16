from __future__ import annotations

from pathlib import Path

from cdel.v1_7r.canon import load_canon_json


def test_efficiency_gate_50pct(v16_run_root: Path) -> None:
    state = v16_run_root / "daemon" / "rsi_sas_metasearch_v16_0" / "state"
    report_path = sorted((state / "reports").glob("sha256_*.metasearch_compute_report_v1.json"))[0]
    report = load_canon_json(report_path)
    assert int(report["c_cand_work_cost_total"]) * 2 <= int(report["c_base_work_cost_total"])
