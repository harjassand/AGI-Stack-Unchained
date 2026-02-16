from __future__ import annotations

from orchestrator.llm_backend import MockBackend
from orchestrator.llm_cache import PromptCache
from orchestrator.llm_call_log import LLMCallLogger


def test_llm_call_logging_has_hashes_and_cache_hit(tmp_path) -> None:
    cache = PromptCache(tmp_path / "cache")
    logger = LLMCallLogger()
    backend = MockBackend(response="ok", cache=cache, logger=logger)

    backend.generate("prompt")
    backend.generate("prompt")

    assert len(logger.records) == 2
    first, second = logger.records
    assert first["prompt_hash"]
    assert first["response_hash"]
    assert first["cache_hit"] is False
    assert second["cache_hit"] is True
    assert second["backend_call_index"] == 1
