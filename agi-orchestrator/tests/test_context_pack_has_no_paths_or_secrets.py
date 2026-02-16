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
                    "new_symbols": ["is_even_base", "is_even_oracle"],
                    "definitions": [
                        {
                            "name": "is_even_base",
                            "params": [{"name": "n", "type": {"tag": "int"}}],
                            "ret_type": {"tag": "bool"},
                            "body": {"tag": "bool", "value": False},
                            "termination": {"kind": "structural", "decreases_param": None},
                        },
                        {
                            "name": "is_even_oracle",
                            "params": [{"name": "n", "type": {"tag": "int"}}],
                            "ret_type": {"tag": "bool"},
                            "body": {
                                "tag": "prim",
                                "op": "eq_int",
                                "args": [
                                    {
                                        "tag": "prim",
                                        "op": "mod",
                                        "args": [
                                            {"tag": "var", "name": "n"},
                                            {"tag": "int", "value": 2},
                                        ],
                                    },
                                    {"tag": "int", "value": 0},
                                ],
                            },
                            "termination": {"kind": "structural", "decreases_param": None},
                        },
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


def test_context_pack_has_no_paths_or_secrets(tmp_path: Path) -> None:
    root = _seed_workspace(tmp_path)
    limits = ContextPackLimits(max_new_symbols=1, max_ast_nodes=50, max_ast_depth=20)
    pack = build_context_pack_v1(
        root_dir=root,
        config_path=root / "config.toml",
        concept="algo.is_even",
        baseline_symbol="is_even_base",
        oracle_symbol="is_even_oracle",
        context_symbols=[],
        counterexamples=[],
        rng_seed=0,
        limits=limits,
    )
    rendered = json.dumps(pack, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    user_prefix = "".join(["/Us", "ers/"])
    forbidden = [user_prefix, "HOME", "CDEL_SEALED_PRIVKEY"]
    for needle in forbidden:
        assert needle not in rendered
