#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    _value = str(_entry)
    if _value not in sys.path:
        sys.path.insert(0, _value)


_ALLOWED_OPS = {"ARG", "CONST", "MUL_Q32", "ADD_I64", "RET"}


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("SCHEMA_FAIL")
    return payload


def _const_i64_list(ir: dict[str, Any]) -> list[int]:
    constants = ir.get("constants_q32")
    if constants is None:
        return []
    if not isinstance(constants, list):
        raise RuntimeError("SCHEMA_FAIL:constants_q32")
    out: list[int] = []
    for row in constants:
        if not isinstance(row, dict):
            raise RuntimeError("SCHEMA_FAIL:constant_row")
        value = row.get("value_i64")
        if not isinstance(value, int):
            raise RuntimeError("SCHEMA_FAIL:value_i64")
        out.append(int(value))
    return out


def _normalized_operations(ir: dict[str, Any]) -> tuple[list[dict[str, Any]], list[int]]:
    schema_version = str(ir.get("schema_version", "")).strip()
    schema_id = str(ir.get("schema_id", "")).strip()
    numeric_mode = str(ir.get("numeric_mode", "")).strip()
    if numeric_mode and numeric_mode not in {"Q32", "Q32_FIXEDPOINT"}:
        raise RuntimeError("SCHEMA_FAIL:numeric_mode")
    constants = _const_i64_list(ir)

    if schema_version == "polymath_restricted_ir_v1":
        ops_raw = ir.get("operations")
        if not isinstance(ops_raw, list) or not ops_raw:
            raise RuntimeError("SCHEMA_FAIL:operations")
        out_legacy: list[dict[str, Any]] = []
        for row in ops_raw:
            if not isinstance(row, dict):
                raise RuntimeError("SCHEMA_FAIL:operation_row")
            op = str(row.get("op", "")).strip()
            args = row.get("args")
            if op not in _ALLOWED_OPS or not isinstance(args, list):
                raise RuntimeError("SCHEMA_FAIL:operation")
            out_legacy.append({"op": op, "args": [int(v) for v in args], "const_immediate_b": False})
        return out_legacy, constants

    if schema_id == "polymath_restricted_ir_v1":
        ops_compact = ir.get("ops")
        if not isinstance(ops_compact, list) or not ops_compact:
            raise RuntimeError("SCHEMA_FAIL:ops")
        out_compact: list[dict[str, Any]] = []
        for row in ops_compact:
            if not isinstance(row, dict):
                raise RuntimeError("SCHEMA_FAIL:op_row")
            op = str(row.get("op", "")).strip()
            if op not in _ALLOWED_OPS:
                raise RuntimeError(f"SCHEMA_FAIL:unsupported_op:{op}")
            args_raw = row.get("args")
            args: list[int]
            const_immediate_b = False
            if isinstance(args_raw, list):
                args = [int(v) for v in args_raw]
            elif op == "ARG" and row.get("idx") is not None:
                args = [int(row.get("idx"))]
            elif op == "CONST" and row.get("value_q32") is not None:
                args = [int(row.get("value_q32"))]
                const_immediate_b = True
            elif op in {"RET"} and row.get("idx") is not None:
                args = [int(row.get("idx"))]
            else:
                args = []
            out_compact.append({"op": op, "args": args, "const_immediate_b": bool(const_immediate_b)})
        return out_compact, constants

    raise RuntimeError("SCHEMA_FAIL:polymath_restricted_ir_v1")


def _i64_literal(value: int) -> str:
    value = int(value)
    if value == -(1 << 63):
        return "(-9223372036854775807l - 1l)"
    return f"{value}l"


