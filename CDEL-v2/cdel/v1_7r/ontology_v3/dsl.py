"""Ontology DSL v3 interpreter + validation."""

from __future__ import annotations

import hashlib
from typing import Any

from ..canon import CanonError, canon_bytes
from .bucket import validate_bucketer_spec
from .io import verify_ontology_def_ids


INT32_MIN = -(2**31)
INT32_MAX = 2**31 - 1

ALLOWED_OUTPUT_TYPES = {"bool", "i32"}


def _wrap_i32(value: int) -> int:
    value = int(value) & 0xFFFFFFFF
    if value >= 2**31:
        value -= 2**32
    return value


def _as_i32(value: Any) -> int:
    if isinstance(value, bool):
        raise CanonError("expected i32, got bool")
    if not isinstance(value, int):
        raise CanonError("expected i32")
    return _wrap_i32(value)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    raise CanonError("expected bool")


def _hash_u32(value: int) -> int:
    raw = _wrap_i32(value)
    u32 = raw & 0xFFFFFFFF
    data = int(u32).to_bytes(4, byteorder="little", signed=False)
    digest = hashlib.sha256(data).digest()
    out = int.from_bytes(digest[:4], byteorder="little", signed=False)
    return _wrap_i32(out)


def _get_path(root: Any, path: list[Any]) -> Any:
    current = root
    for key in path:
        if isinstance(current, dict) and isinstance(key, str):
            if key not in current:
                raise CanonError("get path missing")
            current = current[key]
            continue
        if isinstance(current, list) and isinstance(key, int):
            if key < 0 or key >= len(current):
                raise CanonError("get path index out of bounds")
            current = current[key]
            continue
        raise CanonError("get path type mismatch")
    return current


def count_nodes(expr: Any) -> int:
    if not isinstance(expr, dict):
        raise CanonError("expr must be object")
    op = expr.get("op")
    if not isinstance(op, str):
        raise CanonError("expr op missing")
    args = expr.get("args")
    if args is None:
        args = []
    if not isinstance(args, list):
        raise CanonError("expr args must be list")
    total = 1
    for arg in args:
        total += count_nodes(arg)
    return total


def _validate_expr(expr: Any) -> None:
    if not isinstance(expr, dict):
        raise CanonError("expr must be object")
    op = expr.get("op")
    if not isinstance(op, str):
        raise CanonError("expr op missing")
    args = expr.get("args")
    if args is None:
        args = []
    if not isinstance(args, list):
        raise CanonError("expr args must be list")

    def _require_args(n: int) -> None:
        if len(args) != n:
            raise CanonError(f"expr op {op} expects {n} args")
        for arg in args:
            _validate_expr(arg)

    if op == "const_i32":
        if "value" not in expr or not isinstance(expr.get("value"), int):
            raise CanonError("const_i32 missing value")
        if args:
            raise CanonError("const_i32 args must be empty")
        return
    if op == "const_bool":
        if "value" not in expr or not isinstance(expr.get("value"), bool):
            raise CanonError("const_bool missing value")
        if args:
            raise CanonError("const_bool args must be empty")
        return
    if op == "get":
        path = expr.get("path")
        if not isinstance(path, list) or not all(isinstance(p, (str, int)) for p in path):
            raise CanonError("get path invalid")
        if args:
            raise CanonError("get args must be empty")
        return
    if op in {"add", "sub", "mul", "eq", "lt", "gt", "and", "or"}:
        _require_args(2)
        return
    if op in {"not", "abs_i32"}:
        _require_args(1)
        return
    if op == "select":
        _require_args(3)
        return
    if op == "clamp_i32":
        lo = expr.get("lo")
        hi = expr.get("hi")
        if not isinstance(lo, int) or not isinstance(hi, int):
            raise CanonError("clamp_i32 missing bounds")
        _require_args(1)
        return
    if op == "hash_u32":
        _require_args(1)
        return
    raise CanonError(f"unknown op: {op}")


