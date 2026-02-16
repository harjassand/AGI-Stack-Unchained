from __future__ import annotations

from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json, write_jsonl_line
from cdel.v3_2.barrier_ledger import compute_entry_hash
from cdel.v3_2.constants import require_constants
from cdel.v3_2.immutable_core import load_lock
from cdel.v3_2.swarm_ledger import compute_event_hash, compute_event_ref_hash
from cdel.v3_2.verify_rsi_swarm_v3 import compute_pack_hash, compute_swarm_run_id


def safe_id_fragment(value: str) -> str:
    if value.startswith("sha256:") and len(value) == 71:
        return f"sha256_{value.split(':', 1)[1]}"
    return value.replace(":", "_")


def build_valid_icore_receipt(repo_root: Path, lock_rel: str) -> dict[str, Any]:
    lock_path = repo_root / lock_rel
    lock = load_lock(lock_path)
    receipt = {
        "schema": "immutable_core_receipt_v1",
        "spec_version": lock.get("spec_version", "v2_3"),
        "verdict": "VALID",
        "reason": "OK",
        "repo_root_sha256": sha256_prefixed(str(repo_root).encode("utf-8")),
        "lock_path": str(lock_path.relative_to(repo_root)).replace("\\", "/"),
        "lock_id": lock["lock_id"],
        "core_id_expected": lock["core_id"],
        "core_id_observed": lock["core_id"],
        "mismatches": [],
        "receipt_head_hash": "__SELF__",
    }
    head = dict(receipt)
    head.pop("receipt_head_hash", None)
    receipt["receipt_head_hash"] = sha256_prefixed(canon_bytes(head))
    return receipt


