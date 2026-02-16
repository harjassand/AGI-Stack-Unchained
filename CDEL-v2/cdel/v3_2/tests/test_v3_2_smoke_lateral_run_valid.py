from __future__ import annotations

from cdel.v1_7r.canon import canon_bytes, sha256_prefixed, write_canon_json
from cdel.v3_2.verify_rsi_swarm_v3 import verify

from .utils import (
    create_import,
    create_offer,
    insert_before_swarm_end,
    setup_base_run,
    write_barrier_ledger,
    write_graph_report,
    write_swarm_ledger,
)


def test_v3_2_smoke_lateral_run_valid(tmp_path, repo_root) -> None:
    ctx = setup_base_run(tmp_path, repo_root, with_result=True)
    run_root = ctx["run_root"]
    offer_info = create_offer(run_root, ctx["run_id"], icore_id=ctx["icore_id"], task_id=ctx["task_id"], result_id=ctx["result_id"], verify_ref=ctx["verify_ref"])
    import_info = create_import(run_root, offer_info["offer"])

    proposal_rel = f"agents/agent_0001/tasks/{ctx['task_id_dir']}/artifacts/barrier_entry_proposal_v1.json"
    proposal_payload = {
        "schema": "barrier_entry_proposal_v1",
        "spec_version": "v3_2",
        "barrier_prev": 100,
        "barrier_next": 90,
        "recovery_bundle_id": sha256_prefixed(b"proposal"),
        "receipt_relpath": f"agents/agent_0001/tasks/{ctx['task_id_dir']}/diagnostics/rsi_agent_receipt_v1.json",
    }
    proposal_path = run_root / proposal_rel
    proposal_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(proposal_path, proposal_payload)
    proposal_id = sha256_prefixed(canon_bytes(proposal_payload))

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
    insert_before_swarm_end(
        ctx["events"],
        "BARRIER_UPDATE_PROPOSE",
        {
            "proposal_id": proposal_id,
            "result_id": ctx["result_id"],
            "base_barrier_head_hash": "GENESIS",
            "proposed_barrier_entry_relpath": proposal_rel,
        },
    )
    barrier_accept_payload = {
        "proposal_id": proposal_id,
        "accepted": True,
        "barrier_entry_hash": "sha256:" + "0" * 64,
        "barrier_ledger_head_ref_hash_new": "sha256:" + "0" * 64,
    }
    insert_before_swarm_end(ctx["events"], "BARRIER_UPDATE_ACCEPT", barrier_accept_payload)
    # write ledger once to compute event_ref_hash for import accept
    write_swarm_ledger(run_root / "ledger" / "swarm_ledger_v4.jsonl", ctx["events"])
    import_ref = None
    accept_ref = None
    for event in ctx["events"]:
        if event.get("event_type") == "BRIDGE_IMPORT_ACCEPT":
            import_ref = event.get("event_ref_hash")
        if event.get("event_type") == "BARRIER_UPDATE_ACCEPT":
            accept_ref = event.get("event_ref_hash")

    # Barrier entry referencing bridge import (not stale)
    barrier_entry = {
        "schema": "barrier_entry_v5",
        "spec_version": "v3_2",
        "seq": 1,
        "prev_entry_hash": "GENESIS",
        "swarm_event_ref_hash": accept_ref,
        "agent_id": "agent_0001",
        "task_id": ctx["task_id"],
        "result_id": ctx["result_id"],
        "barrier_metric": {"name": "env_steps_total", "prev": 100, "next": 90},
        "evidence": {
            "receipt_relpath": f"agents/agent_0001/tasks/{ctx['task_id_dir']}/diagnostics/rsi_agent_receipt_v1.json",
            "local_provenance": {"present": False},
            "subswarm_provenance": {"present": False},
            "bridge_provenance": {
                "present": True,
                "offer_id": import_info["offer_id"],
                "import_accept_event_ref_hash": import_ref,
                "imported_artifacts_set_hash": import_info["imported_set_hash"],
                "staleness": {"is_stale": False, "reason": "OK"},
            },
        },
        "entry_hash": "__SELF__",
    }
    barrier_head = write_barrier_ledger(run_root / "ledger" / "barrier_ledger_v5.jsonl", [barrier_entry])

    for event in ctx["events"]:
        if event.get("event_type") == "BARRIER_UPDATE_ACCEPT":
            event["payload"]["barrier_entry_hash"] = barrier_head
            event["payload"]["barrier_ledger_head_ref_hash_new"] = barrier_head
        if event.get("event_type") == "SWARM_END":
            event["payload"]["barrier_ledger_head_ref_hash"] = barrier_head
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
