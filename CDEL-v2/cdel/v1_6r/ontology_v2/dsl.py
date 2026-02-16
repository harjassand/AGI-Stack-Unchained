"""Ontology DSL v2 interpreter + validation."""

from __future__ import annotations

import hashlib
from typing import Any

from ..canon import CanonError, canon_bytes
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
    if op == "not":
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
    raise CanonError(f"unknown op: {op}")


def validate_ontology_def(ontology_def: dict[str, Any], *, constants: dict[str, Any]) -> dict[str, int]:
    if ontology_def.get("schema") != "ontology_def_v2":
        raise CanonError("ontology_def schema mismatch")
    if int(ontology_def.get("schema_version", 0)) != 2:
        raise CanonError("ontology_def schema_version mismatch")
    if int(ontology_def.get("dsl_version", 0)) != 2:
        raise CanonError("ontology_def dsl_version mismatch")
    stateful = ontology_def.get("stateful")
    if stateful not in (False, None):
        raise CanonError("stateful ontology not supported")
    concepts = ontology_def.get("concepts")
    if not isinstance(concepts, list):
        raise CanonError("ontology_def concepts missing")

    limits = constants.get("ontology", {})
    max_concepts = int(limits.get("ONTO_MAX_CONCEPTS", 0) or 0)
    if max_concepts and len(concepts) > max_concepts:
        raise CanonError("ontology_def exceeds ONTO_MAX_CONCEPTS")

    max_nodes_per_concept = int(limits.get("ONTO_MAX_NODES_PER_CONCEPT", 0) or 0)
    max_nodes_per_step = int(limits.get("ONTO_MAX_NODES_PER_STEP", 0) or 0)
    max_def_bytes = int(limits.get("ONTO_MAX_DEF_BYTES", 0) or 0)

    if max_def_bytes and len(canon_bytes(ontology_def)) > max_def_bytes:
        raise CanonError("ontology_def exceeds ONTO_MAX_DEF_BYTES")

    total_nodes = 0
    concept_nodes: dict[str, int] = {}
    for concept in concepts:
        if not isinstance(concept, dict):
            raise CanonError("ontology_def concept must be object")
        if concept.get("output_type") not in ALLOWED_OUTPUT_TYPES:
            raise CanonError("ontology_def concept output_type invalid")
        expr = concept.get("expr")
        _validate_expr(expr)
        nodes = count_nodes(expr)
        if max_nodes_per_concept and nodes > max_nodes_per_concept:
            raise CanonError("ontology_def concept exceeds ONTO_MAX_NODES_PER_CONCEPT")
        total_nodes += nodes
        concept_nodes[str(concept.get("concept_name", ""))] = nodes

    if max_nodes_per_step and total_nodes > max_nodes_per_step:
        raise CanonError("ontology_def exceeds ONTO_MAX_NODES_PER_STEP")

    verify_ontology_def_ids(ontology_def)
    return concept_nodes


def evaluate_ontology(ontology_def: dict[str, Any], z_core: dict[str, Any]) -> list[int]:
    concepts = ontology_def.get("concepts")
    if not isinstance(concepts, list):
        raise CanonError("ontology_def concepts missing")
    values: list[int] = []
    for concept in concepts:
        if not isinstance(concept, dict):
            raise CanonError("ontology_def concept invalid")
        output_type = concept.get("output_type")
        expr = concept.get("expr")
        val = eval_expr(expr, z_core)
        if output_type == "bool":
            if not isinstance(val, bool):
                raise CanonError("ontology concept expected bool")
            values.append(1 if val else 0)
        elif output_type == "i32":
            if isinstance(val, bool) or not isinstance(val, int):
                raise CanonError("ontology concept expected i32")
            values.append(_wrap_i32(val))
        else:
            raise CanonError("ontology concept output_type invalid")
    return values
