from __future__ import annotations

import pytest

from cdel.v11_0.verify_rsi_arch_synthesis_v1 import verify
from .utils import build_valid_state


def _expect_missing(tmp_path, filename: str, reason: str):
    state = build_valid_state(tmp_path)
    path = state["state_dir"] / "control" / filename
    path.unlink(missing_ok=True)
    with pytest.raises(Exception) as excinfo:
        verify(state["state_dir"], mode="prefix")
    assert reason in str(excinfo.value)


def test_missing_enable_research(tmp_path):
    _expect_missing(tmp_path, "ENABLE_RESEARCH", "MISSING_ENABLE_RESEARCH")


def test_missing_enable_arch_synthesis(tmp_path):
    _expect_missing(tmp_path, "ENABLE_ARCH_SYNTHESIS", "MISSING_ENABLE_ARCH_SYNTHESIS")


def test_missing_enable_training(tmp_path):
    _expect_missing(tmp_path, "ENABLE_TRAINING", "MISSING_ENABLE_TRAINING")


def test_missing_enable_model_genesis(tmp_path):
    _expect_missing(tmp_path, "ENABLE_MODEL_GENESIS", "MISSING_ENABLE_MODEL_GENESIS")
