import json
from pathlib import Path

from cdel.bench.experiment import run_experiment
from cdel.config import load_config
from cdel.ledger.audit import audit_run


def test_audit_emits_ok_markers(tmp_path):
    cfg = load_config(tmp_path)
    out_dir = tmp_path / "run"
    run_experiment(cfg, Path("tasks/stream_min.jsonl"), "enum", out_dir, seed=0)

    (out_dir / "audit_fast.ok").unlink(missing_ok=True)
    (out_dir / "audit_full.ok").unlink(missing_ok=True)
    (out_dir / "audit_fast.json").unlink(missing_ok=True)
    (out_dir / "audit_full.json").unlink(missing_ok=True)

    audit_run(load_config(out_dir), out_dir)

    assert (out_dir / "audit_fast.ok").exists()
    assert (out_dir / "audit_full.ok").exists()
    fast = json.loads((out_dir / "audit_fast.json").read_text(encoding="utf-8"))
    full = json.loads((out_dir / "audit_full.json").read_text(encoding="utf-8"))
    assert fast.get("ok") is True
    assert full.get("ok") is True
