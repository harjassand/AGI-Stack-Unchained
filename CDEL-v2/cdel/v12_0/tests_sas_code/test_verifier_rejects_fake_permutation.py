from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v12_0.verify_rsi_sas_code_v1 import verify

from .utils import build_state


def test_verifier_rejects_fake_permutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = build_state(tmp_path)

    def fake_execute(algo_kind: str, xs: list[int]) -> tuple[list[int], dict[str, int]]:
        # Always return a sorted list of zeros with the same length (not a permutation).
        return [0 for _ in xs], {}

    import cdel.v12_0.verify_rsi_sas_code_v1 as verifier

    monkeypatch.setattr(verifier, "execute_algorithm", fake_execute)

    with pytest.raises(Exception) as exc:
        verify(state.state_dir, mode="full")
    assert "INVALID:NOT_PERMUTATION" in str(exc.value)
