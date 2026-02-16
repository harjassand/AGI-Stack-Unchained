"""Math research ledger writer (v8.0)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import loads, write_jsonl_line
from cdel.v8_0.math_ledger import compute_entry_hash


class MathLedgerWriter:
    def __init__(self, ledger_path: Path) -> None:
        self.ledger_path = ledger_path
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.ledger_path.exists():
            self.ledger_path.write_text("", encoding="utf-8")

    def _latest(self) -> tuple[str, int]:
        lines = self.ledger_path.read_text(encoding="utf-8").splitlines()
        if not lines:
            return "GENESIS", 0
        last_line = lines[-1]
        if not last_line.strip():
            return "GENESIS", 0
        last = loads(last_line)
        if isinstance(last, dict):
            return str(last.get("entry_hash")), int(last.get("seq", 0))
        return "GENESIS", 0

    def append(self, *, event_type: str, event_payload: dict[str, Any], tick: int) -> dict[str, Any]:
        prev_hash, last_seq = self._latest()
        entry = {
            "seq": last_seq + 1,
            "tick": int(tick),
            "event_type": event_type,
            "event_payload": dict(event_payload),
            "prev_entry_hash": prev_hash,
            "entry_hash": "",
        }
        entry["entry_hash"] = compute_entry_hash(entry)
        write_jsonl_line(self.ledger_path, entry)
        return entry


__all__ = ["MathLedgerWriter"]
