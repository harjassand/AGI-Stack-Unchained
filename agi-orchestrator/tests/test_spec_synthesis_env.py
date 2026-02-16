from __future__ import annotations

from orchestrator.spec_synthesis import synthesize_specs


def test_spec_synthesis_env_invariants() -> None:
    counterexamples = [
        {"kind": "env", "candidate_steps": 7, "illegal_move": True},
    ]
    specs = synthesize_specs(counterexamples, max_items=5)
    assert {"invariant": "max_steps", "value": 7} in specs["env_invariants"]
    assert {"invariant": "no_illegal_moves"} in specs["env_invariants"]
