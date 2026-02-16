from __future__ import annotations

import json
from pathlib import Path

from tools.omega import omega_benchmark_suite_v1 as benchmark


def test_gate_proof_payload_is_byte_stable_d4_v1(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    gate_eval = {
        "gate_status": {
            "A": "PASS",
            "B": "FAIL",
        },
        "polymath_stats": {},
    }

    first = benchmark._build_gate_proof_payload(
        series_prefix="omega_test",
        run_dir=run_dir,
        ticks_completed=17,
        gate_eval=gate_eval,
    )
    second = benchmark._build_gate_proof_payload(
        series_prefix="omega_test",
        run_dir=run_dir,
        ticks_completed=17,
        gate_eval=gate_eval,
    )

    first_bytes = json.dumps(first, sort_keys=True, separators=(",", ":"))
    second_bytes = json.dumps(second, sort_keys=True, separators=(",", ":"))
    assert first_bytes == second_bytes
    assert first["created_at_utc"] == ""
    assert int(first["created_from_tick_u64"]) == 17
