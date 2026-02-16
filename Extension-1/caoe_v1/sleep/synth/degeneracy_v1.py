"""Deterministic degeneracy checks for CAOE v1 programs."""

from __future__ import annotations

from typing import Any


def is_all_const(program: dict[str, Any]) -> bool:
    ops = program.get("ops") or []
    if not ops:
        return False
    for op in ops:
        if not isinstance(op, dict) or op.get("op") != "CONST":
            return False
    return True


def depends_on(program: dict[str, Any], required_inputs: set[str]) -> bool:
    ops = program.get("ops") or []
    for op in ops:
        if not isinstance(op, dict):
            continue
        for arg in op.get("args") or []:
            if isinstance(arg, str) and arg in required_inputs:
                return True
    return False


def is_degenerate_phi(program: dict[str, Any]) -> bool:
    return not depends_on(program, {"o_t"})


def is_degenerate_lambda(program: dict[str, Any]) -> bool:
    return not depends_on(program, {"psi_0_value"})
