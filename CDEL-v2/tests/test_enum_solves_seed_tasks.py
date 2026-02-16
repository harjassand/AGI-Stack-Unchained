from pathlib import Path

from cdel.bench.run import run_tasks

from tests.conftest import init_repo


def test_enum_solves_seed_tasks(tmp_path):
    cfg = init_repo(tmp_path, budget=1000000)
    report_path = tmp_path / "report.json"
    report = run_tasks(cfg, Path("tasks/stream_min.jsonl"), generator="enum", report_path=str(report_path))
    for entry in report["results"]:
        assert entry["accepted"], f"task {entry['task_id']} rejected: {entry['rejection']}"
