from __future__ import annotations

import pytest

from cdel.v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json
from cdel.v11_0.verify_rsi_arch_synthesis_v1 import verify
from .utils import build_valid_state


def test_capacity_efficiency_mismatch(tmp_path):
    state = build_valid_state(tmp_path)
    dev_dir = state["state_dir"] / "eval" / "dev_receipts"
    dev_path = next(dev_dir.glob("sha256_*.sas_model_eval_receipt_v1.json"))
    dev = load_canon_json(dev_path)
    dev["capacity_efficiency_q32"] = {"schema_version": "q32_v1", "shift": 32, "q": "123"}
    new_hash = sha256_prefixed(canon_bytes(dev))
    new_path = dev_dir / f"sha256_{new_hash.split(':',1)[1]}.sas_model_eval_receipt_v1.json"
    write_canon_json(new_path, dev)
    dev_path.unlink()
    with pytest.raises(Exception) as excinfo:
        verify(state["state_dir"], mode="prefix")
    assert "CAPACITY_EFFICIENCY_MISMATCH" in str(excinfo.value)
