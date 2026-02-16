from __future__ import annotations

from pathlib import Path

from cdel.v17_0.runtime.val_runner_sealed_v1 import ensure_trace_complete


def test_trace_complete(v17_state_dir: Path) -> None:
    ensure_trace_complete(v17_state_dir / "candidate" / "exec_trace" / "val_exec_trace.jsonl")
