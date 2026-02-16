"""Deterministic proof synthesis for closed equality goals."""

from __future__ import annotations

from typing import Iterable

from cdel.kernel.eval import Evaluator
from cdel.kernel.parse import parse_term


def synthesize_missing_proofs(specs: Iterable[dict], defs: dict[str, object], step_limit: int) -> tuple[list[dict], int]:
    synthesized = 0
    out: list[dict] = []
    for spec in specs:
        if spec.get("kind") not in {"proof", "proof_unbounded"}:
            out.append(spec)
            continue
        proof = spec.get("proof") or {}
        if not isinstance(proof, dict) or proof.get("tag") not in {None, "missing"}:
            out.append(spec)
            continue
        goal = spec.get("goal") or {}
        if not isinstance(goal, dict) or goal.get("tag") != "eq":
            out.append(spec)
            continue
        try:
            lhs = parse_term(goal.get("lhs"), [])
            rhs = parse_term(goal.get("rhs"), [])
        except Exception:
            out.append(spec)
            continue
        try:
            evaluator = Evaluator(step_limit)
            lhs_val = evaluator.eval_term(lhs, [], defs)
            rhs_val = evaluator.eval_term(rhs, [], defs)
        except Exception:
            out.append(spec)
            continue
        if lhs_val != rhs_val:
            out.append(spec)
            continue
        updated = dict(spec)
        updated["proof"] = {"tag": "by_eval"}
        out.append(updated)
        synthesized += 1
    return out, synthesized
