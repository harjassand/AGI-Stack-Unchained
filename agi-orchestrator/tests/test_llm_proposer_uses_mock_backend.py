import json
from pathlib import Path

from orchestrator.llm_backend import MockBackend
from orchestrator.proposer.llm import LLMProposer, ProposerLimits
from orchestrator.types import ContextBundle


def _write_config(path: Path) -> None:
    path.write_text("\n", encoding="utf-8")


def test_llm_proposer_uses_mock_backend(tmp_path: Path) -> None:
    payload = {
        "new_symbols": ["cand"],
        "definitions": [
            {
                "name": "cand",
                "params": [{"name": "n", "type": {"tag": "int"}}],
                "ret_type": {"tag": "bool"},
                "body": {"tag": "bool", "value": True},
                "termination": {"kind": "structural", "decreases_param": None},
            }
        ],
        "declared_deps": [],
        "specs": [],
        "concepts": [{"concept": "algo.is_even", "symbol": "cand"}],
    }
    backend = MockBackend(response=json.dumps(payload))
    root_dir = tmp_path / "workspace"
    root_dir.mkdir(parents=True, exist_ok=True)
    cfg = tmp_path / "config.toml"
    _write_config(cfg)
    proposer = LLMProposer(
        backend,
        root_dir=root_dir,
        config_path=cfg,
        limits=ProposerLimits(max_new_symbols=1, max_ast_nodes=5),
    )

    context = ContextBundle(
        concept="algo.is_even",
        baseline_symbol="is_even_base",
        oracle_symbol="is_even_oracle",
        type_norm="Int->Bool",
        symbols=["is_even_base", "is_even_oracle"],
    )

    candidates = proposer.propose(context=context, budget=1, rng_seed=0)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.name == "cand"
    assert candidate.payload["new_symbols"] == ["cand"]
