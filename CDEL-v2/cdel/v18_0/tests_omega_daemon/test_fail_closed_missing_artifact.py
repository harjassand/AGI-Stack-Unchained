from __future__ import annotations

import pytest

from cdel.v18_0.verify_rsi_omega_daemon_v1 import OmegaV18Error, verify
from .utils import latest_file, load_json, run_tick_once


def test_fail_closed_missing_artifact(tmp_path) -> None:
    _, state_dir = run_tick_once(tmp_path, tick_u64=1)

    snapshot = load_json(latest_file(state_dir / "snapshot", "sha256_*.omega_tick_snapshot_v1.json"))
    obs_hash = str(snapshot["observation_report_hash"]).split(":", 1)[1]
    obs_file = state_dir / "observations" / f"sha256_{obs_hash}.omega_observation_report_v1.json"
    obs_file.unlink()

    with pytest.raises(OmegaV18Error, match="MISSING_STATE_INPUT"):
        verify(state_dir, mode="full")
