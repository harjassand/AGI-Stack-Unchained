from __future__ import annotations

import json

from orchestrator.llm_backend import MockBackend
from orchestrator.llm_backend_replay import ReplayBackend
from orchestrator.llm_cache import PromptCache


def test_prompt_cache_roundtrip(tmp_path) -> None:
    cache = PromptCache(tmp_path)
    cache.set("prompt", "response")
    assert cache.get("prompt") == "response"


def test_mock_backend_uses_cache(tmp_path) -> None:
    cache = PromptCache(tmp_path)
    backend = MockBackend(response="ok", cache=cache)
    assert backend.generate("prompt") == "ok"
    assert backend.calls == 1
    assert backend.generate("prompt") == "ok"
    assert backend.calls == 1


def test_replay_backend_uses_cache(tmp_path) -> None:
    replay_path = tmp_path / "replay.jsonl"
    replay_path.write_text(json.dumps({"prompt": "hi", "response": "yo"}) + "\n", encoding="utf-8")
    cache = PromptCache(tmp_path / "cache")
    backend = ReplayBackend.from_path(replay_path, cache=cache)
    assert backend.generate("hi") == "yo"
    backend.entries.pop("hi")
    assert backend.generate("hi") == "yo"
