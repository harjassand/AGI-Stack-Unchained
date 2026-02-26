#!/usr/bin/env python3
"""Frozen Oracle DSL parser + evaluator (v1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_MAX_ABS_INT = 1 << 60


class OracleDslError(RuntimeError):
    def __init__(self, code: str):
        self.code = str(code).strip() or "RUNTIME_ERROR"
        super().__init__(self.code)


@dataclass(frozen=True)
class Program:
    node: dict[str, Any]


_ALLOWED_OPS = {
    "INT",
    "STR",
    "IN",
    "LEN",
    "REV_LIST",
    "SORT_LIST",
    "UNIQ_LIST",
    "MAP_ADD",
    "MAP_MUL",
    "FILTER_MOD_EQ",
    "SUM",
    "PREFIX_SUM",
    "TAKE",
    "DROP",
    "CONCAT_LIST",
    "SUBSTR",
    "CONCAT_STR",
    "REPLACE_STR",
    "FIND_STR",
    "IF_EQ",
    "IF_LT",
}


def _error(code: str) -> dict[str, str]:
    return {"__ERROR__": str(code).strip() or "RUNTIME_ERROR"}


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _ensure_int(v: Any, code: str = "TYPE_ERROR") -> int:
    if not _is_int(v):
        raise OracleDslError(code)
    out = int(v)
    if abs(out) > _MAX_ABS_INT:
        raise OracleDslError("INT_OVERFLOW")
    return out


def _ensure_str(v: Any) -> str:
    if not isinstance(v, str):
        raise OracleDslError("TYPE_ERROR")
    return v


def _ensure_list_int(v: Any) -> list[int]:
    if not isinstance(v, list):
        raise OracleDslError("TYPE_ERROR")
    out: list[int] = []
    for row in v:
        out.append(_ensure_int(row))
    return out


def _node(obj: Any) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise OracleDslError("AST_INVALID")
    if set(obj.keys()) != {"v", "op", "a"}:
        raise OracleDslError("AST_INVALID")
    if int(obj.get("v", -1)) != 1:
        raise OracleDslError("AST_INVALID")
    op = str(obj.get("op", "")).strip()
    if op not in _ALLOWED_OPS:
        raise OracleDslError("AST_INVALID")
    args = obj.get("a")
    if not isinstance(args, list):
        raise OracleDslError("AST_INVALID")
    out_args: list[Any] = []
    for row in args:
        if isinstance(row, dict):
            out_args.append(_node(row))
        elif isinstance(row, (str, int, bool)) or row is None:
            out_args.append(row)
        else:
            raise OracleDslError("AST_INVALID")
    return {"v": 1, "op": op, "a": out_args}


def parse_ast(json_obj: Any) -> Program:
    return Program(node=_node(json_obj))


class _StepCounter:
    __slots__ = ("remaining", "used")

    def __init__(self, budget: int):
        self.remaining = int(max(0, budget))
        self.used = 0

    def spend(self) -> None:
        self.remaining -= 1
        self.used += 1
        if self.remaining < 0:
            raise OracleDslError("STEP_BUDGET_EXCEEDED")


def _slice_bounds(i: int, j: int, n: int) -> tuple[int, int]:
    lo = max(0, min(int(i), int(n)))
    hi = max(0, min(int(j), int(n)))
    if hi < lo:
        hi = lo
    return lo, hi


def _eval(node: dict[str, Any], in_obj: Any, steps: _StepCounter) -> Any:
    steps.spend()
    op = str(node["op"])
    a = list(node["a"])

    if op == "INT":
        if len(a) != 1:
            raise OracleDslError("ARITY_ERROR")
        return _ensure_int(a[0])

    if op == "STR":
        if len(a) != 1:
            raise OracleDslError("ARITY_ERROR")
        return _ensure_str(a[0])

    if op == "IN":
        if a:
            raise OracleDslError("ARITY_ERROR")
        return in_obj

    if op == "IF_EQ":
        if len(a) != 4:
            raise OracleDslError("ARITY_ERROR")
        left = _ensure_int(_eval(_node(a[0]), in_obj, steps))
        right = _ensure_int(_eval(_node(a[1]), in_obj, steps))
        branch = _node(a[2] if left == right else a[3])
        return _eval(branch, in_obj, steps)

    if op == "IF_LT":
        if len(a) != 4:
            raise OracleDslError("ARITY_ERROR")
        left = _ensure_int(_eval(_node(a[0]), in_obj, steps))
        right = _ensure_int(_eval(_node(a[1]), in_obj, steps))
        branch = _node(a[2] if left < right else a[3])
        return _eval(branch, in_obj, steps)

    ev = [_eval(_node(row), in_obj, steps) for row in a]

    if op == "LEN":
        if len(ev) != 1:
            raise OracleDslError("ARITY_ERROR")
        value = ev[0]
        if isinstance(value, str):
            return len(value)
        if isinstance(value, list):
            return len(value)
        raise OracleDslError("TYPE_ERROR")

    if op == "REV_LIST":
        if len(ev) != 1:
            raise OracleDslError("ARITY_ERROR")
        xs = _ensure_list_int(ev[0])
        return list(reversed(xs))

    if op == "SORT_LIST":
        if len(ev) != 1:
            raise OracleDslError("ARITY_ERROR")
        xs = _ensure_list_int(ev[0])
        return sorted(xs)

    if op == "UNIQ_LIST":
        if len(ev) != 1:
            raise OracleDslError("ARITY_ERROR")
        xs = _ensure_list_int(ev[0])
        seen: set[int] = set()
        out: list[int] = []
        for row in xs:
            if row in seen:
                continue
            seen.add(row)
            out.append(row)
        return out

    if op == "MAP_ADD":
        if len(ev) != 2:
            raise OracleDslError("ARITY_ERROR")
        xs = _ensure_list_int(ev[0])
        k = _ensure_int(ev[1])
        return [int(row + k) for row in xs]

    if op == "MAP_MUL":
        if len(ev) != 2:
            raise OracleDslError("ARITY_ERROR")
        xs = _ensure_list_int(ev[0])
        k = _ensure_int(ev[1])
        return [int(row * k) for row in xs]

    if op == "FILTER_MOD_EQ":
        if len(ev) != 3:
            raise OracleDslError("ARITY_ERROR")
        xs = _ensure_list_int(ev[0])
        m = _ensure_int(ev[1])
        r = _ensure_int(ev[2])
        if m == 0:
            raise OracleDslError("DIV_ZERO")
        return [int(row) for row in xs if row % m == r]

    if op == "SUM":
        if len(ev) != 1:
            raise OracleDslError("ARITY_ERROR")
        xs = _ensure_list_int(ev[0])
        return int(sum(xs))

    if op == "PREFIX_SUM":
        if len(ev) != 1:
            raise OracleDslError("ARITY_ERROR")
        xs = _ensure_list_int(ev[0])
        out: list[int] = []
        acc = 0
        for row in xs:
            acc += int(row)
            out.append(int(acc))
        return out

    if op == "TAKE":
        if len(ev) != 2:
            raise OracleDslError("ARITY_ERROR")
        n = max(0, _ensure_int(ev[1]))
        value = ev[0]
        if isinstance(value, list):
            return list(value[:n])
        if isinstance(value, str):
            return value[:n]
        raise OracleDslError("TYPE_ERROR")

    if op == "DROP":
        if len(ev) != 2:
            raise OracleDslError("ARITY_ERROR")
        n = max(0, _ensure_int(ev[1]))
        value = ev[0]
        if isinstance(value, list):
            return list(value[n:])
        if isinstance(value, str):
            return value[n:]
        raise OracleDslError("TYPE_ERROR")

    if op == "CONCAT_LIST":
        if len(ev) != 2:
            raise OracleDslError("ARITY_ERROR")
        left = _ensure_list_int(ev[0])
        right = _ensure_list_int(ev[1])
        return left + right

    if op == "SUBSTR":
        if len(ev) != 3:
            raise OracleDslError("ARITY_ERROR")
        s = _ensure_str(ev[0])
        i = _ensure_int(ev[1])
        j = _ensure_int(ev[2])
        lo, hi = _slice_bounds(i, j, len(s))
        return s[lo:hi]

    if op == "CONCAT_STR":
        if len(ev) != 2:
            raise OracleDslError("ARITY_ERROR")
        return _ensure_str(ev[0]) + _ensure_str(ev[1])

    if op == "REPLACE_STR":
        if len(ev) != 3:
            raise OracleDslError("ARITY_ERROR")
        s = _ensure_str(ev[0])
        old = _ensure_str(ev[1])
        new = _ensure_str(ev[2])
        return s.replace(old, new)

    if op == "FIND_STR":
        if len(ev) != 2:
            raise OracleDslError("ARITY_ERROR")
        s = _ensure_str(ev[0])
        sub = _ensure_str(ev[1])
        return int(s.find(sub))

    raise OracleDslError("BAD_OP")


def eval_program_with_stats(program: Program, input_obj: Any, step_budget_u32: int) -> tuple[Any, int]:
    budget = int(step_budget_u32)
    if budget <= 0:
        raise OracleDslError("STEP_BUDGET_EXCEEDED")
    steps = _StepCounter(budget)
    out = _eval(program.node, input_obj, steps)
    return out, int(steps.used)


def eval_program(program: Program, input_obj: Any, step_budget_u32: int) -> Any:
    try:
        out, _ = eval_program_with_stats(program, input_obj, int(step_budget_u32))
        return out
    except OracleDslError as exc:
        return _error(exc.code)
    except Exception:
        return _error("RUNTIME_ERROR")


__all__ = [
    "OracleDslError",
    "Program",
    "eval_program",
    "eval_program_with_stats",
    "parse_ast",
]
