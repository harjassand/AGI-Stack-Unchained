from __future__ import annotations

from cdel.v3_3.meta_ledger import apply_meta_updates, build_meta_block, compute_update_id


def _make_update(root_run_id: str, icore_id: str, published_epoch: int, topic: str) -> dict:
    body = {
        "schema": "meta_update_v1",
        "spec_version": "v3_3",
        "root_swarm_run_id": root_run_id,
        "icore_id": icore_id,
        "published_at_epoch_index": published_epoch,
        "publisher": {
            "publisher_swarm_run_id": "sha256:" + "2" * 64,
            "publisher_depth": 0,
            "publisher_node_relpath": ".",
            "publisher_task_id": "sha256:" + "3" * 64,
            "publisher_result_id": "sha256:" + "4" * 64,
            "publisher_result_verify_event_ref_hash": "sha256:" + "5" * 64,
        },
        "topics": [topic],
        "update_kind": "POLICY_PATCH_V1",
        "payload": {"policy_delta": {"bridge.subscriptions_add": [topic]}},
    }
    update_id = compute_update_id(body)
    update = dict(body)
    update["update_id"] = update_id
    update["update_hash"] = update_id
    return update


def test_v3_3_meta_block_includes_exact_epoch_updates() -> None:
    root_run_id = "sha256:" + "0" * 64
    icore_id = "sha256:" + "1" * 64
    update0 = _make_update(root_run_id, icore_id, 0, "demo/lemmaA")
    update1 = _make_update(root_run_id, icore_id, 1, "demo/lemmaB")

    prev_state = {"state_hash": "GENESIS", "knowledge_graph": {"assertions": []}}
    prev_policy = {"policy_hash": "GENESIS", "policy": {"bridge": {"subscriptions_add": []}, "task": {"priority": []}}}

    new_state0, new_policy0, accepted0, rejected0, stats0 = apply_meta_updates(
        root_swarm_run_id=root_run_id,
        icore_id=icore_id,
        meta_epoch_index=0,
        prev_state=prev_state,
        prev_policy=prev_policy,
        updates=[update0],
        knowledge_limits={},
        policy_limits={"allowed_keys": ["bridge.subscriptions_add", "task.priority_boost"], "priority_min": 0, "priority_max": 100},
        allowed_update_kinds={"POLICY_PATCH_V1"},
        max_updates_apply=0,
    )
    block0 = build_meta_block(
        root_swarm_run_id=root_run_id,
        icore_id=icore_id,
        meta_epoch_index=0,
        prev_meta_block_id="GENESIS",
        accepted_update_ids=accepted0,
        rejected_updates=rejected0,
        meta_state_hash=new_state0["state_hash"],
        meta_state_path="@ROOT/meta_exchange/state/sha256_dummy0.meta_state_v1.json",
        meta_policy_hash=new_policy0["policy_hash"],
        meta_policy_path="@ROOT/meta_exchange/policy/sha256_dummy0.meta_policy_v1.json",
        stats=stats0,
    )

    new_state1, new_policy1, accepted1, rejected1, stats1 = apply_meta_updates(
        root_swarm_run_id=root_run_id,
        icore_id=icore_id,
        meta_epoch_index=1,
        prev_state=new_state0,
        prev_policy=new_policy0,
        updates=[update1],
        knowledge_limits={},
        policy_limits={"allowed_keys": ["bridge.subscriptions_add", "task.priority_boost"], "priority_min": 0, "priority_max": 100},
        allowed_update_kinds={"POLICY_PATCH_V1"},
        max_updates_apply=0,
    )
    block1 = build_meta_block(
        root_swarm_run_id=root_run_id,
        icore_id=icore_id,
        meta_epoch_index=1,
        prev_meta_block_id=block0["meta_block_id"],
        accepted_update_ids=accepted1,
        rejected_updates=rejected1,
        meta_state_hash=new_state1["state_hash"],
        meta_state_path="@ROOT/meta_exchange/state/sha256_dummy1.meta_state_v1.json",
        meta_policy_hash=new_policy1["policy_hash"],
        meta_policy_path="@ROOT/meta_exchange/policy/sha256_dummy1.meta_policy_v1.json",
        stats=stats1,
    )

    assert block0["accepted_update_ids"] == [update0["update_id"]]
    assert block1["accepted_update_ids"] == [update1["update_id"]]
