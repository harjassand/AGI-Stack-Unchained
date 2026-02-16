from __future__ import annotations

import json
import pytest

from cdel.v11_0.verify_rsi_arch_synthesis_v1 import verify
from .utils import build_valid_state


def test_non_q32_value(tmp_path):
    state = build_valid_state(tmp_path)
    novelty_path = state["novelty_path"]
    data = json.loads(novelty_path.read_text(encoding="utf-8"))
    data["novelty_score_q32"] = 0.1
    novelty_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(Exception) as excinfo:
        verify(state["state_dir"], mode="prefix")
    assert "NON_Q32_VALUE" in str(excinfo.value)
