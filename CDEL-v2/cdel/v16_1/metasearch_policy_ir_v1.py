"""Policy/config helpers for SAS-Metasearch v16.0."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, load_canon_json


class MetaSearchPolicyError(CanonError):
    pass


def _fail(reason: str) -> None:
    raise MetaSearchPolicyError(reason)


THEORY_KINDS = (
    "CANDIDATE_CENTRAL_POWERLAW_V1",
    "CANDIDATE_NBODY_POWERLAW_V1",
)

NORM_POWERS = (1, 2, 3, 4)


@dataclass(frozen=True)
class Hypothesis:
    theory_kind: str
    norm_pow_p: int


@dataclass(frozen=True)
class BaselineSearchConfig:
    seed_u64: int
    population: int
    generations: int
    max_dev_evals: int


@dataclass(frozen=True)
class CandidateSearchConfig:
    seed_u64: int
    max_dev_evals: int


def _load_obj(path: Path) -> dict[str, Any]:
    try:
        obj = load_canon_json(path)
    except CanonError:
        _fail("INVALID:SCHEMA_FAIL")
    if not isinstance(obj, dict):
        _fail("INVALID:SCHEMA_FAIL")
    return obj


def load_policy(path: Path) -> dict[str, Any]:
    obj = _load_obj(path)
    if obj.get("schema_version") != "sas_metasearch_policy_v1":
        _fail("INVALID:SCHEMA_FAIL")
    if sorted(obj.get("allowed_theory_kinds") or []) != sorted(THEORY_KINDS):
        _fail("INVALID:SCHEMA_FAIL")
    if sorted(obj.get("allowed_norm_pow_p") or []) != list(NORM_POWERS):
        _fail("INVALID:SCHEMA_FAIL")
    gate = obj.get("efficiency_gate")
    if not isinstance(gate, dict):
        _fail("INVALID:SCHEMA_FAIL")
    if int(gate.get("cand_mul", 0)) < 1 or int(gate.get("base_mul", 0)) < 1:
        _fail("INVALID:SCHEMA_FAIL")
    return obj


def load_baseline_search_config(path: Path) -> BaselineSearchConfig:
    obj = _load_obj(path)
    if obj.get("schema_version") != "baseline_search_config_v1":
        _fail("INVALID:SCHEMA_FAIL")
    if obj.get("algo_kind") != "GENETIC_ALGO_V1":
        _fail("INVALID:SCHEMA_FAIL")
    population = int(obj.get("population", 0))
    generations = int(obj.get("generations", 0))
    max_dev_evals = int(obj.get("max_dev_evals", 0))
    expected = population * generations
    if max_dev_evals != expected:
        _fail("INVALID:SCHEMA_FAIL")
    return BaselineSearchConfig(
        seed_u64=int(obj.get("seed_u64", 0)),
        population=population,
        generations=generations,
        max_dev_evals=max_dev_evals,
    )


def load_candidate_search_config(path: Path) -> CandidateSearchConfig:
    obj = _load_obj(path)
    if obj.get("schema_version") != "candidate_search_config_v1":
        _fail("INVALID:SCHEMA_FAIL")
    if obj.get("algo_kind") != "TRACE_PRIOR_V1":
        _fail("INVALID:SCHEMA_FAIL")
    max_dev_evals = int(obj.get("max_dev_evals", 0))
    if max_dev_evals < 1:
        _fail("INVALID:SCHEMA_FAIL")
    seed_u64 = int(obj.get("seed_u64", 0))
    if seed_u64 < 0:
        _fail("INVALID:SCHEMA_FAIL")
    return CandidateSearchConfig(seed_u64=seed_u64, max_dev_evals=max_dev_evals)


def enumerate_hypotheses() -> list[Hypothesis]:
    out: list[Hypothesis] = []
    for kind in THEORY_KINDS:
        for p in NORM_POWERS:
            out.append(Hypothesis(theory_kind=kind, norm_pow_p=int(p)))
    return out


__all__ = [
    "MetaSearchPolicyError",
    "Hypothesis",
    "BaselineSearchConfig",
    "CandidateSearchConfig",
    "THEORY_KINDS",
    "NORM_POWERS",
    "load_policy",
    "load_baseline_search_config",
    "load_candidate_search_config",
    "enumerate_hypotheses",
]
