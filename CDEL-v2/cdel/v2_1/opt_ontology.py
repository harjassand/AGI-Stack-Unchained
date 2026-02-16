"""Optimization ontology DSL evaluation and safety checks for v2.1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from ..v1_7r.canon import CanonError, canon_bytes, sha256_prefixed


MAX_U64 = (1 << 64) - 1


@dataclass(frozen=True)
class ConceptRef:
    concept_id: str
    expr: dict[str, Any]


def _checked_add(a: int, b: int) -> int:
    if a > MAX_U64 - b:
        raise CanonError("CONCEPT_OUTPUT_INVALID")
    return a + b


def _checked_sub(a: int, b: int) -> int:
    if a < b:
        raise CanonError("CONCEPT_OUTPUT_INVALID")
    return a - b


def _checked_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    if a > MAX_U64 // b:
        raise CanonError("CONCEPT_OUTPUT_INVALID")
    return a * b


def _checked_floor_div(a: int, b: int) -> int:
    if b == 0:
        raise CanonError("CONCEPT_OUTPUT_INVALID")
    return a // b


def _checked_ceil_div(a: int, b: int) -> int:
    if b == 0:
        raise CanonError("CONCEPT_OUTPUT_INVALID")
    if a > MAX_U64 - (b - 1):
        raise CanonError("CONCEPT_OUTPUT_INVALID")
    return (a + b - 1) // b


def _next_pow2(x: int) -> int:
    if x <= 1:
        return 1
    value = 1
    while value < x:
        if value > MAX_U64 // 2:
            raise CanonError("CONCEPT_OUTPUT_INVALID")
        value <<= 1
    return value


def _highest_pow2_leq(x: int) -> int:
    if x <= 1:
        return 1
    value = 1
    while value <= x // 2:
        value <<= 1
    return value


def _clamp(x: int, lo: int, hi: int) -> int:
    if lo > hi:
        raise CanonError("CONCEPT_OUTPUT_INVALID")
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def _ensure_int(value: Any) -> int:
    if not isinstance(value, int):
        raise CanonError("CONCEPT_OUTPUT_INVALID")
    if value < 0:
        raise CanonError("CONCEPT_OUTPUT_INVALID")
    return int(value)


def _node_count(node: dict[str, Any]) -> int:
    op = node.get("op")
    if op in {"lit", "feat", "call"}:
        return 1
    args = node.get("args", [])
    if not isinstance(args, list):
        raise CanonError("CONCEPT_OUTPUT_INVALID")
    return 1 + sum(_node_count(arg) for arg in args if isinstance(arg, dict))


def _node_depth(node: dict[str, Any]) -> int:
    op = node.get("op")
    if op in {"lit", "feat", "call"}:
        return 1
    args = node.get("args", [])
    if not isinstance(args, list) or not args:
        raise CanonError("CONCEPT_OUTPUT_INVALID")
    return 1 + max(_node_depth(arg) for arg in args if isinstance(arg, dict))


def _collect_calls(node: dict[str, Any], out: set[str]) -> None:
    op = node.get("op")
    if op == "call":
        cid = node.get("concept_id")
        if isinstance(cid, str):
            out.add(cid)
        return
    args = node.get("args")
    if isinstance(args, list):
        for arg in args:
            if isinstance(arg, dict):
                _collect_calls(arg, out)


def concept_uses_call(expr: dict[str, Any]) -> bool:
    calls: set[str] = set()
    _collect_calls(expr, calls)
    return bool(calls)


def compute_concept_id(concept: dict[str, Any]) -> str:
    payload = dict(concept)
    payload.pop("concept_id", None)
    return sha256_prefixed(canon_bytes(payload))


def compute_patch_id(concept: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(concept))


def validate_concept_ids(concept: dict[str, Any]) -> None:
    expected = compute_concept_id(concept)
    if concept.get("concept_id") != expected:
        raise CanonError("CANON_HASH_MISMATCH")


def validate_patch_id(patch: dict[str, Any]) -> None:
    concept = patch.get("concept") if isinstance(patch.get("concept"), dict) else None
    if not isinstance(concept, dict):
        raise CanonError("SCHEMA_INVALID")
    expected = compute_patch_id(concept)
    if patch.get("patch_id") != expected:
        raise CanonError("CANON_HASH_MISMATCH")


def normalize_capacity(cap_raw: int, constants: dict[str, Any]) -> int:
    cap_min = int(constants.get("CAPACITY_MIN", 1) or 1)
    cap_max = int(constants.get("CAPACITY_MAX", 0) or 0)
    if cap_max <= 0:
        raise CanonError("CONCEPT_OUTPUT_INVALID")
    cap = _clamp(int(cap_raw), cap_min, cap_max)
    if bool(constants.get("CAPACITY_REQUIRE_POWER_OF_TWO", False)):
        cap = _highest_pow2_leq(cap)
    if cap < 1:
        cap = 1
    return int(cap)


def _eval_node(
    node: dict[str, Any],
    *,
    features: dict[str, int],
    active_concepts: dict[str, ConceptRef],
    stack: set[str],
) -> int:
    op = node.get("op")
    if op == "lit":
        return _ensure_int(node.get("value"))
    if op == "feat":
        key = node.get("feature")
        if key not in features:
            raise CanonError("CONCEPT_OUTPUT_INVALID")
        return _ensure_int(features.get(key))
    if op == "call":
        cid = node.get("concept_id")
        if not isinstance(cid, str):
            raise CanonError("CONCEPT_CALL_UNKNOWN")
        if cid not in active_concepts:
            raise CanonError("CONCEPT_CALL_UNKNOWN")
        if cid in stack:
            raise CanonError("CONCEPT_GRAPH_CYCLE")
        stack.add(cid)
        try:
            return _eval_node(active_concepts[cid].expr, features=features, active_concepts=active_concepts, stack=stack)
        finally:
            stack.remove(cid)
    args = node.get("args")
    if not isinstance(args, list):
        raise CanonError("CONCEPT_OUTPUT_INVALID")

    if op == "next_pow2":
        if len(args) != 1:
            raise CanonError("CONCEPT_OUTPUT_INVALID")
        value = _eval_node(args[0], features=features, active_concepts=active_concepts, stack=stack)
        return _next_pow2(value)
    if op == "clamp":
        if len(args) != 3:
            raise CanonError("CONCEPT_OUTPUT_INVALID")
        value = _eval_node(args[0], features=features, active_concepts=active_concepts, stack=stack)
        lo = _eval_node(args[1], features=features, active_concepts=active_concepts, stack=stack)
        hi = _eval_node(args[2], features=features, active_concepts=active_concepts, stack=stack)
        return _clamp(value, lo, hi)

    if len(args) != 2:
        raise CanonError("CONCEPT_OUTPUT_INVALID")
    left = _eval_node(args[0], features=features, active_concepts=active_concepts, stack=stack)
    right = _eval_node(args[1], features=features, active_concepts=active_concepts, stack=stack)

    if op == "add":
        return _checked_add(left, right)
    if op == "sub":
        return _checked_sub(left, right)
    if op == "mul":
        return _checked_mul(left, right)
    if op == "min":
        return min(left, right)
    if op == "max":
        return max(left, right)
    if op == "floor_div":
        return _checked_floor_div(left, right)
    if op == "ceil_div":
        return _checked_ceil_div(left, right)

    raise CanonError("CONCEPT_OUTPUT_INVALID")


def evaluate_expr(
    expr: dict[str, Any],
    *,
    features: dict[str, int],
    active_concepts: dict[str, ConceptRef],
) -> int:
    return _eval_node(expr, features=features, active_concepts=active_concepts, stack=set())


def validate_shape(expr: dict[str, Any], constants: dict[str, Any]) -> None:
    max_nodes = int(constants.get("OPT_DSL_MAX_NODES", 0) or 0)
    max_depth = int(constants.get("OPT_DSL_MAX_DEPTH", 0) or 0)
    if max_nodes and _node_count(expr) > max_nodes:
        raise CanonError("CONCEPT_OUTPUT_INVALID")
    if max_depth and _node_depth(expr) > max_depth:
        raise CanonError("CONCEPT_OUTPUT_INVALID")


def validate_call_order(expr: dict[str, Any], active_set_ids: list[str], caller_index: int | None = None) -> None:
    calls: set[str] = set()
    _collect_calls(expr, calls)
    if not calls:
        return
    active_index = {cid: idx for idx, cid in enumerate(active_set_ids)}
    for cid in calls:
        if cid not in active_index:
            raise CanonError("CONCEPT_CALL_UNKNOWN")
        if caller_index is not None and active_index[cid] >= caller_index:
            raise CanonError("CONCEPT_GRAPH_CYCLE")


def safety_check_concept(
    concept: dict[str, Any],
    *,
    constants: dict[str, Any],
    active_concepts: dict[str, ConceptRef],
    active_set_ids: list[str],
) -> None:
    expr = concept.get("expr") if isinstance(concept.get("expr"), dict) else None
    if not isinstance(expr, dict):
        raise CanonError("SCHEMA_INVALID")
    validate_shape(expr, constants)
    validate_call_order(expr, active_set_ids, caller_index=len(active_set_ids))

    grid = constants.get("OPT_CONCEPT_SAFETY_U_GRID", [])
    if not isinstance(grid, list) or not grid:
        raise CanonError("CONCEPT_OUTPUT_INVALID")

    prev_cap = None
    for u in grid:
        if not isinstance(u, int):
            raise CanonError("CONCEPT_OUTPUT_INVALID")
        u_ctx = int(u)
        features = {
            "u_ctx": u_ctx,
            "sha256_calls_total": u_ctx,
            "sha256_bytes_total": 4096 * u_ctx,
            "canon_calls_total": u_ctx,
            "canon_bytes_total": 4096 * u_ctx,
            "onto_ctx_hash_compute_calls_total": 2 * u_ctx,
            "work_cost_base": 1,
        }
        # derived features
        denom = u_ctx if u_ctx > 0 else 1
        features["calls_per_unique_ctx"] = _checked_ceil_div(features["onto_ctx_hash_compute_calls_total"], denom)
        features["bytes_per_unique_ctx"] = _checked_ceil_div(features["sha256_bytes_total"], denom)

        cap_raw = evaluate_expr(expr, features=features, active_concepts=active_concepts)
        cap_norm = normalize_capacity(cap_raw, constants)

        if cap_norm < int(constants.get("CAPACITY_MIN", 1) or 1):
            raise CanonError("CONCEPT_SAFETY_FAIL")
        if cap_norm > int(constants.get("CAPACITY_MAX", 0) or 0):
            raise CanonError("CONCEPT_SAFETY_FAIL")
        if bool(constants.get("CAPACITY_REQUIRE_POWER_OF_TWO", False)):
            if cap_norm & (cap_norm - 1) != 0:
                raise CanonError("CONCEPT_SAFETY_FAIL")

        if prev_cap is not None and cap_norm < prev_cap:
            raise CanonError("CONCEPT_SAFETY_FAIL")
        prev_cap = cap_norm


def _ctx_key(case: dict[str, Any]) -> tuple[Any, ...]:
    ctx_mode = case.get("ctx_mode")
    if ctx_mode == "null":
        return ("NULL_V1",)
    if ctx_mode == "explicit":
        ontology_id = case.get("active_ontology_id")
        snapshot_id = case.get("active_snapshot_id")
        values = case.get("values")
        values_tuple = tuple(values) if isinstance(values, list) else tuple()
        return ("KEY_V1", ontology_id, snapshot_id, values_tuple)
    raise CanonError("translation inputs ctx_mode invalid")


def unique_ctx_count(translation_inputs: dict[str, Any]) -> int:
    cases = translation_inputs.get("cases", [])
    if not isinstance(cases, list):
        raise CanonError("translation inputs cases missing")
    keys = set()
    for case in cases:
        if isinstance(case, dict):
            keys.add(_ctx_key(case))
    return len(keys)


def feature_map_from_report(
    report: dict[str, Any],
    *,
    translation_inputs: dict[str, Any],
) -> dict[str, int]:
    workvec = report.get("workvec_base") if isinstance(report.get("workvec_base"), dict) else None
    if not isinstance(workvec, dict):
        raise CanonError("MISSING_ARTIFACT")

    u_ctx = unique_ctx_count(translation_inputs)
    features = {
        "u_ctx": int(u_ctx),
        "sha256_calls_total": _ensure_int(workvec.get("sha256_calls_total")),
        "sha256_bytes_total": _ensure_int(workvec.get("sha256_bytes_total")),
        "canon_calls_total": _ensure_int(workvec.get("canon_calls_total")),
        "canon_bytes_total": _ensure_int(workvec.get("canon_bytes_total")),
        "onto_ctx_hash_compute_calls_total": _ensure_int(workvec.get("onto_ctx_hash_compute_calls_total")),
        "work_cost_base": _ensure_int(report.get("work_cost_base")),
    }
    denom = u_ctx if u_ctx > 0 else 1
    features["calls_per_unique_ctx"] = _checked_ceil_div(features["onto_ctx_hash_compute_calls_total"], denom)
    features["bytes_per_unique_ctx"] = _checked_ceil_div(features["sha256_bytes_total"], denom)
    return features


def build_active_concepts_from_patches(patches: list[dict[str, Any]]) -> dict[str, ConceptRef]:
    out: dict[str, ConceptRef] = {}
    for patch in patches:
        concept = patch.get("concept") if isinstance(patch, dict) else None
        if isinstance(concept, dict) and isinstance(concept.get("concept_id"), str):
            out[str(concept.get("concept_id"))] = ConceptRef(
                concept_id=str(concept.get("concept_id")), expr=concept.get("expr")
            )
    return out


def active_set_ids_from_patches(patches: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for patch in patches:
        concept = patch.get("concept") if isinstance(patch, dict) else None
        if isinstance(concept, dict) and isinstance(concept.get("concept_id"), str):
            ids.append(str(concept.get("concept_id")))
    return ids


__all__ = [
    "ConceptRef",
    "active_set_ids_from_patches",
    "build_active_concepts_from_patches",
    "compute_concept_id",
    "compute_patch_id",
    "concept_uses_call",
    "evaluate_expr",
    "feature_map_from_report",
    "normalize_capacity",
    "safety_check_concept",
    "unique_ctx_count",
    "validate_call_order",
    "validate_concept_ids",
    "validate_patch_id",
    "validate_shape",
]
