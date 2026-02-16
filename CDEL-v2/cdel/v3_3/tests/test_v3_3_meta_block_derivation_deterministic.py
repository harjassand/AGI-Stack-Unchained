from __future__ import annotations

from cdel.v3_3.meta_ledger import apply_meta_updates, build_meta_block, compute_update_id


def test_v3_3_meta_block_derivation_deterministic() -> None:
    update_body = {
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
    update_id = compute_update_id(update_body)
    update = dict(update_body)
    update["update_id"] = update_id
    update["update_hash"] = update_id

    new_state, new_policy, accepted, rejected, stats = apply_meta_updates(
        root_swarm_run_id=update_body["root_swarm_run_id"],
        icore_id=update_body["icore_id"],
        meta_epoch_index=0,
        prev_state={"state_hash": "GENESIS", "knowledge_graph": {"assertions": []}},
        prev_policy={"policy_hash": "GENESIS", "policy": {"bridge": {"subscriptions_add": []}, "task": {"priority": []}}},
        updates=[update],
        knowledge_limits={},
        policy_limits={"allowed_keys": ["bridge.subscriptions_add", "task.priority_boost"], "priority_min": 0, "priority_max": 100},
        allowed_update_kinds={"POLICY_PATCH_V1"},
        max_updates_apply=0,
    )

    state_hash = new_state["state_hash"]
    policy_hash = new_policy["policy_hash"]
    block1 = build_meta_block(
        root_swarm_run_id=update_body["root_swarm_run_id"],
        icore_id=update_body["icore_id"],
        meta_epoch_index=0,
        prev_meta_block_id="GENESIS",
        accepted_update_ids=accepted,
        rejected_updates=rejected,
        meta_state_hash=state_hash,
        meta_state_path="@ROOT/meta_exchange/state/sha256_dummy.meta_state_v1.json",
        meta_policy_hash=policy_hash,
        meta_policy_path="@ROOT/meta_exchange/policy/sha256_dummy.meta_policy_v1.json",
        stats=stats,
    )
    block2 = build_meta_block(
        root_swarm_run_id=update_body["root_swarm_run_id"],
        icore_id=update_body["icore_id"],
        meta_epoch_index=0,
        prev_meta_block_id="GENESIS",
        accepted_update_ids=accepted,
        rejected_updates=rejected,
        meta_state_hash=state_hash,
        meta_state_path="@ROOT/meta_exchange/state/sha256_dummy.meta_state_v1.json",
        meta_policy_hash=policy_hash,
        meta_policy_path="@ROOT/meta_exchange/policy/sha256_dummy.meta_policy_v1.json",
        stats=stats,
    )
    assert block1 == block2
