"""Deterministic conjecture generator (v11.1, Nat-only)."""

from __future__ import annotations

import random
from typing import Any, Iterable

from .sas_conjecture_ir_v1 import compute_conjecture_id, compute_metrics


def _var(name: str) -> dict[str, Any]:
    return {"op": "Var", "name": name}


def _lit(value: int) -> dict[str, Any]:
    return {"op": "NatLit", "value": int(value)}


def _add(lhs: dict[str, Any], rhs: dict[str, Any]) -> dict[str, Any]:
    return {"op": "Add", "args": [lhs, rhs]}


def _mul(lhs: dict[str, Any], rhs: dict[str, Any]) -> dict[str, Any]:
    return {"op": "Mul", "args": [lhs, rhs]}


def _succ(arg: dict[str, Any]) -> dict[str, Any]:
    return {"op": "Succ", "arg": arg}


def _eq(lhs: dict[str, Any], rhs: dict[str, Any]) -> dict[str, Any]:
    return {"op": "Eq", "lhs": lhs, "rhs": rhs}


def _template_irs() -> list[dict[str, Any]]:
    n = _var("n")
    m = _var("m")
    k = _var("k")
    templates = [
        # n + 0 = n
        {"vars": [{"name": "n", "type": "Nat"}], "goal": _eq(_add(n, _lit(0)), n)},
        # 0 + n = n
        {"vars": [{"name": "n", "type": "Nat"}], "goal": _eq(_add(_lit(0), n), n)},
        # n * 1 = n
        {"vars": [{"name": "n", "type": "Nat"}], "goal": _eq(_mul(n, _lit(1)), n)},
        # n + m = m + n
        {"vars": [{"name": "n", "type": "Nat"}, {"name": "m", "type": "Nat"}], "goal": _eq(_add(n, m), _add(m, n))},
        # (n + m) + k = n + (m + k)
        {
            "vars": [{"name": "n", "type": "Nat"}, {"name": "m", "type": "Nat"}, {"name": "k", "type": "Nat"}],
            "goal": _eq(_add(_add(n, m), k), _add(n, _add(m, k))),
        },
        # succ n = n + 1
        {"vars": [{"name": "n", "type": "Nat"}], "goal": _eq(_succ(n), _add(n, _lit(1)))},
    ]
    out: list[dict[str, Any]] = []
    for item in templates:
        ir = {
            "schema_version": "sas_conjecture_ir_v1",
            "conjecture_id": "",
            "domain": "NAT_ARITH",
            "vars": item["vars"],
            "goal": item["goal"],
        }
        ir["conjecture_id"] = compute_conjecture_id(ir)
        out.append(ir)
    return out


def _filter_by_limits(conjectures: Iterable[dict[str, Any]], *, max_depth: int | None, max_nodes: int | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for conj in conjectures:
        metrics = compute_metrics(conj)
        if max_depth is not None and metrics["depth"] > int(max_depth):
            continue
        if max_nodes is not None and metrics["node_count"] > int(max_nodes):
            continue
        out.append(conj)
    return out


def generate_conjectures(*, seed_hash: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    max_conjectures = int(config.get("max_conjectures", 4))
    max_depth = config.get("max_depth")
    max_nodes = config.get("max_node_count")

    candidates = _template_irs()
    filtered = _filter_by_limits(candidates, max_depth=max_depth, max_nodes=max_nodes)

    # Deterministic shuffle by seed_hash
    if seed_hash.startswith("sha256:"):
        seed_int = int(seed_hash.split(":", 1)[1], 16)
    else:
        seed_int = int.from_bytes(seed_hash.encode("utf-8"), "big")
    rng = random.Random(seed_int)
    rng.shuffle(filtered)

    return filtered[: max(1, max_conjectures)]


__all__ = ["generate_conjectures"]
