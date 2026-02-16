from __future__ import annotations

import json
from pathlib import Path


def test_trace_row_fields(v17_state_dir: Path) -> None:
    rows = []
    for raw in (v17_state_dir / "candidate" / "exec_trace" / "val_exec_trace.jsonl").read_text(encoding="utf-8").splitlines():
        if raw.strip():
            rows.append(json.loads(raw))
    assert rows
    for row in rows:
        for key in ["input_hash", "output_hash", "val_cycles", "prev_hash", "hash"]:
            assert key in row
