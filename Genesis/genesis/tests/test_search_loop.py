from __future__ import annotations

from pathlib import Path

from genesis.core.search_loop import run_search
from genesis.shadow_cdel.calibration import ShadowCalibrator


ROOT = Path(__file__).resolve().parents[2]


def test_repair_loop_produces_pass(monkeypatch, tmp_path):
    config = {
        "seed": 0,
        "iterations": 1,
        "repair_attempts": 2,
        "force_first_operator": "swap",
        "archive_path": str(tmp_path / "archive.jsonl"),
        "seed_capsule": str(ROOT / "genesis" / "capsules" / "seed_capsule.json"),
        "epoch_id": "epoch-1",
        "dataset_config": str(ROOT / "genesis" / "configs" / "datasets.json"),
        "dataset_id": "shadow_eval",
        "forager_max_tests": 0,
    }
    calibrator = ShadowCalibrator(path=None, base_margin=0.0, step=0.01, max_margin=0.2)

    results = run_search(config, calibrator=calibrator)
    events = results["events"]
    repaired_pass = [
        event for event in events if event.operator == "x-revert_last_mutation" and event.shadow.decision == "PASS"
    ]
    assert repaired_pass, "expected a repaired PASS after swap failure"
