from orchestrator.proposer.pyut_repair import PyUTRepairProposer
from orchestrator.pyut_utils import extract_python_source, python_source_payload
from orchestrator.types import Candidate, ContextBundle


def test_pyut_repair_proposer_generates_candidate() -> None:
    source = "def abs_int(x: int) -> int:\n    return x\n"
    payload = python_source_payload(name="abs_int_code", source=source, concept="py.abs_int")
    candidate = Candidate(name="abs_int_code", payload=payload, proposer="test")
    counterexample = {"kind": "pyut", "fn_name": "abs_int", "args": [-3], "expected": 3}

    proposer = PyUTRepairProposer(failing_candidate=candidate, counterexample=counterexample)
    context = ContextBundle(
        concept="py.abs_int",
        baseline_symbol="abs_int_base",
        oracle_symbol="abs_int_oracle",
        type_norm="List[Int]",
        symbols=[],
    )
    results = proposer.propose(context=context, budget=1, rng_seed=0)
    assert results
    new_source = extract_python_source(results[0].payload)
    assert new_source is not None
    assert "def abs_int" in new_source
    assert "return 3" in new_source
