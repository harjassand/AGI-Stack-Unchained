from __future__ import annotations

import json
from pathlib import Path

from orchestrator.suite_miner import mine_cases, write_jsonl


def _write_suite(path: Path) -> None:
    rows = [
        {
            "episode": 0,
            "task_id": "abs_int_v1",
            "fn_name": "abs_int",
            "signature": "def abs_int(x: int) -> int:",
            "tests": [
                {"args": [1], "expected": 1},
                {"args": [-1], "expected": 1},
            ],
        },
        {
            "episode": 1,
            "task_id": "abs_int_v2",
            "fn_name": "abs_int",
            "signature": "def abs_int(x: int) -> int:",
            "tests": [{"args": [2], "expected": 2}],
        },
    ]
    write_jsonl(path, rows)


def _write_artifacts(path: Path) -> None:
    rows = [
        {
            "episode": 0,
            "baseline_success": True,
            "candidate_success": False,
            "candidate_failed_test": 0,
        },
        {
            "episode": 0,
            "baseline_success": True,
            "candidate_success": False,
            "candidate_failed_test": 0,
        },
        {
            "episode": 1,
            "baseline_success": True,
            "candidate_success": False,
            "candidate_failed_test": 0,
        },
        {
            "episode": 1,
            "baseline_success": False,
            "candidate_success": False,
            "candidate_failed_test": 0,
        },
    ]
    write_jsonl(path, rows)


def test_suite_miner_dedup_and_cap(tmp_path: Path) -> None:
    root_dir = tmp_path / "cdel"
    suite_hash = "deadbeef"
    suite_path = root_dir / "sealed_suites" / f"{suite_hash}.jsonl"
    suite_path.parent.mkdir(parents=True, exist_ok=True)
    _write_suite(suite_path)

    run_dir = tmp_path / "runs" / "run1"
    (run_dir / "candidates" / "0" / "dev_artifacts").mkdir(parents=True, exist_ok=True)
    _write_artifacts(run_dir / "candidates" / "0" / "dev_artifacts" / "rows.jsonl")

    manifest = {"root_dir": str(root_dir), "dev_suite_hash": suite_hash}
    (run_dir / "manifest.json").parent.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    mined = mine_cases(run_dir=run_dir, domain="python-ut-v1", max_episodes=10)
    assert len(mined) == 2
    assert mined[0]["task_id"] == "abs_int_v1"
    assert mined[1]["task_id"] == "abs_int_v2"

    capped = mine_cases(run_dir=run_dir, domain="python-ut-v1", max_episodes=1)
    assert len(capped) == 1
