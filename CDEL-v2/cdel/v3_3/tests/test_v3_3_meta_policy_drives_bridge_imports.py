from __future__ import annotations

import pytest

from cdel.v1_7r.canon import CanonError
from cdel.v3_3.verify_rsi_swarm_v4 import verify

from .utils import (
    build_meta_chain,
    create_import,
    create_offer,
    insert_before_swarm_end,
    setup_base_run,
    write_swarm_ledger,
)


def test_v3_3_meta_policy_drives_bridge_imports(tmp_path, repo_root) -> None:
    ctx = setup_base_run(
        tmp_path,
        repo_root,
        max_epochs=2,
        with_result=True,
        subscriptions_static=[],
    )
    run_root = ctx["run_root"]
    meta_cfg = ctx["pack"]["swarm"]["meta"]

    # Create a bridge offer/import, but no meta policy subscription.
    offer_info = create_offer(
        run_root,
        ctx["run_id"],
        icore_id=ctx["icore_id"],
        task_id=ctx["task_id"],
        result_id=ctx["result_id"],
        verify_ref=ctx["verify_ref"],
    )
    import_info = create_import(run_root, offer_info["offer"])

    insert_before_swarm_end(
        ctx["events"],
        "BRIDGE_IMPORT_ACCEPT",
        {
            "epoch_index": 2,
            "offer_id": import_info["offer_id"],
            "offer_path": f"@ROOT/bridge_exchange/offers/sha256_{import_info['offer_hex']}.bridge_offer_v1.json",
            "import_dir_relpath": import_info["import_dir_rel"],
            "import_manifest_relpath": import_info["manifest_rel"],
            "import_receipt_relpath": import_info["receipt_rel"],
            "imported_artifacts_set_hash": import_info["imported_set_hash"],
        },
    )

    derived_blocks, derived_states, derived_policies = build_meta_chain(
        run_root=run_root,
        root_run_id=ctx["run_id"],
        icore_id=ctx["icore_id"],
        max_epochs=2,
        updates_by_epoch={0: [], 1: []},
        meta_cfg=meta_cfg,
    )

    # Meta head declares (genesis + epoch 1 + finalization)
    insert_before_swarm_end(
        ctx["events"],
        "META_HEAD_DECLARE",
        {
            "declared_at_epoch_index": 0,
            "meta_epoch_index": -1,
            "meta_block_id": "GENESIS",
            "meta_block_path": "GENESIS",
            "meta_state_hash": "GENESIS",
            "meta_policy_hash": "GENESIS",
        },
    )
    block0 = derived_blocks[0]
    block0_hex = block0["meta_block_id"].split(":", 1)[1]
    insert_before_swarm_end(
        ctx["events"],
        "META_HEAD_DECLARE",
        {
            "declared_at_epoch_index": 1,
            "meta_epoch_index": 0,
            "meta_block_id": block0["meta_block_id"],
            "meta_block_path": f"@ROOT/meta_exchange/blocks/sha256_{block0_hex}.meta_block_v1.json",
            "meta_state_hash": derived_states[0]["state_hash"],
            "meta_policy_hash": derived_policies[0]["policy_hash"],
        },
    )
    block1 = derived_blocks[1]
    block1_hex = block1["meta_block_id"].split(":", 1)[1]
    insert_before_swarm_end(
        ctx["events"],
        "META_HEAD_DECLARE",
        {
            "declared_at_epoch_index": 2,
            "meta_epoch_index": 1,
            "meta_block_id": block1["meta_block_id"],
            "meta_block_path": f"@ROOT/meta_exchange/blocks/sha256_{block1_hex}.meta_block_v1.json",
            "meta_state_hash": derived_states[1]["state_hash"],
            "meta_policy_hash": derived_policies[1]["policy_hash"],
        },
    )

    write_swarm_ledger(run_root / "ledger" / "swarm_ledger_v5.jsonl", ctx["events"])

    with pytest.raises(CanonError) as exc:
        verify(run_root)
    assert "META_POLICY_IMPORT_VIOLATION" in str(exc.value)
