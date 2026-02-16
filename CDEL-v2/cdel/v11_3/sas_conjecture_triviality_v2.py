"""Triviality filters for SAS conjectures (v11.2)."""

from __future__ import annotations

from typing import Any, Dict, Tuple


def _var_prefix(vtype: str, idx: int) -> str:
    if vtype == "Nat":
        return f"n{idx}"
    if vtype == "ListNat":
        return f"xs{idx}"
    return f"f{idx}"


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
    if op in {"FnSucc", "FnAddConst", "FnMulConst"}:
        node = {"op": op, "type": "NatFn", "args": []}
        if op in {"FnAddConst", "FnMulConst"}:
            node["c"] = int(expr.get("c", 0))
        return node
    args = expr.get("args") or []
    return {
        "op": op,
        "type": typ,
        "args": [_normalize_term(arg, var_map, counters) for arg in args],
    }


def normalize_goal(goal: dict[str, Any]) -> dict[str, Any]:
    var_map: dict[tuple[str, str], str] = {}
    counters = {"Nat": 0, "ListNat": 0, "NatFn": 0}
    return {
        "op": goal.get("op"),
        "args": [_normalize_term(arg, var_map, counters) for arg in (goal.get("args") or [])],
    }


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


def _is_nat_lit(expr: dict[str, Any], value: int) -> bool:
    return expr.get("op") == "NatLit" and int(expr.get("lit", -1)) == int(value)


def is_syntax_tautology(goal: dict[str, Any]) -> bool:
    op = goal.get("op")
    args = goal.get("args") or []
    if op in {"EqNat", "EqListNat", "LeNat", "LtNat", "Dvd"}:
        if len(args) == 2 and _expr_equal(args[0], args[1]):
            return True
    if op == "Prime" and len(args) == 1:
        if _is_nat_lit(args[0], 0) or _is_nat_lit(args[0], 1):
            return True
    if op == "Dvd" and len(args) == 2:
        if _is_nat_lit(args[0], 0) and _is_nat_lit(args[1], 0):
            return True
    return False


