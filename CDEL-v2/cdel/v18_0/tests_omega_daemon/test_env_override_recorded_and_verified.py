from __future__ import annotations

import pytest

from cdel.v18_0.omega_common_v1 import write_hashed_json
from cdel.v18_0.verify_rsi_omega_daemon_v1 import OmegaV18Error, verify
from .utils import latest_file, load_json, repo_root, run_tick_with_pack, write_json


def test_env_override_recorded_and_verified(tmp_path) -> None:
    pack = repo_root() / "campaigns" / "rsi_omega_daemon_v18_0_prod" / "rsi_omega_daemon_pack_v1.json"
    _, state_dir = run_tick_with_pack(tmp_path=tmp_path, campaign_pack=pack, tick_u64=1)

    dispatch_path = latest_file(state_dir / "dispatch", "*/sha256_*.omega_dispatch_receipt_v1.json")
    dispatch = load_json(dispatch_path)
    invocation = dispatch.get("invocation")
    assert isinstance(invocation, dict)
    assert isinstance(invocation.get("env_overrides"), dict)

    dispatch["invocation"]["env_overrides"] = {"V16_MAX_DEV_EVALS": "99999"}
    _, _, dispatch_hash = write_hashed_json(dispatch_path.parent, "omega_dispatch_receipt_v1.json", dispatch)

    snapshot_path = latest_file(state_dir / "snapshot", "sha256_*.omega_tick_snapshot_v1.json")
    snapshot = load_json(snapshot_path)
    snapshot["dispatch_receipt_hash"] = dispatch_hash
    write_json(snapshot_path, snapshot)

    with pytest.raises(OmegaV18Error, match="NONDETERMINISTIC"):
        verify(state_dir, mode="full")
