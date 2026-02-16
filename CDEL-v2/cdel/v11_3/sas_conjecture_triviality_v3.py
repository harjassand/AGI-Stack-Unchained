"""Triviality filters for SAS conjectures (v11.3)."""

from __future__ import annotations

from typing import Any, Dict, Tuple


def _var_prefix(vtype: str, idx: int) -> str:
    if vtype == "Nat":
        return f"n{idx}"
    if vtype == "LNat":
        return f"xs{idx}"
    return f"f{idx}"


def _maybe_fold_nat(op: str, args: list[dict[str, Any]]) -> dict[str, Any] | None:
    if op == "Add" and len(args) == 2:
        if args[0].get("op") == "NatLit" and args[1].get("op") == "NatLit":
            return {
                "op": "NatLit",
                "type": "Nat",
                "args": [],
                "lit": int(args[0].get("lit", 0)) + int(args[1].get("lit", 0)),
            }
    if op == "Mul" and len(args) == 2:
        if args[0].get("op") == "NatLit" and args[1].get("op") == "NatLit":
            return {
                "op": "NatLit",
                "type": "Nat",
                "args": [],
                "lit": int(args[0].get("lit", 0)) * int(args[1].get("lit", 0)),
            }
    if op == "Succ" and len(args) == 1:
        if args[0].get("op") == "NatLit":
            return {
                "op": "NatLit",
                "type": "Nat",
                "args": [],
                "lit": int(args[0].get("lit", 0)) + 1,
            }
    return None


def _normalize_term(expr: dict[str, Any], var_map: dict[tuple[str, str], str], counters: dict[str, int]) -> dict[str, Any]:
    op = expr.get("op")
    typ = expr.get("type")
    if op == "Var":
        name = str(expr.get("name"))
        key = (typ, name)
        if key not in var_map:
            idx = counters.get(typ, 0)
            var_map[key] = _var_prefix(typ, idx)
            counters[typ] = idx + 1
        return {"op": "Var", "type": typ, "args": [], "name": var_map[key]}
    if op == "NatLit":
        return {"op": "NatLit", "type": "Nat", "args": [], "lit": int(expr.get("lit", 0))}
    if op in {"FnId", "FnAddConst", "FnMulConst"}:
        node = {"op": op, "type": "NatFn", "args": []}
        if op in {"FnAddConst", "FnMulConst"}:
            node["c"] = int(expr.get("c", 0))
        return node
    args = [
        _normalize_term(arg, var_map, counters)
        for arg in (expr.get("args") or [])
        if isinstance(arg, dict)
    ]
    folded = _maybe_fold_nat(str(op), args)
    if folded is not None:
        return folded
    return {
        "op": op,
        "type": typ,
        "args": args,
    }


def _normalize_prop(prop: dict[str, Any], var_map: dict[tuple[str, str], str], counters: dict[str, int]) -> dict[str, Any]:
    op = prop.get("op")
    args = prop.get("args") or []
    if op in {"And", "Or", "Imp"}:
        return {"op": op, "args": [_normalize_prop(arg, var_map, counters) for arg in args]}
    return {"op": op, "args": [_normalize_term(arg, var_map, counters) for arg in args]}


def normalize_goal(goal: dict[str, Any]) -> dict[str, Any]:
    var_map: dict[tuple[str, str], str] = {}
    counters = {"Nat": 0, "LNat": 0, "NatFn": 0}
    return _normalize_prop(goal, var_map, counters)


def _expr_equal(a: dict[str, Any], b: dict[str, Any]) -> bool:
    if a.get("op") != b.get("op") or a.get("type") != b.get("type"):
        return False
    if a.get("op") == "Var":
        return a.get("name") == b.get("name")
    if a.get("op") == "NatLit":
        return int(a.get("lit", 0)) == int(b.get("lit", 0))
    if a.get("op") in {"FnAddConst", "FnMulConst"}:
        return int(a.get("c", 0)) == int(b.get("c", 0))
    args_a = a.get("args") or []
    args_b = b.get("args") or []
    if len(args_a) != len(args_b):
        return False
    return all(_expr_equal(x, y) for x, y in zip(args_a, args_b))


def is_syntax_tautology(goal: dict[str, Any]) -> bool:
    op = goal.get("op")
    args = goal.get("args") or []
    if op in {"EqNat", "EqLNat"}:
        if len(args) == 2 and _expr_equal(args[0], args[1]):
            return True
    return False


__all__ = ["normalize_goal", "is_syntax_tautology"]