def is_pattern_trivial(goal: dict[str, Any]) -> bool:
    op = goal.get("op")
    args = goal.get("args") or []
    if op == "EqNat" and len(args) == 2:
        lhs, rhs = args
        # Add commutativity
        if lhs.get("op") == "Add" and rhs.get("op") == "Add":
            a1, a2 = lhs.get("args") or [None, None]
            b1, b2 = rhs.get("args") or [None, None]
            if _expr_equal(a1, b2) and _expr_equal(a2, b1):
                return True
        # Mul commutativity
        if lhs.get("op") == "Mul" and rhs.get("op") == "Mul":
            a1, a2 = lhs.get("args") or [None, None]
            b1, b2 = rhs.get("args") or [None, None]
            if _expr_equal(a1, b2) and _expr_equal(a2, b1):
                return True
        # Add associativity (both directions)
        if lhs.get("op") == "Add" and rhs.get("op") == "Add":
            l1, l2 = lhs.get("args") or [None, None]
            r1, r2 = rhs.get("args") or [None, None]
            if l1.get("op") == "Add" and r2.get("op") == "Add":
                x, y = l1.get("args") or [None, None]
                z = l2
                x2 = r1
                y2, z2 = r2.get("args") or [None, None]
                if _expr_equal(x, x2) and _expr_equal(y, y2) and _expr_equal(z, z2):
                    return True
            if r1.get("op") == "Add" and l2.get("op") == "Add":
                x, y = r1.get("args") or [None, None]
                z = r2
                x2 = l1
                y2, z2 = l2.get("args") or [None, None]
                if _expr_equal(x, x2) and _expr_equal(y, y2) and _expr_equal(z, z2):
                    return True
        # Mul associativity (both directions)
        if lhs.get("op") == "Mul" and rhs.get("op") == "Mul":
            l1, l2 = lhs.get("args") or [None, None]
            r1, r2 = rhs.get("args") or [None, None]
            if l1.get("op") == "Mul" and r2.get("op") == "Mul":
                x, y = l1.get("args") or [None, None]
                z = l2
                x2 = r1
                y2, z2 = r2.get("args") or [None, None]
                if _expr_equal(x, x2) and _expr_equal(y, y2) and _expr_equal(z, z2):
                    return True
            if r1.get("op") == "Mul" and l2.get("op") == "Mul":
                x, y = r1.get("args") or [None, None]
                z = r2
                x2 = l1
                y2, z2 = l2.get("args") or [None, None]
                if _expr_equal(x, x2) and _expr_equal(y, y2) and _expr_equal(z, z2):
                    return True
        # Neutral elements
        if lhs.get("op") == "Add":
            a1, a2 = lhs.get("args") or [None, None]
            if _is_nat_lit(a1, 0) and _expr_equal(a2, rhs):
                return True
            if _is_nat_lit(a2, 0) and _expr_equal(a1, rhs):
                return True
        if rhs.get("op") == "Add":
            a1, a2 = rhs.get("args") or [None, None]
            if _is_nat_lit(a1, 0) and _expr_equal(a2, lhs):
                return True
            if _is_nat_lit(a2, 0) and _expr_equal(a1, lhs):
                return True
        if lhs.get("op") == "Mul":
            a1, a2 = lhs.get("args") or [None, None]
            if _is_nat_lit(a1, 1) and _expr_equal(a2, rhs):
                return True
            if _is_nat_lit(a2, 1) and _expr_equal(a1, rhs):
                return True
            if _is_nat_lit(a1, 0) and _is_nat_lit(rhs, 0):
                return True
            if _is_nat_lit(a2, 0) and _is_nat_lit(rhs, 0):
                return True
        if rhs.get("op") == "Mul":
            a1, a2 = rhs.get("args") or [None, None]
            if _is_nat_lit(a1, 1) and _expr_equal(a2, lhs):
                return True
            if _is_nat_lit(a2, 1) and _expr_equal(a1, lhs):
                return True
            if _is_nat_lit(a1, 0) and _is_nat_lit(lhs, 0):
                return True
            if _is_nat_lit(a2, 0) and _is_nat_lit(lhs, 0):
                return True
        # Range length
        if lhs.get("op") == "ListLen":
            l_arg = (lhs.get("args") or [None])[0]
            if l_arg.get("op") == "ListRange":
                n = (l_arg.get("args") or [None])[0]
                if _expr_equal(n, rhs):
                    return True
        if rhs.get("op") == "ListLen":
            r_arg = (rhs.get("args") or [None])[0]
            if r_arg.get("op") == "ListRange":
                n = (r_arg.get("args") or [None])[0]
                if _expr_equal(n, lhs):
                    return True

    if op == "EqListNat" and len(args) == 2:
        lhs, rhs = args
        if lhs.get("op") == "ListAppend":
            a1, a2 = lhs.get("args") or [None, None]
            if a2.get("op") == "ListNil" and _expr_equal(a1, rhs):
                return True
            if a1.get("op") == "ListNil" and _expr_equal(a2, rhs):
                return True
        if rhs.get("op") == "ListAppend":
            a1, a2 = rhs.get("args") or [None, None]
            if a2.get("op") == "ListNil" and _expr_equal(a1, lhs):
                return True
            if a1.get("op") == "ListNil" and _expr_equal(a2, lhs):
                return True

    return False


def novelty_gate_pass(op_counts: dict[str, int]) -> bool:
    return bool(
        int(op_counts.get("Pow", 0)) > 0
        or int(op_counts.get("Prime", 0)) > 0
        or int(op_counts.get("Dvd", 0)) > 0
        or int(op_counts.get("ListSum", 0)) > 0
        or int(op_counts.get("Gcd", 0)) > 0
        or int(op_counts.get("Mod", 0)) > 0
    )


__all__ = ["normalize_goal", "is_syntax_tautology", "is_pattern_trivial", "novelty_gate_pass"]
