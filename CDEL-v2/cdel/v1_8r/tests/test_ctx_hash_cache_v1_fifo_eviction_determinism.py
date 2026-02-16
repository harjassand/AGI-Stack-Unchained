from __future__ import annotations

from cdel.v1_8r.metabolism_v1.cache_ctx_hash import CtxHashCache, compute_onto_ctx_hash
from cdel.v1_8r.metabolism_v1.workvec import new_workvec


def _ctx(values: list[int]) -> dict[str, object]:
    return {
        "schema": "onto_ctx_key_v1",
        "schema_version": 1,
        "ontology_id": "sha256:" + "0" * 64,
        "snapshot_id": "sha256:" + "1" * 64,
        "values": values,
    }


def test_ctx_hash_cache_v1_fifo_eviction_determinism() -> None:
    cache = CtxHashCache(2)

    compute_onto_ctx_hash(_ctx([1]), cache=cache, workvec=new_workvec())
    compute_onto_ctx_hash(_ctx([2]), cache=cache, workvec=new_workvec())
    compute_onto_ctx_hash(_ctx([3]), cache=cache, workvec=new_workvec())

    # B should still be cached after inserting C.
    wv_b = new_workvec()
    compute_onto_ctx_hash(_ctx([2]), cache=cache, workvec=wv_b)
    assert wv_b.sha256_calls_total == 0
    assert wv_b.onto_ctx_hash_compute_calls_total == 0

    # A should be evicted after inserting C with capacity 2.
    wv_a = new_workvec()
    compute_onto_ctx_hash(_ctx([1]), cache=cache, workvec=wv_a)
    assert wv_a.sha256_calls_total == 1
    assert wv_a.onto_ctx_hash_compute_calls_total == 1
