"""Deterministic omega metrics (v4.0)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cmp_to_key
from typing import Iterable


@dataclass(frozen=True)
class TaskResult:
    task_id: str
    verdict: str
    compute_used: int


def compute_task_results(events: Iterable[dict]) -> list[TaskResult]:
    results: list[TaskResult] = []
    for event in events:
        if event.get("event_type") != "OMEGA_TASK_EVAL_RESULT":
            continue
        payload = event.get("payload") or {}
        task_id = str(payload.get("task_id", ""))
        verdict = str(payload.get("verdict", ""))
        compute_used = int(payload.get("compute_used", 0))
        results.append(TaskResult(task_id=task_id, verdict=verdict, compute_used=compute_used))
    return results


def compute_cumulative(results: Iterable[TaskResult]) -> dict[str, int]:
    attempted = 0
    passed = 0
    compute_total = 0
    for res in results:
        attempted += 1
        if res.verdict == "PASS":
            passed += 1
        compute_total += int(res.compute_used)
    return {
        "tasks_attempted": attempted,
        "tasks_passed": passed,
        "compute_used_total": compute_total,
    }


def compute_rolling_windows(results: list[TaskResult], window_tasks: int) -> list[dict[str, int]]:
    windows: list[dict[str, int]] = []
    if window_tasks <= 0:
        return windows
    total = len(results)
    window_index = 0
    for start in range(0, total, window_tasks):
        end = start + window_tasks
        if end > total:
            break
        chunk = results[start:end]
        pass_count = sum(1 for res in chunk if res.verdict == "PASS")
        compute_used = sum(int(res.compute_used) for res in chunk)
        windows.append(
            {
                "window_index": window_index,
                "window_tasks": window_tasks,
                "pass_rate_num": pass_count,
                "pass_rate_den": window_tasks,
                "compute_num": compute_used,
            }
        )
        window_index += 1
    return windows


def _ratio_for_window(prev: dict[str, int], nxt: dict[str, int]) -> tuple[int, int]:
    pass_prev = int(prev.get("pass_rate_num", 0))
    compute_prev = int(prev.get("compute_num", 0))
    pass_next = int(nxt.get("pass_rate_num", 0))
    compute_next = int(nxt.get("compute_num", 0))
    if pass_prev == 0:
        return (0, 1)
    return (pass_next * max(compute_prev, 1), pass_prev * max(compute_next, 1))


def _compare_ratio(a: tuple[int, int], b: tuple[int, int]) -> int:
    left = a[0] * b[1]
    right = b[0] * a[1]
    if left < right:
        return -1
    if left > right:
        return 1
    return 0


def _median_ratio(ratios: list[tuple[int, int]]) -> tuple[int, int]:
    if not ratios:
        return (0, 1)
    ordered = sorted(ratios, key=cmp_to_key(_compare_ratio))
    return ordered[len(ordered) // 2]


def accel_index_v1(
    rolling_windows: list[dict[str, int]],
    min_consecutive_windows: int,
    min_accel_ratio_num: int,
    min_accel_ratio_den: int,
) -> dict[str, int]:
    if min_consecutive_windows <= 0:
        return {
            "metric": "ACCEL_INDEX_V1",
            "consecutive_windows": 0,
            "accel_ratio_num": 0,
            "accel_ratio_den": 1,
        }
    ratios: list[tuple[int, int]] = []
    for idx in range(len(rolling_windows) - 1):
        ratios.append(_ratio_for_window(rolling_windows[idx], rolling_windows[idx + 1]))

    # Median of the last K ratios (if present).
    if len(ratios) >= min_consecutive_windows:
        last_k = ratios[-min_consecutive_windows:]
        median = _median_ratio(last_k)
        median_num, median_den = int(median[0]), int(median[1])
    else:
        median_num, median_den = 0, 1

    # Count how many trailing ratios meet the threshold.
    consecutive = 0
    for num, den in reversed(ratios):
        if ratio_ge(num, den, min_accel_ratio_num, min_accel_ratio_den):
            consecutive += 1
            if consecutive >= min_consecutive_windows:
                # We cap at K because K is the only value that matters for ignition.
                consecutive = min_consecutive_windows
                break
            continue
        break

    return {
        "metric": "ACCEL_INDEX_V1",
        "consecutive_windows": int(consecutive),
        "accel_ratio_num": int(median_num),
        "accel_ratio_den": int(median_den),
    }


def passrate_gain(omega_passed: int, omega_attempted: int, baseline_passed: int, baseline_attempted: int) -> tuple[int, int]:
    omega_den = max(int(omega_attempted), 1)
    base_den = max(int(baseline_attempted), 1)
    num = int(omega_passed) * base_den - int(baseline_passed) * omega_den
    den = omega_den * base_den
    return num, den


def ratio_ge(num: int, den: int, thresh_num: int, thresh_den: int) -> bool:
    return int(num) * int(thresh_den) >= int(thresh_num) * int(den)


def compute_new_solves_over_baseline(omega_solved: set[str], baseline_solved: set[str]) -> int:
    return len(omega_solved - baseline_solved)


__all__ = [
    "TaskResult",
    "accel_index_v1",
    "compute_cumulative",
    "compute_new_solves_over_baseline",
    "compute_rolling_windows",
    "compute_task_results",
    "passrate_gain",
    "ratio_ge",
]
