from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from orchestrator.llm_backend import get_backend


def _sha256_prefixed(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_llm_backend_replay_miss_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    replay_path = tmp_path / "replay.jsonl"
    prompt = "known-prompt"
    response = "{\"ok\":true}"
    row = {
        "schema_version": "orch_llm_replay_row_v1",
        "backend": "openai",
        "model": "gpt-4.1",
        "prompt_sha256": _sha256_prefixed(prompt),
        "response_sha256": _sha256_prefixed(response),
        "prompt": prompt,
        "response": response,
        "created_at_utc": "2026-02-11T00:00:00Z",
    }
    replay_path.write_text(json.dumps(row, separators=(",", ":")) + "\n", encoding="utf-8")

    monkeypatch.setenv("ORCH_LLM_BACKEND", "openai_replay")
    monkeypatch.setenv("ORCH_OPENAI_MODEL", "gpt-4.1")
    monkeypatch.setenv("ORCH_LLM_REPLAY_PATH", str(replay_path))

    backend = get_backend()
    with pytest.raises(ValueError, match="missing prompt"):
        backend.generate("missing-prompt")

