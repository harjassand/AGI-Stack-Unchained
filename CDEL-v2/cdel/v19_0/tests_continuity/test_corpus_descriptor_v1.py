from __future__ import annotations

import pytest

from cdel.v19_0.common_v1 import validate_schema


def _valid_descriptor() -> dict[str, object]:
    return {
        "schema_name": "corpus_descriptor_v1",
        "schema_version": "v19_0",
        "descriptor_id": "sha256:" + ("a" * 64),
        "discovery_mode": "EXPLICIT_ENUMERATION_ONLY",
        "entries": [
            {
                "run_id": "ignite_v19_super_unified_tick_42",
                "tick_u64": 42,
                "tick_snapshot_hash": "sha256:" + ("b" * 64),
            }
        ],
    }


def test_corpus_descriptor_accepts_explicit_tuple_entries() -> None:
    payload = _valid_descriptor()
    validate_schema(payload, "corpus_descriptor_v1")


def test_corpus_descriptor_rejects_non_explicit_discovery_mode() -> None:
    payload = _valid_descriptor()
    payload["discovery_mode"] = "DISCOVER_AT_RUNTIME"
    with pytest.raises(Exception):
        validate_schema(payload, "corpus_descriptor_v1")

