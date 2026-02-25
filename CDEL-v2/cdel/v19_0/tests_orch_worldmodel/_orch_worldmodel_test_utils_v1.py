from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import canon_bytes, write_canon_json
from cdel.v18_0.omega_common_v1 import canon_hash_obj


def write_hashed_json(dir_path: Path, suffix: str, payload: dict[str, Any]) -> tuple[str, Path]:
    digest = "sha256:" + hashlib.sha256(canon_bytes(payload)).hexdigest()
    path = dir_path / f"sha256_{digest.split(':', 1)[1]}.{suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(path, payload)
    return digest, path


def write_transition_blob(*, path: Path, events: list[dict[str, Any]]) -> tuple[str, Path]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        for event in events:
            handle.write(canon_bytes(event) + b"\n")
    digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    return digest, path


def write_dataset_manifest(
    *,
    repo_root: Path,
    manifest_path: Path,
    transition_events_relpath: str,
    transition_events_blob_id: str,
    ek_id: str,
    kernel_ledger_id: str,
    included_run_ids: list[str],
    events_included_u64: int,
    drop_reason_histogram: dict[str, int] | None = None,
) -> tuple[str, Path, dict[str, Any]]:
    manifest_no_id = {
        "schema_version": "orch_transition_dataset_manifest_v1",
        "ek_id": str(ek_id),
        "kernel_ledger_id": str(kernel_ledger_id),
        "runs_root_rel": "runs",
        "included_run_ids": sorted(set(included_run_ids)),
        "transition_events_blob_id": str(transition_events_blob_id),
        "transition_events_relpath": str(transition_events_relpath),
        "transition_events_sha256": str(transition_events_blob_id),
        "counts": {
            "runs_scanned_u64": len(set(included_run_ids)),
            "runs_included_u64": len(set(included_run_ids)),
            "events_included_u64": int(max(0, int(events_included_u64))),
            "dropped_rows_u64": int(sum(int(v) for v in (drop_reason_histogram or {}).values())),
        },
        "build_params": {
            "max_runs_u64": 5000,
            "max_events_u64": 200000,
            "cost_scale_ms_u64": 60000,
        },
        "drop_reason_histogram": {k: int(v) for k, v in sorted((drop_reason_histogram or {}).items())},
        "created_unix_s64": 0,
    }
    manifest_id = str(canon_hash_obj(manifest_no_id))
    payload = dict(manifest_no_id)
    payload["dataset_manifest_id"] = manifest_id
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(manifest_path, payload)
    return manifest_id, manifest_path, payload


def write_train_config(path: Path, overrides: dict[str, Any] | None = None) -> Path:
    payload: dict[str, Any] = {
        "schema_version": "orch_worldmodel_train_config_v1",
        "max_contexts_u32": 256,
        "max_actions_u32": 64,
        "horizon_u32": 3,
        "discount_q32": 3865470566,
        "planner_kind": "TABULAR_MPC_V1",
        "seed_u64": 0,
    }
    for key, value in (overrides or {}).items():
        payload[str(key)] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(path, payload)
    return path


def make_transition_event(
    *,
    run_id: str,
    tick_u64: int,
    context_key: str,
    lane_kind: str,
    objective_kind: str,
    action_capability_id: str,
    reward_q32: int,
    cost_norm_q32: int,
    toxic_fail_b: bool,
    next_context_key: str,
) -> dict[str, Any]:
    event_no_id = {
        "schema_version": "orch_transition_event_v1",
        "run_id": str(run_id),
        "tick_u64": int(tick_u64),
        "context_key": str(context_key),
        "lane_kind": str(lane_kind),
        "objective_kind": str(objective_kind),
        "action_capability_id": str(action_capability_id),
        "reward_q32": int(reward_q32),
        "cost_norm_q32": int(cost_norm_q32),
        "toxic_fail_b": bool(toxic_fail_b),
        "next_context_key": str(next_context_key),
    }
    out = dict(event_no_id)
    out["event_id"] = str(canon_hash_obj(event_no_id))
    return out


def _tick_state_root(*, run_root: Path, tick_u64: int) -> Path:
    return run_root / f"tick_{tick_u64:06d}" / "daemon" / "rsi_omega_daemon_v19_0" / "state"


def write_sample_run_fixture(runs_root: Path) -> Path:
    run_root = runs_root / "run_alpha"
    for tick_u64 in (1, 2, 3):
        state_root = _tick_state_root(run_root=run_root, tick_u64=tick_u64)
        state_root.mkdir(parents=True, exist_ok=True)

        decision = {
            "schema_version": "omega_decision_plan_v1",
            "tick_u64": tick_u64,
            "action_kind": "RUN_CAMPAIGN",
            "runaway_escalation_level_u64": 0,
            "capability_id": f"CAP_{tick_u64}",
        }
        decision_hash, _ = write_hashed_json(state_root / "decisions", "omega_decision_plan_v1.json", decision)

        lane = {
            "schema_version": "v19_0",
            "schema_name": "lane_decision_receipt_v1",
            "tick_u64": tick_u64,
            "lane_name": "BASELINE",
        }
        lane_hash, _ = write_hashed_json(state_root / "long_run" / "lane", "lane_decision_receipt_v1.json", lane)

        routing = {
            "schema_version": "v19_0",
            "schema_name": "dependency_routing_receipt_v1",
            "tick_u64": tick_u64,
            "selected_capability_id": f"CAP_{tick_u64}",
            "forced_frontier_attempt_b": False,
        }
        routing_hash, _ = write_hashed_json(
            state_root / "long_run" / "debt",
            "dependency_routing_receipt_v1.json",
            routing,
        )

        tick_perf = {
            "schema_version": "omega_tick_perf_v1",
            "tick_u64": tick_u64,
            "total_ns": 1_000_000_000 + (tick_u64 * 1_000_000),
        }
        write_hashed_json(state_root / "perf", "omega_tick_perf_v1.json", tick_perf)

        promotion = {
            "schema_version": "omega_promotion_receipt_v1",
            "tick_u64": tick_u64,
            "result": {
                "status": "PROMOTED" if tick_u64 != 2 else "REJECTED",
                "reason_code": "OK" if tick_u64 != 2 else "SUBVERIFIER_INVALID",
            },
        }
        promotion_hash, _ = write_hashed_json(
            state_root / "dispatch" / f"d{tick_u64:02d}" / "promotion",
            "omega_promotion_receipt_v1.json",
            promotion,
        )

        snapshot = {
            "schema_version": "omega_tick_snapshot_v1",
            "tick_u64": tick_u64,
            "decision_plan_hash": decision_hash,
            "dependency_routing_receipt_hash": routing_hash,
            "lane_decision_receipt_hash": lane_hash,
            "promotion_receipt_hash": promotion_hash,
            "utility_proof_hash": None,
            "activation_receipt_hash": None,
        }
        write_hashed_json(state_root / "snapshot", "omega_tick_snapshot_v1.json", snapshot)

    return run_root
