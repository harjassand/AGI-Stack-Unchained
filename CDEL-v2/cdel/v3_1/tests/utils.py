from __future__ import annotations

from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json, write_jsonl_line
from cdel.v3_1.barrier_ledger import compute_entry_hash
from cdel.v3_1.immutable_core import load_lock
from cdel.v3_1.swarm_ledger import compute_event_hash, compute_event_ref_hash
from cdel.v3_1.verify_rsi_swarm_v2 import compute_pack_hash, compute_swarm_run_id


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
    seq = len(events) + 1
    prev_hash = events[-1]["event_hash"] if events else "GENESIS"
    event = {
        "schema": "swarm_event_v2",
        "spec_version": "v3_1",
        "seq": seq,
        "prev_event_hash": prev_hash,
        "event_type": event_type,
        "payload": payload,
        "event_ref_hash": "__SELF__",
        "event_hash": "__SELF__",
    }
    if event_type == "SWARM_END":
        # compute ref hash without head fields then set
        ref = compute_event_ref_hash(event)
        payload = dict(payload)
        payload["swarm_ledger_head_ref_hash"] = ref
        event["payload"] = payload
    event["event_ref_hash"] = compute_event_ref_hash(event)
    event["event_hash"] = compute_event_hash(event)
    events.append(event)
    return event


def write_swarm_ledger(path: Path, events: list[dict[str, Any]]) -> str:
    path.write_text("", encoding="utf-8")
    prev = "GENESIS"
    seq = 1
    for event in events:
        event["seq"] = seq
        event["prev_event_hash"] = prev
        event["event_ref_hash"] = compute_event_ref_hash(event)
        if event.get("event_type") == "SWARM_END":
            payload = dict(event.get("payload") or {})
            payload["swarm_ledger_head_ref_hash"] = event["event_ref_hash"]
            event["payload"] = payload
            event["event_ref_hash"] = compute_event_ref_hash(event)
        event["event_hash"] = compute_event_hash(event)
        write_jsonl_line(path, event)
        prev = event["event_hash"]
        seq += 1
    return prev


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


