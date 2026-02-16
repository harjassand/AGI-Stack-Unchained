import json
from pathlib import Path

from cdel.bench.run import run_tasks
from cdel.ledger.storage import read_head

from tests.conftest import init_repo


def _run_once(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    cfg = init_repo(tmp_path, budget=1000000)
    report_path = tmp_path / "report.json"
    report = run_tasks(cfg, Path("tasks/stream_min.jsonl"), generator="enum", report_path=str(report_path))
    order_log = (tmp_path / "ledger" / "order.log").read_text(encoding="utf-8")
    head = read_head(cfg)
    report_data = json.loads(report_path.read_text(encoding="utf-8"))
    return head, order_log, report_data


def test_determinism_end_to_end(tmp_path):
    head_a, order_a, report_a = _run_once(tmp_path / "run_a")
    head_b, order_b, report_b = _run_once(tmp_path / "run_b")

    assert head_a == head_b
    assert order_a == order_b
    assert report_a == report_b
