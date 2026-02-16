"""LLM call logging with hashed prompts and responses."""

from __future__ import annotations

from dataclasses import dataclass, field

from blake3 import blake3


@dataclass
class LLMCallLogger:
    records: list[dict] = field(default_factory=list)
    _call_index: int = 0

    def record(self, *, prompt: str, response: str, cache_hit: bool) -> None:
        prompt_hash = blake3(prompt.encode("utf-8")).hexdigest()
        response_hash = blake3(response.encode("utf-8")).hexdigest()
        record = {
            "prompt_hash": prompt_hash,
            "response_hash": response_hash,
            "cache_hit": cache_hit,
            "backend_call_index": self._call_index,
        }
        self.records.append(record)
        self._call_index += 1

    @property
    def calls_used(self) -> int:
        return len(self.records)
