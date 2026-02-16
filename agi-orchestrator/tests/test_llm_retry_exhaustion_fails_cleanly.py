from __future__ import annotations

from pathlib import Path

from orchestrator.proposer.llm import LLMProposer, ProposerLimits


class SequenceBackend:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls = 0

    def generate(self, prompt: str) -> str:
        _ = prompt
        idx = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        return self.responses[idx]


def _write_config(path: Path) -> None:
    path.write_text("\n", encoding="utf-8")


def test_llm_retry_exhaustion_fails_cleanly(tmp_path: Path) -> None:
    backend = SequenceBackend(["{", "{", "{"])
    root_dir = tmp_path / "workspace"
    root_dir.mkdir(parents=True, exist_ok=True)
    cfg = tmp_path / "config.toml"
    _write_config(cfg)
    proposer = LLMProposer(
        backend=backend,
        root_dir=root_dir,
        config_path=cfg,
        limits=ProposerLimits(max_new_symbols=1, max_ast_nodes=10),
    )
    candidates = proposer.propose(context=_fake_context(), budget=1, rng_seed=0)

    assert candidates == []


def _fake_context():
    from orchestrator.types import ContextBundle

    return ContextBundle(
        concept="algo.const",
        baseline_symbol="base",
        oracle_symbol="oracle",
        type_norm="Int -> Int",
        symbols=[],
    )
