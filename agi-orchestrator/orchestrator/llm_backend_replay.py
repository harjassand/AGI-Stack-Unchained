"""Replay backend for deterministic prompt/response runs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from orchestrator.llm_cache import PromptCache
from orchestrator.llm_call_log import LLMCallLogger

@dataclass(frozen=True)
class ReplayEntry:
    prompt: str
    response: str


@dataclass
class ReplayBackend:
    entries: dict[str, ReplayEntry]
    cache: PromptCache | None = None
    logger: LLMCallLogger | None = None
    calls: int = 0

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        *,
        cache: PromptCache | None = None,
        logger: LLMCallLogger | None = None,
    ) -> "ReplayBackend":
        replay_path = Path(path)
        if not replay_path.exists():
            raise FileNotFoundError(f"replay file not found: {replay_path}")
        entries: dict[str, ReplayEntry] = {}
        for line in replay_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError("replay line must be a JSON object")
            prompt = payload.get("prompt")
            response = payload.get("response")
            if not isinstance(prompt, str) or not isinstance(response, str):
                raise ValueError("replay entries require prompt and response strings")
            entries[prompt] = ReplayEntry(prompt=prompt, response=response)
        if not entries:
            raise ValueError("replay file contains no entries")
        return cls(entries=entries, cache=cache, logger=logger)

    def generate(self, prompt: str) -> str:
        cache_hit = False
        if self.cache:
            cached = self.cache.get(prompt)
            if cached is not None:
                cache_hit = True
                response = cached
                if self.logger:
                    self.logger.record(prompt=prompt, response=response, cache_hit=True)
                return response
        entry = self.entries.get(prompt)
        if entry is None:
            raise ValueError("replay backend missing prompt")
        self.calls += 1
        response = entry.response
        if self.cache:
            self.cache.set(prompt, response)
        if self.logger:
            self.logger.record(prompt=prompt, response=response, cache_hit=cache_hit)
        return response
