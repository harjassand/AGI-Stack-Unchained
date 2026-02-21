"""Cross-binding checks for epistemic capsule artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..common_v1 import canon_hash_obj, ensure_sha256, fail, validate_schema, verify_object_id
from ..world.merkle_v1 import compute_world_root
from .verify_epistemic_type_governance_v1 import verify_type_binding


def _load_by_hash(dir_path: Path, digest: str, suffix: str, *, id_field: str | None = None) -> dict[str, Any]:
    target = ensure_sha256(digest, reason="SCHEMA_FAIL")
    rows = sorted(dir_path.glob(f"sha256_*.{suffix}"), key=lambda p: p.as_posix())
    matches: list[dict[str, Any]] = []
    for path in rows:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            fail("SCHEMA_FAIL")
        if id_field is None:
            if canon_hash_obj(payload) != target:
                continue
            matches.append(payload)
            continue
        declared = verify_object_id(payload, id_field=id_field)
        if declared == target:
            matches.append(payload)
    if len(matches) != 1:
        fail("MISSING_STATE_INPUT")
    return matches[0]


def _load_rows(dir_path: Path, suffix: str, *, schema_name: str, id_field: str) -> list[dict[str, Any]]:
    rows = sorted(dir_path.glob(f"sha256_*.{suffix}"), key=lambda p: p.as_posix())
    out: list[dict[str, Any]] = []
    for path in rows:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            fail("SCHEMA_FAIL")
        if canon_hash_obj(payload) != "sha256:" + path.name.split(".", 1)[0].split("_", 1)[1]:
            fail("NONDETERMINISTIC")
        validate_schema(payload, schema_name)
        verify_object_id(payload, id_field=id_field)
        out.append(payload)
    return out


def verify_capsule_bundle(state_root: Path) -> dict[str, Any]:
    epi_root = state_root / "epistemic"
    cap_dir = epi_root / "capsules"
    cap_rows = sorted(cap_dir.glob("sha256_*.epistemic_capsule_v1.json"), key=lambda p: p.as_posix())
    if not cap_rows:
        fail("MISSING_STATE_INPUT")
    capsules: list[tuple[int, bool, str, dict[str, Any]]] = []
    for path in cap_rows:
        capsule = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(capsule, dict):
            fail("SCHEMA_FAIL")
        validate_schema(capsule, "epistemic_capsule_v1")
        capsule_id = verify_object_id(capsule, id_field="capsule_id")
        tick_u64 = int(capsule.get("tick_u64", -1))
        if tick_u64 < 0:
            fail("SCHEMA_FAIL")
        capsules.append((tick_u64, bool(capsule.get("usable_b", False)), capsule_id, capsule))
    candidates = [row for row in capsules if row[1]] or capsules
    candidates.sort(key=lambda row: (row[0], row[2]))
    _tick_u64, _usable_b, capsule_id, capsule = candidates[-1]

    graph_id = str(capsule.get("distillate_graph_id", ""))
    graph = _load_by_hash(epi_root / "graphs", graph_id, "qxwmr_graph_v1.json", id_field="graph_id")
    validate_schema(graph, "qxwmr_graph_v1")
    if verify_object_id(graph, id_field="graph_id") != graph_id:
        fail("NONDETERMINISTIC")
    strip_receipt_rows = _load_rows(
        epi_root / "strip_receipts",
        "epistemic_instruction_strip_receipt_v1.json",
        schema_name="epistemic_instruction_strip_receipt_v1",
        id_field="receipt_id",
    )
    if not strip_receipt_rows:
        fail("MISSING_STATE_INPUT")
    strip_receipt_set_hash = canon_hash_obj(
        {
            "schema_version": "epistemic_instruction_strip_receipt_set_v1",
            "receipt_ids": sorted(
                ensure_sha256(row.get("receipt_id"), reason="SCHEMA_FAIL")
                for row in strip_receipt_rows
            ),
        }
    )
    if ensure_sha256(capsule.get("strip_receipt_id"), reason="SCHEMA_FAIL") != strip_receipt_set_hash:
        fail("NONDETERMINISTIC")

    manifest_id = str(capsule.get("sip_manifest_id", ""))
    manifest = _load_by_hash(
        epi_root / "world" / "manifests",
        manifest_id,
        "world_snapshot_manifest_v1.json",
        id_field="manifest_id",
    )
    validate_schema(manifest, "world_snapshot_manifest_v1")
    if verify_object_id(manifest, id_field="manifest_id") != manifest_id:
        fail("NONDETERMINISTIC")

    receipt_id = str(capsule.get("sip_receipt_id", ""))
    receipt = _load_by_hash(
        epi_root / "world" / "receipts",
        receipt_id,
        "sealed_ingestion_receipt_v1.json",
        id_field="receipt_id",
    )
    validate_schema(receipt, "sealed_ingestion_receipt_v1")
    if verify_object_id(receipt, id_field="receipt_id") != receipt_id:
        fail("NONDETERMINISTIC")

    snapshot_id = str(capsule.get("world_snapshot_id", ""))
    snapshot = _load_by_hash(
        epi_root / "world" / "snapshots",
        snapshot_id,
        "world_snapshot_v1.json",
        id_field="world_snapshot_id",
    )
    validate_schema(snapshot, "world_snapshot_v1")
    if verify_object_id(snapshot, id_field="world_snapshot_id") != snapshot_id:
        fail("NONDETERMINISTIC")

    computed_world_root = compute_world_root(manifest, enforce_sorted=True)
    if str(capsule.get("world_root", "")) != computed_world_root:
        fail("NONDETERMINISTIC")
    if str(receipt.get("computed_world_root", "")) != computed_world_root:
        fail("NONDETERMINISTIC")
    if str(snapshot.get("world_root", "")) != computed_world_root:
        fail("NONDETERMINISTIC")

    if str(snapshot.get("ingestion_receipt_ref", "")) != receipt_id:
        fail("NONDETERMINISTIC")
    if str(snapshot.get("world_manifest_ref", "")) != manifest_id:
        fail("NONDETERMINISTIC")

    leakage_gate = dict((receipt.get("gate_results") or {}).get("leakage_gate") or {})
    non_interference_gate = dict((receipt.get("gate_results") or {}).get("non_interference_gate") or {})
    if str(snapshot.get("leakage_gate_receipt_ref", "")) != canon_hash_obj(leakage_gate):
        fail("NONDETERMINISTIC")
    if str(snapshot.get("non_interference_gate_receipt_ref", "")) != canon_hash_obj(non_interference_gate):
        fail("NONDETERMINISTIC")

    if str(capsule.get("distillate_graph_id", "")) != verify_object_id(graph, id_field="graph_id"):
        fail("NONDETERMINISTIC")

    type_registry_id_raw = capsule.get("type_registry_id")
    type_binding_id_raw = capsule.get("type_binding_id")
    if (type_registry_id_raw is None) != (type_binding_id_raw is None):
        fail("NONDETERMINISTIC")
    if type_registry_id_raw is not None and type_binding_id_raw is not None:
        type_registry_id = ensure_sha256(type_registry_id_raw, reason="SCHEMA_FAIL")
        type_binding_id = ensure_sha256(type_binding_id_raw, reason="SCHEMA_FAIL")
        type_registry = _load_by_hash(
            epi_root / "type_registry",
            type_registry_id,
            "epistemic_type_registry_v1.json",
            id_field="registry_id",
        )
        type_binding = _load_by_hash(
            epi_root / "type_bindings",
            type_binding_id,
            "epistemic_type_binding_v1.json",
            id_field="binding_id",
        )
        provisionals = _load_rows(
            epi_root / "type" / "provisionals",
            "epistemic_type_provisional_v1.json",
            schema_name="epistemic_type_provisional_v1",
            id_field="provisional_id",
        )
        ratifications = _load_rows(
            epi_root / "type" / "ratifications",
            "epistemic_type_ratification_receipt_v1.json",
            schema_name="epistemic_type_ratification_receipt_v1",
            id_field="receipt_id",
        )
        summary = verify_type_binding(
            binding=type_binding,
            graph=graph,
            type_registry=type_registry,
            provisionals=provisionals,
            ratifications=ratifications,
        )
        if str(summary.get("outcome", "")) != "ACCEPT":
            fail("TYPE_GOVERNANCE_FAIL")
        graph_registry_id_raw = graph.get("type_registry_id")
        if graph_registry_id_raw is not None:
            if ensure_sha256(graph_registry_id_raw, reason="SCHEMA_FAIL") != type_registry_id:
                fail("NONDETERMINISTIC")
        graph_binding_id_raw = graph.get("type_binding_id")
        if graph_binding_id_raw is not None:
            if ensure_sha256(graph_binding_id_raw, reason="SCHEMA_FAIL") != type_binding_id:
                fail("NONDETERMINISTIC")

    return {
        "status": "VALID",
        "capsule_id": capsule_id,
        "world_snapshot_id": snapshot_id,
        "world_root": computed_world_root,
        "sip_receipt_id": receipt_id,
        "distillate_graph_id": graph_id,
        "strip_receipt_id": ensure_sha256(capsule.get("strip_receipt_id"), reason="SCHEMA_FAIL"),
        "episode_id": str(capsule.get("episode_id", "")),
    }


__all__ = ["verify_capsule_bundle"]
