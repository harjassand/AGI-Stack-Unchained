from __future__ import annotations

from cdel.v1_8r.metabolism_v1.cache_ctx_hash import CtxHashCache, compute_onto_ctx_hash
from cdel.v1_8r.metabolism_v1.workvec import new_workvec


def test_ctx_hash_cache_v1_correctness() -> None:
    cases = [
        {"schema": "onto_ctx_null_v1", "schema_version": 1},
        {
            "schema": "onto_ctx_key_v1",
            "schema_version": 1,
            "ontology_id": "sha256:" + "0" * 64,
            "snapshot_id": "sha256:" + "1" * 64,
            "values": [0, 1, -1],
        },
    ]

    for ctx_key in cases:
        base = compute_onto_ctx_hash(ctx_key, cache=None, workvec=new_workvec())
        cache = CtxHashCache(8)
        patch = compute_onto_ctx_hash(ctx_key, cache=cache, workvec=new_workvec())
        assert base == patch
