"""Python AST extraction for SAS-System v14.0 workmeter IR."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, sha256_prefixed
from .sas_system_ir_v1 import (
    PROGRAM_KIND,
    SCHEMA_VERSION,
    SPEC_VERSION,
    TARGET_ID,
    compute_ir_id,
)


class SASSystemExtractError(CanonError):
    pass


def _fail(reason: str) -> None:
    raise SASSystemExtractError(reason)


def _hash_file(path: Path) -> str:
    return sha256_prefixed(path.read_bytes())


def _lit(val: int) -> dict[str, Any]:
    return {"lit": int(val)}


def _var(name: str) -> dict[str, Any]:
    return {"var": name}


def _get_job(field: str) -> dict[str, Any]:
    return {"get": f"job.{field}"}


def _bin(op: str, a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    return {"bin": op, "a": a, "b": b}


def _cmp(op: str, a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    return {"cmp": op, "a": a, "b": b}


def _bool(op: str, a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    return {"bool": op, "a": a, "b": b}


def _not(a: dict[str, Any]) -> dict[str, Any]:
    return {"not": a}


def _expr(node: ast.AST) -> dict[str, Any]:
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return _lit(node.value)
    if isinstance(node, ast.Name):
        return _var(node.id)
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "job":
        key = node.slice
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            return _get_job(key.value)
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.Add):
            return _bin("add", _expr(node.left), _expr(node.right))
        if isinstance(node.op, ast.Sub):
            return _bin("sub", _expr(node.left), _expr(node.right))
        if isinstance(node.op, ast.Mult):
            return _bin("mul", _expr(node.left), _expr(node.right))
        if isinstance(node.op, ast.Div):
            return _bin("div", _expr(node.left), _expr(node.right))
    _fail(f"INVALID:REF_AST_UNSUPPORTED:{node.__class__.__name__}")
    return {}


def _cond(node: ast.AST) -> dict[str, Any]:
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and len(node.comparators) == 1:
        op = node.ops[0]
        if isinstance(op, ast.Lt):
            return _cmp("lt", _expr(node.left), _expr(node.comparators[0]))
        if isinstance(op, ast.LtE):
            return _cmp("le", _expr(node.left), _expr(node.comparators[0]))
        if isinstance(op, ast.Eq):
            return _cmp("eq", _expr(node.left), _expr(node.comparators[0]))
    if isinstance(node, ast.BoolOp) and len(node.values) == 2:
        if isinstance(node.op, ast.And):
            return _bool("and", _cond(node.values[0]), _cond(node.values[1]))
        if isinstance(node.op, ast.Or):
            return _bool("or", _cond(node.values[0]), _cond(node.values[1]))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return _not(_cond(node.operand))
    _fail(f"INVALID:REF_AST_UNSUPPORTED:{node.__class__.__name__}")
    return {}


def _stmt(node: ast.AST, locals_set: set[str]) -> list[dict[str, Any]]:
    if isinstance(node, ast.Assign):
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            _fail(f"INVALID:REF_AST_UNSUPPORTED:{node.__class__.__name__}")
        lhs = node.targets[0].id
        locals_set.add(lhs)
        return [{"op": "assign", "lhs": lhs, "rhs": _expr(node.value)}]
    if isinstance(node, ast.AugAssign):
        if not isinstance(node.target, ast.Name) or not isinstance(node.op, ast.Add):
            _fail(f"INVALID:REF_AST_UNSUPPORTED:{node.__class__.__name__}")
        lhs = node.target.id
        locals_set.add(lhs)
        return [{"op": "add_assign", "lhs": lhs, "rhs": _expr(node.value)}]
    if isinstance(node, ast.If):
        then_body: list[dict[str, Any]] = []
        else_body: list[dict[str, Any]] = []
        for inner in node.body:
            then_body.extend(_stmt(inner, locals_set))
        for inner in node.orelse:
            else_body.extend(_stmt(inner, locals_set))
        return [
            {
                "op": "if",
                "cond": _cond(node.test),
                "then": then_body,
                "else": else_body,
            }
        ]
    if isinstance(node, ast.For):
        if not isinstance(node.target, ast.Name):
            _fail(f"INVALID:REF_AST_UNSUPPORTED:{node.__class__.__name__}")
        iter_node = node.iter
        if not isinstance(iter_node, ast.Call) or not isinstance(iter_node.func, ast.Name) or iter_node.func.id != "range":
            _fail(f"INVALID:REF_AST_UNSUPPORTED:{node.__class__.__name__}")
        args = list(iter_node.args)
        if len(args) == 1:
            start = _lit(0)
            end = _expr(args[0])
        elif len(args) == 2:
            start = _expr(args[0])
            end = _expr(args[1])
        else:
            _fail(f"INVALID:REF_AST_UNSUPPORTED:{node.__class__.__name__}")
        var = node.target.id
        locals_set.add(var)
        body: list[dict[str, Any]] = []
        for inner in node.body:
            body.extend(_stmt(inner, locals_set))
        return [{"op": "for_range", "var": var, "start": start, "end": end, "body": body}]
    if isinstance(node, ast.Return):
        # handled separately in extract
        return []
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
        # allow docstring literals
        return []
    _fail(f"INVALID:REF_AST_UNSUPPORTED:{node.__class__.__name__}")
    return []


def extract_reference_ir(source_path: Path, *, expected_sha256: str | None = None) -> dict[str, Any]:
    if expected_sha256 is not None:
        actual = _hash_file(source_path)
        if actual != expected_sha256:
            _fail("INVALID:REF_HASH_MISMATCH")

    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    func: ast.FunctionDef | None = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "compute_workmeter_v1":
            func = node
            break
    if func is None:
        _fail("INVALID:REF_AST_MISSING_FUNC")
    if len(func.args.args) != 1:
        _fail("INVALID:REF_AST_UNSUPPORTED:Args")

    locals_set: set[str] = set()
    stmts: list[dict[str, Any]] = []
    ret_obj: dict[str, Any] | None = None

    for node in func.body:
        if isinstance(node, ast.Return):
            if not isinstance(node.value, ast.Dict):
                _fail("INVALID:REF_AST_UNSUPPORTED:Return")
            keys = node.value.keys
            vals = node.value.values
            mapping: dict[str, Any] = {}
            for k, v in zip(keys, vals):
                if not isinstance(k, ast.Constant) or not isinstance(k.value, str):
                    _fail("INVALID:REF_AST_UNSUPPORTED:Return")
                if isinstance(v, ast.Name):
                    mapping[k.value] = v.id
                elif isinstance(v, ast.Constant) and isinstance(v.value, str):
                    mapping[k.value] = v.value
                else:
                    _fail("INVALID:REF_AST_UNSUPPORTED:Return")
            ret_obj = {
                "schema": mapping.get("schema", ""),
                "sqrt_calls": {"var": mapping.get("sqrt_calls", "")},
                "div_calls": {"var": mapping.get("div_calls", "")},
                "pair_terms_evaluated": {"var": mapping.get("pair_terms_evaluated", "")},
                "work_cost_total": {"var": mapping.get("work_cost_total", "")},
            }
            continue
        stmts.extend(_stmt(node, locals_set))

    if ret_obj is None:
        _fail("INVALID:REF_AST_MISSING_RETURN")

    locals_list = sorted(locals_set)

    ir = {
        "schema": SCHEMA_VERSION,
        "spec_version": SPEC_VERSION,
        "ir_id": "",
        "target_id": TARGET_ID,
        "program_kind": PROGRAM_KIND,
        "locals": locals_list,
        "stmts": stmts,
        "return": ret_obj,
    }
    ir["ir_id"] = compute_ir_id(ir)
    return ir


__all__ = ["extract_reference_ir", "SASSystemExtractError"]
