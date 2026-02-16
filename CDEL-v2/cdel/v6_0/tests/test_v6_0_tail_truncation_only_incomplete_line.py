from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v1_7r.canon import canon_bytes
from cdel.v6_0.daemon_ledger import truncate_incomplete_tail
from .utils import build_entry


def test_v6_0_tail_truncation_only_incomplete_line(tmp_path: Path) -> None:
    ledger = tmp_path / "daemon_ledger_v1.jsonl"

    entry = build_entry(1, 0, "BOOT", "GENESIS")
    line = canon_bytes(entry).decode("utf-8")

    # Valid line + incomplete tail (no newline).
    ledger.write_text(line + "\n" + "{\"seq\":2", encoding="utf-8")
    assert truncate_incomplete_tail(ledger) is True
    assert ledger.read_text(encoding="utf-8") == line + "\n"

    # Corruption before tail should fail closed.
    ledger.write_text("{bad}\n" + line, encoding="utf-8")
    with pytest.raises(Exception):
        truncate_incomplete_tail(ledger)
