from __future__ import annotations

from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import canon_bytes, sha256_prefixed, write_canon_json, write_jsonl_line
from cdel.v3_3.meta_ledger import build_meta_block, build_meta_policy, build_meta_state
from cdel.v4_0.omega_ledger import compute_event_ref_hash
from cdel.v4_0.omega_metrics import TaskResult, accel_index_v1, compute_cumulative, compute_rolling_windows

DUMMY_HASH = "sha256:" + "0" * 64


def write_canon(path: Path, payload: dict[str, Any]) -> None:
    write_canon_json(path, payload)


def write_jsonl(path: Path, payload: dict[str, Any]) -> None:
    write_jsonl_line(path, payload)


def hash_json(payload: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(payload))


def make_event(
    event_type: str,
    payload: dict[str, Any],
    prev_event_ref_hash: str = "GENESIS",
    epoch_index: int = 0,
    root_swarm_run_id: str = DUMMY_HASH,
    icore_id: str = DUMMY_HASH,
) -> dict[str, Any]:
    event = {
        "schema": "omega_ledger_event_v1",
        "spec_version": "v4_0",
        "event_ref_hash": "",
        "prev_event_ref_hash": prev_event_ref_hash,
        "root_swarm_run_id": root_swarm_run_id,
        "icore_id": icore_id,
        "epoch_index": int(epoch_index),
        "event_type": event_type,
        "payload": payload,
    }
    event["event_ref_hash"] = compute_event_ref_hash(event)
    return event


def build_meta_exchange(run_root: Path, root_swarm_run_id: str, icore_id: str, *, meta_epoch_index: int = 0) -> dict[str, Any]:
    meta_state = build_meta_state(
        root_swarm_run_id=root_swarm_run_id,
        icore_id=icore_id,
        meta_epoch_index=meta_epoch_index,
        prev_meta_state_hash="GENESIS",
        assertions=[],
    )
    meta_policy = build_meta_policy(
        root_swarm_run_id=root_swarm_run_id,
        icore_id=icore_id,
        meta_epoch_index=meta_epoch_index,
        prev_meta_policy_hash="GENESIS",
        subscriptions_add=[],
        priorities=[],
    )
    state_hash = meta_state["state_hash"]
    policy_hash = meta_policy["policy_hash"]
    state_hex = state_hash.split(":", 1)[1]
    policy_hex = policy_hash.split(":", 1)[1]
    state_path = f"meta_exchange/state/sha256_{state_hex}.meta_state_v1.json"
    policy_path = f"meta_exchange/policy/sha256_{policy_hex}.meta_policy_v1.json"
    meta_block = build_meta_block(
        root_swarm_run_id=root_swarm_run_id,
        icore_id=icore_id,
        meta_epoch_index=meta_epoch_index,
        prev_meta_block_id="GENESIS",
        accepted_update_ids=[],
        rejected_updates=[],
        meta_state_hash=state_hash,
        meta_state_path=f"@ROOT/{state_path}",
        meta_policy_hash=policy_hash,
        meta_policy_path=f"@ROOT/{policy_path}",
        stats={
            "candidate_updates": 0,
            "accepted_updates": 0,
            "rejected_updates": 0,
            "total_assertions": 0,
            "total_subscriptions_add": 0,
        },
    )
    block_hash = meta_block["meta_block_id"]
    block_hex = block_hash.split(":", 1)[1]
    block_path = f"meta_exchange/blocks/sha256_{block_hex}.meta_block_v1.json"

    write_canon_json(run_root / state_path, meta_state)
    write_canon_json(run_root / policy_path, meta_policy)
    write_canon_json(run_root / block_path, meta_block)

    return {
        "meta_epoch_index": meta_epoch_index,
        "meta_block_id": block_hash,
        "meta_state_hash": state_hash,
        "meta_policy_hash": policy_hash,
    }


def build_baseline_report(run_root: Path, *, baseline_id: str, suite_id: str, solved_task_ids: list[str]) -> dict[str, Any]:
    solved_sorted = sorted(solved_task_ids)
    solved_hash = sha256_prefixed(canon_bytes(solved_sorted))
    report = {
        "schema": "baseline_report_v1",
        "spec_version": "v4_0",
        "baseline_id": baseline_id,
        "suite_id": suite_id,
        "task_budget": {"max_compute_units": 200000, "max_wall_seconds": 60},
        "solved_task_ids": solved_sorted,
        "solved_task_ids_hash": solved_hash,
        "pass_rate_num": len(solved_sorted),
        "pass_rate_den": max(len(solved_sorted), 1),
    }
    write_canon_json(run_root / "baseline_report_v1.json", report)
    return report


