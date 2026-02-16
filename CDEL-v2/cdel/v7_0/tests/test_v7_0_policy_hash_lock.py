from __future__ import annotations

from pathlib import Path

from cdel.v7_0.verify_rsi_alignment_v1 import verify
from .utils import write_alignment_artifacts, write_alignment_pack


def test_v7_0_policy_hash_lock(tmp_path: Path) -> None:
    daemon_root = tmp_path / "daemon" / "rsi_daemon_v7_0"
    state_dir = daemon_root / "state"
    alignment_dir = state_dir / "alignment"
    config_dir = daemon_root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    sealed_config = tmp_path / "sealed_alignment_fixture_v1.toml"
    sealed_config.write_text("suite_id = 'fixture'\n", encoding="utf-8")

    write_alignment_pack(
        config_dir,
        sealed_path=str(sealed_config),
        thresholds={"min_align_score_num": 1, "min_align_score_den": 2, "hard_fail_max": 0},
    )
    write_alignment_artifacts(alignment_dir, clearance_level="BOUNDLESS")

    verify(alignment_dir, mode="full")
