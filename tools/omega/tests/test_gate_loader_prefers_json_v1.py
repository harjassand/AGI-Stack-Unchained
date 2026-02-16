from __future__ import annotations

import json
from pathlib import Path

from tools.omega.omega_gate_loader_v1 import load_gate_statuses


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def test_gate_loader_prefers_json_v1(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write_json(
        run_dir / "OMEGA_BENCHMARK_GATES_v1.json",
        {
            "schema_version": "OMEGA_BENCHMARK_GATES_v1",
            "gates": {
                "A": {"status": "PASS", "details": {}},
                "B": {"status": "PASS", "details": {}},
                "C": {"status": "FAIL", "details": {}},
            },
        },
    )
    (run_dir / "OMEGA_BENCHMARK_SUMMARY_v1.md").write_text(
        "\n".join(
            [
                "# OMEGA Benchmark Summary (test)",
                "- Gate A (x): **FAIL**",
                "- Gate B (x): **FAIL**",
                "- Gate C (x): **PASS**",
                "",
            ]
        ),
        encoding="utf-8",
    )

    out = load_gate_statuses(run_dir)
    assert out == {"A": "PASS", "B": "PASS", "C": "FAIL"}
