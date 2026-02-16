from __future__ import annotations

from pathlib import Path

import pytest
from cdel.v1_7r.canon import CanonError
from cdel.v9_0.verify_rsi_boundless_science_v1 import verify
from .utils import build_valid_state


def test_v9_0_requires_valid_lease(tmp_path: Path) -> None:
    state = build_valid_state(tmp_path)
    lease_path = state["state_dir"] / "science" / "leases" / "lease_fixture.science_lease_token_v1.json"
    lease_path.unlink()
    with pytest.raises(CanonError, match="SCIENCE_LEASE_INVALID"):
        verify(state["state_dir"], mode="prefix")
