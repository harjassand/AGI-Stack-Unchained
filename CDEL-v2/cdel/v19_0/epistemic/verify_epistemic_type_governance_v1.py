"""Verifier for epistemic type-governance artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..common_v1 import canon_hash_obj, ensure_sha256, fail, validate_schema, verify_object_id
from .type_registry_v1 import build_type_binding, is_legacy_registry, validate_type_registry


def _load_hashed(path: Path, *, schema_name: str, id_field: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        fail("SCHEMA_FAIL")
    if canon_hash_obj(payload) != "sha256:" + path.name.split(".", 1)[0].split("_", 1)[1]:
        fail("NONDETERMINISTIC")
    validate_schema(payload, schema_name)
    verify_object_id(payload, id_field=id_field)
    return payload


def verify_type_binding(
    *,
    binding: dict[str, Any],
    graph: dict[str, Any],
    type_registry: dict[str, Any],
    provisionals: list[dict[str, Any]] | None = None,
    ratifications: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    validate_schema(binding, "epistemic_type_binding_v1")
    binding_id = verify_object_id(binding, id_field="binding_id")
    validate_schema(graph, "qxwmr_graph_v1")
    graph_id = ensure_sha256(graph.get("graph_id"), reason="SCHEMA_FAIL")
    registry = validate_type_registry(type_registry)
    registry_id = ensure_sha256(registry.get("registry_id"), reason="SCHEMA_FAIL")

    if ensure_sha256(binding.get("graph_id"), reason="SCHEMA_FAIL") != graph_id:
        fail("NONDETERMINISTIC")
    if ensure_sha256(binding.get("type_registry_id"), reason="SCHEMA_FAIL") != registry_id:
        fail("NONDETERMINISTIC")

    recomputed = build_type_binding(
        graph=graph,
        type_registry=registry,
        provisionals=provisionals,
        ratifications=ratifications,
    )
    if canon_hash_obj(recomputed) != canon_hash_obj(binding):
        fail("NONDETERMINISTIC")

    return {
        "status": "VALID",
        "binding_id": binding_id,
        "graph_id": graph_id,
        "type_registry_id": registry_id,
        "outcome": str(binding.get("outcome", "")),
        "legacy_registry_b": bool(is_legacy_registry(registry)),
    }


def verify_type_governance_state(state_root: Path) -> dict[str, Any]:
    epi_root = state_root / "epistemic"
    binding_paths = sorted((epi_root / "type_bindings").glob("sha256_*.epistemic_type_binding_v1.json"), key=lambda p: p.as_posix())
    registry_paths = sorted((epi_root / "type_registry").glob("sha256_*.epistemic_type_registry_v1.json"), key=lambda p: p.as_posix())
    graph_paths = sorted((epi_root / "graphs").glob("sha256_*.qxwmr_graph_v1.json"), key=lambda p: p.as_posix())
    if len(binding_paths) != 1 or len(registry_paths) != 1 or len(graph_paths) != 1:
        fail("MISSING_STATE_INPUT")

    binding = _load_hashed(binding_paths[0], schema_name="epistemic_type_binding_v1", id_field="binding_id")
    registry = _load_hashed(registry_paths[0], schema_name="epistemic_type_registry_v1", id_field="registry_id")
    graph = _load_hashed(graph_paths[0], schema_name="qxwmr_graph_v1", id_field="graph_id")

    provisional_paths = sorted(
        (epi_root / "type" / "provisionals").glob("sha256_*.epistemic_type_provisional_v1.json"),
        key=lambda p: p.as_posix(),
    )
    ratification_paths = sorted(
        (epi_root / "type" / "ratifications").glob("sha256_*.epistemic_type_ratification_receipt_v1.json"),
        key=lambda p: p.as_posix(),
    )
    provisionals = [
        _load_hashed(path, schema_name="epistemic_type_provisional_v1", id_field="provisional_id")
        for path in provisional_paths
    ]
    ratifications = [
        _load_hashed(path, schema_name="epistemic_type_ratification_receipt_v1", id_field="receipt_id")
        for path in ratification_paths
    ]
    return verify_type_binding(
        binding=binding,
        graph=graph,
        type_registry=registry,
        provisionals=provisionals,
        ratifications=ratifications,
    )


__all__ = [
    "verify_type_binding",
    "verify_type_governance_state",
]
