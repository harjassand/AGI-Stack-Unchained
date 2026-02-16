from __future__ import annotations

import pytest

from cdel.v1_7r.canon import CanonError
from cdel.v3_3.verify_rsi_swarm_v4 import verify

from .utils import (
    build_policy_update,
    insert_before_swarm_end,
    setup_base_run,
    write_meta_update,
    write_swarm_ledger,
)


def test_v3_3_meta_provenance_requires_valid_result_verify(tmp_path, repo_root) -> None:
    ctx = setup_base_run(tmp_path, repo_root, max_epochs=1, with_result=True, verify_verdict="INVALID")
    run_root = ctx["run_root"]

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
    write_swarm_ledger(run_root / "ledger" / "swarm_ledger_v5.jsonl", ctx["events"])

    with pytest.raises(CanonError) as exc:
        verify(run_root)
    assert "META_UNVERIFIED_UPDATE" in str(exc.value)
