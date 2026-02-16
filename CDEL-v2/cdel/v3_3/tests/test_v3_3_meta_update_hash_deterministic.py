from __future__ import annotations

from cdel.v3_3.meta_ledger import compute_update_id


def test_v3_3_meta_update_hash_deterministic() -> None:
    body = {
        "schema": "meta_update_v1",
        "spec_version": "v3_3",
        "root_swarm_run_id": "sha256:" + "0" * 64,
        "icore_id": "sha256:" + "1" * 64,
        "published_at_epoch_index": 0,
        "publisher": {
            "publisher_swarm_run_id": "sha256:" + "2" * 64,
            "publisher_depth": 0,
            "publisher_node_relpath": ".",
            "publisher_task_id": "sha256:" + "3" * 64,
            "publisher_result_id": "sha256:" + "4" * 64,
            "publisher_result_verify_event_ref_hash": "sha256:" + "5" * 64,
        },
        "topics": ["demo/lemmaA"],
        "update_kind": "POLICY_PATCH_V1",
        "payload": {"policy_delta": {"bridge.subscriptions_add": ["demo/lemmaA"]}},
    }
    first = compute_update_id(body)
    second = compute_update_id(body)
    assert first == second

    update = dict(body)
    update["update_id"] = first
    update["update_hash"] = first
    assert compute_update_id(update) == first
