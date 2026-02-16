from __future__ import annotations

import pytest

from cdel.v1_7r.canon import load_canon_json, write_canon_json
from cdel.v11_0.verify_rsi_arch_synthesis_v1 import verify
from .utils import build_valid_state


def test_opset_drift(tmp_path):
    state = build_valid_state(tmp_path)
    opset_path = state["state_dir"].parent / "config" / "sas_opset_manifest_v1.json"
    opset = load_canon_json(opset_path)
    opset["ops"].append("new_op")
    write_canon_json(opset_path, opset)
    with pytest.raises(Exception) as excinfo:
        verify(state["state_dir"], mode="prefix")
    assert "OPSET_HASH_MISMATCH" in str(excinfo.value)
