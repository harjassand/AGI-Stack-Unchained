from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.llm_backend import get_backend


class _FakeHTTPResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001, ANN201
        return False

    def read(self) -> bytes:
        return self._body


def test_llm_backend_harvest_appends_replay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    replay_path = tmp_path / "harvest_replay.jsonl"

    monkeypatch.setenv("ORCH_LLM_BACKEND", "openai_harvest")
    monkeypatch.setenv("ORCH_OPENAI_MODEL", "gpt-4.1")
    monkeypatch.setenv("ORCH_LLM_REPLAY_PATH", str(replay_path))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("ORCH_LLM_LIVE_OK", "1")

    payload = {
        "output": [
            {
                "content": [
                    {
                        "type": "output_text",
                        "text": "{\"selection\":[{\"template_id\":\"t1\",\"target_relpath\":\"a.txt\"}]}",
                    }
                ]
            }
        ]
    }

    monkeypatch.setattr("orchestrator.llm_backend.urlopen", lambda req, timeout=60: _FakeHTTPResponse(payload))

    backend = get_backend()
    response = backend.generate("pick-best-template")
    assert "selection" in response
    assert replay_path.exists()

    rows = [json.loads(line) for line in replay_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 1
    row = rows[0]
    assert row["schema_version"] == "orch_llm_replay_row_v1"
    assert row["backend"] == "openai"
    assert row["model"] == "gpt-4.1"
    assert row["prompt"] == "pick-best-template"
    assert row["response"] == response
    assert row["prompt_sha256"].startswith("sha256:")
    assert row["response_sha256"].startswith("sha256:")
    assert isinstance(row["raw_response_json"], dict)

