from __future__ import annotations

import json
import pytest

from cdel.v11_0.verify_rsi_sas_math_v1 import verify

from .utils import build_state


def test_non_q32_value(tmp_path):
    state = build_state(tmp_path)
    promo_path = state.promotion_path
    promo = json.loads(promo_path.read_text(encoding="utf-8"))
    promo["min_novelty_q32"] = 0.5
    promo_path.write_text(json.dumps(promo, separators=(",", ":"), sort_keys=True), encoding="utf-8")
    with pytest.raises(Exception) as excinfo:
        verify(state.state_dir, mode="prefix")
    assert "NON_Q32_VALUE" in str(excinfo.value)
