from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v12_0.verify_rsi_sas_code_v1 import verify

from .utils import build_state


def test_preamble_hash_mismatch_fail_closed(tmp_path: Path) -> None:
    state = build_state(tmp_path)
    repo_root = Path(__file__).resolve().parents[4]
    preamble_path = repo_root / "CDEL-v2" / "cdel" / "v12_0" / "lean" / "SASCodePreambleV12.lean"
    original = preamble_path.read_bytes()
    try:
        preamble_path.write_bytes(original + b"\n-- tamper")
        with pytest.raises(Exception) as exc:
            verify(state.state_dir, mode="full")
        assert "INVALID:PREAMBLE_HASH_MISMATCH" in str(exc.value)
    finally:
        preamble_path.write_bytes(original)
