from __future__ import annotations

import json
from pathlib import Path

from orchestrator.agent_controller import AgentTask, agent_solve
from orchestrator.cdel_client import CDELClient


def _seed_workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    client = CDELClient()
    client.init_workspace(root)

    module_path = tmp_path / "module_base.json"
    module_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "dsl_version": 1,
                "parent": "GENESIS",
                "payload": {
                    "new_symbols": ["abs_int_base"],
                    "definitions": [
                        {
                            "name": "abs_int_base",
                            "params": [{"name": "n", "type": {"tag": "int"}}],
                            "ret_type": {"tag": "int"},
                            "body": {"tag": "int", "value": 0},
                            "termination": {"kind": "structural", "decreases_param": None},
                        }
                    ],
                    "declared_deps": [],
                    "specs": [],
                    "concepts": [{"concept": "py.abs_int", "symbol": "abs_int_base"}],
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    client.commit_module(root, module_path, root / "config.toml")
    return root


def test_agent_solve_deterministic(tmp_path: Path) -> None:
    root = _seed_workspace(tmp_path)
    task = AgentTask(
        task_id="py_task_1",
        concept="py.abs_int",
        domain="pyut",
        inputs={"n": -3},
        allowed_tools=["json_parse"],
        max_steps=4,
    )
    run_dir1 = tmp_path / "run1"
    run_dir2 = tmp_path / "run2"
    result1 = agent_solve(root_dir=root, run_dir=run_dir1, task=task, rng_seed=0)
    result2 = agent_solve(root_dir=root, run_dir=run_dir2, task=task, rng_seed=0)
    assert result1.plan_id == result2.plan_id
    plan1 = json.loads(result1.plan_path.read_text(encoding="utf-8"))
    plan2 = json.loads(result2.plan_path.read_text(encoding="utf-8"))
    assert plan1 == plan2
