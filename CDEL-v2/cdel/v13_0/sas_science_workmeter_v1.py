"""Workmeter for SAS-Science v13.0."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Workmeter:
    norm_calls: int = 0
    sqrt_calls: int = 0
    div_calls: int = 0
    mul_calls: int = 0
    add_calls: int = 0
    pair_terms_evaluated: int = 0

    def add_term(self, *, dim: int, norm_pow: int) -> None:
        d = int(dim)
        p = int(norm_pow)
        # displacement subtraction
        self.add_calls += d
        # norm computation (sum of squares)
        self.mul_calls += d
        if d > 0:
            self.add_calls += max(0, d - 1)
        self.sqrt_calls += 1
        self.norm_calls += 1
        # norm power (p>=1)
        if p > 1:
            self.mul_calls += (p - 1)
        # division for each dimension
        self.div_calls += d
        # multiply by coefficient and accumulate
        self.mul_calls += d
        self.add_calls += d
        self.pair_terms_evaluated += 1

    def add_hooke(self, *, dim: int) -> None:
        # Treat hooke as a normalized term to keep work budgets comparable.
        self.add_term(dim=int(dim), norm_pow=2)

    def snapshot(self) -> dict[str, int]:
        return {
            "norm_calls": int(self.norm_calls),
            "sqrt_calls": int(self.sqrt_calls),
            "div_calls": int(self.div_calls),
            "mul_calls": int(self.mul_calls),
            "add_calls": int(self.add_calls),
            "pair_terms_evaluated": int(self.pair_terms_evaluated),
        }


def work_cost(counts: dict[str, Any]) -> int:
    return (
        50 * int(counts.get("sqrt_calls", 0))
        + 20 * int(counts.get("div_calls", 0))
        + 3 * int(counts.get("mul_calls", 0))
        + 1 * int(counts.get("add_calls", 0))
        + 5 * int(counts.get("pair_terms_evaluated", 0))
    )


__all__ = ["Workmeter", "work_cost"]


def compute_workmeter_v1(job: dict[str, Any]) -> dict[str, Any]:
    """Deterministic reference workmeter for SAS-System v14.0."""
    dim = job["dim"]
    norm_pow = job["norm_pow"]
    pair_terms = job["pair_terms"]
    hooke_terms = job["hooke_terms"]

    sqrt_calls = 0
    div_calls = 0
    mul_calls = 0
    add_calls = 0
    pair_terms_evaluated = 0

    for _ in range(pair_terms * dim):
        add_calls += 1
    for _ in range(pair_terms * dim):
        mul_calls += 1
    if 0 < dim:
        for _ in range(pair_terms * (dim - 1)):
            add_calls += 1
    for _ in range(pair_terms):
        sqrt_calls += 1
    if 1 < norm_pow:
        for _ in range(pair_terms * (norm_pow - 1)):
            mul_calls += 1
    for _ in range(pair_terms * dim):
        div_calls += 1
    for _ in range(pair_terms * dim):
        mul_calls += 1
    for _ in range(pair_terms * dim):
        add_calls += 1
    for _ in range(pair_terms):
        pair_terms_evaluated += 1

    for _ in range(hooke_terms * dim):
        add_calls += 1
    for _ in range(hooke_terms * dim):
        mul_calls += 1
    if 0 < dim:
        for _ in range(hooke_terms * (dim - 1)):
            add_calls += 1
    for _ in range(hooke_terms):
        sqrt_calls += 1
    if 1 < 2:
        for _ in range(hooke_terms * (2 - 1)):
            mul_calls += 1
    for _ in range(hooke_terms * dim):
        div_calls += 1
    for _ in range(hooke_terms * dim):
        mul_calls += 1
    for _ in range(hooke_terms * dim):
        add_calls += 1
    for _ in range(hooke_terms):
        pair_terms_evaluated += 1

    work_cost_total = (
        50 * sqrt_calls
        + 20 * div_calls
        + 3 * mul_calls
        + 1 * add_calls
        + 5 * pair_terms_evaluated
    )
    return {
        "schema": "sas_science_workmeter_out_v1",
        "spec_version": "v14_0",
        "sqrt_calls": sqrt_calls,
        "div_calls": div_calls,
        "pair_terms_evaluated": pair_terms_evaluated,
        "work_cost_total": work_cost_total,
    }


__all__.append("compute_workmeter_v1")
