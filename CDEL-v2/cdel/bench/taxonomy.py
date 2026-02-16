"""Concept taxonomy for evidence suite and resolver UX."""

from __future__ import annotations

FAMILY_SPECS: dict[str, dict[str, object]] = {
    "arith": {"prefix": "arith.add_k", "count": 10},
    "predicates": {"prefix": "pred.lt_k", "count": 10},
    "lists": {"prefix": "lists.len_plus_k", "count": 10},
    "folds": {"prefix": "folds.sum_plus_k", "count": 10},
    "higher": {"prefix": "higher.apply_add_k", "count": 10},
    "reuse": {"prefix": "reuse.compose_add_k", "count": 10},
}


def families() -> list[str]:
    return sorted(FAMILY_SPECS.keys())


def concepts_for_family(family: str) -> list[str]:
    spec = FAMILY_SPECS.get(family)
    if not spec:
        return []
    prefix = spec["prefix"]
    count = int(spec["count"])
    return [f"{prefix}.{idx}" for idx in range(count)]


def all_concepts() -> list[str]:
    out: list[str] = []
    for family in families():
        out.extend(concepts_for_family(family))
    return out


def concept_family_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for family in families():
        for concept in concepts_for_family(family):
            mapping[concept] = family
    return mapping
