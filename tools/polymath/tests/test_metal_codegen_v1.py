from __future__ import annotations

import pytest

from tools.polymath.metal_codegen_v1 import generate_msl_source


def test_generate_msl_source_accepts_compact_stack_ir() -> None:
    ir = {
        "schema_id": "polymath_restricted_ir_v1",
        "numeric_mode": "Q32",
        "ops": [
            {"op": "ARG", "idx": 0},
            {"op": "ARG", "idx": 1},
            {"op": "MUL_Q32"},
            {"op": "CONST", "value_q32": 7},
            {"op": "ADD_I64"},
            {"op": "RET"},
        ],
    }
    out = generate_msl_source(ir)
    assert "kernel void omega_kernel_eval_v1" in out
    assert "q32_mul_exact" in out


def test_generate_msl_source_accepts_legacy_indexed_ir() -> None:
    ir = {
        "schema_version": "polymath_restricted_ir_v1",
        "numeric_mode": "Q32_FIXEDPOINT",
        "constants_q32": [{"name": "C0", "value_i64": 9}],
        "operations": [
            {"op": "ARG", "args": [0]},
            {"op": "ARG", "args": [1]},
            {"op": "MUL_Q32", "args": [0, 1]},
            {"op": "CONST", "args": [0]},
            {"op": "ADD_I64", "args": [2, 3]},
            {"op": "RET", "args": [4]},
        ],
    }
    out = generate_msl_source(ir)
    assert "sat_i64_add" in out


def test_generate_msl_source_rejects_missing_ret() -> None:
    ir = {
        "schema_id": "polymath_restricted_ir_v1",
        "numeric_mode": "Q32",
        "ops": [
            {"op": "ARG", "idx": 0},
            {"op": "ARG", "idx": 1},
            {"op": "MUL_Q32"},
        ],
    }
    with pytest.raises(RuntimeError, match="SCHEMA_FAIL:missing_RET"):
        generate_msl_source(ir)