def build_suite_manifest(run_root: Path, *, suite_id: str, task_count: int) -> dict[str, Any]:
    suitepack_path = run_root / "grand_challenge_heldout_v1.suitepack"
    suitepack_path.write_bytes(b"suitepack")
    suitepack_hash = sha256_prefixed(suitepack_path.read_bytes())
    suite_hash = sha256_prefixed(canon_bytes({"suite_id": suite_id, "task_count": task_count}))
    manifest = {
        "schema": "grand_challenge_suite_manifest_v1",
        "spec_version": "v4_0",
        "suite_id": suite_id,
        "suite_hash": suite_hash,
        "task_count": task_count,
        "sealed_storage": {
            "format": "SEALED_SUITEPACK_V1",
            "suitepack_path": f"@ROOT/{suitepack_path.name}",
            "suitepack_hash": suitepack_hash,
            "answer_commitment": {"commitment_alg": "SHA256_SALT_V1", "salt_id": "test_salt"},
        },
        "task_schema": "sealed_task_v2",
        "task_prompt_visibility": "RE3_VISIBLE",
        "answer_visibility": "RE2_ONLY",
    }
    write_canon_json(run_root / "suite_manifest.json", manifest)
    return manifest


def build_checkpoint_receipt(
    *,
    root_swarm_run_id: str,
    icore_id: str,
    checkpoint_index: int,
    closed_epoch_index: int,
    meta_head: dict[str, Any],
    results: list[dict[str, Any]],
    window_tasks: int,
    accel_windows: int,
    accel_min_num: int = 0,
    accel_min_den: int = 1,
) -> dict[str, Any]:
    task_results = [
        TaskResult(
            task_id=str(row.get("task_id", "")),
            verdict=str(row.get("verdict", "")),
            compute_used=int(row.get("compute_used", 0)),
        )
        for row in results
    ]
    cumulative = compute_cumulative(task_results)
    windows = compute_rolling_windows(task_results, window_tasks)
    accel = accel_index_v1(windows, accel_windows, accel_min_num, accel_min_den)
    receipt = {
        "schema": "omega_checkpoint_receipt_v1",
        "spec_version": "v4_0",
        "receipt_hash": "",
        "root_swarm_run_id": root_swarm_run_id,
        "icore_id": icore_id,
        "checkpoint_index": checkpoint_index,
        "closed_epoch_index": closed_epoch_index,
        "meta_head": meta_head,
        "active_system": {
            "active_promotion_bundle_id": "GENESIS",
            "active_ontology_id": "GENESIS",
            "active_macros_id": "GENESIS",
        },
        "cumulative": cumulative,
        "rolling_windows": windows,
        "acceleration": accel,
    }
    receipt["receipt_hash"] = sha256_prefixed(
        canon_bytes({k: v for k, v in receipt.items() if k != "receipt_hash"})
    )
    return receipt


