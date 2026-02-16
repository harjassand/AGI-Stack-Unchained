from __future__ import annotations

from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json, write_jsonl_line
from cdel.v3_0.verify_rsi_swarm_v1 import compute_swarm_run_id
from cdel.v3_0.immutable_core import load_lock


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


def make_event(seq: int, prev_hash: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    event = {
        "schema": "swarm_event_v1",
        "spec_version": "v3_0",
        "seq": int(seq),
        "prev_event_hash": prev_hash,
        "event_type": event_type,
        "payload": payload,
        "event_hash": "__SELF__",
    }
    head = dict(event)
    head.pop("event_hash", None)
    event["event_hash"] = sha256_prefixed(canon_bytes(head))
    return event


def rewrite_swarm_ledger(path: Path, events: list[dict[str, Any]]) -> str:
    prev = "GENESIS"
    seq = 1
    path.write_text("", encoding="utf-8")
    for event in events:
        event["seq"] = seq
        event["prev_event_hash"] = prev
        head = dict(event)
        head.pop("event_hash", None)
        event["event_hash"] = sha256_prefixed(canon_bytes(head))
        write_jsonl_line(path, event)
        prev = event["event_hash"]
        seq += 1
    return prev


def rewrite_barrier_ledger(path: Path, entries: list[dict[str, Any]]) -> str:
    prev = "GENESIS"
    seq = 1
    path.write_text("", encoding="utf-8")
    for entry in entries:
        entry["seq"] = seq
        entry["prev_entry_hash"] = prev
        head = dict(entry)
        head.pop("entry_hash", None)
        entry["entry_hash"] = sha256_prefixed(canon_bytes(head))
        write_jsonl_line(path, entry)
        prev = entry["entry_hash"]
        seq += 1
    return prev


def build_valid_swarm_run(tmp_path: Path, repo_root: Path) -> dict[str, Any]:
    run_root = tmp_path / "run"
    (run_root / "diagnostics").mkdir(parents=True, exist_ok=True)
    (run_root / "ledger").mkdir(parents=True, exist_ok=True)
    (run_root / "tasks").mkdir(parents=True, exist_ok=True)
    (run_root / "results").mkdir(parents=True, exist_ok=True)
    (run_root / "agents").mkdir(parents=True, exist_ok=True)

    lock_rel = "meta-core/meta_constitution/v3_0/immutable_core_lock_v1.json"
    icore_receipt = build_valid_icore_receipt(repo_root, lock_rel)
    write_canon_json(run_root / "diagnostics" / "immutable_core_receipt_v1.json", icore_receipt)

    agents = [
        {"agent_id": "agent_0001", "role": "PROVER", "capabilities": ["SUBPROOF_V1"]},
        {"agent_id": "agent_0002", "role": "PATCHER", "capabilities": ["CSI_PATCH_PROPOSE_V1"]},
    ]
    for agent in agents:
        agent_diag = run_root / "agents" / agent["agent_id"] / "diagnostics"
        agent_diag.mkdir(parents=True, exist_ok=True)
        write_canon_json(agent_diag / "immutable_core_receipt_v1.json", icore_receipt)

    input_dir = run_root / "inputs"
    input_dir.mkdir(parents=True, exist_ok=True)
    problem1 = {
        "schema": "swarm_problem_payload_v1",
        "spec_version": "v3_0",
        "barrier_prev": 500,
        "barrier_next": 400,
        "note": "demo_subproof",
    }
    problem2 = {
        "schema": "swarm_problem_payload_v1",
        "spec_version": "v3_0",
        "note": "demo_patch",
    }
    write_canon_json(input_dir / "problem1.json", problem1)
    write_canon_json(input_dir / "problem2.json", problem2)
    problem1_id = sha256_prefixed(canon_bytes(problem1))
    problem2_id = sha256_prefixed(canon_bytes(problem2))

    pack = {
        "schema": "rsi_real_swarm_pack_v1",
        "spec_version": "v3_0",
        "swarm": {
            "num_agents": 2,
            "max_epochs": 1,
            "commit_policy": "ROUND_COMMIT_V1",
            "max_tasks_per_epoch": 4,
            "max_accepts_per_epoch": 1,
            "barrier_alpha_num": 19,
            "barrier_alpha_den": 20,
        },
        "agents": agents,
        "task_enumerator": {
            "kind": "DEMO_ENUMERATOR_V1",
            "inputs_relpath": "inputs/swarm_inputs_v1.json",
        },
    }
    pack_path = run_root / "pack.json"
    write_canon_json(pack_path, pack)

    run_id = compute_swarm_run_id(pack)
    pack_hash = sha256_prefixed(canon_bytes(pack))
    lock = load_lock(repo_root / lock_rel)

    task_specs = []
    task1 = {
        "schema": "swarm_task_spec_v1",
        "spec_version": "v3_0",
        "task_type": "SUBPROOF_V1",
        "domain": "formal_math_v1",
        "required_capabilities": ["SUBPROOF_V1"],
        "base_barrier_head_hash": "GENESIS",
        "base_frontier_state_head_hash": "GENESIS",
        "inputs": {
            "problem_id": problem1_id,
            "problem_payload_relpath": "inputs/problem1.json",
        },
        "budgets": {"work_cost_limit": 2000, "max_attempts": 1},
    }
    task2 = {
        "schema": "swarm_task_spec_v1",
        "spec_version": "v3_0",
        "task_type": "CSI_PATCH_PROPOSE_V1",
        "domain": "python_ut_v1",
        "required_capabilities": ["CSI_PATCH_PROPOSE_V1"],
        "base_barrier_head_hash": "GENESIS",
        "base_frontier_state_head_hash": "GENESIS",
        "inputs": {
            "problem_id": problem2_id,
            "problem_payload_relpath": "inputs/problem2.json",
        },
        "budgets": {"work_cost_limit": 2000, "max_attempts": 1},
    }
    for spec in (task1, task2):
        task_id = sha256_prefixed(canon_bytes(spec))
        task_dir = run_root / "tasks" / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        write_canon_json(task_dir / "task_spec_v1.json", spec)
        task_specs.append((task_id, spec, f"tasks/{task_id}/task_spec_v1.json"))

    task_specs_sorted = sorted(task_specs, key=lambda item: item[0])
    agent_ids = [a["agent_id"] for a in agents]

    results = []
    for idx, (task_id, spec, relpath) in enumerate(task_specs_sorted):
        agent_id = agent_ids[idx % len(agent_ids)]
        result_dir = run_root / "results" / task_id
        result_dir.mkdir(parents=True, exist_ok=True)
        diag_dir = result_dir / "diagnostics"
        diag_dir.mkdir(parents=True, exist_ok=True)
        agent_receipt = {
            "schema": "rsi_agent_receipt_v1",
            "spec_version": "v3_0",
            "agent_id": agent_id,
            "task_id": task_id,
            "result_id": "",
            "verdict": "OK",
            "reason": "OK",
        }
        verifier_receipt = {"schema": "task_verify_receipt_v1", "spec_version": "v3_0", "verdict": "VALID"}
        write_canon_json(diag_dir / "task_verify_receipt_v1.json", verifier_receipt)

        optional = {"present": False}
        proposal_rel = ""
        if idx == 0:
            proposal = {
                "schema": "barrier_entry_proposal_v1",
                "spec_version": "v3_0",
                "barrier_prev": 500,
                "barrier_next": 400,
                "recovery_bundle_id": "sha256:" + "1" * 64,
                "receipt_relpath": f"results/{task_id}/diagnostics/rsi_agent_receipt_v1.json",
            }
            proposal_rel = f"results/{task_id}/barrier_entry_proposal_v1.json"
            write_canon_json(run_root / proposal_rel, proposal)
            optional = {
                "present": True,
                "barrier_prev": proposal["barrier_prev"],
                "barrier_next": proposal["barrier_next"],
                "recovery_bundle_id": proposal["recovery_bundle_id"],
                "proposal_relpath": proposal_rel,
            }

        manifest = {
            "schema": "swarm_result_manifest_v1",
            "spec_version": "v3_0",
            "task_id": task_id,
            "agent_id": agent_id,
            "status": "OK",
            "failure_reason": "NONE",
            "agent_receipt_relpath": f"results/{task_id}/diagnostics/rsi_agent_receipt_v1.json",
            "artifacts": [],
            "optional_barrier_proposal": optional,
        }
        result_id = sha256_prefixed(canon_bytes(manifest))
        agent_receipt["result_id"] = result_id
        write_canon_json(diag_dir / "rsi_agent_receipt_v1.json", agent_receipt)
        write_canon_json(result_dir / "result_manifest_v1.json", manifest)

        results.append(
            {
                "task_id": task_id,
                "agent_id": agent_id,
                "result_id": result_id,
                "manifest_relpath": f"results/{task_id}/result_manifest_v1.json",
                "verifier_receipt_relpath": f"results/{task_id}/diagnostics/task_verify_receipt_v1.json",
                "proposal_relpath": proposal_rel,
            }
        )

    # Build swarm ledger
    events: list[dict[str, Any]] = []
    events.append(
        make_event(
            1,
            "GENESIS",
            "SWARM_INIT",
            {
                "swarm_run_id": run_id,
                "pack_relpath": "pack.json",
                "pack_hash": pack_hash,
                "icore_id_expected": lock["core_id"],
                "num_agents": 2,
                "max_epochs": 1,
                "commit_policy": "ROUND_COMMIT_V1",
            },
        )
    )
    prev = events[-1]["event_hash"]
    seq = 2
    for agent in agents:
        events.append(
            make_event(
                seq,
                prev,
                "AGENT_REGISTER",
                {
                    "agent_id": agent["agent_id"],
                    "role": agent["role"],
                    "capabilities": agent["capabilities"],
                    "agent_icore_receipt_relpath": f"agents/{agent['agent_id']}/diagnostics/immutable_core_receipt_v1.json",
                    "core_id_observed": lock["core_id"],
                },
            )
        )
        prev = events[-1]["event_hash"]
        seq += 1

    events.append(
        make_event(
            seq,
            prev,
            "EPOCH_BEGIN",
            {
                "epoch_index": 1,
                "barrier_ledger_head_hash": "GENESIS",
                "frontier_state_head_hash": "GENESIS",
            },
        )
    )
    prev = events[-1]["event_hash"]
    seq += 1

    for idx, (task_id, _spec, relpath) in enumerate(task_specs_sorted):
        agent_id = agent_ids[idx % len(agent_ids)]
        events.append(
            make_event(
                seq,
                prev,
                "TASK_ASSIGN",
                {
                    "epoch_index": 1,
                    "task_id": task_id,
                    "agent_id": agent_id,
                    "task_spec_relpath": relpath,
                    "base_barrier_head_hash": "GENESIS",
                },
            )
        )
        prev = events[-1]["event_hash"]
        seq += 1

    for result in results:
        events.append(
            make_event(
                seq,
                prev,
                "TASK_RESULT",
                {
                    "epoch_index": 1,
                    "task_id": result["task_id"],
                    "agent_id": result["agent_id"],
                    "result_id": result["result_id"],
                    "result_manifest_relpath": result["manifest_relpath"],
                    "status": "OK",
                },
            )
        )
        prev = events[-1]["event_hash"]
        seq += 1

    verify_order = sorted(
        results,
        key=lambda r: (r["task_id"], r["agent_id"], r["result_id"]),
    )
    for result in verify_order:
        events.append(
            make_event(
                seq,
                prev,
                "RESULT_VERIFY",
                {
                    "result_id": result["result_id"],
                    "verdict": "VALID",
                    "reason": "OK",
                    "verifier_receipt_relpath": result["verifier_receipt_relpath"],
                },
            )
        )
        prev = events[-1]["event_hash"]
        seq += 1

    # Barrier proposal + accept for first result
    accept_ref_hash = None
    barrier_entry_hash = "GENESIS"
    barrier_entry = None
    proposal_id = None
    if results[0]["proposal_relpath"]:
        proposal = load_canon_json(run_root / results[0]["proposal_relpath"])
        proposal_id = sha256_prefixed(canon_bytes(proposal))
        events.append(
            make_event(
                seq,
                prev,
                "BARRIER_UPDATE_PROPOSE",
                {
                    "proposal_id": proposal_id,
                    "result_id": results[0]["result_id"],
                    "base_barrier_head_hash": "GENESIS",
                    "proposed_barrier_entry_relpath": results[0]["proposal_relpath"],
                },
            )
        )
        prev = events[-1]["event_hash"]
        seq += 1

        # accept event placeholder for ref hash
        accept_event = {
            "schema": "swarm_event_v1",
            "spec_version": "v3_0",
            "seq": seq,
            "prev_event_hash": prev,
            "event_type": "BARRIER_UPDATE_ACCEPT",
            "payload": {
                "proposal_id": proposal_id,
                "accepted": True,
                "barrier_entry_hash": "",
                "barrier_ledger_head_hash_new": "",
            },
            "event_hash": "__SELF__",
        }
        accept_ref_payload = dict(accept_event)
        accept_ref_payload.pop("event_hash", None)
        inner = dict(accept_ref_payload["payload"])
        inner.pop("barrier_entry_hash", None)
        inner.pop("barrier_ledger_head_hash_new", None)
        accept_ref_payload["payload"] = inner
        accept_ref_hash = sha256_prefixed(canon_bytes(accept_ref_payload))

        barrier_entry = {
            "schema": "barrier_entry_v2",
            "spec_version": "v3_0",
            "seq": 1,
            "prev_entry_hash": "GENESIS",
            "swarm_event_hash": accept_ref_hash,
            "agent_id": results[0]["agent_id"],
            "task_id": results[0]["task_id"],
            "result_id": results[0]["result_id"],
            "barrier_metric": {"name": "env_steps_total", "prev": 500, "next": 400},
            "work_cost": {"base": 500, "delta": -100},
            "evidence": {
                "recovery_bundle_id": "sha256:" + "1" * 64,
                "receipt_relpath": f"results/{results[0]['task_id']}/diagnostics/rsi_agent_receipt_v1.json",
            },
            "entry_hash": "__SELF__",
        }
        head = dict(barrier_entry)
        head.pop("entry_hash", None)
        barrier_entry["entry_hash"] = sha256_prefixed(canon_bytes(head))
        barrier_entry_hash = barrier_entry["entry_hash"]

        accept_event["payload"]["barrier_entry_hash"] = barrier_entry_hash
        accept_event["payload"]["barrier_ledger_head_hash_new"] = barrier_entry_hash
        accept_head = dict(accept_event)
        accept_head.pop("event_hash", None)
        accept_event["event_hash"] = sha256_prefixed(canon_bytes(accept_head))
        events.append(accept_event)
        prev = accept_event["event_hash"]
        seq += 1

    events.append(
        make_event(
            seq,
            prev,
            "EPOCH_END",
            {
                "epoch_index": 1,
                "tasks_assigned": len(task_specs_sorted),
                "results_ok": len(results),
                "results_valid": len(results),
                "barrier_updates_accepted": 1 if barrier_entry else 0,
            },
        )
    )
    prev = events[-1]["event_hash"]
    seq += 1

    events.append(
        make_event(
            seq,
            prev,
            "SWARM_END",
            {
                "verdict": "VALID",
                "reason": "OK",
                "swarm_ledger_head_hash": "",
                "barrier_ledger_head_hash": barrier_entry_hash,
            },
        )
    )
    # compute reference hash for swarm end without swarm_ledger_head_hash
    end_event = dict(events[-1])
    end_payload = dict(end_event.get("payload") or {})
    end_payload.pop("swarm_ledger_head_hash", None)
    end_event["payload"] = end_payload
    end_event.pop("event_hash", None)
    end_ref = sha256_prefixed(canon_bytes(end_event))
    events[-1]["payload"]["swarm_ledger_head_hash"] = end_ref
    swarm_path = run_root / "ledger" / "swarm_ledger_v1.jsonl"
    head_hash = rewrite_swarm_ledger(swarm_path, events)

    barrier_path = run_root / "ledger" / "barrier_ledger_v2.jsonl"
    if barrier_entry:
        rewrite_barrier_ledger(barrier_path, [barrier_entry])
    else:
        barrier_path.write_text("", encoding="utf-8")

    return {
        "run_root": run_root,
        "swarm_events": events,
        "barrier_entry": barrier_entry,
        "swarm_head_hash": head_hash,
    }
