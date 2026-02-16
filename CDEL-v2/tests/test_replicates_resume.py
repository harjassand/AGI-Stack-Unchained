import csv
import json
import runpy
import sys
from pathlib import Path

from cdel.bench import experiment as exp
from cdel.config import write_default_config


def _run_replicates(args: list[str]) -> None:
    argv = ["run_replicates.py"] + args
    old_argv = sys.argv
    sys.argv = argv
    try:
        runpy.run_path(str(Path("experiments/run_replicates.py")), run_name="__main__")
    finally:
        sys.argv = old_argv


def _count_metrics(path: Path) -> int:
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        return sum(1 for _ in reader)


def test_replicates_resume(tmp_path, monkeypatch):
    write_default_config(tmp_path, budget=100000)
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    lines = Path("tasks/stream_min.jsonl").read_text(encoding="utf-8").splitlines()
    full_lines = lines[:5]
    tasks_path = tasks_dir / "stream_small.jsonl"
    tasks_path.write_text("\n".join(full_lines) + "\n", encoding="utf-8")

    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(
        json.dumps(
            {
                "runs": [
                    {
                        "run_id": "repl_small",
                        "tasks_file": "tasks/stream_small.jsonl",
                        "generator_mode": "enum",
                        "certificate_mode": "bounded",
                        "budget": 100000,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    out_root = tmp_path / "runs"

    original_run_tasks = exp.run_tasks

    def limited_run_tasks(cfg, stream_path, **kwargs):
        partial_path = stream_path.parent / "stream_partial.jsonl"
        partial_path.write_text("\n".join(full_lines[:2]) + "\n", encoding="utf-8")
        return original_run_tasks(cfg, partial_path, **kwargs)

    monkeypatch.setattr(exp, "run_tasks", limited_run_tasks)

    _run_replicates(
        [
            "--matrix",
            str(matrix_path),
            "--seeds",
            "0",
            "--out",
            str(out_root),
            "--overwrite",
            "--root",
            str(tmp_path),
        ]
    )

    run_dir = out_root / "repl_small_s0"
    done_path = run_dir / "DONE"
    if done_path.exists():
        done_path.unlink()
    status_path = run_dir / "STATUS.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status["status"] = "running"
    status_path.write_text(json.dumps(status, sort_keys=True), encoding="utf-8")

    monkeypatch.setattr(exp, "run_tasks", original_run_tasks)

    _run_replicates(
        [
            "--matrix",
            str(matrix_path),
            "--seeds",
            "0,1",
            "--out",
            str(out_root),
            "--resume",
            "--root",
            str(tmp_path),
        ]
    )

    assert (out_root / "repl_small_s0" / "DONE").exists()
    assert (out_root / "repl_small_s1" / "DONE").exists()
    assert (out_root / "replicates_run_summary.json").exists()
    assert _count_metrics(out_root / "repl_small_s0" / "metrics.csv") == len(full_lines)
