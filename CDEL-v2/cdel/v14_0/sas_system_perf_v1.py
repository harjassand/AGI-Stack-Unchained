"""Deterministic IR cost model for SAS-System v14.0."""

from __future__ import annotations

from typing import Any


class SASSystemPerfError(RuntimeError):
    pass


def _fail(reason: str) -> None:
    raise SASSystemPerfError(reason)


def _eval_expr(expr: dict[str, Any], env: dict[str, int], job: dict[str, Any]) -> int:
    if "lit" in expr:
        return int(expr["lit"])
    if "var" in expr:
        name = expr["var"]
        if name not in env:
            _fail("INVALID:IR_EVAL_UNBOUND")
        return int(env[name])
    if "get" in expr:
        key = str(expr["get"])
        if not key.startswith("job."):
            _fail("INVALID:IR_EVAL_UNBOUND")
        field = key.split(".", 1)[1]
        if field not in job:
            _fail("INVALID:IR_EVAL_UNBOUND")
        return int(job[field])
    if "bin" in expr:
        a = _eval_expr(expr["a"], env, job)
        b = _eval_expr(expr["b"], env, job)
        op = expr["bin"]
        if op == "add":
            return int(a + b)
        if op == "sub":
            return int(a - b)
        if op == "mul":
            return int(a * b)
        if op == "div":
            if b == 0:
                _fail("INVALID:IR_DIV_ZERO")
            return int(a // b)
    _fail("INVALID:IR_EVAL_UNSUPPORTED")
    return 0


def _eval_cond(cond: dict[str, Any], env: dict[str, int], job: dict[str, Any]) -> bool:
    if "cmp" in cond:
        a = _eval_expr(cond["a"], env, job)
        b = _eval_expr(cond["b"], env, job)
        op = cond["cmp"]
        if op == "lt":
            return a < b
        if op == "le":
            return a <= b
        if op == "eq":
            return a == b
    if "bool" in cond:
        a = _eval_cond(cond["a"], env, job)
        b = _eval_cond(cond["b"], env, job)
        op = cond["bool"]
        if op == "and":
            return a and b
        if op == "or":
            return a or b
    if "not" in cond:
        return not _eval_cond(cond["not"], env, job)
    _fail("INVALID:IR_EVAL_UNSUPPORTED")
    return False


def _cost_expr(expr: dict[str, Any]) -> int:
    if "lit" in expr or "var" in expr:
        return 0
    if "get" in expr:
        return 1
    if "bin" in expr:
        return 1 + _cost_expr(expr["a"]) + _cost_expr(expr["b"])
    return 0


def _cost_cond(cond: dict[str, Any]) -> int:
    if "cmp" in cond:
        return 1 + _cost_expr(cond["a"]) + _cost_expr(cond["b"])
    if "bool" in cond:
        return 1 + _cost_cond(cond["a"]) + _cost_cond(cond["b"])
    if "not" in cond:
        return 1 + _cost_cond(cond["not"])
    return 0


def _exec_stmt(stmt: dict[str, Any], env: dict[str, int], job: dict[str, Any]) -> int:
    op = stmt.get("op")
    cost = 0
    if op == "assign":
        env[stmt["lhs"]] = _eval_expr(stmt["rhs"], env, job)
        cost += _cost_expr(stmt["rhs"])
        return cost
    if op == "add_assign":
        env[stmt["lhs"]] = int(env.get(stmt["lhs"], 0)) + _eval_expr(stmt["rhs"], env, job)
        cost += 1 + _cost_expr(stmt["rhs"])
        return cost
    if op == "if":
        cost += 1  # if overhead
        cond = stmt["cond"]
        _ = _cost_cond(cond)  # ignored by spec, but keep deterministic structure
        if _eval_cond(cond, env, job):
            for inner in stmt.get("then", []):
                cost += _exec_stmt(inner, env, job)
        else:
            for inner in stmt.get("else", []):
                cost += _exec_stmt(inner, env, job)
        return cost
    if op == "for_range":
        cost += 1  # loop overhead
        start = _eval_expr(stmt["start"], env, job)
        end = _eval_expr(stmt["end"], env, job)
        var = stmt.get("var")
        if not isinstance(var, str):
            _fail("INVALID:IR_EVAL_UNSUPPORTED")
        step = 1
        n = 0
        if step == 1:
            n = max(0, end - start)
        # execute loop to update env; cost counted per-iteration
        for i in range(start, end, step):
            env[var] = int(i)
            for inner in stmt.get("body", []):
                cost += _exec_stmt(inner, env, job)
        # If loop didn't run, env[var] remains last value; keep as-is.
        return cost
    _fail("INVALID:IR_EVAL_UNSUPPORTED")
    return cost


def ir_step_cost_total(ir: dict[str, Any], job: dict[str, Any]) -> int:
    env: dict[str, int] = {}
    total = 0
    for stmt in ir.get("stmts", []):
        total += _exec_stmt(stmt, env, job)
    return int(total)


def ir_step_cost_total_for_suite(ir: dict[str, Any], suite: dict[str, Any]) -> dict[str, int]:
    totals: dict[str, int] = {}
    cases = suite.get("cases") if isinstance(suite, dict) else None
    if not isinstance(cases, list):
        _fail("INVALID:SUITEPACK_SCHEMA_FAIL")
    for case in cases:
        if not isinstance(case, dict):
            _fail("INVALID:SUITEPACK_SCHEMA_FAIL")
        case_id = str(case.get("case_id"))
        job = case.get("job")
        if not isinstance(job, dict):
            _fail("INVALID:SUITEPACK_SCHEMA_FAIL")
        totals[case_id] = ir_step_cost_total(ir, job)
    return totals


__all__ = ["ir_step_cost_total", "ir_step_cost_total_for_suite", "SASSystemPerfError"]