def eval_expr(expr: dict[str, Any], z_core: dict[str, Any]) -> Any:
    op = expr.get("op")
    args = expr.get("args") or []
    if op == "const_i32":
        return _wrap_i32(expr.get("value"))
    if op == "const_bool":
        return bool(expr.get("value"))
    if op == "get":
        return _get_path(z_core, expr.get("path") or [])
    if op == "add":
        return _wrap_i32(_as_i32(eval_expr(args[0], z_core)) + _as_i32(eval_expr(args[1], z_core)))
    if op == "sub":
        return _wrap_i32(_as_i32(eval_expr(args[0], z_core)) - _as_i32(eval_expr(args[1], z_core)))
    if op == "mul":
        return _wrap_i32(_as_i32(eval_expr(args[0], z_core)) * _as_i32(eval_expr(args[1], z_core)))
    if op == "eq":
        left = eval_expr(args[0], z_core)
        right = eval_expr(args[1], z_core)
        return left == right
    if op == "lt":
        return _as_i32(eval_expr(args[0], z_core)) < _as_i32(eval_expr(args[1], z_core))
    if op == "gt":
        return _as_i32(eval_expr(args[0], z_core)) > _as_i32(eval_expr(args[1], z_core))
    if op == "and":
        return _as_bool(eval_expr(args[0], z_core)) and _as_bool(eval_expr(args[1], z_core))
    if op == "or":
        return _as_bool(eval_expr(args[0], z_core)) or _as_bool(eval_expr(args[1], z_core))
    if op == "not":
        return not _as_bool(eval_expr(args[0], z_core))
    if op == "select":
        cond = _as_bool(eval_expr(args[0], z_core))
        then_val = eval_expr(args[1], z_core)
        else_val = eval_expr(args[2], z_core)
        if type(then_val) is not type(else_val):
            raise CanonError("select branch type mismatch")
        return then_val if cond else else_val
    if op == "clamp_i32":
        val = _as_i32(eval_expr(args[0], z_core))
        lo = int(expr.get("lo"))
        hi = int(expr.get("hi"))
        if lo > hi:
            raise CanonError("clamp_i32 invalid bounds")
        return _wrap_i32(min(max(val, lo), hi))
    if op == "hash_u32":
        return _hash_u32(_as_i32(eval_expr(args[0], z_core)))
    if op == "abs_i32":
        val = _as_i32(eval_expr(args[0], z_core))
        return _wrap_i32(abs(val))
    raise CanonError(f"unknown op: {op}")


def validate_ontology_def(ontology_def: dict[str, Any], *, constants: dict[str, Any]) -> None:
    if ontology_def.get("schema") != "ontology_def_v3":
        raise CanonError("ontology_def schema mismatch")
    if int(ontology_def.get("schema_version", 0)) != 3:
        raise CanonError("ontology_def schema_version mismatch")
    if int(ontology_def.get("dsl_version", 0)) != 3:
        raise CanonError("ontology_def dsl_version mismatch")

    concepts = ontology_def.get("concepts")
    if not isinstance(concepts, list):
        raise CanonError("ontology_def concepts missing")

    max_concepts = int(constants.get("ONTO_V3_MAX_CONCEPTS", 0) or 0)
    if max_concepts and len(concepts) > max_concepts:
        raise CanonError("ontology_def exceeds ONTO_V3_MAX_CONCEPTS")

    context_kernel = ontology_def.get("context_kernel")
    if not isinstance(context_kernel, dict):
        raise CanonError("context_kernel missing")
    if context_kernel.get("schema") != "onto_context_kernel_spec_v1":
        raise CanonError("context_kernel schema mismatch")
    if int(context_kernel.get("schema_version", 0)) != 1:
        raise CanonError("context_kernel schema_version mismatch")
    max_arity = context_kernel.get("max_arity")
    if not isinstance(max_arity, int) or max_arity < 0:
        raise CanonError("context_kernel max_arity invalid")
    max_allowed = int(constants.get("ONTO_V3_MAX_CTX_ARITY", 0) or 0)
    if max_allowed and max_arity > max_allowed:
        raise CanonError("context_kernel max_arity exceeds ONTO_V3_MAX_CTX_ARITY")

    training = ontology_def.get("training")
    if not isinstance(training, dict):
        raise CanonError("training missing")
    if training.get("schema") != "onto_training_spec_v1":
        raise CanonError("training schema mismatch")
    if int(training.get("schema_version", 0)) != 1:
        raise CanonError("training schema_version mismatch")
    if training.get("method") != "greedy_forward_select_v1":
        raise CanonError("training method mismatch")
    stop_gain = training.get("stop_if_gain_bits_lt")
    if not isinstance(stop_gain, int) or stop_gain < 0:
        raise CanonError("training stop_if_gain_bits_lt invalid")
    expected_stop = int(constants.get("ONTO_V3_TRAIN_STOP_GAIN_BITS_LT", 0) or 0)
    if expected_stop and stop_gain != expected_stop:
        raise CanonError("training stop_if_gain_bits_lt mismatch")

    for concept in concepts:
        if not isinstance(concept, dict):
            raise CanonError("ontology_def concept must be object")
        output_type = concept.get("output_type")
        if output_type not in ALLOWED_OUTPUT_TYPES:
            raise CanonError("ontology_def concept output_type invalid")
        expr = concept.get("expr")
        _validate_expr(expr)
        bucketer = concept.get("bucketer")
        validate_bucketer_spec(bucketer, output_type)

    verify_ontology_def_ids(ontology_def)

    if len(canon_bytes(ontology_def)) <= 0:
        raise CanonError("ontology_def invalid bytes")