def build_minimal_omega_run(
    tmp_path: Path,
    repo_root: Path,
    *,
    epochs: int = 1,
    tasks_per_epoch: int = 1,
    checkpoint_every: int = 1,
    include_stop: bool = True,
    leak_field: str | None = None,
    stop_partial: bool = False,
) -> dict[str, Any]:
    from cdel.v1_7r.canon import write_canon_json
    from cdel.v2_3.immutable_core import load_lock, validate_lock
    from cdel.v3_3.tests.utils import setup_base_run, write_graph_report
    from cdel.v4_0.constants import meta_identities

    ctx = setup_base_run(tmp_path, repo_root, max_epochs=epochs, with_result=True, meta_enabled=False)
    run_root = ctx["run_root"]
    run_id = ctx["run_id"]
    verify_ref = ctx["verify_ref"]
    write_graph_report(run_root, run_id)

    omega_dir = run_root / "omega"
    (omega_dir / "checkpoints").mkdir(parents=True, exist_ok=True)
    (omega_dir / "task_attempts").mkdir(parents=True, exist_ok=True)

    lock_path = repo_root / "meta-core" / "meta_constitution" / "v4_0" / "immutable_core_lock_v1.json"
    lock = load_lock(lock_path)
    validate_lock(lock)
    icore_id = lock.get("core_id", DUMMY_HASH)
    meta_hash = meta_identities().get("META_HASH", DUMMY_HASH)

    meta_head = build_meta_exchange(run_root, run_id, icore_id)
    suite = build_suite_manifest(run_root, suite_id="suite_v1", task_count=tasks_per_epoch * epochs)
    baseline = build_baseline_report(run_root, baseline_id="baseline_v1", suite_id=suite["suite_id"], solved_task_ids=[])
    baseline_hash = sha256_prefixed(canon_bytes(baseline))

    pack = {
        "schema": "rsi_real_omega_pack_v1",
        "spec_version": "v4_0",
        "pack_hash": "",
        "root": {"required_icore_id": icore_id, "required_meta_hash": meta_hash},
        "swarm": {
            "protocol_version": "v3_3",
            "commit_policy": "ROUND_COMMIT_V4_OMEGA",
            "authority": {"min_nodes": 1, "max_depth": 0},
            "meta": {"enabled": True, "consensus_policy": "HOLO_CONSENSUS_V1", "exchange_root_path": "@ROOT/meta_exchange"},
        },
        "omega": {
            "enabled": True,
            "unbounded_epochs": True,
            "tasks_per_epoch": tasks_per_epoch,
            "task_sampling": {"policy": "SHUFFLE_CYCLE_V1", "seed": DUMMY_HASH, "allow_repeats": True},
            "checkpoint": {"every_epochs": checkpoint_every, "write_receipt": True},
            "suite": {"suite_manifest_path": "@ROOT/suite_manifest.json"},
            "baseline": {
                "baseline_id": baseline["baseline_id"],
                "baseline_report_path": "@ROOT/baseline_report_v1.json",
                "baseline_report_hash": baseline_hash,
            },
            "self_improvement": {
                "enabled": False,
                "proposal_systems": {
                    "autonomy_v2": False,
                    "recursive_ontology_v2_1": False,
                    "csi_v2_2": False,
                    "hardening_v2_3": False,
                },
                "promotion_policy": "PROMOTE_ONLY_IF_DEV_IMPROVES_V1",
                "dev_gate": {"sealed_config_path": "@ROOT/dev.toml", "min_delta_score_num": 0, "min_delta_score_den": 1},
                "max_promotions_per_checkpoint": 0,
                "max_patch_bytes": 0,
                "max_patch_files_touched": 0,
            },
            "success_criteria": {
                "min_new_solves_over_baseline": tasks_per_epoch * epochs + 1,
                "rolling_window": {"window_tasks": max(tasks_per_epoch, 1), "min_windows": 2},
                "min_passrate_gain_num": 1,
                "min_passrate_gain_den": 1,
                "acceleration": {
                    "metric": "ACCEL_INDEX_V1",
                    "min_accel_ratio_num": 2,
                    "min_accel_ratio_den": 1,
                    "min_consecutive_windows": 2,
                },
            },
            "stop_conditions": [{"kind": "MAX_CHECKPOINTS", "max_checkpoints": max(1, epochs // checkpoint_every)}],
        },
    }
    pack_hash = sha256_prefixed(canon_bytes({k: v for k, v in pack.items() if k != "pack_hash"}))
    pack["pack_hash"] = pack_hash
    write_canon_json(run_root / "rsi_real_omega_pack_v1.json", pack)

    events: list[dict[str, Any]] = []
    prev = "GENESIS"
    events.append(make_event("OMEGA_RUN_BEGIN", {}, prev, 0, run_id, icore_id))
    prev = events[-1]["event_ref_hash"]

    all_results: list[dict[str, Any]] = []
    checkpoint_index = 0
    last_checkpoint_hash = DUMMY_HASH

    for epoch in range(epochs):
        events.append(make_event("OMEGA_EPOCH_OPEN", {}, prev, epoch, run_id, icore_id))
        prev = events[-1]["event_ref_hash"]

        for i in range(tasks_per_epoch):
            task_id = sha256_prefixed(canon_bytes({"epoch": epoch, "i": i}))
            attempt_id = sha256_prefixed(canon_bytes({"task_id": task_id, "attempt": 0}))
            events.append(
                make_event(
                    "OMEGA_TASK_SAMPLE",
                    {"suite_id": suite["suite_id"], "task_id": task_id, "sample_index": i},
                    prev,
                    epoch,
                    run_id,
                    icore_id,
                )
            )
            prev = events[-1]["event_ref_hash"]

            attempt_dir = omega_dir / "task_attempts" / task_id / "attempt_0"
            attempt_dir.mkdir(parents=True, exist_ok=True)
            candidate_path = attempt_dir / "candidate_output.json"
            write_canon_json(candidate_path, {"task_id": task_id, "output": "ok"})
            receipt_path = attempt_dir / "sealed_eval_receipt.json"
            receipt_payload = {
                "schema": "sealed_eval_receipt_v1",
                "verdict": "PASS",
                "score_num": 1,
                "score_den": 1,
                "budget": {"max_compute_units": 200000, "max_wall_seconds": 60},
            }
            if leak_field:
                receipt_payload[leak_field] = "leak"
            write_canon_json(receipt_path, receipt_payload)
            receipt_hash = sha256_prefixed(canon_bytes(receipt_payload))

            events.append(
                make_event(
                    "OMEGA_TASK_EVAL_REQUEST",
                    {
                        "task_id": task_id,
                        "attempt_id": attempt_id,
                        "candidate_output_path": f"@ROOT/omega/task_attempts/{task_id}/attempt_0/candidate_output.json",
                        "sealed_config_path": "@ROOT/sealed.toml",
                        "eval_budget": {"max_compute_units": 200000, "max_wall_seconds": 60},
                    },
                    prev,
                    epoch,
                    run_id,
                    icore_id,
                )
            )
            prev = events[-1]["event_ref_hash"]

            events.append(
                make_event(
                    "OMEGA_TASK_EVAL_RESULT",
                    {
                        "task_id": task_id,
                        "attempt_id": attempt_id,
                        "verdict": "PASS",
                        "score_num": 1,
                        "score_den": 1,
                        "compute_used": 10,
                        "sealed_eval_receipt_hash": receipt_hash,
                        "sealed_eval_receipt_path": f"@ROOT/omega/task_attempts/{task_id}/attempt_0/sealed_eval_receipt.json",
                        "publisher_result_verify_event_ref_hash": verify_ref,
                    },
                    prev,
                    epoch,
                    run_id,
                    icore_id,
                )
            )
            prev = events[-1]["event_ref_hash"]
            all_results.append({"task_id": task_id, "verdict": "PASS", "compute_used": 10})

        if stop_partial:
            break

        events.append(
            make_event(
                "OMEGA_EPOCH_CLOSE",
                {
                    "epoch_index": epoch,
                    "tasks_sampled": tasks_per_epoch,
                    "tasks_attempted": tasks_per_epoch,
                    "tasks_passed": tasks_per_epoch,
                    "compute_used_total": 10 * tasks_per_epoch,
                    "meta_head": meta_head,
                },
                prev,
                epoch,
                run_id,
                icore_id,
            )
        )
        prev = events[-1]["event_ref_hash"]

        if (epoch + 1) % checkpoint_every == 0:
            receipt = build_checkpoint_receipt(
                root_swarm_run_id=run_id,
                icore_id=icore_id,
                checkpoint_index=checkpoint_index,
                closed_epoch_index=epoch,
                meta_head=meta_head,
                results=list(all_results),
                window_tasks=max(tasks_per_epoch, 1),
                accel_windows=2,
                accel_min_num=2,
                accel_min_den=1,
            )
            receipt_hex = receipt["receipt_hash"].split(":", 1)[1]
            receipt_path = omega_dir / "checkpoints" / f"sha256_{receipt_hex}.omega_checkpoint_receipt_v1.json"
            write_canon_json(receipt_path, receipt)
            events.append(
                make_event(
                    "OMEGA_CHECKPOINT_WRITE",
                    {
                        "checkpoint_index": checkpoint_index,
                        "receipt_hash": receipt["receipt_hash"],
                        "receipt_path": f"@ROOT/omega/checkpoints/sha256_{receipt_hex}.omega_checkpoint_receipt_v1.json",
                    },
                    prev,
                    epoch,
                    run_id,
                    icore_id,
                )
            )
            prev = events[-1]["event_ref_hash"]
            last_checkpoint_hash = receipt["receipt_hash"]
            checkpoint_index += 1

    if include_stop:
        final_epoch = epochs - 1 if not stop_partial else 0
        events.append(
            make_event(
                "OMEGA_STOP",
                {
                    "stop_kind": "MAX_CHECKPOINTS",
                    "final_closed_epoch_index": final_epoch,
                    "final_checkpoint_receipt_hash": last_checkpoint_hash,
                },
                prev,
                final_epoch,
                run_id,
                icore_id,
            )
        )

    ledger_path = omega_dir / "omega_ledger_v1.jsonl"
    for event in events:
        write_jsonl(ledger_path, event)

    return {
        "run_root": run_root,
        "omega_ledger": ledger_path,
        "meta_head": meta_head,
    }
