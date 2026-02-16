"""Repair proposer with simple guard templates."""

from __future__ import annotations

import random

from orchestrator.proposer.base import Proposer
from orchestrator.types import Candidate, ContextBundle


class RepairProposer(Proposer):
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
        if not self.failing_candidate or not self.counterexample:
            return []
        if self.max_new_symbols <= 0:
            return []
        defns = self.failing_candidate.payload.get("definitions") or []
        if len(defns) != 1:
            return []
        args = self.counterexample.get("args") if isinstance(self.counterexample, dict) else None
        if not isinstance(args, list) or len(args) != 1:
            return []
        arg0 = args[0]
        if not isinstance(arg0, dict) or arg0.get("tag") != "int":
            return []
        value = arg0.get("value")
        if not isinstance(value, int):
            return []
        base_def = defns[0]
        params = base_def.get("params") or []
        if len(params) != 1:
            return []
        param_name = params[0].get("name")
        if not isinstance(param_name, str) or not param_name:
            return []

        target_term = _value_to_term(self.counterexample.get("target"))
        rng = random.Random(rng_seed)
        candidate_name = f"{context.concept}_repair_{rng.randint(1000, 9999)}"
        guard = {
            "tag": "prim",
            "op": "eq_int",
            "args": [
                {"tag": "var", "name": param_name},
                {"tag": "int", "value": value},
            ],
        }
        body = {
            "tag": "if",
            "cond": guard,
            "then": target_term
            if target_term is not None
            else {
                "tag": "app",
                "fn": {"tag": "sym", "name": context.oracle_symbol},
                "args": [{"tag": "var", "name": param_name}],
            },
            "else": {
                "tag": "app",
                "fn": {"tag": "sym", "name": context.baseline_symbol},
                "args": [{"tag": "var", "name": param_name}],
            },
        }
        payload = {
            "new_symbols": [candidate_name],
            "definitions": [
                {
                    "name": candidate_name,
                    "params": params,
                    "ret_type": base_def.get("ret_type"),
                    "body": body,
                    "termination": {"kind": "structural", "decreases_param": None},
                }
            ],
            "declared_deps": [context.oracle_symbol, context.baseline_symbol],
            "specs": [],
            "concepts": [{"concept": context.concept, "symbol": candidate_name}],
        }
        return [
            Candidate(
                name=candidate_name,
                payload=payload,
                proposer="repair",
                notes="guard-counterexample",
            )
        ]


def _value_to_term(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None
    tag = raw.get("tag")
    if tag == "int":
        value = raw.get("value")
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        return {"tag": "int", "value": value}
    if tag == "bool":
        value = raw.get("value")
        if not isinstance(value, bool):
            return None
        return {"tag": "bool", "value": value}
    return None
