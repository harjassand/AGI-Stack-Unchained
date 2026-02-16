from __future__ import annotations

from pathlib import Path

from self_improve_code_v1.canon.json_canon_v1 import canon_bytes
from self_improve_code_v1.domains.flagship_code_rsi_v1.replay_v1 import verify_run


def test_partial_run_verify_ok(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    (run_dir / "epochs" / "epoch_0000").mkdir(parents=True)

    (run_dir / "run_manifest.json").write_bytes(canon_bytes({}))
    (run_dir / "scoreboard.json").write_bytes(canon_bytes({}))

    summary = {
        "epoch": 0,
        "status": "INCOMPLETE",
        "where": "sealed_dev",
        "partial": {"step": "sealed_dev_submit", "candidates_generated": 2, "eligible_candidates": 1, "submitted": 0},
    }
    (run_dir / "epochs" / "epoch_0000" / "epoch_summary.json").write_bytes(canon_bytes(summary))

    ok, errors = verify_run(str(run_dir))
    assert not ok
    assert "E_RUN_INCOMPLETE" in errors
