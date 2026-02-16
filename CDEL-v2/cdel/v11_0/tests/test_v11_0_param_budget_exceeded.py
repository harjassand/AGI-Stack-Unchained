from __future__ import annotations

import pytest

from cdel.v1_7r.canon import load_canon_json, write_canon_json
from cdel.v11_0.verify_rsi_arch_synthesis_v1 import verify
from .utils import build_valid_state


def test_param_budget_exceeded(tmp_path):
    state = build_valid_state(tmp_path)
    allowlist_path = state["state_dir"].parent / "config" / "arch_allowlist_v1.json"
    allowlist = load_canon_json(allowlist_path)
    allowlist["max_total_params"] = 1
    write_canon_json(allowlist_path, allowlist)
    with pytest.raises(Exception) as excinfo:
        verify(state["state_dir"], mode="prefix")
    assert "PARAM_BUDGET_EXCEEDED" in str(excinfo.value)
