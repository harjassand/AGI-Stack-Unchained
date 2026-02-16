from __future__ import annotations

import pytest

from cdel.v11_1.verify_rsi_sas_math_v1 import verify

from .utils import build_state


def test_no_improvement(tmp_path):
    state = build_state(
        tmp_path,
        baseline_token="refl",
        candidate_token="refl",
        require_novelty=False,
        min_novelty_q=0,
        min_utility_delta_q=0,
        min_efficiency_delta_q=0,
        max_utility_regression_q=0,
    )
    with pytest.raises(Exception) as excinfo:
        verify(state.state_dir, mode="prefix")
    assert "NO_IMPROVEMENT" in str(excinfo.value)
