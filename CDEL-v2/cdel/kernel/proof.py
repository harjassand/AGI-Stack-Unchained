"""Minimal proof checker for equality goals."""

from __future__ import annotations

from dataclasses import dataclass

from cdel.kernel.cost import count_term_nodes
from cdel.kernel.eval import Evaluator
from cdel.kernel.parse import parse_term


class ProofError(Exception):
    pass


@dataclass(frozen=True)
class EqGoal:
    lhs: object
    rhs: object


def check_proof_spec(spec: dict, defs: dict[str, object], step_limit: int) -> int:
    goal = spec.get("goal")
    proof = spec.get("proof")
    if not isinstance(goal, dict):
        raise ProofError("goal must be an object")
    if goal.get("tag") != "eq":
        raise ProofError("only eq goals are supported")
    lhs = parse_term(goal.get("lhs"), [])
    rhs = parse_term(goal.get("rhs"), [])
    if not isinstance(proof, dict):
        raise ProofError("proof must be an object")

    tag = proof.get("tag")
    if tag == "missing":
        raise ProofError("PROOF_MISSING")
    if tag == "by_eval":
        evaluator = Evaluator(step_limit)
        lhs_val = evaluator.eval_term(lhs, [], defs)
        rhs_val = evaluator.eval_term(rhs, [], defs)
        if lhs_val != rhs_val:
            raise ProofError("by_eval failed")
        return proof_size(proof) + count_term_nodes(lhs) + count_term_nodes(rhs)

    proved = _prove(proof)
    if proved.lhs != lhs or proved.rhs != rhs:
        raise ProofError("proof does not match goal")
    return proof_size(proof)


def _prove(node: dict) -> EqGoal:
    tag = node.get("tag")
    if tag == "refl":
        term = parse_term(node.get("term"), [])
        return EqGoal(lhs=term, rhs=term)
    if tag == "sym":
        inner = _prove(node.get("proof"))
        return EqGoal(lhs=inner.rhs, rhs=inner.lhs)
    if tag == "trans":
        left = _prove(node.get("left"))
        right = _prove(node.get("right"))
        if left.rhs != right.lhs:
            raise ProofError("trans chain mismatch")
        return EqGoal(lhs=left.lhs, rhs=right.rhs)
    raise ProofError(f"unsupported proof tag: {tag}")


def proof_size(node: dict) -> int:
    if not isinstance(node, dict):
        return 0
    tag = node.get("tag")
    if tag == "missing":
        return 0
    if tag == "refl":
        return 1 + count_term_nodes(parse_term(node.get("term"), []))
    if tag == "by_eval":
        return 1
    if tag == "sym":
        return 1 + proof_size(node.get("proof"))
    if tag == "trans":
        return 1 + proof_size(node.get("left")) + proof_size(node.get("right"))
    return 1
