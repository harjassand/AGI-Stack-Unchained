from __future__ import annotations

from pathlib import Path

from self_improve_code_v1.canon.json_canon_v1 import canon_bytes
from self_improve_code_v1.domains.flagship_code_rsi_v1.scoreboard_v1 import init_scoreboard, update_scoreboard


def test_scoreboard_canonical(tmp_path: Path) -> None:
    sb = init_scoreboard("run123")
    epoch_summary = {
        "epoch": 0,
        "sealed_passes": 1,
        "sealed_heldout_passes": 0,
        "topk_submitted": 4,
        "curriculum": {"tier": "t0"},
        "noop_filtered": 0,
        "noop_filtered_fraction": "0/1",
        "null_control_pass": False,
        "improvement_events": 0,
        "top_template_ids": ["t1"],
    }
    sb = update_scoreboard(sb, epoch_summary, {"t1": {"attempts": 1}}, {"devscreen_runs": 1}, rolling_window=2)
    path = tmp_path / "scoreboard.json"
    path.write_bytes(canon_bytes(sb))
    assert path.read_bytes() == canon_bytes(sb)
