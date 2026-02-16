from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json
from cdel.v12_0.verify_rsi_sas_code_v1 import verify

from .utils import build_state


def test_perf_policy_cannot_disable_scaling_sanity(tmp_path: Path) -> None:
    state = build_state(tmp_path)
    policy_path = state.config_dir / "sas_code_perf_policy_v1.json"
    policy = load_canon_json(policy_path)
    policy["require_scaling_sanity"] = False
    write_canon_json(policy_path, policy)

    new_hash = sha256_prefixed(canon_bytes(policy))
    pack_path = state.config_dir / "rsi_sas_code_pack_v1.json"
    pack = load_canon_json(pack_path)
    pack["perf_policy_hash"] = new_hash
    write_canon_json(pack_path, pack)

    with pytest.raises(Exception) as exc:
        verify(state.state_dir, mode="full")
    assert "INVALID:PERF_POLICY_FORBIDDEN_VALUE:require_scaling_sanity" in str(exc.value)
