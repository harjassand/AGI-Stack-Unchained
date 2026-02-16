from __future__ import annotations

from cdel.v1_7r.canon import canon_bytes, sha256_prefixed
from cdel.v1_7r.ontology_v3.context_kernel import ctx_hash


def test_trace_v2_context_hash_rule() -> None:
    ctx_key = {
        "schema": "onto_ctx_key_v1",
        "schema_version": 1,
        "ontology_id": "sha256:" + "1" * 64,
        "snapshot_id": "sha256:" + "2" * 64,
        "values": [1, 0, -1],
    }
    expected = sha256_prefixed(canon_bytes(ctx_key))
    assert ctx_hash(ctx_key) == expected
