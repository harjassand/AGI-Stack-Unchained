from __future__ import annotations

import json
from pathlib import Path

from orchestrator.suite_miner import mine_cases


def _write_suite(path: Path) -> None:
    rows = [
        {
            "episode": 0,
            "task_id": "abs_int_v1",
            "fn_name": "abs_int",
            "signature": "def abs_int(x: int) -> int:",
            "tests": [{"args": [1], "expected": 1}],
        }
    ]
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")


def _write_artifacts(path: Path) -> None:
    row = {
        "episode": 0,
        "baseline_success": True,
        "candidate_success": False,
        "candidate_failed_test": 0,
    }
    path.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")


def _compute_hash(path: Path) -> str:
    import blake3

    return blake3.blake3(path.read_bytes()).hexdigest()


def test_suite_augment_writes_new_hash_file(tmp_path: Path) -> None:
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

    mined = mine_cases(run_dir=run_dir, domain="python-ut-v1", max_episodes=5)
    assert mined

    out_dir = tmp_path / "sealed_suites_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    combined = [json.loads(line) for line in suite_path.read_text(encoding="utf-8").splitlines() if line] + mined
    temp = out_dir / "combined.jsonl"
    temp.write_text("\n".join(json.dumps(row, sort_keys=True) for row in combined) + "\n", encoding="utf-8")
    new_hash = _compute_hash(temp)
    final = out_dir / f"{new_hash}.jsonl"
    temp.replace(final)

    assert final.exists()
