"""Shared types for the orchestrator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SymbolInfo:
    name: str
    type_norm: str
    module_hash: str


@dataclass(frozen=True)
class SignatureInfo:
    symbol: str
    type_norm: str


@dataclass(frozen=True)
class AdoptionInfo:
    adoption_hash: str
    concept: str
    chosen_symbol: str
    baseline_symbol: str | None
    accepted_at: int


@dataclass(frozen=True)
class Candidate:
    name: str
    payload: dict[str, Any]
    proposer: str
    notes: str | None = None
    meta: dict[str, Any] | None = None


@dataclass(frozen=True)
class ContextBundle:
    concept: str
    baseline_symbol: str
    oracle_symbol: str
    type_norm: str
    symbols: list[str]


@dataclass(frozen=True)
class DevEvalResult:
    n: int
    diff_sum: int
    baseline_successes: int
    candidate_successes: int
    passes_min_dev_diff_sum: bool


@dataclass(frozen=True)
class PromotionResult:
    accepted: bool
    reason: str
    module_hash: str | None = None
    adoption_hash: str | None = None
    dev_eval: DevEvalResult | None = None
    counterexamples: list[dict] | None = None
