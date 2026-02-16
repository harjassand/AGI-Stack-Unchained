from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from cdel.v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json, write_jsonl_line
from cdel.v3_3.barrier_ledger import compute_entry_hash
from cdel.v3_3.constants import require_constants
from cdel.v3_3.immutable_core import load_lock
from cdel.v3_3.meta_ledger import (
    apply_meta_updates,
    build_meta_block,
    compute_assertion_id,
    compute_update_id,
)
from cdel.v3_3.swarm_ledger import compute_event_hash, compute_event_ref_hash
from cdel.v3_3.verify_rsi_swarm_v4 import compute_pack_hash, compute_swarm_run_id


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
        "schema": "swarm_event_v5",
        "spec_version": "v3_3",
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
        "schema": "swarm_event_v5",
        "spec_version": "v3_3",
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


def write_graph_report(
    run_root: Path,
    run_id: str,
    knowledge_edges: list[dict[str, str]] | None = None,
    meta_edges: list[dict[str, Any]] | None = None,
) -> None:
    knowledge_edges = knowledge_edges or []
    meta_edges = meta_edges or []
    report = {
        "schema": "swarm_graph_report_v2",
        "spec_version": "v3_3",
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
            key=lambda row: (
                row.get("importer_swarm_run_id"),
                row.get("publisher_swarm_run_id"),
                row.get("offer_id"),
            ),
        ),
        "meta_edges": sorted(
            meta_edges,
            key=lambda row: (
                row.get("publisher_swarm_run_id"),
                row.get("update_id"),
                int(row.get("meta_epoch_index", 0)),
            ),
        ),
    }
    write_canon_json(run_root / "diagnostics" / "swarm_graph_report_v2.json", report)


def build_base_pack(
    *,
    max_epochs: int = 1,
    num_agents: int = 1,
    meta_enabled: bool = True,
    subscriptions_static: list[str] | None = None,
    meta_cfg_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    subs_static = subscriptions_static or []
    meta_cfg = {
        "enabled": meta_enabled,
        "exchange_root_path": "@ROOT/meta_exchange",
        "consensus_policy": "HOLO_CONSENSUS_V1",
        "max_updates_publish_per_node_per_epoch": 8,
        "max_updates_apply_per_epoch": 256,
        "allowed_update_kinds": ["KNOWLEDGE_ASSERTION_ADD_V1", "POLICY_PATCH_V1"],
        "topic_regex": "^[A-Za-z0-9_.:/-]{1,64}$",
        "knowledge_limits": {
            "max_assertions_per_update": 64,
            "max_total_assertions": 4096,
            "max_evidence_refs_per_assertion": 4,
        },
        "policy_limits": {
            "allowed_keys": ["bridge.subscriptions_add", "task.priority_boost"],
            "max_subscriptions_add_total": 128,
            "max_priority_topics": 256,
            "priority_min": 0,
            "priority_max": 100,
        },
        "omega_min_subscriptions": 0,
        "omega_stability_epochs": 0,
    }
    if meta_cfg_override:
        meta_cfg.update(meta_cfg_override)

    pack = {
        "schema": "rsi_real_swarm_pack_v4",
        "spec_version": "v3_3",
        "pack_hash": "__SELF__",
        "swarm": {
            "commit_policy": "ROUND_COMMIT_V4_HOLOGRAPHIC",
            "num_agents": num_agents,
            "max_epochs": max_epochs,
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
                "subscriptions_static": subs_static,
            },
            "meta": meta_cfg,
        },
        "agents": [
            {
                "agent_id": "agent_0001",
                "role": "PLANNER",
                "capabilities": ["TASK_DECOMP_V1"],
            }
        ],
        "task_enumerator": {
            "kind": "DEMO_ENUMERATOR_V3_LATERAL",
            "inputs_relpath": "inputs/swarm_inputs_v3.json",
        },
        "parent_link": {"present": False},
    }
    return pack


