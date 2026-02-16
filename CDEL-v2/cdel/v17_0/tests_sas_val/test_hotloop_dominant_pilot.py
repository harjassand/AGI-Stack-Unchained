from __future__ import annotations

from pathlib import Path

from cdel.v1_7r.canon import load_canon_json


def test_hotloop_dominant_pilot(v17_state_dir: Path) -> None:
    report = load_canon_json(sorted((v17_state_dir / "hotloop").glob("sha256_*.kernel_hotloop_report_v1.json"))[0])
    assert int(report["top_n"]) >= 10
    assert len(report["top_loops"]) >= 10
    assert report["pilot_loop_id"] == report["dominant_loop_id"]
