from __future__ import annotations

import json
from pathlib import Path

from orchestrator.agent_transcript import AgentTranscript


def test_agent_transcript_logs_hashes(tmp_path: Path) -> None:
    path = tmp_path / "agent_transcript.jsonl"
    transcript = AgentTranscript(path=path)
    entry_hash = transcript.record(kind="action", payload={"tool": "read_file", "path": "input.json"})
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["entry_hash"] == entry_hash
