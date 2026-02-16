from __future__ import annotations

from pathlib import Path

import pytest
from cdel.v1_7r.canon import CanonError, load_canon_json, write_canon_json
from cdel.v10_0.verify_rsi_model_genesis_v1 import verify
from .utils import build_valid_state


def test_v10_0_training_config_drift(tmp_path: Path) -> None:
    state = build_valid_state(tmp_path)
    cfg_path = Path(state["training_config_path"])
    cfg = load_canon_json(cfg_path)
    cfg["steps"] = int(cfg.get("steps", 1)) + 1
    write_canon_json(cfg_path, cfg)
    with pytest.raises(CanonError, match="TRAINING_CONFIG_HASH_MISMATCH"):
        verify(state["state_dir"], mode="prefix")
