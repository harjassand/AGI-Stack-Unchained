from __future__ import annotations

import pytest

from cdel.v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json
from cdel.v11_0.verify_rsi_arch_synthesis_v1 import verify
from .utils import build_valid_state


def test_training_network_used(tmp_path):
    state = build_valid_state(tmp_path)
    receipt_path = state["training_receipt_path"]
    receipt = load_canon_json(receipt_path)
    receipt["network_used"] = True
    new_hash = sha256_prefixed(canon_bytes(receipt))
    new_path = receipt_path.parent / f"sha256_{new_hash.split(':',1)[1]}.sas_sealed_training_receipt_v1.json"
    write_canon_json(new_path, receipt)
    receipt_path.unlink()
    with pytest.raises(Exception) as excinfo:
        verify(state["state_dir"], mode="prefix")
    assert "TRAINING_NETWORK_USED" in str(excinfo.value)
