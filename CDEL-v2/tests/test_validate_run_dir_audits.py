import runpy
import sys
from pathlib import Path

import pytest

from cdel.bench.experiment import run_experiment
from cdel.config import load_config


def _run_validate(path: Path) -> None:
    argv = ["validate_run_dir.py", str(path)]
    old_argv = sys.argv
    sys.argv = argv
    try:
        runpy.run_path(str(Path("analysis/validate_run_dir.py")), run_name="__main__")
    finally:
        sys.argv = old_argv


def test_validate_run_dir_requires_audits(tmp_path):
    cfg = load_config(tmp_path)
    out_dir = tmp_path / "run"
    run_experiment(cfg, Path("tasks/stream_min.jsonl"), "enum", out_dir, seed=0)

    (out_dir / "audit_fast.ok").unlink(missing_ok=True)
    (out_dir / "audit_full.ok").unlink(missing_ok=True)

    with pytest.raises(SystemExit):
        _run_validate(out_dir)
