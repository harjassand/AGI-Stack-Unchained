from __future__ import annotations

from pathlib import Path

from cdel.v17_0.verify_rsi_sas_val_v1 import verify


def test_full_verify_valid(v17_state_dir: Path) -> None:
    assert verify(v17_state_dir, mode="full") == "VALID"
