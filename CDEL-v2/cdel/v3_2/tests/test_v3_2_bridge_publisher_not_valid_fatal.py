from __future__ import annotations

import pytest

from cdel.v1_7r.canon import CanonError
from cdel.v3_2.constants import require_constants
from cdel.v3_2.immutable_core import load_lock
from cdel.v3_2.verify_rsi_swarm_v3 import NodeInfo, VerifyContext, _verify_bridge_imports, _verify_bridge_exchange

from .utils import create_import, create_offer, insert_before_swarm_end, setup_base_run, write_swarm_ledger


def test_v3_2_bridge_publisher_not_valid_fatal(tmp_path, repo_root) -> None:
    ctx_data = setup_base_run(tmp_path, repo_root, with_result=True)
    run_root = ctx_data["run_root"]
    offer_info = create_offer(run_root, ctx_data["run_id"], icore_id=ctx_data["icore_id"], task_id=ctx_data["task_id"], result_id=ctx_data["result_id"], verify_ref=ctx_data["verify_ref"])
    import_info = create_import(run_root, offer_info["offer"])

    accept_payload = {
        "epoch_index": 1,
        "offer_id": import_info["offer_id"],
        "offer_path": f"@ROOT/bridge_exchange/offers/sha256_{import_info['offer_hex']}.bridge_offer_v1.json",
        "import_dir_relpath": import_info["import_dir_rel"],
        "import_manifest_relpath": import_info["manifest_rel"],
        "import_receipt_relpath": import_info["receipt_rel"],
        "imported_artifacts_set_hash": import_info["imported_set_hash"],
    }
    insert_before_swarm_end(ctx_data["events"], "BRIDGE_IMPORT_ACCEPT", accept_payload)
    write_swarm_ledger(run_root / "ledger" / "swarm_ledger_v4.jsonl", ctx_data["events"])

    constants = require_constants()
    lock_rel = constants.get("IMMUTABLE_CORE_LOCK_REL")
    lock = load_lock(repo_root / lock_rel)

    ctx = VerifyContext(
        lock=lock,
        constants=constants,
        root_dir=run_root,
        visited=set([ctx_data["run_id"]]),
        nodes=[NodeInfo(run_id=ctx_data["run_id"], parent_run_id=None, depth=0, out_dir_relpath=".")],
        child_links={},
        node_receipts={ctx_data["run_id"]: {"verdict": "INVALID"}},
        allow_child=False,
    )

    offers = _verify_bridge_exchange(ctx, ctx_data["run_id"])
    with pytest.raises(CanonError) as exc:
        _verify_bridge_imports(ctx, offers, ctx_data["run_id"])
    assert "BRIDGE_PUBLISHER_NOT_VALID" in str(exc.value)
