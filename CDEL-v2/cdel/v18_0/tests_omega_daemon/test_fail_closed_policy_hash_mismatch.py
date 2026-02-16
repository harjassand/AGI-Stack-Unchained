from __future__ import annotations

import pytest

from cdel.v18_0.verify_rsi_omega_daemon_v1 import OmegaV18Error, verify
from .utils import load_json, run_tick_once, write_json


def test_fail_closed_policy_hash_mismatch(tmp_path) -> None:
    _, state_dir = run_tick_once(tmp_path, tick_u64=1)

    policy_path = state_dir.parent / "config" / "omega_policy_ir_v1.json"
    policy = load_json(policy_path)
    policy["policy_id"] = str(policy.get("policy_id", "policy")) + "_tamper"
    write_json(policy_path, policy)

    with pytest.raises(OmegaV18Error, match="POLICY_HASH_MISMATCH"):
        verify(state_dir, mode="full")
