"""Context key helpers for ontology v3."""

from __future__ import annotations

from typing import Any

from ..canon import canon_bytes, sha256_prefixed


def build_ctx_key(ontology_id: str, snapshot_id: str, values: list[int]) -> dict[str, Any]:
    return {
        "schema": "onto_ctx_key_v1",
        "schema_version": 1,
        "ontology_id": ontology_id,
        "snapshot_id": snapshot_id,
        "values": values,
    }


def build_null_ctx_key() -> dict[str, Any]:
    return {"schema": "onto_ctx_null_v1", "schema_version": 1}


def ctx_hash(ctx_key: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(ctx_key))
