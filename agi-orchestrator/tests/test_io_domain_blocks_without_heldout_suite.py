import json
from pathlib import Path

from cdel.sealed.suites import compute_suite_hash_bytes

from orchestrator.cdel_client import CDELClient
from orchestrator.domains.io_algorithms_v1 import candidate_templates, load_domain
from orchestrator.run import run_orchestrator


def _write_sealed_config(path: Path, suite_hash: str) -> None:
    content = (
        "[sealed]\n"
        "eval_harness_id = \"io-harness-v1\"\n"
        "eval_harness_hash = \"io-harness-v1-hash\"\n"
        f"eval_suite_hash = \"{suite_hash}\"\n"
        "alpha_total = \"1e-4\"\n"
        "episodes = 1\n\n"
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


def test_io_domain_blocks_without_heldout_suite(tmp_path: Path) -> None:
    cdel_root = tmp_path / "cdel_root"
    configs = cdel_root / "configs"
    configs.mkdir(parents=True)
    dev_config = configs / "sealed_io_dev.toml"
    heldout_config = configs / "sealed_io_heldout.toml"

    domain = load_domain(cdel_root)
    domain_candidates = candidate_templates(concept=domain.concept, rng_seed=0)

    client = CDELClient()
    root = tmp_path / "workspace"
    client.init_workspace(root)
    base_module = root / "module_base.json"
    _write_base_module(base_module)
    client.commit_module(root, base_module, root / "config.toml")

    suite_row = {
        "episode": 0,
        "args": [{"tag": "int", "value": 0}],
        "target": {"tag": "bool", "value": True},
    }
    suite_bytes = (json.dumps(suite_row, sort_keys=True) + "\n").encode("utf-8")
    suite_hash = compute_suite_hash_bytes(suite_bytes)
    _write_sealed_config(dev_config, suite_hash)
    _write_sealed_config(heldout_config, "heldout-suite")

    suite_dir = root / "sealed_suites"
    suite_dir.mkdir()
    (suite_dir / f"{suite_hash}.jsonl").write_bytes(suite_bytes)

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
        max_attempts=1,
        max_context_symbols=5,
        run_id="test-io-domain-blocked",
        runs_dir=runs_dir,
        baseline_symbol=domain.baseline_symbol,
        rng_seed=0,
        domain_candidates=domain_candidates,
    )

    adoption_path = run_dir / "candidates" / "0" / "adoption.json"
    assert not adoption_path.exists()
