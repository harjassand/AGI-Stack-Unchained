from __future__ import annotations

from cdel.v1_7r.canon import canon_bytes, sha256_prefixed


def _compute_offer_id(offer: dict) -> str:
    body = dict(offer)
    body.pop("offer_id", None)
    body.pop("offer_hash", None)
    return sha256_prefixed(canon_bytes(body))


def test_v3_2_bridge_offer_id_hash_deterministic() -> None:
    offer = {
        "schema": "bridge_offer_v1",
        "spec_version": "v3_2",
        "offer_id": "__SELF__",
        "offer_hash": "__SELF__",
        "root_swarm_run_id": "sha256:" + "0" * 64,
        "icore_id": "sha256:" + "1" * 64,
        "publisher": {
            "publisher_swarm_run_id": "sha256:" + "2" * 64,
            "publisher_depth": 0,
            "publisher_node_relpath": ".",
            "publisher_task_id": "sha256:" + "3" * 64,
            "publisher_result_id": "sha256:" + "4" * 64,
            "publisher_result_verify_event_ref_hash": "sha256:" + "5" * 64,
        },
        "topics": ["demo/lemmaA"],
        "artifacts": [
            {
                "kind": "SUBPROOF_BUNDLE_V1",
                "blob_sha256": "sha256:" + "6" * 64,
                "bytes": 4,
                "exchange_blob_path": "@ROOT/bridge_exchange/blobs/sha256_" + "6" * 64 + ".blob",
            }
        ],
        "context_requirements": {"kind": "NONE", "required_barrier_head_ref_hash": "GENESIS"},
    }
    first = _compute_offer_id(offer)
    second = _compute_offer_id(offer)
    assert first == second
