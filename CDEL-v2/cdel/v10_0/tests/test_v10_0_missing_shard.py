from __future__ import annotations

from pathlib import Path

import pytest
from cdel.v1_7r.canon import CanonError
from cdel.v10_0.verify_rsi_model_genesis_v1 import verify
from .utils import build_valid_state


def test_v10_0_missing_shard(tmp_path: Path) -> None:
    state = build_valid_state(tmp_path)
    Path(state["corpus_shard_path"]).unlink()
    with pytest.raises(CanonError, match="CORPUS_SHARD_MISSING"):
        verify(state["state_dir"], mode="prefix")