def append_event(events: list[dict[str, Any]], event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    event = {
        "schema": "swarm_event_v4",
        "spec_version": "v3_2",
        "seq": 0,
        "prev_event_hash": "",
        "event_type": event_type,
        "payload": payload,
        "event_ref_hash": "__SELF__",
        "event_hash": "__SELF__",
    }
    events.append(event)
    return event


def insert_before_swarm_end(events: list[dict[str, Any]], event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    event = {
        "schema": "swarm_event_v4",
        "spec_version": "v3_2",
        "seq": 0,
        "prev_event_hash": "",
        "event_type": event_type,
        "payload": payload,
        "event_ref_hash": "__SELF__",
        "event_hash": "__SELF__",
    }
    if events and events[-1].get("event_type") == "SWARM_END":
        events.insert(len(events) - 1, event)
    else:
        events.append(event)
    return event


def write_swarm_ledger(path: Path, events: list[dict[str, Any]]) -> tuple[str, str]:
    path.write_text("", encoding="utf-8")
    prev = "GENESIS"
    seq = 1
    head_ref = prev
    for event in events:
        event["seq"] = seq
        event["prev_event_hash"] = prev
        # update SWARM_END payload with head ref hash placeholder
        if event.get("event_type") == "SWARM_END":
            payload = dict(event.get("payload") or {})
            payload["swarm_ledger_head_ref_hash"] = "__SELF__"
            event["payload"] = payload
        event["event_ref_hash"] = compute_event_ref_hash(event)
        if event.get("event_type") == "SWARM_END":
            payload = dict(event.get("payload") or {})
            payload["swarm_ledger_head_ref_hash"] = event["event_ref_hash"]
            event["payload"] = payload
            event["event_ref_hash"] = compute_event_ref_hash(event)
        event["event_hash"] = compute_event_hash(event)
        write_jsonl_line(path, event)
        prev = event["event_hash"]
        head_ref = event["event_ref_hash"]
        seq += 1
    return prev, head_ref


def write_barrier_ledger(path: Path, entries: list[dict[str, Any]]) -> str:
    path.write_text("", encoding="utf-8")
    prev = "GENESIS"
    seq = 1
    for entry in entries:
        entry["seq"] = seq
        entry["prev_entry_hash"] = prev
        entry["entry_hash"] = compute_entry_hash(entry)
        write_jsonl_line(path, entry)
        prev = entry["entry_hash"]
        seq += 1
    return prev


def write_graph_report(run_root: Path, run_id: str, knowledge_edges: list[dict[str, str]] | None = None) -> None:
    knowledge_edges = knowledge_edges or []
    report = {
        "schema": "swarm_graph_report_v1",
        "spec_version": "v3_2",
        "root_swarm_run_id": run_id,
        "nodes": [
            {
                "swarm_run_id": run_id,
                "parent_swarm_run_id": None,
                "depth": 0,
                "out_dir_relpath": ".",
            }
        ],
        "authority_edges": [],
        "knowledge_edges": sorted(
            knowledge_edges,
            key=lambda row: (row.get("importer_swarm_run_id"), row.get("publisher_swarm_run_id"), row.get("offer_id")),
        ),
    }
    write_canon_json(run_root / "diagnostics" / "swarm_graph_report_v1.json", report)


def build_base_pack() -> dict[str, Any]:
    return {
        "schema": "rsi_real_swarm_pack_v3",
        "spec_version": "v3_2",
        "pack_hash": "__SELF__",
        "swarm": {
            "commit_policy": "ROUND_COMMIT_V3_LATERAL",
            "num_agents": 1,
            "max_epochs": 1,
            "max_tasks_per_epoch": 4,
            "max_accepts_per_epoch": 1,
            "barrier_alpha_num": 19,
            "barrier_alpha_den": 20,
            "subswarm": {
                "enabled": False,
                "max_depth": 1,
                "max_total_nodes": 1,
                "max_children_per_parent_task": 1,
                "max_spawns_per_epoch": 0,
                "max_joins_per_epoch": 0,
                "join_timeout_epochs": 1,
                "child_defaults": {
                    "num_agents": 1,
                    "max_epochs": 1,
                    "max_tasks_per_epoch": 1,
                    "max_accepts_per_epoch": 0,
                },
            },
            "bridge": {
                "enabled": True,
                "exchange_root_path": "@ROOT/bridge_exchange",
                "max_offers_publish_per_epoch": 8,
                "max_import_accepts_per_epoch": 8,
                "publish_policy": "PUBLISH_VERIFIED_RESULTS_V1",
                "import_policy": "IMPORT_BY_SUBSCRIPTION_V1",
                "allowed_artifact_kinds": ["SUBPROOF_BUNDLE_V1"],
                "topic_regex": "^[A-Za-z0-9_.:/-]{1,64}$",
                "subscriptions_static": ["demo/lemmaA"],
            },
        },
        "agents": [
            {
                "agent_id": "agent_0001",
                "role": "PLANNER",
                "capabilities": ["TASK_DECOMP_V1"],
            }
        ],
        "task_enumerator": {"kind": "DEMO_ENUMERATOR_V3_LATERAL", "inputs_relpath": "inputs/swarm_inputs_v3.json"},
        "parent_link": {"present": False},
    }


def setup_base_run(tmp_path: Path, repo_root: Path, *, with_result: bool = True) -> dict[str, Any]:
    run_root = tmp_path / "run"
    (run_root / "diagnostics").mkdir(parents=True, exist_ok=True)
    (run_root / "ledger").mkdir(parents=True, exist_ok=True)
    (run_root / "tasks").mkdir(parents=True, exist_ok=True)
    (run_root / "results").mkdir(parents=True, exist_ok=True)
    (run_root / "agents").mkdir(parents=True, exist_ok=True)
    (run_root / "bridge_exchange" / "offers").mkdir(parents=True, exist_ok=True)
    (run_root / "bridge_exchange" / "blobs").mkdir(parents=True, exist_ok=True)

    constants = require_constants()
    lock_rel = constants.get("IMMUTABLE_CORE_LOCK_REL")
    icore_receipt = build_valid_icore_receipt(repo_root, lock_rel)
    write_canon_json(run_root / "diagnostics" / "immutable_core_receipt_v1.json", icore_receipt)

    agent_diag = run_root / "agents" / "agent_0001" / "diagnostics"
    agent_diag.mkdir(parents=True, exist_ok=True)
    write_canon_json(agent_diag / "immutable_core_receipt_v1.json", icore_receipt)

    pack = build_base_pack()
    pack_hash = compute_pack_hash(pack)
    pack["pack_hash"] = pack_hash
    pack_path = run_root / "pack.json"
    write_canon_json(pack_path, pack)

    run_id = compute_swarm_run_id(pack)

    # create inputs file (not used by verifier)
    (run_root / "inputs").mkdir(parents=True, exist_ok=True)
    write_canon_json(run_root / "inputs" / "swarm_inputs_v3.json", {"schema": "swarm_inputs_v3", "spec_version": "v3_2", "tasks": []})

    events: list[dict[str, Any]] = []
    append_event(
        events,
        "SWARM_INIT",
        {
            "swarm_run_id": run_id,
            "pack_relpath": "pack.json",
            "pack_hash": pack_hash,
            "icore_id_expected": icore_receipt.get("core_id_expected"),
            "num_agents": 1,
            "max_epochs": 1,
            "commit_policy": pack["swarm"]["commit_policy"],
        },
    )
    append_event(
        events,
        "AGENT_REGISTER",
        {
            "agent_id": "agent_0001",
            "role": "PLANNER",
            "capabilities": ["TASK_DECOMP_V1"],
            "agent_icore_receipt_relpath": "agents/agent_0001/diagnostics/immutable_core_receipt_v1.json",
            "core_id_observed": icore_receipt.get("core_id_observed"),
        },
    )
    append_event(
        events,
        "EPOCH_BEGIN",
        {"epoch_index": 1, "barrier_ledger_head_hash": "GENESIS", "frontier_state_head_hash": "GENESIS"},
    )

    task_id = None
    task_id_dir = None
    result_id = None
    verify_ref = None

    if with_result:
        task_id = sha256_prefixed(b"task")
        task_id_dir = safe_id_fragment(task_id)
        result_manifest_rel = f"results/{task_id_dir}/result_manifest_v2.json"
        (run_root / f"results/{task_id_dir}").mkdir(parents=True, exist_ok=True)

        manifest = {
            "schema": "swarm_result_manifest_v2",
            "spec_version": "v3_2",
            "task_id": task_id,
            "agent_id": "agent_0001",
            "status": "OK",
            "failure_reason": "NONE",
            "agent_receipt_relpath": f"agents/agent_0001/tasks/{task_id_dir}/diagnostics/rsi_agent_receipt_v1.json",
            "artifacts": [],
            "optional_barrier_proposal": {"present": False},
            "spawn_child": {"present": False},
        }
        result_id = sha256_prefixed(canon_bytes(manifest))
        write_canon_json(run_root / result_manifest_rel, manifest)

        task_diag = run_root / f"agents/agent_0001/tasks/{task_id_dir}/diagnostics"
        task_diag.mkdir(parents=True, exist_ok=True)
        write_canon_json(task_diag / "rsi_agent_receipt_v1.json", {"schema": "rsi_agent_receipt_v1", "spec_version": "v3_0", "agent_id": "agent_0001", "task_id": task_id, "result_id": result_id, "verdict": "OK", "reason": "OK"})
        write_canon_json(task_diag / "task_verify_receipt_v2.json", {"schema": "task_verify_receipt_v2", "spec_version": "v3_2", "verdict": "VALID"})

        append_event(
            events,
            "TASK_RESULT",
            {
                "epoch_index": 1,
                "task_id": task_id,
                "agent_id": "agent_0001",
                "result_id": result_id,
                "result_manifest_relpath": result_manifest_rel,
                "status": "OK",
            },
        )
        append_event(
            events,
            "RESULT_VERIFY",
            {
                "result_id": result_id,
                "verdict": "VALID",
                "reason": "OK",
                "verifier_receipt_relpath": f"agents/agent_0001/tasks/{task_id_dir}/diagnostics/task_verify_receipt_v2.json",
            },
        )

    append_event(
        events,
        "EPOCH_END",
        {"epoch_index": 1, "tasks_assigned": 0, "results_ok": 1 if with_result else 0, "results_valid": 1 if with_result else 0, "barrier_updates_accepted": 0},
    )
    append_event(
        events,
        "SWARM_END",
        {"verdict": "VALID", "reason": "OK", "swarm_ledger_head_ref_hash": "", "barrier_ledger_head_ref_hash": "GENESIS"},
    )

    swarm_head, swarm_head_ref = write_swarm_ledger(run_root / "ledger" / "swarm_ledger_v4.jsonl", events)

    if with_result:
        for event in events:
            if event.get("event_type") == "RESULT_VERIFY":
                verify_ref = event.get("event_ref_hash")
                break

    # empty barrier ledger
    write_barrier_ledger(run_root / "ledger" / "barrier_ledger_v5.jsonl", [])

    # initial graph report (no knowledge edges)
    write_graph_report(run_root, run_id)

    return {
        "run_root": run_root,
        "pack": pack,
        "run_id": run_id,
        "pack_hash": pack_hash,
        "icore_id": icore_receipt.get("core_id_expected"),
        "task_id": task_id,
        "task_id_dir": task_id_dir if with_result else None,
        "result_id": result_id,
        "verify_ref": verify_ref,
        "events": events,
    }


def create_offer(
    run_root: Path,
    run_id: str,
    icore_id: str,
    task_id: str,
    result_id: str,
    verify_ref: str,
    *,
    blob_bytes: bytes | None = None,
    root_swarm_run_id: str | None = None,
    icore_override: str | None = None,
    verify_ref_override: str | None = None,
) -> dict[str, Any]:
    blob_bytes = blob_bytes or b"bridge-blob"
    blob_sha = sha256_prefixed(blob_bytes)
    blob_hex = blob_sha.split(":", 1)[1]
    blob_path = run_root / "bridge_exchange" / "blobs" / f"sha256_{blob_hex}.blob"
    blob_path.write_bytes(blob_bytes)

    offer = {
        "schema": "bridge_offer_v1",
        "spec_version": "v3_2",
        "offer_id": "__SELF__",
        "offer_hash": "__SELF__",
        "root_swarm_run_id": root_swarm_run_id or run_id,
        "icore_id": icore_override or icore_id,
        "publisher": {
            "publisher_swarm_run_id": run_id,
            "publisher_depth": 0,
            "publisher_node_relpath": ".",
            "publisher_task_id": task_id,
            "publisher_result_id": result_id,
            "publisher_result_verify_event_ref_hash": verify_ref_override or verify_ref,
        },
        "topics": ["demo/lemmaA"],
        "artifacts": [
            {
                "kind": "SUBPROOF_BUNDLE_V1",
                "blob_sha256": blob_sha,
                "bytes": len(blob_bytes),
                "exchange_blob_path": f"@ROOT/bridge_exchange/blobs/sha256_{blob_hex}.blob",
            }
        ],
        "context_requirements": {"kind": "NONE", "required_barrier_head_ref_hash": "GENESIS"},
    }
    offer_id = sha256_prefixed(canon_bytes({k: v for k, v in offer.items() if k not in {"offer_id", "offer_hash"}}))
    offer["offer_id"] = offer_id
    offer["offer_hash"] = offer_id
    offer_hex = offer_id.split(":", 1)[1]
    offer_path = run_root / "bridge_exchange" / "offers" / f"sha256_{offer_hex}.bridge_offer_v1.json"
    write_canon_json(offer_path, offer)
    return {"offer": offer, "offer_id": offer_id, "blob_path": blob_path}


def create_import(run_root: Path, offer: dict[str, Any]) -> dict[str, Any]:
    offer_id = offer["offer_id"]
    offer_hex = offer_id.split(":", 1)[1]
    import_dir = run_root / "bridge" / "imports" / f"sha256_{offer_hex}"
    blobs_dir = import_dir / "blobs"
    blobs_dir.mkdir(parents=True, exist_ok=True)

    art = offer["artifacts"][0]
    blob_sha = art["blob_sha256"]
    blob_hex = blob_sha.split(":", 1)[1]
    local_rel = f"bridge/imports/sha256_{offer_hex}/blobs/sha256_{blob_hex}.blob"
    local_path = run_root / local_rel
    local_path.write_bytes((run_root / "bridge_exchange" / "blobs" / f"sha256_{blob_hex}.blob").read_bytes())

    imports = [{
        "kind": art["kind"],
        "blob_sha256": blob_sha,
        "local_blob_relpath": local_rel,
        "bytes": art["bytes"],
    }]
    imported_set_hash = sha256_prefixed(canon_bytes({"imports": imports}))

    manifest = {
        "schema": "bridge_import_manifest_v1",
        "spec_version": "v3_2",
        "offer_id": offer_id,
        "offer_hash": offer["offer_hash"],
        "imported_at_epoch_index": 1,
        "imports": imports,
        "imported_artifacts_set_hash": imported_set_hash,
    }
    manifest_rel = f"bridge/imports/sha256_{offer_hex}/bridge_import_manifest_v1.json"
    write_canon_json(run_root / manifest_rel, manifest)

    receipt = {
        "schema": "bridge_import_receipt_v1",
        "spec_version": "v3_2",
        "offer_id": offer_id,
        "verdict": "ACCEPTED",
        "checks": {
            "offer_schema_valid": True,
            "root_match": True,
            "icore_match": True,
            "blobs_present": True,
            "blob_hashes_valid": True,
            "publisher_provenance_valid": True,
        },
        "receipt_hash": "__SELF__",
    }
    head = dict(receipt)
    head.pop("receipt_hash", None)
    receipt["receipt_hash"] = sha256_prefixed(canon_bytes(head))
    receipt_rel = f"bridge/imports/sha256_{offer_hex}/bridge_import_receipt_v1.json"
    write_canon_json(run_root / receipt_rel, receipt)

    return {
        "offer_id": offer_id,
        "offer_hex": offer_hex,
        "import_dir_rel": f"bridge/imports/sha256_{offer_hex}",
        "manifest_rel": manifest_rel,
        "receipt_rel": receipt_rel,
        "imported_set_hash": imported_set_hash,
    }
