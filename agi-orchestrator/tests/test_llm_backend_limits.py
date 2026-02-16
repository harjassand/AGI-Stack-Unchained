from __future__ import annotations

import os

import pytest

from orchestrator.llm_limits import LLMBackendLimits, LimitEnforcingBackend


class StaticBackend:
    def __init__(self, response: str) -> None:
        self.response = response

    def generate(self, prompt: str) -> str:
        _ = prompt
        return self.response


def test_limits_enforce_prompt_length() -> None:
    backend = LimitEnforcingBackend(
        backend=StaticBackend("ok"),
        limits=LLMBackendLimits(max_prompt_chars=3, max_response_chars=10, max_calls=1),
    )
    with pytest.raises(ValueError, match="prompt exceeds"):
        backend.generate("long")


def test_limits_enforce_response_length() -> None:
    backend = LimitEnforcingBackend(
        backend=StaticBackend("toolong"),
        limits=LLMBackendLimits(max_prompt_chars=10, max_response_chars=3, max_calls=1),
    )
    with pytest.raises(ValueError, match="response exceeds"):
        backend.generate("ok")


def test_limits_enforce_call_budget() -> None:
    backend = LimitEnforcingBackend(
        backend=StaticBackend("ok"),
        limits=LLMBackendLimits(max_prompt_chars=10, max_response_chars=10, max_calls=1),
    )
    backend.generate("ok")
    with pytest.raises(ValueError, match="call budget"):
        backend.generate("ok")


def test_limits_from_env_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ORCH_LLM_MAX_PROMPT_CHARS", raising=False)
    monkeypatch.delenv("ORCH_LLM_MAX_RESPONSE_CHARS", raising=False)
    monkeypatch.delenv("ORCH_LLM_MAX_CALLS", raising=False)
    limits = LLMBackendLimits.from_env()
    assert limits.max_prompt_chars == 8000
    assert limits.max_response_chars == 8000
    assert limits.max_calls == 10
