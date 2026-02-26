#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    _value = str(_entry)
    if _value not in sys.path:
        sys.path.insert(0, _value)

from cdel.v18_0.omega_common_v1 import validate_schema as validate_schema_v18
from cdel.v19_0.common_v1 import validate_schema as validate_schema_v19


_MACRO_TOKEN_RE = re.compile(r"^OP_[A-Z0-9_]{3,64}$")


class MacroRuntimeError(RuntimeError):
    pass


def _fail(reason: str) -> None:
    raise MacroRuntimeError(str(reason))


def _load_ir(ir_text_or_ast: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(ir_text_or_ast, dict):
        return dict(ir_text_or_ast)
    try:
        payload = json.loads(str(ir_text_or_ast))
    except Exception as exc:  # noqa: BLE001
        raise MacroRuntimeError("SCHEMA_FAIL:ir_json") from exc
    if not isinstance(payload, dict):
        _fail("SCHEMA_FAIL:ir_obj")
    return payload


def _macro_map(bank: dict[str, Any]) -> dict[str, dict[str, Any]]:
    validate_schema_v19(bank, "oracle_operator_bank_v1")
    out: dict[str, dict[str, Any]] = {}
    macros = bank.get("macros")
    if isinstance(macros, list):
        for row in macros:
            if not isinstance(row, dict):
                continue
            token = str(row.get("token", "")).strip()
            if token:
                out[token] = row
    return out


def _expand_legacy_ops(ops: list[dict[str, Any]], bank_map: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    changed = False
    expanded: list[dict[str, Any]] = []
    for row in ops:
        if not isinstance(row, dict):
            _fail("SCHEMA_FAIL:operation_row")
        op = str(row.get("op", "")).strip()
        args = row.get("args")
        if not isinstance(args, list):
            _fail("SCHEMA_FAIL:operation_args")

        macro = bank_map.get(op)
        if macro is None:
            if _MACRO_TOKEN_RE.fullmatch(op) is not None:
                _fail("UNKNOWN_MACRO_TOKEN")
            expanded.append({"op": op, "args": [int(v) for v in args]})
            continue

        arity = int(macro.get("arity_u64", 0))
        if len(args) != arity:
            _fail("ARITY_MISMATCH")
        exp_ir = macro.get("expansion_ir")
        if not isinstance(exp_ir, dict):
            _fail("SCHEMA_FAIL:expansion_ir")
        exp_ops = exp_ir.get("ops")
        if not isinstance(exp_ops, list) or not exp_ops:
            _fail("SCHEMA_FAIL:expansion_ops")

        for exp_row_raw in exp_ops:
            if not isinstance(exp_row_raw, dict):
                _fail("SCHEMA_FAIL:expansion_op_row")
            exp_op = str(exp_row_raw.get("op", "")).strip()
            if not exp_op:
                _fail("SCHEMA_FAIL:expansion_op")

            if exp_op == "ARG":
                idx_raw = exp_row_raw.get("idx")
                if idx_raw is None:
                    raw_args = exp_row_raw.get("args")
                    if isinstance(raw_args, list) and len(raw_args) == 1:
                        idx_raw = raw_args[0]
                idx = int(idx_raw)
                if idx < 0 or idx >= arity:
                    _fail("ARITY_MISMATCH")
                expanded.append({"op": "ARG", "args": [int(args[idx])]})
                continue

            out_row: dict[str, Any] = {"op": exp_op}
            exp_args = exp_row_raw.get("args")
            if isinstance(exp_args, list):
                out_row["args"] = [int(v) for v in exp_args]
            elif exp_op == "CONST" and "value_q32" in exp_row_raw:
                out_row["args"] = [int(exp_row_raw.get("value_q32", 0))]
            else:
                out_row["args"] = []
            expanded.append(out_row)
        changed = True

    return expanded, changed


def _expand_compact_ops(ops: list[dict[str, Any]], bank_map: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    changed = False
    expanded: list[dict[str, Any]] = []
    for row in ops:
        if not isinstance(row, dict):
            _fail("SCHEMA_FAIL:op_row")
        op = str(row.get("op", "")).strip()
        raw_args = row.get("args")
        args = [int(v) for v in raw_args] if isinstance(raw_args, list) else []

        macro = bank_map.get(op)
        if macro is None:
            if _MACRO_TOKEN_RE.fullmatch(op) is not None:
                _fail("UNKNOWN_MACRO_TOKEN")
            expanded.append(dict(row))
            continue

        arity = int(macro.get("arity_u64", 0))
        if len(args) != arity:
            _fail("ARITY_MISMATCH")
        exp_ir = macro.get("expansion_ir")
        if not isinstance(exp_ir, dict):
            _fail("SCHEMA_FAIL:expansion_ir")
        exp_ops = exp_ir.get("ops")
        if not isinstance(exp_ops, list) or not exp_ops:
            _fail("SCHEMA_FAIL:expansion_ops")

        for exp_row_raw in exp_ops:
            if not isinstance(exp_row_raw, dict):
                _fail("SCHEMA_FAIL:expansion_row")
            exp_op = str(exp_row_raw.get("op", "")).strip()
            if exp_op == "ARG":
                idx_raw = exp_row_raw.get("idx")
                if idx_raw is None:
                    raw2 = exp_row_raw.get("args")
                    if isinstance(raw2, list) and len(raw2) == 1:
                        idx_raw = raw2[0]
                idx = int(idx_raw)
                if idx < 0 or idx >= arity:
                    _fail("ARITY_MISMATCH")
                expanded.append({"op": "ARG", "idx": int(args[idx])})
                continue
            expanded.append(dict(exp_row_raw))
        changed = True
    return expanded, changed


def _validate_compact_ir(ir: dict[str, Any]) -> None:
    if str(ir.get("schema_id", "")).strip() != "polymath_restricted_ir_v1":
        _fail("SCHEMA_FAIL:compact_schema")
    numeric_mode = str(ir.get("numeric_mode", "")).strip()
    if numeric_mode not in {"Q32", "Q32_FIXEDPOINT"}:
        _fail("SCHEMA_FAIL:compact_numeric_mode")
    ops = ir.get("ops")
    if not isinstance(ops, list):
        _fail("SCHEMA_FAIL:compact_ops")
    for row in ops:
        if not isinstance(row, dict):
            _fail("SCHEMA_FAIL:compact_row")
        op = str(row.get("op", "")).strip()
        if not op:
            _fail("SCHEMA_FAIL:compact_op")
        if _MACRO_TOKEN_RE.fullmatch(op) is not None:
            _fail("UNKNOWN_MACRO_TOKEN")
        if "args" in row and not isinstance(row.get("args"), list):
            _fail("SCHEMA_FAIL:compact_args")
        if "idx" in row:
            idx = row.get("idx")
            if not isinstance(idx, int) or idx < 0:
                _fail("SCHEMA_FAIL:compact_idx")
        if "value_q32" in row and not isinstance(row.get("value_q32"), int):
            _fail("SCHEMA_FAIL:compact_value_q32")


def expand_macros(ir_text_or_ast: str | dict[str, Any], bank: dict[str, Any]) -> dict[str, Any]:
    ir = _load_ir(ir_text_or_ast)
    bank_map = _macro_map(bank)

    if isinstance(ir.get("operations"), list):
        current = list(ir.get("operations") or [])
        for _ in range(16):
            current, changed = _expand_legacy_ops(current, bank_map)
            if not changed:
                break
        out = dict(ir)
        out["operations"] = current
        validate_schema_v18(out, "polymath_restricted_ir_v1")
        return out

    if isinstance(ir.get("ops"), list):
        current2 = list(ir.get("ops") or [])
        for _ in range(16):
            current2, changed = _expand_compact_ops(current2, bank_map)
            if not changed:
                break
        out2 = dict(ir)
        out2["ops"] = current2
        _validate_compact_ir(out2)
        return out2

    _fail("SCHEMA_FAIL:ir_missing_ops")


def contract_macros(ir_text_or_ast: str | dict[str, Any], bank: dict[str, Any]) -> dict[str, Any]:
    # Contracting is intentionally conservative: return input unchanged.
    _ = _macro_map(bank)
    return _load_ir(ir_text_or_ast)


__all__ = ["MacroRuntimeError", "contract_macros", "expand_macros"]
