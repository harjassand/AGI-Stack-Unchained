import json
from pathlib import Path

from analysis.check_claims import _claim_cache


def _write_run(root: Path, run_id: str, rows: list[dict]) -> None:
    run_dir = root / run_id
    (run_dir / "ledger").mkdir(parents=True, exist_ok=True)
    (run_dir / "ledger" / "order.log").write_text("hash\n", encoding="utf-8")
    (run_dir / "DONE").write_text("hash\n", encoding="utf-8")
    report = {"run_id": run_id, "results": rows, "status": "complete"}
    (run_dir / "report.json").write_text(json.dumps(report, sort_keys=True), encoding="utf-8")


def test_claims_normalization_does_not_mask_semantic_diff(tmp_path):
    base_rows = [
        {"task_id": "T1", "accepted": True, "rejection": None},
        {"task_id": "T1", "accepted": False, "rejection": "FRESHNESS_VIOLATION"},
    ]
    cache_rows = [
        {"task_id": "T1", "accepted": True, "rejection": None},
    ]
    _write_run(tmp_path, "base", base_rows)
    _write_run(tmp_path, "cache", cache_rows)
    cfg = {"baseline_run": "base", "cache_run": "cache", "required": True}
    policy = {"policy": "all_must_pass", "allow_failures": 0}
    result = _claim_cache(cfg, tmp_path, policy)
    assert result["pass"] is False
    assert "T1" in result["details"]["corrupt_tasks"]["base"]
