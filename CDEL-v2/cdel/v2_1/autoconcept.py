"""Autoconcept enumeration for v2.1."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ..v1_7r.canon import CanonError, canon_bytes, sha256_prefixed
from .constants import require_constants
from .opt_ontology import (
    build_active_concepts_from_patches,
    compute_concept_id,
    compute_patch_id,
    evaluate_expr,
    normalize_capacity,
)


OP_ORDER = [
    "feat",
    "lit",
    "call",
    "next_pow2",
    "clamp",
    "min",
    "max",
    "add",
    "sub",
    "mul",
    "floor_div",
    "ceil_div",
]

FEATURE_ORDER = [
    "u_ctx",
    "calls_per_unique_ctx",
    "bytes_per_unique_ctx",
    "sha256_bytes_total",
    "onto_ctx_hash_compute_calls_total",
    "work_cost_base",
]

LITERAL_SET = [0, 1, 2, 3, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096]


@dataclass(frozen=True)
class ExprNode:
    expr: dict[str, Any]
    depth: int
    nodes: int


def _literal_order(constants: dict[str, Any]) -> list[int]:
    cap_max = int(constants.get("CAPACITY_MAX", 0) or 0)
    literals = list(LITERAL_SET)
    if cap_max and cap_max not in literals:
        literals.append(cap_max)
    return literals


def _base_nodes(active_ids: list[str], literals: list[int]) -> list[ExprNode]:
    nodes: list[ExprNode] = []
    for feat in FEATURE_ORDER:
        nodes.append(ExprNode(expr={"op": "feat", "feature": feat}, depth=1, nodes=1))
    for lit in literals:
        nodes.append(ExprNode(expr={"op": "lit", "value": lit}, depth=1, nodes=1))
    if active_ids:
        for cid in active_ids:
            nodes.append(ExprNode(expr={"op": "call", "concept_id": cid}, depth=1, nodes=1))
    return nodes


def _derive_nodes(
    *,
    depth: int,
    max_nodes: int,
    by_depth: dict[int, list[ExprNode]],
    all_nodes: list[ExprNode],
    literals: list[int],
) -> list[ExprNode]:
    derived: list[ExprNode] = []

    # unary ops
    for child in by_depth.get(depth - 1, []):
        nodes = 1 + child.nodes
        if max_nodes and nodes > max_nodes:
            continue
        derived.append(ExprNode(expr={"op": "next_pow2", "args": [child.expr]}, depth=depth, nodes=nodes))

    # clamp op: args [node, lit, lit]
    for child in by_depth.get(depth - 1, []):
        for lo in literals:
            for hi in literals:
                if lo > hi:
                    continue
                nodes = 1 + child.nodes + 1 + 1
                if max_nodes and nodes > max_nodes:
                    continue
                derived.append(
                    ExprNode(
                        expr={
                            "op": "clamp",
                            "args": [child.expr, {"op": "lit", "value": lo}, {"op": "lit", "value": hi}],
                        },
                        depth=depth,
                        nodes=nodes,
                    )
                )

    # binary ops
    binary_ops = ["min", "max", "add", "sub", "mul", "floor_div", "ceil_div"]
    for op in binary_ops:
        for left in all_nodes:
            for right in all_nodes:
                if max(left.depth, right.depth) != depth - 1:
                    continue
                nodes = 1 + left.nodes + right.nodes
                if max_nodes and nodes > max_nodes:
                    continue
                derived.append(ExprNode(expr={"op": op, "args": [left.expr, right.expr]}, depth=depth, nodes=nodes))

    return derived


def _synthetic_features(u: int) -> dict[str, int]:
    u_ctx = int(u)
    denom = u_ctx if u_ctx > 0 else 1
    features = {
        "u_ctx": u_ctx,
        "sha256_calls_total": u_ctx,
        "sha256_bytes_total": 4096 * u_ctx,
        "canon_calls_total": u_ctx,
        "canon_bytes_total": 4096 * u_ctx,
        "onto_ctx_hash_compute_calls_total": 2 * u_ctx,
        "work_cost_base": 1,
    }
    features["calls_per_unique_ctx"] = (features["onto_ctx_hash_compute_calls_total"] + denom - 1) // denom
    features["bytes_per_unique_ctx"] = (features["sha256_bytes_total"] + denom - 1) // denom
    return features


def _prune_invalid(expr: dict[str, Any], *, constants: dict[str, Any], active_concepts: dict[str, Any]) -> bool:
    grid = constants.get("OPT_CONCEPT_SAFETY_U_GRID", [])
    if not isinstance(grid, list):
        return False
    for u in grid:
        if not isinstance(u, int):
            return False
        features = _synthetic_features(int(u))
        try:
            cap_raw = evaluate_expr(expr, features=features, active_concepts=active_concepts)
            normalize_capacity(cap_raw, constants)
        except CanonError:
            return False
    return True


def enumerate_expressions(
    *,
    active_concept_patches: list[dict[str, Any]],
    constants: dict[str, Any] | None = None,
) -> Iterable[dict[str, Any]]:
    if constants is None:
        constants = require_constants()
    max_depth = int(constants.get("OPT_DSL_MAX_DEPTH", 0) or 0)
    max_nodes = int(constants.get("OPT_DSL_MAX_NODES", 0) or 0)

    active_concepts = build_active_concepts_from_patches(active_concept_patches)
    active_ids = list(active_concepts.keys())

    literals = _literal_order(constants)
    by_depth: dict[int, list[ExprNode]] = {}
    all_nodes: list[ExprNode] = []

    base = _base_nodes(active_ids, literals)
    by_depth[1] = base
    all_nodes.extend(base)

    for node in base:
        if _prune_invalid(node.expr, constants=constants, active_concepts=active_concepts):
            yield node.expr

    if max_depth <= 1:
        return

    for depth in range(2, max_depth + 1):
        derived = _derive_nodes(
            depth=depth,
            max_nodes=max_nodes,
            by_depth=by_depth,
            all_nodes=all_nodes,
            literals=literals,
        )
        by_depth[depth] = derived
        all_nodes.extend(derived)
        for node in derived:
            if _prune_invalid(node.expr, constants=constants, active_concepts=active_concepts):
                yield node.expr


def select_candidate_expr(
    *,
    insertion_index: int,
    candidate_rank: int,
    active_concept_patches: list[dict[str, Any]],
    constants: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if constants is None:
        constants = require_constants()
    max_candidates = int(constants.get("OPT_ENUM_MAX_CANDIDATES_PER_INSERTION", 0) or 0)
    target_rank = int(candidate_rank)
    if target_rank < 0:
        raise CanonError("CONCEPT_ENUM_EXHAUSTED")

    for idx, expr in enumerate(
        enumerate_expressions(active_concept_patches=active_concept_patches, constants=constants)
    ):
        if max_candidates and idx >= max_candidates:
            break
        if idx == target_rank:
            return expr
    raise CanonError("CONCEPT_ENUM_EXHAUSTED")


def build_concept(*, expr: dict[str, Any], run_id: str, insertion_index: int, candidate_rank: int) -> dict[str, Any]:
    constants = require_constants()
    concept = {
        "schema": "opt_concept_v1",
        "dsl_version": int(constants.get("OPT_DSL_VERSION", 1) or 1),
        "concept_id": "__SELF__",
        "created_in_run_id": run_id,
        "name": f"autoconcept_{insertion_index:02d}_{candidate_rank:04d}",
        "description": "autoconcept enum v1",
        "output_kind": "ctx_hash_cache_v1_capacity_policy",
        "expr": expr,
    }
    concept["concept_id"] = compute_concept_id(concept)
    return concept


def build_concept_patch(concept: dict[str, Any]) -> dict[str, Any]:
    patch = {
        "schema": "opt_concept_patch_v1",
        "patch_id": "__SELF__",
        "concept": concept,
    }
    patch["patch_id"] = compute_patch_id(concept)
    return patch


def _manifest_head_hash(manifest: dict[str, Any]) -> str:
    payload = dict(manifest)
    payload.pop("manifest_head_hash", None)
    return sha256_prefixed(canon_bytes(payload))


def build_manifest(
    *,
    run_id: str,
    attempt_id: str,
    insertion_index: int,
    candidate_rank: int,
    concept_patch_relpath: str,
    concept_id: str,
    patch_id: str,
) -> dict[str, Any]:
    manifest = {
        "schema": "autoconcept_manifest_v1",
        "run_id": run_id,
        "attempt_id": attempt_id,
        "insertion_index": int(insertion_index),
        "candidate_rank": int(candidate_rank),
        "generated": [
            {
                "concept_patch_relpath": concept_patch_relpath,
                "concept_id": concept_id,
                "patch_id": patch_id,
            }
        ],
        "manifest_head_hash": "__SELF__",
    }
    manifest["manifest_head_hash"] = _manifest_head_hash(manifest)
    return manifest


def write_autoconcept_outputs(
    *,
    run_dir: Path,
    run_id: str,
    attempt_id: str,
    insertion_index: int,
    candidate_rank: int,
    active_concept_patches: list[dict[str, Any]],
) -> dict[str, Any]:
    expr = select_candidate_expr(
        insertion_index=insertion_index,
        candidate_rank=candidate_rank,
        active_concept_patches=active_concept_patches,
    )
    concept = build_concept(
        expr=expr,
        run_id=run_id,
        insertion_index=insertion_index,
        candidate_rank=candidate_rank,
    )
    patch = build_concept_patch(concept)

    concepts_dir = run_dir / "autonomy" / "opt_ontology_v1" / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)
    patch_path = concepts_dir / "concept_patch.json"
    patch_path.write_bytes(canon_bytes(patch) + b"\n")

    relpath = "autonomy/opt_ontology_v1/concepts/concept_patch.json"
    manifest = build_manifest(
        run_id=run_id,
        attempt_id=attempt_id,
        insertion_index=insertion_index,
        candidate_rank=candidate_rank,
        concept_patch_relpath=relpath,
        concept_id=concept.get("concept_id"),
        patch_id=patch.get("patch_id"),
    )
    manifest_path = run_dir / "autonomy" / "opt_ontology_v1" / "autoconcept_manifest_v1.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(canon_bytes(manifest) + b"\n")

    return {
        "concept": concept,
        "patch": patch,
        "manifest": manifest,
    }


__all__ = [
    "enumerate_expressions",
    "select_candidate_expr",
    "write_autoconcept_outputs",
]
