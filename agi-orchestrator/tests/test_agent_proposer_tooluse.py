from __future__ import annotations

import json
from pathlib import Path

from blake3 import blake3

from orchestrator.proposer.agent import AgentProposer
from orchestrator.types import ContextBundle


def test_agent_proposer_tooluse(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    suite_dir = root / "sealed_suites"
    suite_dir.mkdir(parents=True)

    row = {
        "episode": 0,
        "task_id": "copy_text_0",
        "allowed_tools": ["read_file", "write_file"],
        "initial_fs": [{"path": "input.txt", "contents": "alpha"}],
        "tool_calls": [
            {"tool": "read_file", "args": ["input.txt"]},
            {"tool": "write_file", "args": ["out.txt", "$LAST"]},
        ],
        "success": {"type": "file_equals", "path": "out.txt", "contents": "alpha"},
        "max_steps": 2,
    }
    content = json.dumps(row, sort_keys=True) + "\n"
    suite_hash = blake3(content.encode("utf-8")).hexdigest()
    suite_path = suite_dir / f"{suite_hash}.jsonl"
    suite_path.write_text(content, encoding="utf-8")

    config_path = root / "config.toml"
    config_path.write_text(
        "\n".join(
            [
                "[sealed]",
                'eval_harness_id = "tooluse-harness-v1"',
                'eval_harness_hash = "tooluse-harness-v1-hash"',
                f'eval_suite_hash = "{suite_hash}"',
                "episodes = 1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    proposer = AgentProposer(root_dir=root, config_path=config_path, run_dir=tmp_path / "run")
    bundle = ContextBundle(
        concept="tooluse.file_transform",
        baseline_symbol="tooluse_base",
        oracle_symbol="tooluse_oracle",
        type_norm="Int -> Int",
        symbols=[],
    )
    candidates = proposer.propose(context=bundle, budget=1, rng_seed=0)
    assert candidates
    definition = candidates[0].payload["definitions"][0]
    assert definition["ret_type"]["tag"] == "int"
