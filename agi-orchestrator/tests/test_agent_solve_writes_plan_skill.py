from __future__ import annotations

import json
from pathlib import Path

from orchestrator.agent_controller import AgentTask, agent_solve
from orchestrator.cdel_client import CDELClient
from orchestrator.plan_skill import plan_skill_hash


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
                    "new_symbols": ["is_even_base"],
                    "definitions": [
                        {
                            "name": "is_even_base",
                            "params": [{"name": "n", "type": {"tag": "int"}}],
                            "ret_type": {"tag": "bool"},
                            "body": {"tag": "bool", "value": False},
                            "termination": {"kind": "structural", "decreases_param": None},
                        }
                    ],
                    "declared_deps": [],
                    "specs": [],
                    "concepts": [{"concept": "algo.is_even", "symbol": "is_even_base"}],
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    client.commit_module(root, module_path, root / "config.toml")
    return root


def test_agent_solve_writes_plan_skill(tmp_path: Path) -> None:
    root = _seed_workspace(tmp_path)
    run_dir = tmp_path / "run"
    task = AgentTask(
        task_id="io_task_1",
        concept="algo.is_even",
        domain="io",
        inputs={"n": 2},
        allowed_tools=["read_file"],
        max_steps=5,
    )
    result = agent_solve(root_dir=root, run_dir=run_dir, task=task, rng_seed=0)
    assert result.plan_path.exists()
    plan = json.loads(result.plan_path.read_text(encoding="utf-8"))
    assert plan["plan_id"] == result.plan_id
    assert plan["plan_id"] == plan_skill_hash(plan)
