import csv
import json
from pathlib import Path

from cdel.bench.experiment import run_experiment
from cdel.config import load_config


def _load_module() -> dict:
    module = json.loads(Path("tests/fixtures/module1.json").read_text(encoding="utf-8"))
    module["parent"] = "GENESIS"
    return module


def _run_single(tmp_path: Path, module: dict, budget: int | None = None) -> Path:
    tasks_path = tmp_path / "tasks.jsonl"
    task = {"task_id": "T0001", "module": module}
    tasks_path.write_text(json.dumps(task) + "\n", encoding="utf-8")
    out_dir = tmp_path / "out"
    cfg = load_config(tmp_path)
    run_experiment(cfg, tasks_path, "enum", out_dir, budget_override=budget)
    return out_dir


def _load_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _ndjson_count(path: Path) -> int:
    return len([line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()])


def test_metrics_written_on_accept(tmp_path):
    out_dir = _run_single(tmp_path, _load_module())
    rows = _load_rows(out_dir / "metrics.csv")
    assert len(rows) >= 1
    assert str(rows[0].get("accepted")).lower() in {"true", "1", "yes"}
    assert _ndjson_count(out_dir / "report.ndjson") >= 1


def test_metrics_written_on_reject_non_capacity(tmp_path):
    module = _load_module()
    module["payload"]["definitions"][0]["body"] = {"tag": "sym", "name": "nope"}
    out_dir = _run_single(tmp_path, module)
    rows = _load_rows(out_dir / "metrics.csv")
    assert len(rows) >= 1
    assert str(rows[0].get("accepted")).lower() in {"false", "0", "no"}
    assert rows[0].get("rejection_code") not in {None, "", "CAPACITY_EXCEEDED"}
    assert _ndjson_count(out_dir / "report.ndjson") >= 1


def test_metrics_written_on_capacity_reject(tmp_path):
    module = _load_module()
    out_dir = _run_single(tmp_path, module, budget=0)
    rows = _load_rows(out_dir / "metrics.csv")
    assert len(rows) >= 1
    assert rows[0].get("rejection_code") == "CAPACITY_EXCEEDED"
    assert _ndjson_count(out_dir / "report.ndjson") >= 1
