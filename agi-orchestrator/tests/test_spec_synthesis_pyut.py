from __future__ import annotations

from orchestrator.spec_synthesis import synthesize_specs


def test_spec_synthesis_pyut_tests() -> None:
    counterexamples = [
        {"kind": "pyut", "args": [1], "expected": 2},
        {"kind": "pyut", "args": [1], "expected": 2},
    ]
    specs = synthesize_specs(counterexamples, max_items=5)
    assert specs["pyut_tests"] == [{"args": [1], "expected": 2}]
