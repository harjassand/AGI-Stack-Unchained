from pathlib import Path

from cdel.bench.experiment import run_experiment
from cdel.config import load_config
from cdel.ledger.audit import audit_ledger


def test_run_experiment_and_audit(tmp_path):
    cfg = load_config(tmp_path)
    out_dir = tmp_path / "out"
    report = run_experiment(cfg, Path("tasks/stream_min.jsonl"), "enum", out_dir, seed=0)
    assert (out_dir / "config.json").exists()
    assert (out_dir / "report.json").exists()
    assert (out_dir / "metrics.csv").exists()
    assert (out_dir / "summary.txt").exists()
    assert (out_dir / "ledger" / "order.log").exists()
    assert report["results"]
    audit_ledger(load_config(out_dir), full=False)
