from __future__ import annotations

import json
from pathlib import Path

from scripts.aggregate_scoreboards import aggregate_scoreboards


def _write_scoreboard(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def test_aggregate_scoreboards_deterministic(tmp_path: Path) -> None:
    run1 = tmp_path / "runs" / "run1" / "scoreboard.json"
    run2 = tmp_path / "runs" / "run2" / "scoreboard.json"

    _write_scoreboard(
        run1,
        {
            "domain": "pyut-harness-v1",
            "run_id": "run1",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "dev_suite_hash": "suite-a",
            "baseline_success_rate": 0.5,
            "best_candidate_success_rate": 0.6,
            "heldout_cert_passed": False,
        },
    )
    _write_scoreboard(
        run2,
        {
            "domain": "pyut-harness-v1",
            "run_id": "run2",
            "timestamp": "2026-01-02T00:00:00+00:00",
            "dev_suite_hash": "suite-a",
            "baseline_success_rate": 0.75,
            "best_candidate_success_rate": 0.8,
            "heldout_cert_passed": True,
        },
    )

    agg1 = aggregate_scoreboards(
        tmp_path / "runs", domain="pyut-harness-v1", generated_at="2026-01-03T00:00:00+00:00"
    )
    agg2 = aggregate_scoreboards(
        tmp_path / "runs", domain="pyut-harness-v1", generated_at="2026-01-03T00:00:00+00:00"
    )

    assert json.dumps(agg1, sort_keys=True) == json.dumps(agg2, sort_keys=True)
