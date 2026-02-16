from __future__ import annotations

import json
import os
from pathlib import Path

from orchestrator.run import run_orchestrator


def test_replay_regression_io_domain(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "workspace"
    root.mkdir()

    dev_config = tmp_path / "dev_config.toml"
    heldout_config = tmp_path / "heldout_config.toml"
    suite_dir = root / "sealed_suites"
    suite_dir.mkdir(parents=True, exist_ok=True)
    suite_hash = "37f59d7530bba7c59d6291d2a770ebef6faf61f2eda9dd902fa3a640a7867c6f"
    suite_path = suite_dir / f"{suite_hash}.jsonl"
    suite_path.write_text(
        json.dumps(
            {
                "episode": 0,
                "args": [{"tag": "int", "value": 0}],
                "target": {"tag": "bool", "value": True},
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    dev_config.write_text(
        "\n".join(
            [
                "[sealed]",
                'eval_harness_id = "io-harness-v1"',
                'eval_harness_hash = "io-harness-v1-hash"',
                f'eval_suite_hash = "{suite_hash}"',
                "episodes = 1",
                "",
                "[sealed.alpha_schedule]",
                'name = "p_series"',
                "exponent = 2",
                'coefficient = "0.5"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    heldout_config.write_text(dev_config.read_text(encoding="utf-8"), encoding="utf-8")

    # Initialize workspace and seed baseline/oracle in the ledger.
    from orchestrator.cdel_client import CDELClient

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
                    "concepts": [],
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    client.commit_module(root, module_path, dev_config)

    replay_path = Path(__file__).parents[0] / "fixtures" / "llm_replays" / "io_algorithms_v1_replay.jsonl"
    cache_dir = tmp_path / "llm_cache"

    monkeypatch.setenv("ORCH_LLM_BACKEND", "replay")
    monkeypatch.setenv("ORCH_LLM_REPLAY_PATH", str(replay_path))
    monkeypatch.setenv("ORCH_LLM_CACHE_DIR", str(cache_dir))
    monkeypatch.setenv("ORCH_LLM_MAX_CALLS", "3")

    run_dir = run_orchestrator(
        root_dir=root,
        concept="algo.is_even",
        oracle_symbol="is_even_oracle",
        dev_config=dev_config,
        heldout_config=heldout_config,
        heldout_suites_dir=None,
        safety_config=None,
        safety_suites_dir=None,
        constraint_spec_path=None,
        seed_key="sealed-seed",
        min_dev_diff_sum=0,
        max_attempts=1,
        max_heldout_attempts=0,
        max_context_symbols=0,
        max_counterexamples=0,
        run_id="replay_test",
        runs_dir=tmp_path / "runs",
        baseline_symbol="is_even_base",
        rng_seed=0,
        proposer_names=["llm"],
        domain_candidates=None,
    )

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    llm = manifest["llm"]
    assert llm["backend"] == "replay"
    assert llm["calls_used"] >= 1
    assert any(call["cache_hit"] is False for call in llm["calls"])

    # Run again to force cache hit.
    run_orchestrator(
        root_dir=root,
        concept="algo.is_even",
        oracle_symbol="is_even_oracle",
        dev_config=dev_config,
        heldout_config=heldout_config,
        heldout_suites_dir=None,
        safety_config=None,
        safety_suites_dir=None,
        constraint_spec_path=None,
        seed_key="sealed-seed",
        min_dev_diff_sum=0,
        max_attempts=1,
        max_heldout_attempts=0,
        max_context_symbols=0,
        max_counterexamples=0,
        run_id="replay_test_2",
        runs_dir=tmp_path / "runs",
        baseline_symbol="is_even_base",
        rng_seed=0,
        proposer_names=["llm"],
        domain_candidates=None,
    )
    manifest2 = json.loads((tmp_path / "runs" / "replay_test_2" / "manifest.json").read_text(encoding="utf-8"))
    llm2 = manifest2["llm"]
    assert any(call["cache_hit"] is True for call in llm2["calls"])
    assert llm2["calls_used"] <= 3
