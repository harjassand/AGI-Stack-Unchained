"""Deterministic runtime transcript logging for agents."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from blake3 import blake3


@dataclass
class AgentTranscript:
    path: Path
    events: list[dict[str, Any]] = field(default_factory=list)

    def record(self, *, kind: str, payload: dict[str, Any]) -> str:
        entry = {"kind": kind, "payload": payload}
        entry_hash = _hash_entry(entry)
        record = {
            "kind": kind,
            "payload": payload,
            "entry_hash": entry_hash,
        }
        self.events.append(record)
        self._flush(record)
        return entry_hash

    def _flush(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def _hash_entry(entry: dict[str, Any]) -> str:
    canonical = json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return blake3(canonical.encode("utf-8")).hexdigest()