def build_valid_swarm_run(
    tmp_path: Path,
    repo_root: Path,
    root_max_total_nodes: int | None = None,
    root_max_depth: int | None = None,
    child_depth: int = 1,
) -> dict[str, Any]:
    run_root = tmp_path / "run"
    (run_root / "diagnostics").mkdir(parents=True, exist_ok=True)
    (run_root / "ledger").mkdir(parents=True, exist_ok=True)
    (run_root / "tasks").mkdir(parents=True, exist_ok=True)
    (run_root / "results").mkdir(parents=True, exist_ok=True)
    (run_root / "agents").mkdir(parents=True, exist_ok=True)

    lock_rel = "meta-core/meta_constitution/v3_1/immutable_core_lock_v1.json"
    icore_receipt = build_valid_icore_receipt(repo_root, lock_rel)
    write_canon_json(run_root / "diagnostics" / "immutable_core_receipt_v1.json", icore_receipt)

    agents = [
        {"agent_id": "agent_0001", "role": "PLANNER", "capabilities": ["TASK_DECOMP_V1", "SUBSWARM_SPAWN_V1", "SUBSWARM_JOIN_V1"]},
        {"agent_id": "agent_0002", "role": "PATCHER", "capabilities": ["CSI_PATCH_PROPOSE_V1"]},
    ]
    for agent in agents:
        agent_diag = run_root / "agents" / agent["agent_id"] / "diagnostics"
        agent_diag.mkdir(parents=True, exist_ok=True)
        write_canon_json(agent_diag / "immutable_core_receipt_v1.json", icore_receipt)

    max_total_nodes = 8 if root_max_total_nodes is None else root_max_total_nodes
    max_depth = 4 if root_max_depth is None else root_max_depth
    pack = {
        "schema": "rsi_real_swarm_pack_v2",
        "spec_version": "v3_1",
        "pack_hash": "__SELF__",
        "swarm": {
            "commit_policy": "ROUND_COMMIT_V2_RECURSIVE",
            "num_agents": 2,
            "max_epochs": 2,
            "max_tasks_per_epoch": 4,
            "max_accepts_per_epoch": 1,
            "barrier_alpha_num": 19,
            "barrier_alpha_den": 20,
            "subswarm": {
                "enabled": True,
                "max_depth": max_depth,
                "max_total_nodes": max_total_nodes,
                "max_children_per_parent_task": 4,
                "max_spawns_per_epoch": 2,
                "max_joins_per_epoch": 2,
                "join_retry_policy": "JOIN_RETRY_V1",
                "join_timeout_epochs": 4,
                "child_defaults": {
                    "num_agents": 1,
                    "max_epochs": 1,
                    "max_tasks_per_epoch": 2,
                    "max_accepts_per_epoch": 1,
                },
            },
        },
        "agents": agents,
        "task_enumerator": {
            "kind": "DEMO_ENUMERATOR_V2_RECURSIVE",
            "inputs_relpath": "inputs/swarm_inputs_v2.json",
        },
        "parent_link": {"present": False},
    }
    pack_hash = compute_pack_hash(pack)
    pack["pack_hash"] = pack_hash
    pack_path = run_root / "pack.json"
    write_canon_json(pack_path, pack)

    run_id = compute_swarm_run_id(pack)

    # Build tasks
    task_specs = []
    task_spawn = {
        "schema": "swarm_task_spec_v2",
        "spec_version": "v3_1",
        "task_type": "SUBPROOF_V1",
        "domain": "formal_math_v1",
        "required_capabilities": ["TASK_DECOMP_V1"],
        "base_barrier_head_hash": "GENESIS",
        "base_frontier_state_head_hash": "GENESIS",
        "inputs": {"problem_id": "sha256:01", "problem_payload_relpath": "inputs/problem_spawn.json"},
        "budgets": {"work_cost_limit": 2000, "max_attempts": 1},
    }
    task_barrier = {
        "schema": "swarm_task_spec_v2",
        "spec_version": "v3_1",
        "task_type": "CSI_PATCH_PROPOSE_V1",
        "domain": "python_ut_v1",
        "required_capabilities": ["CSI_PATCH_PROPOSE_V1"],
        "base_barrier_head_hash": "GENESIS",
        "base_frontier_state_head_hash": "GENESIS",
        "inputs": {"problem_id": "sha256:02", "problem_payload_relpath": "inputs/problem_barrier.json"},
        "budgets": {"work_cost_limit": 2000, "max_attempts": 1},
    }
    for spec in (task_spawn, task_barrier):
        task_id = sha256_prefixed(canon_bytes(spec))
        task_dir = run_root / "tasks" / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        write_canon_json(task_dir / "task_spec_v2.json", spec)
        task_specs.append((task_id, spec, f"tasks/{task_id}/task_spec_v2.json"))

    # Child pack
    child_pack = {
        "schema": "rsi_real_swarm_pack_v2",
        "spec_version": "v3_1",
        "pack_hash": "__SELF__",
        "swarm": {
            "commit_policy": "ROUND_COMMIT_V2_RECURSIVE",
            "num_agents": 1,
            "max_epochs": 1,
            "max_tasks_per_epoch": 2,
            "max_accepts_per_epoch": 1,
            "barrier_alpha_num": 19,
            "barrier_alpha_den": 20,
            "subswarm": {
                "enabled": True,
                "max_depth": 2,
                "max_total_nodes": 4,
                "max_children_per_parent_task": 2,
                "max_spawns_per_epoch": 1,
                "max_joins_per_epoch": 1,
                "join_retry_policy": "JOIN_RETRY_V1",
                "join_timeout_epochs": 2,
                "child_defaults": {
                    "num_agents": 1,
                    "max_epochs": 1,
                    "max_tasks_per_epoch": 1,
                    "max_accepts_per_epoch": 1,
                },
            },
        },
        "agents": [{"agent_id": "agent_0001", "role": "PROVER", "capabilities": ["SUBPROOF_V1"]}],
        "task_enumerator": {
            "kind": "DEMO_ENUMERATOR_V2_RECURSIVE",
            "inputs_relpath": "inputs/child_inputs_v2.json",
        },
        "parent_link": {
            "present": True,
            "schema": "subswarm_parent_link_v1",
            "spec_version": "v3_1",
            "parent_swarm_run_id": run_id,
            "parent_task_id": task_specs[0][0],
            "sponsor_agent_id": "agent_0001",
            "spawn_event_ref_hash": "sha256:" + "0" * 64,
            "depth": child_depth,
            "subswarm_slot": 1,
        },
    }
    child_pack_hash = compute_pack_hash(child_pack)
    child_pack["pack_hash"] = child_pack_hash
    child_run_id = compute_swarm_run_id(child_pack)
    child_dir = run_root / "agents" / "agent_0001" / "subswarms" / f"sha256_{child_run_id.split(':',1)[1]}"
    child_dir.mkdir(parents=True, exist_ok=True)
    write_canon_json(child_dir / "subswarm_pack_v2.json", child_pack)

    # child run ledger
    (child_dir / "diagnostics").mkdir(parents=True, exist_ok=True)
    (child_dir / "ledger").mkdir(parents=True, exist_ok=True)
    (child_dir / "tasks").mkdir(parents=True, exist_ok=True)
    (child_dir / "results").mkdir(parents=True, exist_ok=True)
    (child_dir / "agents").mkdir(parents=True, exist_ok=True)

    write_canon_json(child_dir / "diagnostics" / "immutable_core_receipt_v1.json", icore_receipt)
    agent_diag = child_dir / "agents" / "agent_0001" / "diagnostics"
    agent_diag.mkdir(parents=True, exist_ok=True)
    write_canon_json(agent_diag / "immutable_core_receipt_v1.json", icore_receipt)

    child_task = {
        "schema": "swarm_task_spec_v2",
        "spec_version": "v3_1",
        "task_type": "SUBPROOF_V1",
        "domain": "formal_math_v1",
        "required_capabilities": ["SUBPROOF_V1"],
        "base_barrier_head_hash": "GENESIS",
        "base_frontier_state_head_hash": "GENESIS",
        "inputs": {"problem_id": "sha256:03", "problem_payload_relpath": "inputs/child_problem.json"},
        "budgets": {"work_cost_limit": 1000, "max_attempts": 1},
    }
    child_task_id = sha256_prefixed(canon_bytes(child_task))
    child_task_dir = child_dir / "tasks" / child_task_id
    child_task_dir.mkdir(parents=True, exist_ok=True)
    write_canon_json(child_task_dir / "task_spec_v2.json", child_task)

    # child result
    child_manifest = {
        "schema": "swarm_result_manifest_v2",
        "spec_version": "v3_1",
        "task_id": child_task_id,
        "agent_id": "agent_0001",
        "status": "OK",
        "failure_reason": "NONE",
        "agent_receipt_relpath": f"agents/agent_0001/tasks/{child_task_id}/diagnostics/rsi_agent_receipt_v1.json",
        "artifacts": [],
        "optional_barrier_proposal": {"present": False},
        "spawn_child": {"present": False},
    }
    child_result_id = sha256_prefixed(canon_bytes(child_manifest))
    child_result_dir = child_dir / "results" / child_task_id
    child_result_dir.mkdir(parents=True, exist_ok=True)
    child_diag_dir = child_dir / "agents" / "agent_0001" / "tasks" / child_task_id / "diagnostics"
    child_diag_dir.mkdir(parents=True, exist_ok=True)
    write_canon_json(child_diag_dir / "rsi_agent_receipt_v1.json", {
        "schema": "rsi_agent_receipt_v1",
        "spec_version": "v3_0",
        "agent_id": "agent_0001",
        "task_id": child_task_id,
        "result_id": child_result_id,
        "verdict": "OK",
        "reason": "OK",
    })
    write_canon_json(child_diag_dir / "task_verify_receipt_v2.json", {"schema": "task_verify_receipt_v2", "spec_version": "v3_1", "verdict": "VALID"})
    write_canon_json(child_result_dir / "result_manifest_v2.json", child_manifest)

    # child ledger
    child_events: list[dict[str, Any]] = []
    append_event(child_events, "SWARM_INIT", {
        "swarm_run_id": child_run_id,
        "pack_relpath": "subswarm_pack_v2.json",
        "pack_hash": child_pack_hash,
        "icore_id_expected": icore_receipt.get("core_id_expected"),
        "num_agents": 1,
        "max_epochs": 1,
        "commit_policy": "ROUND_COMMIT_V2_RECURSIVE",
    })
    append_event(child_events, "AGENT_REGISTER", {
        "agent_id": "agent_0001",
        "role": "PROVER",
        "capabilities": ["SUBPROOF_V1"],
        "agent_icore_receipt_relpath": "agents/agent_0001/diagnostics/immutable_core_receipt_v1.json",
        "core_id_observed": icore_receipt.get("core_id_observed"),
    })
    append_event(child_events, "EPOCH_BEGIN", {"epoch_index": 1, "barrier_ledger_head_hash": "GENESIS", "frontier_state_head_hash": "GENESIS"})
    append_event(child_events, "TASK_ASSIGN", {"epoch_index": 1, "task_id": child_task_id, "agent_id": "agent_0001", "task_spec_relpath": f"tasks/{child_task_id}/task_spec_v2.json", "base_barrier_head_hash": "GENESIS"})
    append_event(child_events, "TASK_RESULT", {"epoch_index": 1, "task_id": child_task_id, "agent_id": "agent_0001", "result_id": child_result_id, "result_manifest_relpath": f"results/{child_task_id}/result_manifest_v2.json", "status": "OK"})
    append_event(child_events, "RESULT_VERIFY", {"result_id": child_result_id, "verdict": "VALID", "reason": "OK", "verifier_receipt_relpath": f"agents/agent_0001/tasks/{child_task_id}/diagnostics/task_verify_receipt_v2.json"})
    append_event(child_events, "EPOCH_END", {"epoch_index": 1, "tasks_assigned": 1, "results_ok": 1, "results_valid": 1, "barrier_updates_accepted": 0})
    append_event(child_events, "SWARM_END", {"verdict": "VALID", "reason": "OK", "swarm_ledger_head_ref_hash": "", "barrier_ledger_head_ref_hash": "GENESIS"})

    child_swarm_head_hash = write_swarm_ledger(child_dir / "ledger" / "swarm_ledger_v2.jsonl", child_events)
    write_barrier_ledger(child_dir / "ledger" / "barrier_ledger_v3.jsonl", [])

    child_receipt = {
        "schema": "rsi_swarm_receipt_v2",
        "spec_version": "v3_1",
        "run_id": child_run_id,
        "pack_hash": child_pack_hash,
        "constitution_hash": "",
        "verdict": "VALID",
        "reason": "OK",
        "num_agents": 1,
        "epochs_executed": 1,
        "swarm_ledger_head_ref_hash": child_events[-1]["event_ref_hash"],
        "barrier_ledger_head_ref_hash": "GENESIS",
    }
    write_canon_json(child_dir / "diagnostics" / "rsi_swarm_receipt_v2.json", child_receipt)

    export_bundle = {
        "schema": "subswarm_export_bundle_v1",
        "spec_version": "v3_1",
        "child_swarm_run_id": child_run_id,
        "parent_swarm_run_id": run_id,
        "parent_task_id": task_specs[0][0],
        "depth": child_depth,
        "child_swarm_ledger_head_ref_hash": child_events[-1]["event_ref_hash"],
        "child_barrier_ledger_head_ref_hash": "GENESIS",
        "export_policy": "EXPORT_ALL_VALID_ARTIFACTS_V1",
        "exports": [],
        "export_bundle_hash": "__SELF__",
    }
    head = dict(export_bundle)
    head.pop("export_bundle_hash", None)
    export_bundle["export_bundle_hash"] = sha256_prefixed(canon_bytes(head))
    write_canon_json(child_dir / "diagnostics" / "subswarm_export_bundle_v1.json", export_bundle)

    tree_report_child = {
        "schema": "swarm_tree_report_v1",
        "spec_version": "v3_1",
        "root_swarm_run_id": child_run_id,
        "nodes": [
            {
                "swarm_run_id": child_run_id,
                "parent_swarm_run_id": run_id,
                "depth": child_depth,
                "out_dir_relpath": ".",
            }
        ],
    }
    write_canon_json(child_dir / "diagnostics" / "swarm_tree_report_v1.json", tree_report_child)

    # Root results + manifests
    results = []
    for idx, (task_id, spec, relpath) in enumerate(task_specs):
        agent_id = agents[idx % len(agents)]["agent_id"]
        result_dir = run_root / "results" / task_id
        result_dir.mkdir(parents=True, exist_ok=True)
        diag_dir = run_root / "agents" / agent_id / "tasks" / task_id / "diagnostics"
        diag_dir.mkdir(parents=True, exist_ok=True)
        artifacts = []
        optional = {"present": False}
        if spec["task_type"] == "CSI_PATCH_PROPOSE_V1":
            proposal = {
                "schema": "barrier_entry_proposal_v1",
                "spec_version": "v3_1",
                "barrier_prev": 500500,
                "barrier_next": 400400,
                "recovery_bundle_id": sha256_prefixed(b"recovery:demo"),
                "receipt_relpath": f"agents/{agent_id}/tasks/{task_id}/diagnostics/rsi_agent_receipt_v1.json",
            }
            proposal_rel = f"agents/{agent_id}/tasks/{task_id}/artifacts/barrier_entry_proposal_v1.json"
            proposal_path = run_root / proposal_rel
            proposal_path.parent.mkdir(parents=True, exist_ok=True)
            write_canon_json(proposal_path, proposal)
            optional = {
                "present": True,
                "barrier_prev": proposal["barrier_prev"],
                "barrier_next": proposal["barrier_next"],
                "recovery_bundle_id": proposal["recovery_bundle_id"],
                "proposal_relpath": proposal_rel,
            }
            artifacts.append({
                "kind": "BARRIER_PROPOSAL_V1",
                "relpath": proposal_rel,
                "sha256": sha256_prefixed(proposal_path.read_bytes()),
                "bytes": proposal_path.stat().st_size,
            })

        spawn_child = {"present": False}
        if spec["task_type"] == "SUBPROOF_V1":
            spawn_child = {
                "present": True,
                "subswarm_slot": 1,
                "desired_depth": child_depth,
                "child_pack_relpath": f"agents/agent_0001/subswarms/sha256_{child_run_id.split(':',1)[1]}/subswarm_pack_v2.json",
                "child_pack_hash": child_pack_hash,
                "child_swarm_run_id": child_run_id,
            }

        manifest = {
            "schema": "swarm_result_manifest_v2",
            "spec_version": "v3_1",
            "task_id": task_id,
            "agent_id": agent_id,
            "status": "OK",
            "failure_reason": "NONE",
            "agent_receipt_relpath": f"agents/{agent_id}/tasks/{task_id}/diagnostics/rsi_agent_receipt_v1.json",
            "artifacts": artifacts,
            "optional_barrier_proposal": optional,
            "spawn_child": spawn_child,
        }
        result_id = sha256_prefixed(canon_bytes(manifest))
        results.append((task_id, agent_id, result_id, manifest))
        write_canon_json(diag_dir / "rsi_agent_receipt_v1.json", {
            "schema": "rsi_agent_receipt_v1",
            "spec_version": "v3_0",
            "agent_id": agent_id,
            "task_id": task_id,
            "result_id": result_id,
            "verdict": "OK",
            "reason": "OK",
        })
        write_canon_json(diag_dir / "task_verify_receipt_v2.json", {"schema": "task_verify_receipt_v2", "spec_version": "v3_1", "verdict": "VALID"})
        write_canon_json(result_dir / "result_manifest_v2.json", manifest)

    # Root ledger
    events: list[dict[str, Any]] = []
    append_event(events, "SWARM_INIT", {
        "swarm_run_id": run_id,
        "pack_relpath": "pack.json",
        "pack_hash": pack_hash,
        "icore_id_expected": icore_receipt.get("core_id_expected"),
        "num_agents": 2,
        "max_epochs": 2,
        "commit_policy": "ROUND_COMMIT_V2_RECURSIVE",
    })
    for agent in agents:
        append_event(events, "AGENT_REGISTER", {
            "agent_id": agent["agent_id"],
            "role": agent["role"],
            "capabilities": agent["capabilities"],
            "agent_icore_receipt_relpath": f"agents/{agent['agent_id']}/diagnostics/immutable_core_receipt_v1.json",
            "core_id_observed": icore_receipt.get("core_id_observed"),
        })

    append_event(events, "EPOCH_BEGIN", {"epoch_index": 1, "barrier_ledger_head_hash": "GENESIS", "frontier_state_head_hash": "GENESIS"})

    # Assign tasks deterministic order
    for task_id, spec, relpath in sorted(task_specs, key=lambda row: row[0]):
        agent_id = agents[0]["agent_id"] if spec["task_type"] == "SUBPROOF_V1" else agents[1]["agent_id"]
        append_event(events, "TASK_ASSIGN", {
            "epoch_index": 1,
            "task_id": task_id,
            "agent_id": agent_id,
            "task_spec_relpath": relpath,
            "base_barrier_head_hash": "GENESIS",
        })

    for task_id, agent_id, result_id, manifest in sorted(results, key=lambda row: row[0]):
        append_event(events, "TASK_RESULT", {
            "epoch_index": 1,
            "task_id": task_id,
            "agent_id": agent_id,
            "result_id": result_id,
            "result_manifest_relpath": f"results/{task_id}/result_manifest_v2.json",
            "status": "OK",
        })

    for task_id, agent_id, result_id, manifest in sorted(results, key=lambda row: (row[0], row[1], row[2])):
        append_event(events, "RESULT_VERIFY", {
            "result_id": result_id,
            "verdict": "VALID",
            "reason": "OK",
            "verifier_receipt_relpath": f"agents/{agent_id}/tasks/{task_id}/diagnostics/task_verify_receipt_v2.json",
        })

    # Barrier proposal
    barrier_task = next(r for r in results if r[3]["optional_barrier_proposal"]["present"])
    proposal_rel = barrier_task[3]["optional_barrier_proposal"]["proposal_relpath"]
    proposal = load_canon_json(run_root / proposal_rel)
    proposal_id = sha256_prefixed(canon_bytes(proposal))
    append_event(events, "BARRIER_UPDATE_PROPOSE", {
        "proposal_id": proposal_id,
        "result_id": barrier_task[2],
        "base_barrier_head_hash": "GENESIS",
        "proposed_barrier_entry_relpath": proposal_rel,
    })

    # Spawn event (compute ref and patch child pack)
    spawn_payload = {
        "parent_epoch_index": 1,
        "parent_task_id": task_specs[0][0],
        "sponsor_agent_id": "agent_0001",
        "depth": child_depth,
        "subswarm_slot": 1,
        "child_swarm_run_id": child_run_id,
        "child_pack_relpath": f"agents/agent_0001/subswarms/sha256_{child_run_id.split(':',1)[1]}/subswarm_pack_v2.json",
        "child_pack_hash": child_pack_hash,
        "child_out_dir_relpath": f"agents/agent_0001/subswarms/sha256_{child_run_id.split(':',1)[1]}",
        "child_expected_icore_id": icore_receipt.get("core_id_expected"),
        "child_limits": {
            "num_agents": 1,
            "max_epochs": 1,
            "max_tasks_per_epoch": 2,
            "max_accepts_per_epoch": 1,
        },
    }
    spawn_event = append_event(events, "SUBSWARM_SPAWN", spawn_payload)
    # patch child pack spawn ref
    child_pack["parent_link"]["spawn_event_ref_hash"] = spawn_event["event_ref_hash"]
    write_canon_json(child_dir / "subswarm_pack_v2.json", child_pack)

    # Barrier update accept with entry
    accept_payload = {
        "proposal_id": proposal_id,
        "accepted": True,
        "barrier_entry_hash": "",
        "barrier_ledger_head_ref_hash_new": "",
    }
    accept_ref = compute_event_ref_hash({
        "schema": "swarm_event_v2",
        "spec_version": "v3_1",
        "seq": len(events) + 1,
        "prev_event_hash": events[-1]["event_hash"],
        "event_type": "BARRIER_UPDATE_ACCEPT",
        "payload": accept_payload,
        "event_ref_hash": "",
        "event_hash": "",
    })
    entry = {
        "schema": "barrier_entry_v3",
        "spec_version": "v3_1",
        "seq": 1,
        "prev_entry_hash": "GENESIS",
        "swarm_event_ref_hash": accept_ref,
        "agent_id": barrier_task[1],
        "task_id": barrier_task[0],
        "result_id": barrier_task[2],
        "barrier_metric": {"name": "env_steps_total", "prev": 500500, "next": 400400},
        "evidence": {"receipt_relpath": proposal["receipt_relpath"], "subswarm_provenance": {"present": False}},
        "entry_hash": "",
    }
    entry["entry_hash"] = compute_entry_hash(entry)
    accept_payload["barrier_entry_hash"] = entry["entry_hash"]
    accept_payload["barrier_ledger_head_ref_hash_new"] = entry["entry_hash"]
    append_event(events, "BARRIER_UPDATE_ACCEPT", accept_payload)

    append_event(events, "EPOCH_END", {"epoch_index": 1, "tasks_assigned": 2, "results_ok": 2, "results_valid": 2, "barrier_updates_accepted": 1})

    # Epoch 2 join
    append_event(events, "EPOCH_BEGIN", {"epoch_index": 2, "barrier_ledger_head_hash": entry["entry_hash"], "frontier_state_head_hash": "GENESIS"})
    append_event(events, "SUBSWARM_JOIN_ATTEMPT", {
        "parent_epoch_index": 2,
        "child_swarm_run_id": child_run_id,
        "child_out_dir_relpath": spawn_payload["child_out_dir_relpath"],
        "attempt_index": 1,
        "expected_child_receipt_relpath": f"{spawn_payload['child_out_dir_relpath']}/diagnostics/rsi_swarm_receipt_v2.json",
        "join_policy": "JOIN_RETRY_V1",
    })
    append_event(events, "SUBSWARM_JOIN_ACCEPT", {
        "parent_epoch_index": 2,
        "child_swarm_run_id": child_run_id,
        "child_receipt_relpath": f"{spawn_payload['child_out_dir_relpath']}/diagnostics/rsi_swarm_receipt_v2.json",
        "child_swarm_ledger_head_ref_hash": child_events[-1]["event_ref_hash"],
        "child_barrier_ledger_head_ref_hash": "GENESIS",
        "export_bundle_relpath": f"{spawn_payload['child_out_dir_relpath']}/diagnostics/subswarm_export_bundle_v1.json",
        "export_bundle_hash": export_bundle["export_bundle_hash"],
        "joined_artifact_set_hash": sha256_prefixed(canon_bytes({"exports": []})),
        "base_barrier_head_ref_hash_at_spawn": "GENESIS",
        "base_barrier_head_ref_hash_now": entry["entry_hash"],
        "staleness": {"is_stale": True, "reason": "STALE_BASE"},
    })
    append_event(events, "EPOCH_END", {"epoch_index": 2, "tasks_assigned": 0, "results_ok": 0, "results_valid": 0, "barrier_updates_accepted": 0})
    append_event(events, "SWARM_END", {"verdict": "VALID", "reason": "OK", "swarm_ledger_head_ref_hash": "", "barrier_ledger_head_ref_hash": entry["entry_hash"]})

    swarm_head_hash = write_swarm_ledger(run_root / "ledger" / "swarm_ledger_v2.jsonl", events)
    write_barrier_ledger(run_root / "ledger" / "barrier_ledger_v3.jsonl", [entry])

    # root report + receipt
    root_receipt = {
        "schema": "rsi_swarm_receipt_v2",
        "spec_version": "v3_1",
        "run_id": run_id,
        "pack_hash": pack_hash,
        "constitution_hash": "",
        "verdict": "VALID",
        "reason": "OK",
        "num_agents": 2,
        "epochs_executed": 2,
        "swarm_ledger_head_ref_hash": events[-1]["event_ref_hash"],
        "barrier_ledger_head_ref_hash": entry["entry_hash"],
    }
    write_canon_json(run_root / "diagnostics" / "rsi_swarm_receipt_v2.json", root_receipt)
    write_canon_json(run_root / "diagnostics" / "rsi_swarm_report_v2.json", {
        "schema": "rsi_swarm_report_v2",
        "spec_version": "v3_1",
        "run_id": run_id,
        "pack_hash": pack_hash,
        "constitution_hash": "",
        "num_agents": 2,
        "epochs_executed": 2,
        "tasks_assigned": 2,
        "results_ok": 2,
        "results_valid": 2,
        "barrier_updates_accepted": 1,
        "swarm_ledger_head_ref_hash": events[-1]["event_ref_hash"],
        "barrier_ledger_head_ref_hash": entry["entry_hash"],
    })

    tree_report = {
        "schema": "swarm_tree_report_v1",
        "spec_version": "v3_1",
        "root_swarm_run_id": run_id,
        "nodes": [
            {"swarm_run_id": run_id, "parent_swarm_run_id": None, "depth": 0, "out_dir_relpath": "."},
            {
                "swarm_run_id": child_run_id,
                "parent_swarm_run_id": run_id,
                "depth": child_depth,
                "out_dir_relpath": f"agents/agent_0001/subswarms/sha256_{child_run_id.split(':',1)[1]}",
            },
        ],
    }
    write_canon_json(run_root / "diagnostics" / "swarm_tree_report_v1.json", tree_report)

    return {
        "run_root": run_root,
        "child_dir": child_dir,
        "child_run_id": child_run_id,
        "entry_hash": entry["entry_hash"],
        "events": events,
    }
