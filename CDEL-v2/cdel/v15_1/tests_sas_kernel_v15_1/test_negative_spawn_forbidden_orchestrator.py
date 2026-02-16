from __future__ import annotations

import pytest

from cdel.v1_7r.canon import write_jsonl_line
from cdel.v15_1.verify_rsi_sas_kernel_v15_1 import V15_1KernelError, _validate_spawn_forbidden


def test_negative_spawn_forbidden_orchestrator(tmp_path) -> None:
    trace_path = tmp_path / "trace.jsonl"
    write_jsonl_line(
        trace_path,
        {
            "schema_version": "kernel_trace_event_v1",
            "event_ref_hash": "sha256:" + ("0" * 64),
            "prev_event_ref_hash": "GENESIS",
            "event_type": "SPAWN_V1",
            "payload": {"argv": ["python3", "-m", "orchestrator.run"]},
        },
    )
    with pytest.raises(V15_1KernelError):
        _validate_spawn_forbidden(trace_path)
