"""Ledger writer for daemon v7.0."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import canon_bytes, sha256_hex, write_jsonl_line
from cdel.v7_0.daemon_ledger import load_daemon_ledger, validate_daemon_chain


def _compute_entry_hash(entry: dict[str, Any]) -> str:
    payload = dict(entry)
    payload.pop("entry_hash", None)
    return sha256_hex(canon_bytes(payload))


def recover_ledger_state(ledger_path: Path) -> tuple[str, int, int]:
    if not ledger_path.exists():
        return "GENESIS", 0, 0
    entries = load_daemon_ledger(ledger_path)
    head_hash, last_tick, last_seq = validate_daemon_chain(entries)
    return head_hash, last_tick, last_seq


class LedgerWriter:
    def __init__(self, ledger_path: Path, *, prev_hash: str, seq: int) -> None:
        self.ledger_path = ledger_path
        self.prev_hash = prev_hash
        self.seq = seq
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.ledger_path.exists():
            self.ledger_path.write_text("", encoding="utf-8")

    def append(self, *, event_type: str, event_payload: dict[str, Any], tick: int) -> dict[str, Any]:
        self.seq += 1
        entry: dict[str, Any] = {
            "seq": self.seq,
            "tick": int(tick),
            "event_type": str(event_type),
            "event_payload": dict(event_payload),
            "prev_entry_hash": self.prev_hash,
            "entry_hash": "",
        }
        entry["entry_hash"] = _compute_entry_hash(entry)
        write_jsonl_line(self.ledger_path, entry)
        self.prev_hash = entry["entry_hash"]
        return entry


__all__ = ["LedgerWriter", "recover_ledger_state"]
