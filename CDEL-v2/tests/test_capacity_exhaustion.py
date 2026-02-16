from pathlib import Path

from cdel.bench.experiment import run_experiment
from cdel.config import load_config
from cdel.ledger.errors import RejectCode


def test_capacity_exhaustion(tmp_path):
    cfg = load_config(tmp_path)
    out_dir = tmp_path / "out"
    report = run_experiment(cfg, Path("tasks/stream_min.jsonl"), "enum", out_dir, seed=0, budget_override=1)
    rejections = [row.get("rejection") for row in report.get("results") or []]
    assert RejectCode.CAPACITY_EXCEEDED.value in rejections
