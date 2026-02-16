"""IR definition and validation for SAS-System v14.0."""

from __future__ import annotations

import re
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, sha256_prefixed

SCHEMA_VERSION = "sas_system_ir_v1"
SPEC_VERSION = "v14_0"
PROGRAM_KIND = "IMPERATIVE_INT64_V1"
TARGET_ID = "SAS_SCIENCE_WORKMETER_V1"

ALLOWED_STMTS = {"assign", "add_assign", "if", "for_range"}
ALLOWED_BIN = {"add", "sub", "mul", "div"}
ALLOWED_CMP = {"lt", "le", "eq"}
ALLOWED_BOOL = {"and", "or"}


class SASSystemIRError(CanonError):
    pass


def _fail(reason: str) -> None:
    raise SASSystemIRError(reason)


def compute_ir_id(ir: dict[str, Any]) -> str:
    payload = dict(ir)
    payload["ir_id"] = ""
    return sha256_prefixed(canon_bytes(payload))


def _require_dict(obj: Any) -> dict[str, Any]:
    if not isinstance(obj, dict):
        _fail("INVALID:IR_SCHEMA_FAIL")
    return obj


def _require_str(obj: dict[str, Any], key: str) -> str:
    val = obj.get(key)
    if not isinstance(val, str):
        _fail("INVALID:IR_SCHEMA_FAIL")
    return val


def _require_list(obj: dict[str, Any], key: str) -> list[Any]:
    val = obj.get(key)
    if not isinstance(val, list):
        _fail("INVALID:IR_SCHEMA_FAIL")
    return val


def _validate_expr(expr: Any) -> None:
    expr = _require_dict(expr)
    if "lit" in expr:
        if not isinstance(expr.get("lit"), int):
            _fail("INVALID:IR_SCHEMA_FAIL")
        return
    if "var" in expr:
        if not isinstance(expr.get("var"), str):
            _fail("INVALID:IR_SCHEMA_FAIL")
        return
    if "get" in expr:
        val = expr.get("get")
        if not isinstance(val, str) or not re.fullmatch(r"job\.[A-Za-z0-9_]+", val):
            _fail("INVALID:IR_SCHEMA_FAIL")
        return
    if "bin" in expr:
        if expr.get("bin") not in ALLOWED_BIN:
            _fail("INVALID:IR_UNSUPPORTED_NODE")
        _validate_expr(expr.get("a"))
        _validate_expr(expr.get("b"))
        return
    _fail("INVALID:IR_UNSUPPORTED_NODE")


def _validate_cond(cond: Any) -> None:
    cond = _require_dict(cond)
    if "cmp" in cond:
        if cond.get("cmp") not in ALLOWED_CMP:
            _fail("INVALID:IR_UNSUPPORTED_NODE")
        _validate_expr(cond.get("a"))
        _validate_expr(cond.get("b"))
        return
    if "bool" in cond:
        if cond.get("bool") not in ALLOWED_BOOL:
            _fail("INVALID:IR_UNSUPPORTED_NODE")
        _validate_cond(cond.get("a"))
        _validate_cond(cond.get("b"))
        return
    if "not" in cond:
        _validate_cond(cond.get("not"))
        return
    _fail("INVALID:IR_UNSUPPORTED_NODE")


def _validate_stmt(stmt: Any) -> None:
    stmt = _require_dict(stmt)
    op = stmt.get("op")
    if op not in ALLOWED_STMTS:
        _fail("INVALID:IR_UNSUPPORTED_NODE")
    if op in {"assign", "add_assign"}:
        if not isinstance(stmt.get("lhs"), str):
            _fail("INVALID:IR_SCHEMA_FAIL")
        _validate_expr(stmt.get("rhs"))
        return
    if op == "if":
        _validate_cond(stmt.get("cond"))
        for branch in ["then", "else"]:
            body = stmt.get(branch)
            if not isinstance(body, list):
                _fail("INVALID:IR_SCHEMA_FAIL")
            for inner in body:
                _validate_stmt(inner)
        return
    if op == "for_range":
        if not isinstance(stmt.get("var"), str):
            _fail("INVALID:IR_SCHEMA_FAIL")
        _validate_expr(stmt.get("start"))
        _validate_expr(stmt.get("end"))
        body = stmt.get("body")
        if not isinstance(body, list):
            _fail("INVALID:IR_SCHEMA_FAIL")
        for inner in body:
            _validate_stmt(inner)
        return
    _fail("INVALID:IR_UNSUPPORTED_NODE")


def validate_ir(ir: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(ir, dict):
        _fail("INVALID:IR_SCHEMA_FAIL")
    if ir.get("schema") != SCHEMA_VERSION or ir.get("spec_version") != SPEC_VERSION:
        _fail("INVALID:IR_SCHEMA_FAIL")
    if ir.get("program_kind") != PROGRAM_KIND:
        _fail("INVALID:IR_SCHEMA_FAIL")
    if ir.get("target_id") != TARGET_ID:
        _fail("INVALID:IR_SCHEMA_FAIL")

    ir_id = _require_str(ir, "ir_id")
    locals_list = _require_list(ir, "locals")
    if not all(isinstance(item, str) for item in locals_list):
        _fail("INVALID:IR_SCHEMA_FAIL")
    stmts = _require_list(ir, "stmts")
    for stmt in stmts:
        _validate_stmt(stmt)

    ret = _require_dict(ir.get("return"))
    if ret.get("schema") != "sas_science_workmeter_out_v1":
        _fail("INVALID:IR_SCHEMA_FAIL")
    for key in ["sqrt_calls", "div_calls", "pair_terms_evaluated", "work_cost_total"]:
        slot = ret.get(key)
        if not isinstance(slot, dict) or slot.get("var") not in locals_list:
            _fail("INVALID:IR_SCHEMA_FAIL")

    expected = compute_ir_id(ir)
    if ir_id != expected:
        _fail("INVALID:IR_HASH_MISMATCH")
    return ir


__all__ = [
    "SCHEMA_VERSION",
    "SPEC_VERSION",
    "PROGRAM_KIND",
    "TARGET_ID",
    "compute_ir_id",
    "validate_ir",
    "SASSystemIRError",
]
