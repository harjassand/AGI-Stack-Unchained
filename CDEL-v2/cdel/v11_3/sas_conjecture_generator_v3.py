"""Deterministic conjecture generator (v11.3)."""

from __future__ import annotations

from typing import Any, Dict, List

from .sas_conjecture_ir_v3 import DOMAIN, SCHEMA_VERSION, compute_fingerprint_hash, compute_metrics
from .sas_conjecture_seed_v3 import rng_u64_for_seed


def _seed_bytes_from(seed: str) -> bytes:
    text = str(seed)
    if text.startswith("sha256:"):
        hex_part = text.split(":", 1)[1]
        if len(hex_part) == 64:
            try:
                return bytes.fromhex(hex_part)
            except ValueError:
                return text.encode("utf-8")
    return text.encode("utf-8")


class DeterministicRNG:
    def __init__(self, seed: str) -> None:
        self._seed_bytes = _seed_bytes_from(seed)
        self._counter = 0

    def _u64(self, label: str) -> int:
        val = rng_u64_for_seed(self._seed_bytes, label, self._counter)
        self._counter += 1
        return val

    def choice(self, items: List[Any], label: str) -> Any:
        if not items:
            raise ValueError("empty choice list")
        idx = self._u64(label) % len(items)
        return items[int(idx)]

    def shuffle(self, items: List[Any], label: str) -> List[Any]:
        out = list(items)
        for i in range(len(out) - 1, 0, -1):
            j = int(self._u64(f"{label}_{i}") % (i + 1))
            out[i], out[j] = out[j], out[i]
        return out


# Node builders

def _var(name: str, typ: str) -> dict[str, Any]:
    return {"op": "Var", "type": typ, "args": [], "name": name}


def _nat_lit(value: int) -> dict[str, Any]:
    return {"op": "NatLit", "type": "Nat", "args": [], "lit": int(value)}


def _add(lhs: dict[str, Any], rhs: dict[str, Any]) -> dict[str, Any]:
    return {"op": "Add", "type": "Nat", "args": [lhs, rhs]}


def _mul(lhs: dict[str, Any], rhs: dict[str, Any]) -> dict[str, Any]:
    return {"op": "Mul", "type": "Nat", "args": [lhs, rhs]}


def _succ(arg: dict[str, Any]) -> dict[str, Any]:
    return {"op": "Succ", "type": "Nat", "args": [arg]}


def _len(xs: dict[str, Any]) -> dict[str, Any]:
    return {"op": "Len", "type": "Nat", "args": [xs]}


def _sum(xs: dict[str, Any]) -> dict[str, Any]:
    return {"op": "Sum", "type": "Nat", "args": [xs]}


def _nil() -> dict[str, Any]:
    return {"op": "Nil", "type": "LNat", "args": []}


def _cons(head: dict[str, Any], tail: dict[str, Any]) -> dict[str, Any]:
    return {"op": "Cons", "type": "LNat", "args": [head, tail]}


