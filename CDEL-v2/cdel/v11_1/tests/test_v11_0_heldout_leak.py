from __future__ import annotations

import json
import pytest

from cdel.v11_0.verify_rsi_arch_synthesis_v1 import verify
from .utils import build_valid_state


def test_heldout_leak(tmp_path):
    state = build_valid_state(tmp_path)
    training_path = state["state_dir"] / "training" / "inputs" / "training_examples_v1.jsonl"
    lines = training_path.read_text(encoding="utf-8").splitlines()
    obj = json.loads(lines[0])
    obj.setdefault("source", {})["split"] = "HELDOUT"
    lines[0] = json.dumps(obj, separators=(",", ":"), sort_keys=True)
    training_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(Exception) as excinfo:
        verify(state["state_dir"], mode="prefix")
    assert "HELDOUT_LEAK" in str(excinfo.value)
