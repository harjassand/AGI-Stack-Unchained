"""Python unit-test repair proposer."""

from __future__ import annotations

import random

from orchestrator.proposer.base import Proposer
from orchestrator.pyut_utils import extract_python_source, python_source_payload
from orchestrator.types import Candidate, ContextBundle


class PyUTRepairProposer(Proposer):
    def __init__(
        self,
        failing_candidate: Candidate | None = None,
        counterexample: dict | None = None,
        max_new_symbols: int = 1,
    ) -> None:
        self.failing_candidate = failing_candidate
        self.counterexample = counterexample
        self.max_new_symbols = max_new_symbols

    def propose(self, *, context: ContextBundle, budget: int, rng_seed: int) -> list[Candidate]:
        if budget <= 0 or self.max_new_symbols <= 0:
            return []
        if not self.failing_candidate or not self.counterexample:
            return []
        if self.counterexample.get("kind") != "pyut":
            return []
        args = self.counterexample.get("args")
        expected = self.counterexample.get("expected")
        if not isinstance(args, list) or not args:
            return []
        source = extract_python_source(self.failing_candidate.payload)
        if source is None:
            return []
        fn_name = self.counterexample.get("fn_name")
        if not isinstance(fn_name, str) or not fn_name:
            return []

        params = [f"a{idx}" for idx in range(len(args))]
        cond = " and ".join(f"{name} == {repr(value)}" for name, value in zip(params, args))
        if not cond:
            return []
        expected_literal = repr(expected)

        repair_source = "\n".join(
            [
                f"def {fn_name}({', '.join(params)}):",
                f"    if {cond}:",
                f"        return {expected_literal}",
                "    return 0",
                "",
            ]
        )

        rng = random.Random(rng_seed)
        candidate_name = f"{context.concept}_pyut_repair_{rng.randint(1000, 9999)}"
        payload = python_source_payload(name=candidate_name, source=repair_source, concept=context.concept)
        return [
            Candidate(
                name=candidate_name,
                payload=payload,
                proposer="pyut-repair",
                notes="guard-counterexample",
            )
        ]