def _append(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    return {"op": "Append", "type": "LNat", "args": [a, b]}


def _rev(xs: dict[str, Any]) -> dict[str, Any]:
    return {"op": "Rev", "type": "LNat", "args": [xs]}


def _map(fn_term: dict[str, Any], xs: dict[str, Any]) -> dict[str, Any]:
    return {"op": "Map", "type": "LNat", "args": [fn_term, xs]}


def _range(n: dict[str, Any]) -> dict[str, Any]:
    return {"op": "Range", "type": "LNat", "args": [n]}


def _insert(a: dict[str, Any], xs: dict[str, Any]) -> dict[str, Any]:
    return {"op": "Insert", "type": "LNat", "args": [a, xs]}


def _sort(xs: dict[str, Any]) -> dict[str, Any]:
    return {"op": "Sort", "type": "LNat", "args": [xs]}


def _fn_id() -> dict[str, Any]:
    return {"op": "FnId", "type": "NatFn", "args": []}


def _fn_add_const(c: int) -> dict[str, Any]:
    return {"op": "FnAddConst", "type": "NatFn", "args": [], "c": int(c)}


def _eq_nat(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    return {"op": "EqNat", "args": [a, b]}


def _eq_lnat(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    return {"op": "EqLNat", "args": [a, b]}


def _le_nat(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    return {"op": "LeNat", "args": [a, b]}


def _sorted(xs: dict[str, Any]) -> dict[str, Any]:
    return {"op": "Sorted", "args": [xs]}


# Template builders

def _template_len_append() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    xs = _var("xs", "LNat")
    ys = _var("ys", "LNat")
    lhs = _len(_append(xs, ys))
    rhs = _add(_len(xs), _len(ys))
    return [{"name": "xs", "type": "LNat"}, {"name": "ys", "type": "LNat"}], _eq_nat(lhs, rhs)


def _template_sum_append() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    xs = _var("xs", "LNat")
    ys = _var("ys", "LNat")
    lhs = _sum(_append(xs, ys))
    rhs = _add(_sum(xs), _sum(ys))
    return [{"name": "xs", "type": "LNat"}, {"name": "ys", "type": "LNat"}], _eq_nat(lhs, rhs)


def _template_rev_rev() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    xs = _var("xs", "LNat")
    lhs = _rev(_rev(xs))
    return [{"name": "xs", "type": "LNat"}], _eq_lnat(lhs, xs)


def _template_len_rev() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    xs = _var("xs", "LNat")
    lhs = _len(_rev(xs))
    rhs = _len(xs)
    return [{"name": "xs", "type": "LNat"}], _eq_nat(lhs, rhs)


def _template_len_append_range(k: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    xs = _var("xs", "LNat")
    lhs = _len(_append(xs, _range(_nat_lit(k))))
    rhs = _add(_len(xs), _nat_lit(k))
    return [{"name": "xs", "type": "LNat"}], _eq_nat(lhs, rhs)


def _template_len_insert(k: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    xs = _var("xs", "LNat")
    lhs = _len(_insert(_nat_lit(k), xs))
    rhs = _succ(_len(xs))
    return [{"name": "xs", "type": "LNat"}], _eq_nat(lhs, rhs)


def _template_len_map_const(k: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    xs = _var("xs", "LNat")
    lhs = _len(_map(_fn_add_const(k), xs))
    rhs = _len(xs)
    return [{"name": "xs", "type": "LNat"}], _eq_nat(lhs, rhs)


def _template_len_append_nil() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    xs = _var("xs", "LNat")
    lhs = _len(_append(xs, _nil()))
    rhs = _len(xs)
    return [{"name": "xs", "type": "LNat"}], _eq_nat(lhs, rhs)


def _build_template_pool(nat_lits: list[int]) -> list[tuple[list[dict[str, Any]], dict[str, Any]]]:
    pool: list[tuple[list[dict[str, Any]], dict[str, Any]]] = [
        _template_len_append(),
        _template_sum_append(),
        _template_rev_rev(),
        _template_len_rev(),
        _template_len_append_nil(),
    ]
    for k in nat_lits:
        pool.append(_template_len_append_range(k))
        pool.append(_template_len_insert(k))
        pool.append(_template_len_map_const(k))
    return pool


def _within_bounds(metrics: dict[str, Any], bounds: dict[str, Any]) -> bool:
    if int(metrics.get("depth", 0)) > int(bounds.get("max_depth", 5)):
        return False
    if int(metrics.get("node_count", 0)) > int(bounds.get("max_node_count", 24)):
        return False
    if int(metrics.get("binder_count", 0)) > int(bounds.get("max_binders_total", 4)):
        return False
    op_counts = metrics.get("op_counts") or {}
    if int(op_counts.get("Cons", 0)) > int(bounds.get("max_cons_nodes", 3)):
        return False
    if int(op_counts.get("Append", 0)) > int(bounds.get("max_append_nodes", 2)):
        return False
    if int(op_counts.get("Map", 0)) > int(bounds.get("max_map_nodes", 1)):
        return False
    if int(op_counts.get("Rev", 0)) > int(bounds.get("max_rev_nodes", 1)):
        return False
    if int(op_counts.get("Range", 0)) > int(bounds.get("max_range_nodes", 1)):
        return False
    if int(op_counts.get("Sort", 0)) > int(bounds.get("max_sort_nodes", 1)):
        return False
    if int(op_counts.get("Insert", 0)) > int(bounds.get("max_insert_nodes", 1)):
        return False
    if int(op_counts.get("Sorted", 0)) > int(bounds.get("max_sorted_nodes", 1)):
        return False
    return True


def generate_conjectures(*, seed_hash: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    rng = DeterministicRNG(seed_hash)
    bounds = dict(config.get("bounds") or {})
    max_conjectures = int(bounds.get("max_conjectures_per_tick", 1))
    nat_lits = list(bounds.get("nat_lits_allowed") or [0, 1, 2, 3])

    pool = _build_template_pool(nat_lits)
    shuffled = rng.shuffle(pool, label="templates")

    conjectures: list[dict[str, Any]] = []
    for tmpl in shuffled[:max_conjectures]:
        vars_list, goal = tmpl
        ir = {
            "schema_version": SCHEMA_VERSION,
            "domain": DOMAIN,
            "vars": vars_list,
            "goal": goal,
            "conjecture_id": "",
            "fingerprint_hash": "",
            "metrics": {},
        }
        metrics = compute_metrics(ir)
        if not _within_bounds(metrics, bounds):
            continue
        ir["metrics"] = metrics
        fp = compute_fingerprint_hash(ir)
        ir["fingerprint_hash"] = fp
        ir["conjecture_id"] = fp
        conjectures.append(ir)

    return conjectures


__all__ = ["generate_conjectures"]
