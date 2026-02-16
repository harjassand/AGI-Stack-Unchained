"""Loop summarizer for SAS-System v14.0."""

from __future__ import annotations

from typing import Any

from .sas_system_ir_v1 import compute_ir_id


class SASSystemOptimizeError(RuntimeError):
    pass


def _fail(reason: str) -> None:
    raise SASSystemOptimizeError(reason)


def _is_lit(expr: dict[str, Any], value: int | None = None) -> bool:
    if not isinstance(expr, dict):
        return False
    if "lit" not in expr:
        return False
    if not isinstance(expr.get("lit"), int):
        return False
    if value is None:
        return True
    return int(expr.get("lit")) == value


def _const_expr(expr: dict[str, Any]) -> bool:
    if _is_lit(expr):
        return True
    if expr.get("bin") in {"add", "sub", "mul", "div"}:
        return _const_expr(expr.get("a")) and _const_expr(expr.get("b"))
    return False


def _mul(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    return {"bin": "mul", "a": a, "b": b}


def _range_len(stmt: dict[str, Any]) -> dict[str, Any]:
    start = stmt.get("start")
    end = stmt.get("end")
    if not isinstance(start, dict) or not isinstance(end, dict):
        _fail("INVALID:SUMMARIZER_UNSUPPORTED_PATTERN")
    if not _is_lit(start, 0):
        _fail("INVALID:SUMMARIZER_UNSUPPORTED_PATTERN")
    return end


def _summarize_for(stmt: dict[str, Any]) -> dict[str, Any]:
    if stmt.get("op") != "for_range":
        _fail("INVALID:SUMMARIZER_UNSUPPORTED_PATTERN")
    if stmt.get("var") != "_":
        _fail("INVALID:SUMMARIZER_UNSUPPORTED_PATTERN")
    body = stmt.get("body")
    if not isinstance(body, list) or len(body) != 1:
        _fail("INVALID:SUMMARIZER_UNSUPPORTED_PATTERN")
    inner = body[0]
    # nested two-level loop
    if isinstance(inner, dict) and inner.get("op") == "for_range":
        if inner.get("var") != "_":
            _fail("INVALID:SUMMARIZER_UNSUPPORTED_PATTERN")
        inner_body = inner.get("body")
        if not isinstance(inner_body, list) or len(inner_body) != 1:
            _fail("INVALID:SUMMARIZER_UNSUPPORTED_PATTERN")
        leaf = inner_body[0]
        if not isinstance(leaf, dict) or leaf.get("op") != "add_assign":
            _fail("INVALID:SUMMARIZER_UNSUPPORTED_PATTERN")
        rhs = leaf.get("rhs")
        if not isinstance(rhs, dict) or not _const_expr(rhs):
            _fail("INVALID:SUMMARIZER_UNSUPPORTED_PATTERN")
        count = _mul(_range_len(stmt), _range_len(inner))
        return {"op": "add_assign", "lhs": leaf.get("lhs"), "rhs": _mul(count, rhs)}

    if not isinstance(inner, dict) or inner.get("op") != "add_assign":
        _fail("INVALID:SUMMARIZER_UNSUPPORTED_PATTERN")
    rhs = inner.get("rhs")
    if not isinstance(rhs, dict) or not _const_expr(rhs):
        _fail("INVALID:SUMMARIZER_UNSUPPORTED_PATTERN")
    return {"op": "add_assign", "lhs": inner.get("lhs"), "rhs": _mul(_range_len(stmt), rhs)}


def _summarize_stmt(stmt: dict[str, Any]) -> dict[str, Any] | list[dict[str, Any]]:
    op = stmt.get("op")
    if op == "for_range":
        return _summarize_for(stmt)
    if op == "if":
        then_body = stmt.get("then")
        else_body = stmt.get("else")
        if not isinstance(then_body, list) or not isinstance(else_body, list):
            _fail("INVALID:SUMMARIZER_UNSUPPORTED_PATTERN")
        if len(then_body) == 1 and not else_body:
            inner = then_body[0]
            if isinstance(inner, dict) and inner.get("op") == "for_range":
                summarized = _summarize_for(inner)
                return {"op": "if", "cond": stmt.get("cond"), "then": [summarized], "else": []}
        # otherwise recursively process
        new_then = []
        for sub in then_body:
            out = _summarize_stmt(sub)
            if isinstance(out, list):
                new_then.extend(out)
            else:
                new_then.append(out)
        new_else = []
        for sub in else_body:
            out = _summarize_stmt(sub)
            if isinstance(out, list):
                new_else.extend(out)
            else:
                new_else.append(out)
        return {"op": "if", "cond": stmt.get("cond"), "then": new_then, "else": new_else}
    return stmt


def summarize_loops_v1(ir: dict[str, Any]) -> dict[str, Any]:
    stmts = ir.get("stmts")
    if not isinstance(stmts, list):
        _fail("INVALID:SUMMARIZER_UNSUPPORTED_PATTERN")
    new_stmts: list[dict[str, Any]] = []
    for stmt in stmts:
        if not isinstance(stmt, dict):
            _fail("INVALID:SUMMARIZER_UNSUPPORTED_PATTERN")
        out = _summarize_stmt(stmt)
        if isinstance(out, list):
            new_stmts.extend(out)
        else:
            new_stmts.append(out)
    new_ir = dict(ir)
    new_ir["stmts"] = new_stmts
    new_ir["ir_id"] = compute_ir_id(new_ir)
    return new_ir


__all__ = ["summarize_loops_v1", "SASSystemOptimizeError"]
