from __future__ import annotations

import json
from pathlib import Path

from orchestrator.cdel_client import CDELClient
from orchestrator.context_pack import ContextPackLimits, build_context_pack_v1


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
                    "new_symbols": ["abs_int_base", "abs_int_oracle"],
                    "definitions": [
                        {
                            "name": "abs_int_base",
                            "params": [{"name": "n", "type": {"tag": "int"}}],
                            "ret_type": {"tag": "int"},
                            "body": {"tag": "int", "value": 0},
                            "termination": {"kind": "structural", "decreases_param": None},
                        },
                        {
                            "name": "abs_int_oracle",
                            "params": [{"name": "n", "type": {"tag": "int"}}],
                            "ret_type": {"tag": "int"},
                            "body": {"tag": "int", "value": 1},
                            "termination": {"kind": "structural", "decreases_param": None},
                        },
                    ],
                    "declared_deps": [],
                    "specs": [],
                    "concepts": [],
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    client.commit_module(root, module_path, root / "config.toml")
    return root


def test_context_pack_includes_spec_hints(tmp_path: Path) -> None:
    root = _seed_workspace(tmp_path)
    pack = build_context_pack_v1(
        root_dir=root,
        config_path=root / "config.toml",
        concept="py.abs_int",
        baseline_symbol="abs_int_base",
        oracle_symbol="abs_int_oracle",
        context_symbols=[],
        counterexamples=[{"kind": "pyut", "args": [1], "expected": 1}],
        rng_seed=0,
        limits=ContextPackLimits(max_new_symbols=1, max_ast_nodes=50, max_ast_depth=20),
    )
    assert {"args": [1], "expected": 1} in pack["spec_hints"]["pyut_tests"]
