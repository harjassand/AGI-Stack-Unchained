"""Limits for backend LLM requests."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMBackendLimits:
    max_prompt_chars: int
    max_response_chars: int
    max_calls: int

    @classmethod
    def from_env(cls) -> "LLMBackendLimits":
        return cls(
            max_prompt_chars=_read_int("ORCH_LLM_MAX_PROMPT_CHARS", 8000),
            max_response_chars=_read_int("ORCH_LLM_MAX_RESPONSE_CHARS", 8000),
            max_calls=_read_int("ORCH_LLM_MAX_CALLS", 10),
        )


class LimitEnforcingBackend:
    def __init__(self, *, backend, limits: LLMBackendLimits) -> None:
        self.backend = backend
        self.limits = limits
        self.calls = 0

    def generate(self, prompt: str) -> str:
        if len(prompt) > self.limits.max_prompt_chars:
            raise ValueError("prompt exceeds max length")
        if self.calls >= self.limits.max_calls:
            raise ValueError("llm call budget exceeded")
        self.calls += 1
        response = self.backend.generate(prompt)
        if len(response) > self.limits.max_response_chars:
            raise ValueError("response exceeds max length")
        return response


def _read_int(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default
