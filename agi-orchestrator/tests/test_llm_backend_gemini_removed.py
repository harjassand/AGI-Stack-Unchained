from __future__ import annotations

import pytest

from orchestrator.llm_backend import get_backend


def test_llm_backend_gemini_removed_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORCH_LLM_BACKEND", "gemini_harvest")
    with pytest.raises(ValueError, match="Gemini backend removed"):
        get_backend()
