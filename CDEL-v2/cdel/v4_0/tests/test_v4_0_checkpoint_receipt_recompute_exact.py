from __future__ import annotations

from cdel.v1_7r.canon import canon_bytes, sha256_prefixed
from cdel.v4_0.omega_metrics import TaskResult, accel_index_v1, compute_cumulative, compute_rolling_windows

from .utils import build_checkpoint_receipt


def test_v4_0_checkpoint_receipt_recompute_exact() -> None:
    results = [
        {"task_id": "t1", "verdict": "PASS", "compute_used": 5},
        {"task_id": "t2", "verdict": "FAIL", "compute_used": 7},
        {"task_id": "t3", "verdict": "PASS", "compute_used": 3},
        {"task_id": "t4", "verdict": "PASS", "compute_used": 2},
    ]
    meta_head = {
        "meta_epoch_index": 0,
        "meta_block_id": "sha256:" + "1" * 64,
        "meta_state_hash": "sha256:" + "2" * 64,
        "meta_policy_hash": "sha256:" + "3" * 64,
    }
    receipt = build_checkpoint_receipt(
        root_swarm_run_id="sha256:" + "4" * 64,
        icore_id="sha256:" + "5" * 64,
        checkpoint_index=0,
        closed_epoch_index=0,
        meta_head=meta_head,
        results=results,
        window_tasks=2,
        accel_windows=1,
        accel_min_num=1,
        accel_min_den=1,
    )

    task_results = [
        TaskResult(task_id=row["task_id"], verdict=row["verdict"], compute_used=row["compute_used"])
        for row in results
    ]
    cumulative = compute_cumulative(task_results)
    windows = compute_rolling_windows(task_results, 2)
    accel = accel_index_v1(windows, 1, 1, 1)

    assert receipt["cumulative"] == cumulative
    assert receipt["rolling_windows"] == windows
    assert receipt["acceleration"] == accel

    expected_hash = sha256_prefixed(canon_bytes({k: v for k, v in receipt.items() if k != "receipt_hash"}))
    assert receipt["receipt_hash"] == expected_hash
