import json
from pathlib import Path

from orchestrator.cdel_client import CDELClient
from orchestrator.counterexamples import capture_counterexamples
from orchestrator.proposer.repair import RepairProposer
from orchestrator.types import Candidate, ContextBundle


def _write_sealed_config(path: Path) -> None:
    content = (
        "[sealed]\n"
        "eval_harness_id = \"io-harness-v1\"\n"
        "eval_harness_hash = \"io-harness-v1-hash\"\n"
        "eval_suite_hash = \"dev-suite\"\n"
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
            "new_symbols": ["baseline_true", "is_even_oracle"],
            "definitions": [
                {
                    "name": "baseline_true",
                    "params": [{"name": "n", "type": {"tag": "int"}}],
                    "ret_type": {"tag": "bool"},
                    "body": {"tag": "bool", "value": True},
                    "termination": {"kind": "structural", "decreases_param": None},
                },
                {
                    "name": "is_even_oracle",
                    "params": [{"name": "n", "type": {"tag": "int"}}],
                    "ret_type": {"tag": "bool"},
                    "body": {"tag": "bool", "value": True},
                    "termination": {"kind": "structural", "decreases_param": None},
                },
            ],
            "declared_deps": [],
            "specs": [],
            "concepts": [],
        },
    }
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def test_counterexample_capture_io(tmp_path: Path) -> None:
    client = CDELClient()
    root = tmp_path / "workspace"
    client.init_workspace(root)

    base_module = root / "module_base.json"
    _write_base_module(base_module)
    client.commit_module(root, base_module, root / "config.toml")

    dev_config = tmp_path / "dev.toml"
    _write_sealed_config(dev_config)

    candidate_payload = {
        "new_symbols": ["cand"],
        "definitions": [
            {
                "name": "cand",
                "params": [{"name": "n", "type": {"tag": "int"}}],
                "ret_type": {"tag": "bool"},
                "body": {"tag": "bool", "value": False},
                "termination": {"kind": "structural", "decreases_param": None},
            }
        ],
        "declared_deps": [],
        "specs": [],
        "concepts": [{"concept": "algo.is_even", "symbol": "cand"}],
    }
    candidate = Candidate(name="cand", payload=candidate_payload, proposer="test")

    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    row = {
        "episode": 0,
        "args": [{"tag": "int", "value": 2}],
        "target": {"tag": "bool", "value": True},
        "baseline_success": True,
        "candidate_success": False,
        "diff": -1,
    }
    (artifact_dir / "rows.jsonl").write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")

    counter = capture_counterexamples(
        root_dir=root,
        config_path=dev_config,
        baseline="baseline_true",
        candidate="cand",
        oracle="is_even_oracle",
        candidate_payload=candidate_payload,
        artifact_dir=artifact_dir,
        max_examples=2,
    )

    assert counter.examples
    example = counter.examples[0]
    assert example["baseline_output"] == {"tag": "bool", "value": True}
    assert example["candidate_output"] == {"tag": "bool", "value": False}

    repair = RepairProposer(failing_candidate=candidate, counterexample=example)
    context = ContextBundle(
        concept="algo.is_even",
        baseline_symbol="baseline_true",
        oracle_symbol="is_even_oracle",
        type_norm="Int->Bool",
        symbols=[],
    )
    repairs = repair.propose(context=context, budget=1, rng_seed=0)
    assert repairs
