from pathlib import Path
import json

from cdel.bench.run import run_tasks
from tests.conftest import init_repo
from tasks.make_curriculum import generate_tasks


def test_curriculum_subset_acceptance(tmp_path):
    cfg = init_repo(tmp_path, budget=1000000)
    tasks = generate_tasks(30, seed=0)
    stream_path = tmp_path / "subset.jsonl"
    with stream_path.open("w", encoding="utf-8") as fh:
        for task in tasks:
            fh.write(json.dumps(task, sort_keys=True) + "\n")
    report = run_tasks(cfg, Path(stream_path), generator="enum", report_path=None)
    accepted = sum(1 for row in report["results"] if row.get("accepted"))
    assert accepted >= 25
