import json
from pathlib import Path

from orchestrator.cdel_client import CDELClient
from orchestrator.run import run_orchestrator


def _write_sealed_config(path: Path, suite_hash: str) -> None:
    content = (
        "[sealed]\n"
        "eval_harness_id = \"suite-harness-v1\"\n"
        "eval_harness_hash = \"suite-harness-hash\"\n"
        f"eval_suite_hash = \"{suite_hash}\"\n"
        "alpha_total = \"1e-4\"\n"
        "episodes = 2\n\n"
        "[sealed.alpha_schedule]\n"
        "name = \"p_series\"\n"
        "exponent = 2\n"
        "coefficient = \"0.5\"\n"
    )
    path.write_text(content, encoding="utf-8")


def _write_base_module(path: Path) -> None:
    payload = {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": "GENESIS",
        "payload": {
            "new_symbols": ["baseline_bad", "is_even_oracle"],
            "definitions": [
                {
                    "name": "baseline_bad",
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
            "concepts": [{"concept": "parity", "symbol": "baseline_bad"}],
        },
    }
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def test_run_manifest_written(tmp_path: Path) -> None:
    client = CDELClient()
    root = tmp_path / "workspace"
    client.init_workspace(root)

    base_module = root / "module_base.json"
    _write_base_module(base_module)
    client.commit_module(root, base_module, root / "config.toml")

    dev_config = tmp_path / "dev.toml"
    heldout_config = tmp_path / "heldout.toml"
    _write_sealed_config(dev_config, "dev-suite")
    _write_sealed_config(heldout_config, "heldout-suite")

    runs_dir = tmp_path / "runs"
    run_dir = run_orchestrator(
        root_dir=root,
        concept="parity",
        oracle_symbol="is_even_oracle",
        dev_config=dev_config,
        heldout_config=heldout_config,
        heldout_suites_dir=None,
        safety_config=None,
        safety_suites_dir=None,
        constraint_spec_path=None,
        seed_key="sealed-seed",
        min_dev_diff_sum=1,
        max_attempts=0,
        max_context_symbols=5,
        run_id="test-run",
        runs_dir=runs_dir,
        baseline_symbol=None,
        rng_seed=0,
    )

    manifest_path = run_dir / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    required = {
        "cdel_version",
        "cdel_commit",
        "dev_config",
        "heldout_config",
        "dev_suite_hash",
        "heldout_suite_hash",
        "dev_harness_hash",
        "heldout_harness_hash",
        "seed_keys",
        "alpha_schedule",
        "commands",
    }
    assert required.issubset(set(manifest))
