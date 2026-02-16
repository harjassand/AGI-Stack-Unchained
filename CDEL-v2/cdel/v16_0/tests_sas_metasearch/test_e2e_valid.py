from __future__ import annotations

from pathlib import Path

from cdel.v16_0.verify_rsi_sas_metasearch_v1 import verify


def test_e2e_valid(v16_run_root: Path) -> None:
    assert verify(v16_run_root, mode="full") == "VALID"
