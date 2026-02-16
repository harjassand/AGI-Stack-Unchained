"""Canonical IO + hashing helpers for ontology v2."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from ..canon import CanonError, canon_bytes, hash_json, load_canon_json, sha256_prefixed, write_canon_json


def hash_bytes(payload: bytes) -> str:
    return sha256_prefixed(payload)


def hash_json_obj(obj: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(obj))


def compute_self_hash(obj: dict[str, Any], field: str) -> str:
    temp = deepcopy(obj)
    temp[field] = "__SELF__"
    return sha256_prefixed(canon_bytes(temp))


def compute_concept_id(concept: dict[str, Any]) -> str:
    return compute_self_hash(concept, "concept_id")


def compute_ontology_id(ontology_def: dict[str, Any]) -> str:
    return compute_self_hash(ontology_def, "ontology_id")


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


def ensure_ontology_dirs(root: Path) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    defs_dir = root / "defs"
    reports_dir = root / "reports"
    receipts_dir = root / "receipts"
    snapshots_dir = root / "snapshots"
    for path in (defs_dir, reports_dir, receipts_dir, snapshots_dir):
        path.mkdir(parents=True, exist_ok=True)
    return {
        "root": root,
        "defs": defs_dir,
        "reports": reports_dir,
        "receipts": receipts_dir,
        "snapshots": snapshots_dir,
    }


def load_def_by_hash(def_hash: str, *, inbox_root: Path, defs_root: Path) -> dict[str, Any]:
    hex_part = def_hash.split(":", 1)[1] if ":" in def_hash else def_hash
    candidates = [
        defs_root / f"{hex_part}.json",
        inbox_root / "defs" / f"{hex_part}.json",
        inbox_root / f"{hex_part}.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        payload = load_canon_json(path)
        if hash_json(payload) == def_hash or compute_ontology_id(payload) == def_hash:
            return payload
        raise CanonError(f"ontology_def hash mismatch: {path}")

    search_roots = [defs_root, inbox_root / "defs", inbox_root]
    for root in search_roots:
        if not root.exists():
            continue
        for path in sorted(root.glob("*.json")):
            payload = load_canon_json(path)
            if hash_json(payload) == def_hash or compute_ontology_id(payload) == def_hash:
                return payload
    raise FileNotFoundError(f"missing ontology_def: {def_hash}")


def write_def_if_missing(def_payload: dict[str, Any], defs_root: Path) -> Path:
    def_hash = hash_json(def_payload)
    hex_part = def_hash.split(":", 1)[1]
    out_path = defs_root / f"{hex_part}.json"
    if not out_path.exists():
        write_canon_json(out_path, def_payload)
    return out_path