def generate_msl_source(ir: dict[str, Any]) -> str:
    ops, constants = _normalized_operations(ir)
    value_count = 0
    value_stack: list[int] = []
    kernel_lines: list[str] = []
    out_assigned = False

    for pos, row in enumerate(ops):
        op = str(row.get("op", "")).strip()
        args = [int(v) for v in list(row.get("args") or [])]
        if op == "ARG":
            if len(args) != 1:
                raise RuntimeError("SCHEMA_FAIL:ARG_arity")
            which = int(args[0])
            if which not in {0, 1}:
                raise RuntimeError("SCHEMA_FAIL:ARG_index")
            src = "x_q32" if which == 0 else "y_q32"
            kernel_lines.append(f"    long v{value_count} = {src};")
            value_stack.append(value_count)
            value_count += 1
            continue
        if op == "CONST":
            if len(args) != 1:
                raise RuntimeError("SCHEMA_FAIL:CONST_arity")
            if bool(row.get("const_immediate_b", False)):
                literal = _i64_literal(int(args[0]))
            else:
                c_idx = int(args[0])
                if c_idx < 0 or c_idx >= len(constants):
                    raise RuntimeError("SCHEMA_FAIL:CONST_index")
                literal = _i64_literal(constants[c_idx])
            kernel_lines.append(f"    long v{value_count} = {literal};")
            value_stack.append(value_count)
            value_count += 1
            continue
        if op == "MUL_Q32":
            if len(args) == 2:
                a_idx = int(args[0])
                b_idx = int(args[1])
            elif len(args) == 0:
                if len(value_stack) < 2:
                    raise RuntimeError("SCHEMA_FAIL:MUL_Q32_stack_underflow")
                b_idx = int(value_stack.pop())
                a_idx = int(value_stack.pop())
            else:
                raise RuntimeError("SCHEMA_FAIL:MUL_Q32_arity")
            if a_idx < 0 or a_idx >= value_count or b_idx < 0 or b_idx >= value_count:
                raise RuntimeError("SCHEMA_FAIL:MUL_Q32_index")
            kernel_lines.append(f"    long v{value_count} = q32_mul_exact(v{a_idx}, v{b_idx});")
            value_stack.append(value_count)
            value_count += 1
            continue
        if op == "ADD_I64":
            if len(args) == 2:
                a_idx = int(args[0])
                b_idx = int(args[1])
            elif len(args) == 0:
                if len(value_stack) < 2:
                    raise RuntimeError("SCHEMA_FAIL:ADD_I64_stack_underflow")
                b_idx = int(value_stack.pop())
                a_idx = int(value_stack.pop())
            else:
                raise RuntimeError("SCHEMA_FAIL:ADD_I64_arity")
            if a_idx < 0 or a_idx >= value_count or b_idx < 0 or b_idx >= value_count:
                raise RuntimeError("SCHEMA_FAIL:ADD_I64_index")
            kernel_lines.append(f"    long v{value_count} = sat_i64_add(v{a_idx}, v{b_idx});")
            value_stack.append(value_count)
            value_count += 1
            continue
        if op == "RET":
            if len(args) == 1:
                ret_idx = int(args[0])
            elif len(args) == 0:
                if not value_stack:
                    raise RuntimeError("SCHEMA_FAIL:RET_stack_empty")
                ret_idx = int(value_stack[-1])
            else:
                raise RuntimeError("SCHEMA_FAIL:RET_arity")
            if pos != len(ops) - 1:
                raise RuntimeError("SCHEMA_FAIL:RET_not_last")
            if ret_idx < 0 or ret_idx >= value_count:
                raise RuntimeError("SCHEMA_FAIL:RET_index")
            kernel_lines.append(f"    long outv = v{ret_idx};")
            out_assigned = True
            continue
        raise RuntimeError(f"SCHEMA_FAIL:unsupported_op:{op}")

    if not out_assigned:
        raise RuntimeError("SCHEMA_FAIL:missing_RET")

    kernel_body = "\n".join(kernel_lines)

    return (
        "#include <metal_stdlib>\n"
        "using namespace metal;\n\n"
        "struct U128 { ulong hi; ulong lo; };\n\n"
        "inline U128 umul64wide(ulong a, ulong b) {\n"
        "    const ulong mask32 = 0xfffffffful;\n"
        "    ulong a0 = a & mask32;\n"
        "    ulong a1 = a >> 32;\n"
        "    ulong b0 = b & mask32;\n"
        "    ulong b1 = b >> 32;\n"
        "    ulong p00 = a0 * b0;\n"
        "    ulong p01 = a0 * b1;\n"
        "    ulong p10 = a1 * b0;\n"
        "    ulong p11 = a1 * b1;\n"
        "    ulong lo_hi = (p00 >> 32) + (p01 & mask32) + (p10 & mask32);\n"
        "    U128 out;\n"
        "    out.lo = (p00 & mask32) | (lo_hi << 32);\n"
        "    out.hi = p11 + (p01 >> 32) + (p10 >> 32) + (lo_hi >> 32);\n"
        "    return out;\n"
        "}\n\n"
        "inline U128 twos_complement_128(U128 v) {\n"
        "    U128 out;\n"
        "    out.hi = ~v.hi;\n"
        "    out.lo = ~v.lo + 1ul;\n"
        "    if (out.lo == 0ul) { out.hi += 1ul; }\n"
        "    return out;\n"
        "}\n\n"
        "inline U128 mul_i64_to_i128(long a, long b) {\n"
        "    bool neg = (a < 0) != (b < 0);\n"
        "    ulong ua = (a < 0) ? (~as_type<ulong>(a) + 1ul) : as_type<ulong>(a);\n"
        "    ulong ub = (b < 0) ? (~as_type<ulong>(b) + 1ul) : as_type<ulong>(b);\n"
        "    U128 out = umul64wide(ua, ub);\n"
        "    if (neg) { out = twos_complement_128(out); }\n"
        "    return out;\n"
        "}\n\n"
        "inline long sat_from_shift32(U128 prod) {\n"
        "    const ulong ALL1 = 0xfffffffffffffffful;\n"
        "    const long I64_MAX = 9223372036854775807l;\n"
        "    const long I64_MIN = (-9223372036854775807l - 1l);\n"
        "\n"
        "    ulong shifted_lo = (prod.hi << 32) | (prod.lo >> 32);\n"
        "    ulong shifted_hi;\n"
        "    if ((prod.hi & 0x8000000000000000ul) != 0ul) {\n"
        "        shifted_hi = (prod.hi >> 32) | 0xffffffff00000000ul;\n"
        "    } else {\n"
        "        shifted_hi = (prod.hi >> 32);\n"
        "    }\n"
        "\n"
        "    ulong sign_ext = ((shifted_lo & 0x8000000000000000ul) != 0ul) ? ALL1 : 0ul;\n"
        "    if (shifted_hi != sign_ext) {\n"
        "        if (sign_ext == 0ul) {\n"
        "            return I64_MAX;\n"
        "        }\n"
        "        return I64_MIN;\n"
        "    }\n"
        "    return as_type<long>(shifted_lo);\n"
        "}\n\n"
        "inline long q32_mul_exact(long a, long b) {\n"
        "    return sat_from_shift32(mul_i64_to_i128(a, b));\n"
        "}\n\n"
        "inline long sat_i64_add(long a, long b) {\n"
        "    const long I64_MAX = 9223372036854775807l;\n"
        "    const long I64_MIN = (-9223372036854775807l - 1l);\n"
        "    if (b > 0 && a > I64_MAX - b) { return I64_MAX; }\n"
        "    if (b < 0 && a < I64_MIN - b) { return I64_MIN; }\n"
        "    return a + b;\n"
        "}\n\n"
        "kernel void omega_kernel_eval_v1_kernel(\n"
        "    const device long2* in_args [[buffer(0)]],\n"
        "    device long* out_vals [[buffer(1)]],\n"
        "    uint tid [[thread_position_in_grid]]) {\n"
        "    long x_q32 = in_args[tid].x;\n"
        "    long y_q32 = in_args[tid].y;\n"
        f"{kernel_body}\n"
        "    out_vals[tid] = outv;\n"
        "}\n"
    )


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="metal_codegen_v1")
    ap.add_argument("--restricted_ir", required=True)
    ap.add_argument("--out", required=True)
    return ap.parse_args()


def main() -> None:
    args = _parse_args()
    ir = _load_json(Path(args.restricted_ir).resolve())
    msl = generate_msl_source(ir)
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(msl, encoding="utf-8")
    print(json.dumps({"msl_path": out_path.as_posix()}, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
