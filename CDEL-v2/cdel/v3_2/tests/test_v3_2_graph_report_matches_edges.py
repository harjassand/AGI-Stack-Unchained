from __future__ import annotations

from cdel.v3_2.verify_rsi_swarm_v3 import verify

from .utils import (
    create_import,
    create_offer,
    insert_before_swarm_end,
    setup_base_run,
    write_graph_report,
    write_swarm_ledger,
)


def test_v3_2_graph_report_matches_edges(tmp_path, repo_root) -> None:
    ctx = setup_base_run(tmp_path, repo_root, with_result=True)
    run_root = ctx["run_root"]
    offer_info = create_offer(run_root, ctx["run_id"], icore_id=ctx["icore_id"], task_id=ctx["task_id"], result_id=ctx["result_id"], verify_ref=ctx["verify_ref"])
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
    insert_before_swarm_end(ctx["events"], "BRIDGE_IMPORT_ACCEPT", accept_payload)
    write_swarm_ledger(run_root / "ledger" / "swarm_ledger_v4.jsonl", ctx["events"])

    write_graph_report(
        run_root,
        ctx["run_id"],
        knowledge_edges=[{
            "importer_swarm_run_id": ctx["run_id"],
            "publisher_swarm_run_id": ctx["run_id"],
            "offer_id": import_info["offer_id"],
        }],
    )

    receipt = verify(run_root)
    assert receipt["verdict"] == "VALID"
