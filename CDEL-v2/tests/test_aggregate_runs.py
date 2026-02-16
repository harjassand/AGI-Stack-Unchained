import subprocess
import sys
from pathlib import Path

from cdel.bench.experiment import run_experiment
from cdel.config import load_config


def test_aggregate_runs_deterministic(tmp_path):
    cfg = load_config(tmp_path)
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    run_experiment(cfg, Path("tasks/stream_min.jsonl"), "enum", runs_dir / "run_1", seed=0)

    out_dir = tmp_path / "analysis"
    cmd = [sys.executable, "analysis/aggregate_runs.py", "--runs", str(runs_dir), "--out", str(out_dir)]
    subprocess.run(cmd, check=True)
    master_runs_a = (out_dir / "master_runs.csv").read_bytes()
    master_tasks_a = (out_dir / "master_tasks.csv").read_bytes()

    subprocess.run(cmd, check=True)
    master_runs_b = (out_dir / "master_runs.csv").read_bytes()
    master_tasks_b = (out_dir / "master_tasks.csv").read_bytes()

    assert master_runs_a == master_runs_b
    assert master_tasks_a == master_tasks_b