def setup_base_run(
    tmp_path: Path,
    repo_root: Path,
    *,
    max_epochs: int = 1,
    with_result: bool = True,
    verify_verdict: str = "VALID",
    meta_enabled: bool = True,
    subscriptions_static: list[str] | None = None,
) -> dict[str, Any]:
    run_root = tmp_path / "run"
    (run_root / "diagnostics").mkdir(parents=True, exist_ok=True)
    (run_root / "ledger").mkdir(parents=True, exist_ok=True)
    (run_root / "tasks").mkdir(parents=True, exist_ok=True)
    (run_root / "results").mkdir(parents=True, exist_ok=True)
    (run_root / "agents").mkdir(parents=True, exist_ok=True)
    (run_root / "bridge_exchange" / "offers").mkdir(parents=True, exist_ok=True)
    (run_root / "bridge_exchange" / "blobs").mkdir(parents=True, exist_ok=True)
    if meta_enabled:
        (run_root / "meta_exchange" / "updates").mkdir(parents=True, exist_ok=True)
        (run_root / "meta_exchange" / "blocks").mkdir(parents=True, exist_ok=True)
        (run_root / "meta_exchange" / "state").mkdir(parents=True, exist_ok=True)
        (run_root / "meta_exchange" / "policy").mkdir(parents=True, exist_ok=True)

    constants = require_constants()
    lock_rel = constants.get("IMMUTABLE_CORE_LOCK_REL")
    icore_receipt = build_valid_icore_receipt(repo_root, lock_rel)
    write_canon_json(run_root / "diagnostics" / "immutable_core_receipt_v1.json", icore_receipt)

    agent_diag = run_root / "agents" / "agent_0001" / "diagnostics"
    agent_diag.mkdir(parents=True, exist_ok=True)
    write_canon_json(agent_diag / "immutable_core_receipt_v1.json", icore_receipt)

    pack = build_base_pack(
        max_epochs=max_epochs,
        num_agents=1,
        meta_enabled=meta_enabled,
        subscriptions_static=subscriptions_static,
    )
    pack_hash = compute_pack_hash(pack)
    pack["pack_hash"] = pack_hash
    pack_path = run_root / "pack.json"
    write_canon_json(pack_path, pack)

    run_id = compute_swarm_run_id(pack)

    # create inputs file (not used by verifier)
    (run_root / "inputs").mkdir(parents=True, exist_ok=True)
    write_canon_json(run_root / "inputs" / "swarm_inputs_v3.json", {"schema": "swarm_inputs_v3", "spec_version": "v3_3", "tasks": []})

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
            "max_epochs": max_epochs,
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

    task_id = None
    task_id_dir = None
    result_id = None
    verify_ref = None

    for epoch in range(1, max_epochs + 1):
        append_event(
            events,
            "EPOCH_BEGIN",
            {"epoch_index": epoch, "barrier_ledger_head_hash": "GENESIS", "frontier_state_head_hash": "GENESIS"},
        )

        if with_result and epoch == 1:
            task_id = sha256_prefixed(b"task")
            task_id_dir = safe_id_fragment(task_id)
            result_manifest_rel = f"results/{task_id_dir}/result_manifest_v2.json"
            (run_root / f"results/{task_id_dir}").mkdir(parents=True, exist_ok=True)

            manifest = {
                "schema": "swarm_result_manifest_v2",
                "spec_version": "v3_3",
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
            write_canon_json(
                task_diag / "rsi_agent_receipt_v1.json",
                {
                    "schema": "rsi_agent_receipt_v1",
                    "spec_version": "v3_0",
                    "agent_id": "agent_0001",
                    "task_id": task_id,
                    "result_id": result_id,
                    "verdict": "OK",
                    "reason": "OK",
                },
            )
            write_canon_json(
                task_diag / "task_verify_receipt_v2.json",
                {"schema": "task_verify_receipt_v2", "spec_version": "v3_3", "verdict": verify_verdict},
            )

            append_event(
                events,
                "TASK_RESULT",
                {
                    "epoch_index": epoch,
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
                    "verdict": verify_verdict,
                    "reason": "OK",
                    "verifier_receipt_relpath": f"agents/agent_0001/tasks/{task_id_dir}/diagnostics/task_verify_receipt_v2.json",
                },
            )

        append_event(
            events,
            "EPOCH_END",
            {
                "epoch_index": epoch,
                "tasks_assigned": 0,
                "results_ok": 1 if with_result and epoch == 1 else 0,
                "results_valid": 1 if with_result and epoch == 1 and verify_verdict == "VALID" else 0,
                "barrier_updates_accepted": 0,
            },
        )

    append_event(
        events,
        "SWARM_END",
        {
            "verdict": "VALID",
            "reason": "OK",
            "swarm_ledger_head_ref_hash": "",
            "barrier_ledger_head_ref_hash": "GENESIS",
        },
    )

    swarm_head, swarm_head_ref = write_swarm_ledger(run_root / "ledger" / "swarm_ledger_v5.jsonl", events)

    if with_result:
        for event in events:
            if event.get("event_type") == "RESULT_VERIFY":
                verify_ref = event.get("event_ref_hash")
                break

    # empty barrier ledger
    write_barrier_ledger(run_root / "ledger" / "barrier_ledger_v5.jsonl", [])

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
        "swarm_head_ref": swarm_head_ref,
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
    return {"offer": offer, "offer_id": offer_id, "offer_hex": offer_hex, "blob_path": blob_path}


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


def build_policy_update(
    *,
    root_run_id: str,
    icore_id: str,
    published_epoch: int,
    publisher: dict[str, Any],
    topics: list[str],
    policy_delta: dict[str, Any],
) -> dict[str, Any]:
    body = {
        "schema": "meta_update_v1",
        "spec_version": "v3_3",
        "root_swarm_run_id": root_run_id,
        "icore_id": icore_id,
        "published_at_epoch_index": published_epoch,
        "publisher": publisher,
        "topics": topics,
        "update_kind": "POLICY_PATCH_V1",
        "payload": {"policy_delta": policy_delta},
    }
    update_id = compute_update_id(body)
    update = dict(body)
    update["update_id"] = update_id
    update["update_hash"] = update_id
    return update


def build_knowledge_update(
    *,
    root_run_id: str,
    icore_id: str,
    published_epoch: int,
    publisher: dict[str, Any],
    topics: list[str],
    assertions: list[dict[str, Any]],
) -> dict[str, Any]:
    normalized = []
    for assertion in assertions:
        entry = dict(assertion)
        if "assertion_id" not in entry:
            entry["assertion_id"] = compute_assertion_id(entry)
        normalized.append(entry)
    body = {
        "schema": "meta_update_v1",
        "spec_version": "v3_3",
        "root_swarm_run_id": root_run_id,
        "icore_id": icore_id,
        "published_at_epoch_index": published_epoch,
        "publisher": publisher,
        "topics": topics,
        "update_kind": "KNOWLEDGE_ASSERTION_ADD_V1",
        "payload": {"assertions": normalized},
    }
    update_id = compute_update_id(body)
    update = dict(body)
    update["update_id"] = update_id
    update["update_hash"] = update_id
    return update


def write_meta_update(run_root: Path, update: dict[str, Any]) -> Path:
    update_id = update.get("update_id")
    update_hex = update_id.split(":", 1)[1]
    path = run_root / "meta_exchange" / "updates" / f"sha256_{update_hex}.meta_update_v1.json"
    write_canon_json(path, update)
    return path


def meta_evidence_validator(run_root: Path, ref: dict[str, Any]) -> bool:
    if ref.get("kind") != "BRIDGE_OFFER_ARTIFACT":
        return False
    offer_id = ref.get("offer_id")
    blob_sha = ref.get("blob_sha256")
    if not isinstance(offer_id, str) or not isinstance(blob_sha, str):
        return False
    if not offer_id.startswith("sha256:") or not blob_sha.startswith("sha256:"):
        return False
    offer_hex = offer_id.split(":", 1)[1]
    offer_path = run_root / "bridge_exchange" / "offers" / f"sha256_{offer_hex}.bridge_offer_v1.json"
    if not offer_path.exists():
        return False
    try:
        offer = load_canon_json(offer_path)
    except Exception:
        return False
    if not isinstance(offer, dict):
        return False
    expected_offer_id = sha256_prefixed(canon_bytes({k: v for k, v in offer.items() if k not in {"offer_id", "offer_hash"}}))
    if offer.get("offer_id") != expected_offer_id or offer.get("offer_hash") != expected_offer_id:
        return False
    artifacts = offer.get("artifacts")
    if not isinstance(artifacts, list):
        return False
    if blob_sha not in {art.get("blob_sha256") for art in artifacts if isinstance(art, dict)}:
        return False
    blob_hex = blob_sha.split(":", 1)[1]
    blob_path = run_root / "bridge_exchange" / "blobs" / f"sha256_{blob_hex}.blob"
    if not blob_path.exists():
        return False
    if sha256_prefixed(blob_path.read_bytes()) != blob_sha:
        return False
    return True


def build_meta_chain(
    *,
    run_root: Path,
    root_run_id: str,
    icore_id: str,
    max_epochs: int,
    updates_by_epoch: dict[int, list[dict[str, Any]]],
    meta_cfg: dict[str, Any],
    evidence_validator: Callable[[dict[str, Any]], bool] | None = None,
) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    prev_state = {"state_hash": "GENESIS", "knowledge_graph": {"assertions": []}}
    prev_policy = {"policy_hash": "GENESIS", "policy": {"bridge": {"subscriptions_add": []}, "task": {"priority": []}}}
    prev_block_id = "GENESIS"

    blocks: dict[int, dict[str, Any]] = {}
    states: dict[int, dict[str, Any]] = {}
    policies: dict[int, dict[str, Any]] = {}

    allowed_kinds = set(meta_cfg.get("allowed_update_kinds") or [])
    knowledge_limits = meta_cfg.get("knowledge_limits") if isinstance(meta_cfg.get("knowledge_limits"), dict) else {}
    policy_limits = meta_cfg.get("policy_limits") if isinstance(meta_cfg.get("policy_limits"), dict) else {}
    max_apply = int(meta_cfg.get("max_updates_apply_per_epoch", 0))

    for epoch in range(max_epochs):
        updates = updates_by_epoch.get(epoch, [])
        new_state, new_policy, accepted, rejected, stats = apply_meta_updates(
            root_swarm_run_id=root_run_id,
            icore_id=icore_id,
            meta_epoch_index=epoch,
            prev_state=prev_state,
            prev_policy=prev_policy,
            updates=updates,
            knowledge_limits=knowledge_limits,
            policy_limits=policy_limits,
            allowed_update_kinds=allowed_kinds,
            max_updates_apply=max_apply,
            evidence_validator=evidence_validator,
        )
        state_hash = new_state.get("state_hash")
        policy_hash = new_policy.get("policy_hash")
        state_hex = state_hash.split(":", 1)[1]
        policy_hex = policy_hash.split(":", 1)[1]
        state_path = f"@ROOT/meta_exchange/state/sha256_{state_hex}.meta_state_v1.json"
        policy_path = f"@ROOT/meta_exchange/policy/sha256_{policy_hex}.meta_policy_v1.json"
        write_canon_json(run_root / "meta_exchange" / "state" / f"sha256_{state_hex}.meta_state_v1.json", new_state)
        write_canon_json(run_root / "meta_exchange" / "policy" / f"sha256_{policy_hex}.meta_policy_v1.json", new_policy)

        block = build_meta_block(
            root_swarm_run_id=root_run_id,
            icore_id=icore_id,
            meta_epoch_index=epoch,
            prev_meta_block_id=prev_block_id,
            accepted_update_ids=accepted,
            rejected_updates=rejected,
            meta_state_hash=state_hash,
            meta_state_path=state_path,
            meta_policy_hash=policy_hash,
            meta_policy_path=policy_path,
            stats=stats,
        )
        block_hex = block.get("meta_block_id").split(":", 1)[1]
        write_canon_json(run_root / "meta_exchange" / "blocks" / f"sha256_{block_hex}.meta_block_v1.json", block)

        blocks[epoch] = block
        states[epoch] = new_state
        policies[epoch] = new_policy
        prev_state = new_state
        prev_policy = new_policy
        prev_block_id = block.get("meta_block_id")

    return blocks, states, policies


def compute_meta_edges(
    derived_blocks: dict[int, dict[str, Any]],
    update_publishers: dict[str, str],
) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for epoch, block in derived_blocks.items():
        for update_id in block.get("accepted_update_ids", []) or []:
            publisher = update_publishers.get(update_id)
            if not publisher:
                continue
            edges.append(
                {
                    "publisher_swarm_run_id": publisher,
                    "update_id": update_id,
                    "meta_block_id": block.get("meta_block_id"),
                    "meta_epoch_index": epoch,
                }
            )
    return edges


def write_meta_ledger_report(
    *,
    run_root: Path,
    root_run_id: str,
    icore_id: str,
    max_epochs: int,
    meta_cfg: dict[str, Any],
    derived_blocks: dict[int, dict[str, Any]],
    derived_states: dict[int, dict[str, Any]],
    derived_policies: dict[int, dict[str, Any]],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    meta_blocks = len(derived_blocks)
    seen_updates: set[str] = set()
    for event in events:
        if event.get("event_type") != "META_UPDATE_PUBLISH":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        update_id = payload.get("update_id")
        if isinstance(update_id, str):
            seen_updates.add(update_id)
    meta_updates_published = len(seen_updates)

    accepted = sum(len(b.get("accepted_update_ids", []) or []) for b in derived_blocks.values())
    rejected = sum(len(b.get("rejected_updates", []) or []) for b in derived_blocks.values())

    final_block = derived_blocks.get(max_epochs - 1)
    final_meta_block_id = final_block.get("meta_block_id") if isinstance(final_block, dict) else "GENESIS"
    final_meta_state_hash = derived_states.get(max_epochs - 1, {}).get("state_hash", "GENESIS")
    final_meta_policy_hash = derived_policies.get(max_epochs - 1, {}).get("policy_hash", "GENESIS")

    omega_min = int(meta_cfg.get("omega_min_subscriptions", 0))
    omega_stability = int(meta_cfg.get("omega_stability_epochs", 0))
    subscriptions = []
    if isinstance(final_meta_policy_hash, str) and final_meta_policy_hash != "GENESIS":
        policy_path = run_root / "meta_exchange" / "policy" / f"sha256_{final_meta_policy_hash.split(':', 1)[1]}.meta_policy_v1.json"
        policy = load_canon_json(policy_path)
        if isinstance(policy, dict):
            bridge = policy.get("policy") if isinstance(policy.get("policy"), dict) else {}
            bridge = bridge.get("bridge") if isinstance(bridge.get("bridge"), dict) else {}
            subscriptions = bridge.get("subscriptions_add") if isinstance(bridge.get("subscriptions_add"), list) else []
    subs_ok = len(subscriptions) >= omega_min

    stable = True
    if omega_stability:
        start_idx = max(max_epochs - omega_stability, 0)
        for idx in range(start_idx, max_epochs):
            block = derived_blocks.get(idx)
            if not block or block.get("stats", {}).get("accepted_updates", 0) != 0:
                stable = False
                break

    declared = []
    for event in events:
        if event.get("event_type") != "META_HEAD_DECLARE":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if payload.get("declared_at_epoch_index") == max_epochs:
            declared.append(payload.get("meta_block_id"))
    declared_ok = bool(declared) and all(val == declared[0] for val in declared) and declared[0] == final_meta_block_id

    report = {
        "schema": "meta_ledger_report_v1",
        "spec_version": "v3_3",
        "root_swarm_run_id": root_run_id,
        "icore_id": icore_id,
        "max_epochs": max_epochs,
        "meta_blocks": meta_blocks,
        "meta_updates_published": meta_updates_published,
        "meta_updates_accepted": accepted,
        "meta_updates_rejected": rejected,
        "final_meta_block_id": final_meta_block_id or "GENESIS",
        "final_meta_state_hash": final_meta_state_hash or "GENESIS",
        "final_meta_policy_hash": final_meta_policy_hash or "GENESIS",
        "omega_ready": bool(declared_ok and subs_ok and stable),
    }
    write_canon_json(run_root / "diagnostics" / "meta_ledger_report_v1.json", report)
    return report
