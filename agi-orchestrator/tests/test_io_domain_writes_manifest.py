import json
from pathlib import Path

from orchestrator.cdel_client import CDELClient
from orchestrator.domains.io_algorithms_v1 import load_domain
from orchestrator.run import run_orchestrator


def _write_sealed_config(path: Path, suite_hash: str) -> None:
    content = (
        "[sealed]\n"
        "eval_harness_id = \"io-harness-v1\"\n"
        "eval_harness_hash = \"io-harness-v1-hash\"\n"
        f"eval_suite_hash = \"{suite_hash}\"\n"
        "alpha_total = \"1e-4\"\n"
        "episodes = 8\n\n"
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
    }
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def test_io_domain_writes_manifest(tmp_path: Path) -> None:
    cdel_root = tmp_path / "cdel_root"
    configs = cdel_root / "configs"
    configs.mkdir(parents=True)
    dev_config = configs / "sealed_io_dev.toml"
    heldout_config = configs / "sealed_io_heldout.toml"
    _write_sealed_config(dev_config, "dev-suite-io")
    _write_sealed_config(heldout_config, "heldout-suite-io")

    domain = load_domain(cdel_root)

    client = CDELClient()
    root = tmp_path / "workspace"
    client.init_workspace(root)
    base_module = root / "module_base.json"
    _write_base_module(base_module)
    client.commit_module(root, base_module, root / "config.toml")

    runs_dir = tmp_path / "runs"
    run_dir = run_orchestrator(
        root_dir=root,
        concept=domain.concept,
        oracle_symbol=domain.oracle_symbol,
        dev_config=domain.dev_config,
        heldout_config=domain.heldout_config,
        heldout_suites_dir=None,
        safety_config=None,
        safety_suites_dir=None,
        constraint_spec_path=None,
        seed_key="sealed-seed",
        min_dev_diff_sum=1,
        max_attempts=0,
        max_context_symbols=5,
        run_id="test-io-domain-manifest",
        runs_dir=runs_dir,
        baseline_symbol=domain.baseline_symbol,
        rng_seed=0,
    )

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["dev_harness_hash"] == "io-harness-v1-hash"
    assert manifest["heldout_harness_hash"] == "io-harness-v1-hash"
    assert manifest["dev_suite_hash"] == "dev-suite-io"
    assert manifest["heldout_suite_hash"] == "heldout-suite-io"
