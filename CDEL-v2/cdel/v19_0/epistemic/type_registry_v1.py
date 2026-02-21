"""Deterministic epistemic type-governance helpers (R4)."""

from __future__ import annotations

from typing import Any

from ..common_v1 import canon_hash_obj, ensure_sha256, fail, validate_schema, verify_object_id


def _sorted_unique(values: list[str]) -> list[str]:
    return sorted({str(row) for row in values})


def collect_graph_type_ids(graph: dict[str, Any]) -> list[str]:
    validate_schema(graph, "qxwmr_graph_v1")
    out: list[str] = []
    for key in ("nodes", "edges"):
        rows = graph.get(key)
        if not isinstance(rows, list):
            fail("SCHEMA_FAIL")
        for row in rows:
            if not isinstance(row, dict):
                fail("SCHEMA_FAIL")
            type_id = str(row.get("type_id", "")).strip()
            if not type_id:
                fail("SCHEMA_FAIL")
            out.append(type_id)
    return _sorted_unique(out)


def validate_type_registry(registry: dict[str, Any]) -> dict[str, Any]:
    validate_schema(registry, "epistemic_type_registry_v1")
    verify_object_id(registry, id_field="registry_id")
    prefix = str(registry.get("provisional_namespace_prefix", ""))
    if not prefix.endswith("/"):
        fail("SCHEMA_FAIL")
    allowed_raw = registry.get("allowed_type_ids")
    if not isinstance(allowed_raw, list):
        fail("SCHEMA_FAIL")
    allowed = [str(row).strip() for row in allowed_raw]
    if not allowed or any(not row for row in allowed):
        fail("SCHEMA_FAIL")
    if len(set(allowed)) != len(allowed):
        fail("SCHEMA_FAIL")
    type_definitions_raw = registry.get("type_definitions")
    if type_definitions_raw is not None:
        if not isinstance(type_definitions_raw, dict) or not type_definitions_raw:
            fail("SCHEMA_FAIL")
        for type_id, type_def_hash in type_definitions_raw.items():
            if not isinstance(type_id, str) or not type_id:
                fail("SCHEMA_FAIL")
            _ = ensure_sha256(type_def_hash, reason="SCHEMA_FAIL")
    evolution_rule = registry.get("evolution_rule")
    if evolution_rule is not None and str(evolution_rule) != "APPEND_ONLY":
        fail("SCHEMA_FAIL")
    legacy_b = is_legacy_registry(registry)
    if not legacy_b:
        if str(registry.get("evolution_rule", "")) != "APPEND_ONLY":
            fail("SCHEMA_FAIL")
        if not isinstance(type_definitions_raw, dict):
            fail("SCHEMA_FAIL")
        for type_id in allowed:
            if str(type_id) not in type_definitions_raw:
                fail("SCHEMA_FAIL")
    return dict(registry)


def is_legacy_registry(registry: dict[str, Any]) -> bool:
    return any(
        key not in registry
        for key in (
            "registry_epoch_u64",
            "parent_registry_id",
            "evolution_rule",
            "type_definitions",
        )
    )


def _type_definitions(registry: dict[str, Any]) -> dict[str, str]:
    raw = registry.get("type_definitions")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in raw.items():
        out[str(key)] = ensure_sha256(value, reason="SCHEMA_FAIL")
    return out


def validate_registry_transition(*, parent: dict[str, Any], child: dict[str, Any]) -> dict[str, bool]:
    parent_norm = validate_type_registry(parent)
    child_norm = validate_type_registry(child)
    legacy_registry_b = is_legacy_registry(parent_norm) or is_legacy_registry(child_norm)

    parent_allowed = {str(row) for row in list(parent_norm.get("allowed_type_ids") or [])}
    child_allowed = {str(row) for row in list(child_norm.get("allowed_type_ids") or [])}
    if not parent_allowed.issubset(child_allowed):
        fail("TYPE_GOVERNANCE_FAIL")

    parent_defs = _type_definitions(parent_norm)
    child_defs = _type_definitions(child_norm)
    for type_id in sorted(parent_allowed):
        if type_id in parent_defs and type_id in child_defs:
            if parent_defs[type_id] != child_defs[type_id]:
                fail("TYPE_GOVERNANCE_FAIL")

    if not legacy_registry_b:
        if str(child_norm.get("evolution_rule")) != "APPEND_ONLY":
            fail("TYPE_GOVERNANCE_FAIL")
        parent_epoch = int(parent_norm.get("registry_epoch_u64", -1))
        child_epoch = int(child_norm.get("registry_epoch_u64", -1))
        if child_epoch != parent_epoch + 1:
            fail("TYPE_GOVERNANCE_FAIL")
        if ensure_sha256(child_norm.get("parent_registry_id"), reason="SCHEMA_FAIL") != ensure_sha256(
            parent_norm.get("registry_id"),
            reason="SCHEMA_FAIL",
        ):
            fail("TYPE_GOVERNANCE_FAIL")
        for type_id in sorted(parent_allowed):
            if type_id not in parent_defs or type_id not in child_defs:
                fail("TYPE_GOVERNANCE_FAIL")
            if parent_defs.get(type_id) != child_defs.get(type_id):
                fail("TYPE_GOVERNANCE_FAIL")

    return {"legacy_registry_b": bool(legacy_registry_b)}


