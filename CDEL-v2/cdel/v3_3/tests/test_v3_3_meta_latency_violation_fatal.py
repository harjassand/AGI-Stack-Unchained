from __future__ import annotations

import pytest

from cdel.v1_7r.canon import CanonError, load_canon_json, write_canon_json
from cdel.v3_3.verify_rsi_swarm_v4 import verify

from .utils import (
    build_meta_chain,
    build_policy_update,
    insert_before_swarm_end,
    setup_base_run,
    write_meta_update,
    write_swarm_ledger,
)


def test_v3_3_meta_latency_violation_fatal(tmp_path, repo_root) -> None:
    ctx = setup_base_run(tmp_path, repo_root, max_epochs=2, with_result=True)
    run_root = ctx["run_root"]
    meta_cfg = ctx["pack"]["swarm"]["meta"]

    publisher = {
        "publisher_swarm_run_id": ctx["run_id"],
        "publisher_depth": 0,
        "publisher_node_relpath": ".",
        "publisher_task_id": ctx["task_id"],
        "publisher_result_id": ctx["result_id"],
        "publisher_result_verify_event_ref_hash": ctx["verify_ref"],
    }
    update = build_policy_update(
        root_run_id=ctx["run_id"],
        icore_id=ctx["icore_id"],
        published_epoch=0,
        publisher=publisher,
        topics=["demo/lemmaA"],
        policy_delta={"bridge.subscriptions_add": ["demo/lemmaA"]},
    )
    write_meta_update(run_root, update)
    update_id = update["update_id"]
    update_hex = update_id.split(":", 1)[1]
    update_path = f"@ROOT/meta_exchange/updates/sha256_{update_hex}.meta_update_v1.json"
    insert_before_swarm_end(
        ctx["events"],
        "META_UPDATE_PUBLISH",
        {
            "epoch_index": 1,
            "update_id": update_id,
            "update_path": update_path,
            "update_kind": update["update_kind"],
            "topics": update["topics"],
        },
    )

    updates_by_epoch = {0: [update], 1: []}
    derived_blocks, _, _ = build_meta_chain(
        run_root=run_root,
        root_run_id=ctx["run_id"],
        icore_id=ctx["icore_id"],
        max_epochs=2,
        updates_by_epoch=updates_by_epoch,
        meta_cfg=meta_cfg,
    )

    # Corrupt block 0 so it no longer contains the epoch-0 update.
    block0 = derived_blocks[0]
    block_hex = block0["meta_block_id"].split(":", 1)[1]
    block_path = run_root / "meta_exchange" / "blocks" / f"sha256_{block_hex}.meta_block_v1.json"
    bad_block = load_canon_json(block_path)
    bad_block["accepted_update_ids"] = []
    bad_block["rejected_updates"] = []
    write_canon_json(block_path, bad_block)

    write_swarm_ledger(run_root / "ledger" / "swarm_ledger_v5.jsonl", ctx["events"])

    with pytest.raises(CanonError) as exc:
        verify(run_root)
    assert "META_LATENCY_VIOLATION" in str(exc.value)
