"""Ledger writer for SAS-MATH (v11.0)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import loads, write_jsonl_line
from cdel.v11_0.sas_math_ledger import compute_entry_hash


class SASMathLedgerWriter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._prev_hash = "GENESIS"
        self._seq = 0
        if path.exists():
            last = None
            for raw in path.read_text(encoding="utf-8").splitlines():
                if not raw.strip():
                    continue
                last = raw
            if last is not None:
                entry = loads(last)
                if isinstance(entry, dict):
                    seq = entry.get("seq")
                    if isinstance(seq, int):
                        self._seq = seq
                    entry_hash = entry.get("entry_hash")
                    if isinstance(entry_hash, str):
                        self._prev_hash = entry_hash

    def append(self, *, event_type: str, event_payload: dict[str, Any], tick: int) -> dict[str, Any]:
        entry = {
            "seq": self._seq + 1,
            "tick": int(tick),
            "event_type": event_type,
            "event_payload": dict(event_payload),
            "prev_entry_hash": self._prev_hash,
            "entry_hash": "",
        }
        entry["entry_hash"] = compute_entry_hash(entry)
        write_jsonl_line(self.path, entry)
        self._seq += 1
        self._prev_hash = entry["entry_hash"]
        return entry


__all__ = ["SASMathLedgerWriter"]
