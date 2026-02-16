import json
from pathlib import Path

from cdel.bench.run import run_tasks

from tests.conftest import init_repo


def _stream_with_missing_proof(path: Path) -> None:
    module = {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": None,
        "payload": {
            "new_symbols": ["const_two"],
            "definitions": [
                {
                    "name": "const_two",
                    "params": [],
                    "ret_type": {"tag": "int"},
                    "body": {"tag": "int", "value": 2},
                    "termination": {"kind": "structural", "decreases_param": None},
                }
            ],
            "declared_deps": [],
            "specs": [
                {
                    "kind": "proof_unbounded",
                    "goal": {
                        "tag": "eq",
                        "lhs": {"tag": "app", "fn": {"tag": "sym", "name": "const_two"}, "args": []},
                        "rhs": {"tag": "int", "value": 2},
                    },
                    "proof": {"tag": "missing"},
                }
            ],
        },
    }
    task = {"task_id": "P0001", "certificate_mode": "proof", "task_group": "proof_only_core", "module": module}
    path.write_text(json.dumps(task, sort_keys=True) + "\n", encoding="utf-8")


def test_proof_synth_disabled_rejects(tmp_path):
    cfg = init_repo(tmp_path, budget=1000000)
    stream_path = tmp_path / "proof_stream.jsonl"
    _stream_with_missing_proof(stream_path)
    report = run_tasks(cfg, stream_path, generator="enum", report_path=None, proof_synth=False)
    row = report["results"][0]
    assert not row["accepted"]
    assert row["rejection"] == "SPEC_FAIL"
    assert row["proof_synth_result"] == "disabled"


def test_proof_synth_enabled_accepts(tmp_path):
    cfg = init_repo(tmp_path, budget=1000000)
    stream_path = tmp_path / "proof_stream.jsonl"
    _stream_with_missing_proof(stream_path)
    report = run_tasks(cfg, stream_path, generator="enum", report_path=None, proof_synth=True)
    row = report["results"][0]
    assert row["accepted"]
    assert row["proof_synth_result"] == "success"
