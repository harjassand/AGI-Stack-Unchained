from __future__ import annotations

import json

import pytest

from orchestrator.llm_backend_replay import ReplayBackend


def test_replay_backend_returns_response(tmp_path) -> None:
    path = tmp_path / "replay.jsonl"
    payload = {"prompt": "hello", "response": "{\"ok\": true}"}
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    backend = ReplayBackend.from_path(path)
    assert backend.generate("hello") == "{\"ok\": true}"


def test_replay_backend_missing_prompt_fails_cleanly(tmp_path) -> None:
    path = tmp_path / "replay.jsonl"
    payload = {"prompt": "known", "response": "value"}
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    backend = ReplayBackend.from_path(path)
    with pytest.raises(ValueError, match="missing prompt"):
        backend.generate("unknown")