def _validate_provisional_rows(
    *,
    graph_id: str,
    prefix: str,
    provisionals: list[dict[str, Any]] | None,
) -> tuple[dict[str, str], list[str]]:
    by_type: dict[str, str] = {}
    refs: list[str] = []
    for row in list(provisionals or []):
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        validate_schema(row, "epistemic_type_provisional_v1")
        provisional_id = verify_object_id(row, id_field="provisional_id")
        if ensure_sha256(row.get("graph_id"), reason="SCHEMA_FAIL") != graph_id:
            fail("NONDETERMINISTIC")
        type_id = str(row.get("type_id", "")).strip()
        if not type_id.startswith(prefix):
            fail("SCHEMA_FAIL")
        by_type[type_id] = provisional_id
        refs.append(provisional_id)
    return by_type, _sorted_unique(refs)


def _validate_ratification_rows(
    *,
    registry_id: str,
    ratifications: list[dict[str, Any]] | None,
) -> tuple[set[str], list[str]]:
    ratified_types: set[str] = set()
    refs: list[str] = []
    for row in list(ratifications or []):
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        validate_schema(row, "epistemic_type_ratification_receipt_v1")
        receipt_id = verify_object_id(row, id_field="receipt_id")
        if ensure_sha256(row.get("type_registry_id"), reason="SCHEMA_FAIL") != registry_id:
            fail("NONDETERMINISTIC")
        if str(row.get("outcome", "")) == "RATIFIED":
            ratified_types.add(str(row.get("ratified_type_id", "")).strip())
        refs.append(receipt_id)
    return ratified_types, _sorted_unique(refs)


def build_type_binding(
    *,
    graph: dict[str, Any],
    type_registry: dict[str, Any],
    provisionals: list[dict[str, Any]] | None = None,
    ratifications: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    registry = validate_type_registry(type_registry)
    validate_schema(graph, "qxwmr_graph_v1")
    graph_id = verify_object_id(graph, id_field="graph_id")
    registry_id = ensure_sha256(registry.get("registry_id"), reason="SCHEMA_FAIL")
    prefix = str(registry.get("provisional_namespace_prefix", ""))

    declared_types = collect_graph_type_ids(graph)
    allowed = set(str(row) for row in registry.get("allowed_type_ids", []))
    provisional_by_type, provisional_refs = _validate_provisional_rows(
        graph_id=graph_id,
        prefix=prefix,
        provisionals=provisionals,
    )
    ratified_types, ratification_refs = _validate_ratification_rows(
        registry_id=registry_id,
        ratifications=ratifications,
    )

    unknown: list[str] = []
    for type_id in declared_types:
        if type_id in allowed:
            continue
        if type_id in ratified_types:
            continue
        if type_id.startswith(prefix) and type_id in provisional_by_type:
            continue
        unknown.append(type_id)

    payload = {
        "schema_version": "epistemic_type_binding_v1",
        "binding_id": "sha256:" + ("0" * 64),
        "graph_id": graph_id,
        "type_registry_id": registry_id,
        "declared_type_ids": list(declared_types),
        "provisional_refs": list(provisional_refs),
        "ratification_receipt_refs": list(ratification_refs),
        "unknown_type_ids": list(_sorted_unique(unknown)),
        "outcome": "ACCEPT" if not unknown else "SAFE_HALT",
    }
    payload_no_id = dict(payload)
    payload_no_id.pop("binding_id", None)
    payload["binding_id"] = canon_hash_obj(payload_no_id)
    validate_schema(payload, "epistemic_type_binding_v1")
    verify_object_id(payload, id_field="binding_id")
    return payload


__all__ = [
    "build_type_binding",
    "collect_graph_type_ids",
    "is_legacy_registry",
    "validate_registry_transition",
    "validate_type_registry",
]
