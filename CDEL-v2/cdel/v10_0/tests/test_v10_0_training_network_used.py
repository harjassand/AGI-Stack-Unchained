from __future__ import annotations

from pathlib import Path

import pytest
from cdel.v1_7r.canon import CanonError, load_canon_json, write_canon_json
from cdel.v10_0.verify_rsi_model_genesis_v1 import verify
from .utils import build_valid_state


def test_v10_0_training_network_used(tmp_path: Path) -> None:
    state = build_valid_state(tmp_path)
    receipt_path = Path(state["training_receipt_path"])
    receipt = load_canon_json(receipt_path)
    receipt["network_used"] = True
    write_canon_json(receipt_path, receipt)
    with pytest.raises(CanonError, match="TRAINING_NETWORK_USED"):
        verify(state["state_dir"], mode="prefix")
