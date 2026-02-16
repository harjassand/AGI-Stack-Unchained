"""Trace-derived prior builder for SAS-Metasearch v16.0."""

from __future__ import annotations

from fractions import Fraction
from typing import Any

from ..v1_7r.canon import canon_bytes, sha256_prefixed
from .metasearch_policy_ir_v1 import THEORY_KINDS, NORM_POWERS

Q32_ONE = 1 << 32


def _q32_obj(value: int) -> dict[str, Any]:
    return {"schema_version": "q32_v1", "shift": 32, "q": str(int(value))}


def _stable_key(kind: str, p: int) -> tuple[str, int]:
    return (str(kind), int(p))


def _distribute_q32(counts: dict[tuple[str, int], int], alpha: int) -> dict[tuple[str, int], int]:
    total = sum(int(v) + int(alpha) for v in counts.values())
    floors: dict[tuple[str, int], int] = {}
    fracs: list[tuple[Fraction, tuple[str, int]]] = []
    used = 0
    for key in sorted(counts.keys()):
        num = (int(counts[key]) + int(alpha)) * Q32_ONE
        q = num // total
        floors[key] = q
        used += q
        fracs.append((Fraction(num, total) - q, key))
    remain = Q32_ONE - used
    fracs.sort(key=lambda item: (-item[0], item[1]))
    idx = 0
    while remain > 0:
        key = fracs[idx % len(fracs)][1]
        floors[key] += 1
        remain -= 1
        idx += 1
    return floors


def build_prior_from_corpus(corpus: dict[str, Any], *, alpha: int = 1) -> dict[str, Any]:
    counts: dict[tuple[str, int], int] = {}
    for kind in THEORY_KINDS:
        for p in NORM_POWERS:
            counts[_stable_key(kind, p)] = 0

    theory_index: dict[str, tuple[str, int]] = {}
    for row in corpus.get("theory_index", []):
        theory_index[str(row["theory_id"])] = (str(row["theory_kind"]), int(row["norm_pow_p"]))

    for case in corpus.get("cases", []):
        best_id = str(case.get("best_theory_id_dev"))
        key = theory_index.get(best_id)
        if key is None:
            continue
        if key in counts:
            counts[key] += 1

    q32_probs = _distribute_q32(counts, alpha)

    hypotheses: list[dict[str, Any]] = []
    for key in sorted(counts.keys()):
        kind, p = key
        hypotheses.append(
            {
                "theory_kind": kind,
                "norm_pow_p": int(p),
                "count_u64": int(counts[key]),
                "prob_q32": _q32_obj(int(q32_probs[key])),
            }
        )

    prior = {
        "schema_version": "metasearch_prior_v1",
        "prior_id": "",
        "alpha_u32": int(alpha),
        "hypotheses": hypotheses,
    }
    prior["prior_id"] = sha256_prefixed(canon_bytes({k: v for k, v in prior.items() if k != "prior_id"}))
    return prior


__all__ = ["build_prior_from_corpus"]
