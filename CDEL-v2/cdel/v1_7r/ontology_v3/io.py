"""Canonical IO + hashing helpers for ontology v3."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..canon import CanonError, load_canon_json, write_canon_json
from ..hashutil import compute_self_hash


def compute_concept_id(concept: dict[str, Any]) -> str:
    return compute_self_hash(concept, "concept_id")


def compute_ontology_id(ontology_def: dict[str, Any]) -> str:
    return compute_self_hash(ontology_def, "ontology_id")


def compute_snapshot_id(snapshot: dict[str, Any]) -> str:
    return compute_self_hash(snapshot, "snapshot_id")


def verify_ontology_def_ids(ontology_def: dict[str, Any]) -> None:
    concepts = ontology_def.get("concepts")
    if not isinstance(concepts, list):
        raise CanonError("ontology_def concepts missing")
    for concept in concepts:
        if not isinstance(concept, dict):
            raise CanonError("ontology_def concept must be object")
        expected = compute_concept_id(concept)
        if concept.get("concept_id") != expected:
            raise CanonError("concept_id mismatch")
    expected_ontology = compute_ontology_id(ontology_def)
    if ontology_def.get("ontology_id") != expected_ontology:
        raise CanonError("ontology_id mismatch")


def verify_snapshot_id(snapshot: dict[str, Any]) -> None:
    expected = compute_snapshot_id(snapshot)
    if snapshot.get("snapshot_id") != expected:
        raise CanonError("snapshot_id mismatch")


def ensure_ontology_dirs(root: Path) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    ledger_dir = root / "ledger"
    active_dir = root / "active"
    defs_dir = root / "defs" / "by_ontology_id"
    snapshots_dir = root / "snapshots" / "by_hash"
    reports_dir = root / "reports"
    receipts_dir = root / "receipts"
    for path in (ledger_dir, active_dir, defs_dir, snapshots_dir, reports_dir, receipts_dir):
        path.mkdir(parents=True, exist_ok=True)
    return {
        "root": root,
        "ledger": ledger_dir,
        "active": active_dir,
        "defs": defs_dir,
        "snapshots": snapshots_dir,
        "reports": reports_dir,
        "receipts": receipts_dir,
    }


def load_def_by_ontology_id(ontology_id: str, *, defs_root: Path) -> dict[str, Any]:
    hex_part = ontology_id.split(":", 1)[1] if ":" in ontology_id else ontology_id
    path = defs_root / f"{hex_part}.json"
    if not path.exists():
        raise FileNotFoundError(f"missing ontology_def: {ontology_id}")
    payload = load_canon_json(path)
    if payload.get("ontology_id") != ontology_id:
        raise CanonError("ontology_def id mismatch")
    return payload


def load_snapshot_by_id(snapshot_id: str, *, snapshots_root: Path) -> dict[str, Any]:
    hex_part = snapshot_id.split(":", 1)[1] if ":" in snapshot_id else snapshot_id
    path = snapshots_root / f"{hex_part}.json"
    if not path.exists():
        raise FileNotFoundError(f"missing snapshot: {snapshot_id}")
    payload = load_canon_json(path)
    if payload.get("snapshot_id") != snapshot_id:
        raise CanonError("snapshot_id mismatch")
    return payload


def write_def_if_missing(ontology_def: dict[str, Any], defs_root: Path) -> Path:
    ontology_id = ontology_def.get("ontology_id")
    if not isinstance(ontology_id, str):
        raise CanonError("ontology_id missing")
    hex_part = ontology_id.split(":", 1)[1] if ":" in ontology_id else ontology_id
    out_path = defs_root / f"{hex_part}.json"
    if not out_path.exists():
        write_canon_json(out_path, ontology_def)
    return out_path


def write_snapshot_if_missing(snapshot: dict[str, Any], snapshots_root: Path) -> Path:
    snapshot_id = snapshot.get("snapshot_id")
    if not isinstance(snapshot_id, str):
        raise CanonError("snapshot_id missing")
    hex_part = snapshot_id.split(":", 1)[1] if ":" in snapshot_id else snapshot_id
    out_path = snapshots_root / f"{hex_part}.json"
    if not out_path.exists():
        write_canon_json(out_path, snapshot)
    return out_path
