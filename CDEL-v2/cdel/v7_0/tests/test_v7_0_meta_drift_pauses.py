from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v7_0.verify_rsi_alignment_v1 import verify
from cdel.v1_7r.canon import load_canon_json, write_canon_json
from .utils import write_alignment_artifacts, write_alignment_pack, copy_policy


def test_v7_0_meta_drift_pauses(tmp_path: Path) -> None:
    daemon_root = tmp_path / "daemon" / "rsi_daemon_v7_0"
    alignment_dir = daemon_root / "state" / "alignment"
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

    # Tamper meta hash in policy lock
    lock_path = alignment_dir / "policy" / "superego_policy_lock_v1.json"
    lock = load_canon_json(lock_path)
    lock["meta_hash"] = "0" * 64
    write_canon_json(lock_path, lock)

    with pytest.raises(Exception):
        verify(alignment_dir, mode="full")
