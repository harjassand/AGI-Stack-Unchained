from __future__ import annotations

import pytest

from cdel.v11_1.verify_rsi_sas_math_v1 import verify

from .utils import build_state


def test_conjecture_statement_hash_mismatch(tmp_path):
    state = build_state(tmp_path)
    stmt_path = next((state.state_dir / "math" / "problems").glob("sha256_*.statement.txt"))
    stmt_path.write_text("example : 0 = 1 :=\n", encoding="utf-8")

    with pytest.raises(Exception) as excinfo:
        verify(state.state_dir, mode="full")
    assert "CONJECTURE_STATEMENT_HASH_MISMATCH" in str(excinfo.value)
