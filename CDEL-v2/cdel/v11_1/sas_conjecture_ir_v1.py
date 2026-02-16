"""SAS conjecture IR helpers (v11.1)."""

from __future__ import annotations

from typing import Any, Dict

from ..v1_7r.canon import CanonError, canon_bytes, sha256_prefixed

SCHEMA_VERSION = "sas_conjecture_ir_v1"


class ConjectureIRError(CanonError):
    pass


def _fail(reason: str) -> None:
    raise ConjectureIRError(reason)


def compute_conjecture_id(conjecture_ir: dict[str, Any]) -> str:
    payload = dict(conjecture_ir)
    payload.pop("conjecture_id", None)
    return sha256_prefixed(canon_bytes(payload))


def _validate_expr(expr: dict[str, Any]) -> None:
    if not isinstance(expr, dict):
        _fail("SCHEMA_INVALID")
    op = expr.get("op")
    if op not in {"Var", "NatLit", "Add", "Mul", "Succ", "Eq"}:
        _fail("SCHEMA_INVALID")
    if op == "Var":
        if not isinstance(expr.get("name"), str):
            _fail("SCHEMA_INVALID")
    elif op == "NatLit":
        value = expr.get("value")
        if not isinstance(value, int) or value < 0:
            _fail("SCHEMA_INVALID")
    elif op in {"Add", "Mul"}:
        args = expr.get("args")
        if not isinstance(args, list) or len(args) != 2:
            _fail("SCHEMA_INVALID")
        _validate_expr(args[0])
        _validate_expr(args[1])
    elif op == "Succ":
        arg = expr.get("arg")
        if not isinstance(arg, dict):
            _fail("SCHEMA_INVALID")
        _validate_expr(arg)
    elif op == "Eq":
        lhs = expr.get("lhs")
        rhs = expr.get("rhs")
        if not isinstance(lhs, dict) or not isinstance(rhs, dict):
            _fail("SCHEMA_INVALID")
        _validate_expr(lhs)
        _validate_expr(rhs)


def validate_conjecture_ir(conjecture_ir: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(conjecture_ir, dict) or conjecture_ir.get("schema_version") != SCHEMA_VERSION:
        _fail("SCHEMA_INVALID")
    if conjecture_ir.get("domain") != "NAT_ARITH":
        _fail("SCHEMA_INVALID")
    vars_list = conjecture_ir.get("vars")
    if not isinstance(vars_list, list):
        _fail("SCHEMA_INVALID")
    for item in vars_list:
        if not isinstance(item, dict):
            _fail("SCHEMA_INVALID")
        if item.get("type") != "Nat":
            _fail("SCHEMA_INVALID")
        if not isinstance(item.get("name"), str):
            _fail("SCHEMA_INVALID")
    goal = conjecture_ir.get("goal")
    if not isinstance(goal, dict):
        _fail("SCHEMA_INVALID")
    _validate_expr(goal)

    expected = compute_conjecture_id(conjecture_ir)
    if conjecture_ir.get("conjecture_id") != expected:
        _fail("CONJECTURE_ID_MISMATCH")
    return conjecture_ir


def _normalize_expr(expr: dict[str, Any], var_map: dict[str, str]) -> dict[str, Any]:
    op = expr.get("op")
    if op == "Var":
        name = str(expr.get("name"))
        return {"op": "Var", "name": var_map.get(name, name)}
    if op == "NatLit":
        return {"op": "NatLit", "value": int(expr.get("value", 0))}
    if op in {"Add", "Mul"}:
        args = expr.get("args") or []
        return {"op": op, "args": [_normalize_expr(args[0], var_map), _normalize_expr(args[1], var_map)]}
    if op == "Succ":
        return {"op": "Succ", "arg": _normalize_expr(expr.get("arg"), var_map)}
    if op == "Eq":
        return {
            "op": "Eq",
            "lhs": _normalize_expr(expr.get("lhs"), var_map),
            "rhs": _normalize_expr(expr.get("rhs"), var_map),
        }
    return {"op": "Var", "name": "x"}


def compute_fingerprint(conjecture_ir: dict[str, Any]) -> dict[str, Any]:
    vars_list = conjecture_ir.get("vars") or []
    var_map = {}
    norm_vars = []
    for idx, item in enumerate(vars_list):
        name = str(item.get("name"))
        new_name = f"v{idx}"
        var_map[name] = new_name
        norm_vars.append({"name": new_name, "type": "Nat"})
    goal = _normalize_expr(conjecture_ir.get("goal"), var_map)
    payload = {
        "domain": "NAT_ARITH",
        "vars": norm_vars,
        "goal": goal,
    }
    fingerprint_hash = sha256_prefixed(canon_bytes(payload))
    return {
        "schema_version": "sas_conjecture_fingerprint_v1",
        "conjecture_id": compute_conjecture_id(conjecture_ir),
        "fingerprint_hash": fingerprint_hash,
    }


def _expr_node_count(expr: dict[str, Any]) -> int:
    op = expr.get("op")
    if op in {"Var", "NatLit"}:
        return 1
    if op in {"Add", "Mul"}:
        args = expr.get("args") or []
        return 1 + _expr_node_count(args[0]) + _expr_node_count(args[1])
    if op == "Succ":
        return 1 + _expr_node_count(expr.get("arg"))
    if op == "Eq":
        return 1 + _expr_node_count(expr.get("lhs")) + _expr_node_count(expr.get("rhs"))
    return 1


def _expr_depth(expr: dict[str, Any]) -> int:
    op = expr.get("op")
    if op in {"Var", "NatLit"}:
        return 1
    if op in {"Add", "Mul"}:
        args = expr.get("args") or []
        return 1 + max(_expr_depth(args[0]), _expr_depth(args[1]))
    if op == "Succ":
        return 1 + _expr_depth(expr.get("arg"))
    if op == "Eq":
        return 1 + max(_expr_depth(expr.get("lhs")), _expr_depth(expr.get("rhs")))
    return 1


def compute_metrics(conjecture_ir: dict[str, Any]) -> dict[str, int]:
    goal = conjecture_ir.get("goal") or {}
    return {
        "node_count": int(_expr_node_count(goal)),
        "binder_count": int(len(conjecture_ir.get("vars") or [])),
        "depth": int(_expr_depth(goal)),
    }


def _render_expr(expr: dict[str, Any]) -> str:
    op = expr.get("op")
    if op == "Var":
        return str(expr.get("name"))
    if op == "NatLit":
        return str(int(expr.get("value", 0)))
    if op == "Add":
        args = expr.get("args") or []
        return f"({_render_expr(args[0])} + {_render_expr(args[1])})"
    if op == "Mul":
        args = expr.get("args") or []
        return f"({_render_expr(args[0])} * {_render_expr(args[1])})"
    if op == "Succ":
        return f"(Nat.succ {_render_expr(expr.get('arg'))})"
    if op == "Eq":
        return f"({_render_expr(expr.get('lhs'))} = {_render_expr(expr.get('rhs'))})"
    return "0"


def render_statement(conjecture_ir: dict[str, Any]) -> str:
    vars_list = conjecture_ir.get("vars") or []
    vars_part = " ".join([f"({item.get('name')} : Nat)" for item in vars_list])
    goal_expr = _render_expr(conjecture_ir.get("goal"))
    if vars_part:
        return f"example {vars_part} : {goal_expr} :="
    return f"example : {goal_expr} :="


__all__ = [
    "compute_conjecture_id",
    "validate_conjecture_ir",
    "compute_fingerprint",
    "compute_metrics",
    "render_statement",
    "ConjectureIRError",
]
