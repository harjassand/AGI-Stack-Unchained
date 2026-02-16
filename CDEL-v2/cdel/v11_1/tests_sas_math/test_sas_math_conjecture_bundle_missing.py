from __future__ import annotations

import pytest

from cdel.v11_1.verify_rsi_sas_math_v1 import verify

from .utils import build_state


def test_conjecture_bundle_missing(tmp_path):
    state = build_state(tmp_path)
    bundle_path = next((state.state_dir / "conjectures" / "bundles").glob("sha256_*.sas_conjecture_bundle_v1.json"))
    bundle_path.unlink()

    with pytest.raises(Exception) as excinfo:
        verify(state.state_dir, mode="full")
    assert "CONJECTURE_BUNDLE_MISSING" in str(excinfo.value)
