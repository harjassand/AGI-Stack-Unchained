from __future__ import annotations

import pytest

from cdel.v1_7r.canon import CanonError
from cdel.v3_3.verify_rsi_swarm_v4 import verify

from .utils import (
    build_meta_chain,
    insert_before_swarm_end,
    setup_base_run,
    write_swarm_ledger,
)


def test_v3_3_meta_head_declare_mismatch_fatal(tmp_path, repo_root) -> None:
    ctx = setup_base_run(tmp_path, repo_root, max_epochs=1, with_result=False)
    run_root = ctx["run_root"]
    meta_cfg = ctx["pack"]["swarm"]["meta"]

    derived_blocks, derived_states, derived_policies = build_meta_chain(
        run_root=run_root,
        root_run_id=ctx["run_id"],
        icore_id=ctx["icore_id"],
        max_epochs=1,
        updates_by_epoch={0: []},
        meta_cfg=meta_cfg,
    )

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

    # Intentionally wrong final meta head.
    insert_before_swarm_end(
        ctx["events"],
        "META_HEAD_DECLARE",
        {
            "declared_at_epoch_index": 1,
            "meta_epoch_index": 0,
            "meta_block_id": "sha256:" + "0" * 64,
            "meta_block_path": "@ROOT/meta_exchange/blocks/sha256_" + "0" * 64 + ".meta_block_v1.json",
            "meta_state_hash": derived_states[0]["state_hash"],
            "meta_policy_hash": derived_policies[0]["policy_hash"],
        },
    )

    write_swarm_ledger(run_root / "ledger" / "swarm_ledger_v5.jsonl", ctx["events"])

    with pytest.raises(CanonError) as exc:
        verify(run_root)
    assert "META_HEAD_MISMATCH" in str(exc.value)
