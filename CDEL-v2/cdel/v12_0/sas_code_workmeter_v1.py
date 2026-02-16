"""Deterministic workmeter for SAS-CODE sorting (v12.0)."""

from __future__ import annotations

from typing import Any, Iterable, Tuple

from ..v11_1.fixed_q32_v1 import q32_from_ratio


Counts = dict[str, int]


def _empty_counts() -> Counts:
    return {
        "cmp_count": 0,
        "rec_calls": 0,
        "cons_count": 0,
        "append_count": 0,
        "merge_count": 0,
        "split_count": 0,
    }


def _policy_int(policy: dict[str, Any] | None, key: str, default: int) -> int:
    if not policy:
        return int(default)
    value = policy.get(key, default)
    try:
        return int(value)
    except Exception:
        return int(default)


def _policy_bool(policy: dict[str, Any] | None, key: str, default: bool) -> bool:
    if not policy:
        return bool(default)
    value = policy.get(key, default)
    return bool(value)


def _bubble_sort(xs: list[int]) -> tuple[list[int], Counts]:
    arr = list(xs)
    n = len(arr)
    counts = _empty_counts()
    swaps = 0
    for i in range(n):
        counts["rec_calls"] += 1
        for j in range(0, n - 1 - i):
            counts["cmp_count"] += 1
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
                swaps += 1
    counts["cons_count"] += swaps * 2
    counts["append_count"] += n
    return arr, counts


def _insertion_sort(xs: list[int], *, penalty_multiplier: int = 0) -> tuple[list[int], Counts]:
    arr = list(xs)
    counts = _empty_counts()
    for i in range(1, len(arr)):
        counts["rec_calls"] += 1
        key = arr[i]
        j = i - 1
        while j >= 0:
            counts["cmp_count"] += 1
            if arr[j] > key:
                arr[j + 1] = arr[j]
                counts["cons_count"] += 1
                j -= 1
            else:
                break
        arr[j + 1] = key
        counts["cons_count"] += 1
    counts["append_count"] += len(arr)
    # Optional policy-driven penalty to keep insertion sort as a negative control.
    if penalty_multiplier:
        counts["cmp_count"] += counts["cons_count"] * int(penalty_multiplier)
    return arr, counts


def _merge(left: list[int], right: list[int], counts: Counts) -> list[int]:
    merged: list[int] = []
    i = 0
    j = 0
    while i < len(left) and j < len(right):
        counts["cmp_count"] += 1
        if left[i] <= right[j]:
            merged.append(left[i])
            counts["cons_count"] += 1
            i += 1
        else:
            merged.append(right[j])
            counts["cons_count"] += 1
            j += 1
    if i < len(left):
        tail = left[i:]
        merged.extend(tail)
        counts["append_count"] += len(tail)
        counts["cons_count"] += len(tail)
    if j < len(right):
        tail = right[j:]
        merged.extend(tail)
        counts["append_count"] += len(tail)
        counts["cons_count"] += len(tail)
    return merged


def _merge_sort(xs: list[int], counts: Counts) -> list[int]:
    counts["rec_calls"] += 1
    n = len(xs)
    if n <= 1:
        return list(xs)
    counts["split_count"] += 1
    mid = n // 2
    left = _merge_sort(xs[:mid], counts)
    right = _merge_sort(xs[mid:], counts)
    counts["merge_count"] += 1
    return _merge(left, right, counts)


def execute_algorithm(algo_kind: str, xs: list[int], *, policy: dict[str, Any] | None = None) -> tuple[list[int], Counts]:
    if algo_kind == "BUBBLE_SORT_V1":
        return _bubble_sort(xs)
    if algo_kind == "INSERTION_SORT_V1":
        penalty = _policy_int(policy, "insertion_shift_penalty_multiplier", 0)
        return _insertion_sort(xs, penalty_multiplier=penalty)
    if algo_kind == "MERGE_SORT_V1":
        counts = _empty_counts()
        out = _merge_sort(xs, counts)
        return out, counts
    if algo_kind == "QUICK_SORT_V1":
        # Deterministic quicksort fallback (not used by v12.0).
        counts = _empty_counts()
        def _qsort(vals: list[int]) -> list[int]:
            counts["rec_calls"] += 1
            if len(vals) <= 1:
                return list(vals)
            pivot = vals[0]
            left: list[int] = []
            right: list[int] = []
            for item in vals[1:]:
                counts["cmp_count"] += 1
                if item <= pivot:
                    left.append(item)
                    counts["cons_count"] += 1
                else:
                    right.append(item)
                    counts["cons_count"] += 1
            out = _qsort(left) + [pivot] + _qsort(right)
            counts["append_count"] += len(out)
            return out
        return _qsort(list(xs)), counts
    # Unknown algorithm kinds are treated as maximal cost.
    counts = _empty_counts()
    n = len(xs)
    counts["cmp_count"] = n * n
    counts["rec_calls"] = n
    counts["cons_count"] = n * n
    counts["append_count"] = n * n
    return list(xs), counts


def compute_workvec(algo_kind: str, xs: list[int], *, policy: dict[str, Any] | None = None) -> dict[str, int]:
    _out, counts = execute_algorithm(algo_kind, xs, policy=policy)
    work_cost = (
        10 * counts["cmp_count"]
        + 3 * counts["merge_count"]
        + 3 * counts["split_count"]
        + counts["rec_calls"]
        + counts["cons_count"]
        + counts["append_count"]
    )
    return {
        "cmp_count": int(counts["cmp_count"]),
        "rec_calls": int(counts["rec_calls"]),
        "cons_count": int(counts["cons_count"]),
        "append_count": int(counts["append_count"]),
        "merge_count": int(counts["merge_count"]),
        "split_count": int(counts["split_count"]),
        "work_cost": int(work_cost),
    }


def _speedup_ratio(baseline_cost: int, cand_cost: int) -> tuple[int, int]:
    denom = cand_cost if cand_cost > 0 else 1
    return baseline_cost, denom


def compute_perf_report(
    *,
    eval_kind: str,
    suitepack: dict[str, Any],
    baseline_algo_id: str,
    baseline_algo_kind: str,
    candidate_algo_id: str,
    candidate_algo_kind: str,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cases = suitepack.get("cases") or []
    baseline_total = 0
    candidate_total = 0

    base_128 = 0
    cand_128 = 0
    count_128 = 0
    base_512 = 0
    cand_512 = 0
    count_512 = 0

    for case in cases:
        xs = case.get("xs") or []
        if not isinstance(xs, list):
            continue
        n = len(xs)
        base_vec = compute_workvec(baseline_algo_kind, xs, policy=policy)
        cand_vec = compute_workvec(candidate_algo_kind, xs, policy=policy)
        baseline_total += base_vec["work_cost"]
        candidate_total += cand_vec["work_cost"]
        if n == 128:
            base_128 += base_vec["work_cost"]
            cand_128 += cand_vec["work_cost"]
            count_128 += 1
        if n == 512:
            base_512 += base_vec["work_cost"]
            cand_512 += cand_vec["work_cost"]
            count_512 += 1

    num, den = _speedup_ratio(baseline_total, candidate_total)
    speedup_q32 = q32_from_ratio(num, den)

    gate_reasons: list[str] = []
    min_improvement_percent = _policy_int(policy, "min_improvement_percent", 30)
    if candidate_total * 100 > baseline_total * (100 - min_improvement_percent):
        gate_reasons.append("NO_PERF_GAIN")

    if _policy_bool(policy, "require_scaling_sanity", True) and count_128 > 0 and count_512 > 0:
        speed_128 = (base_128 / cand_128) if cand_128 > 0 else float("inf")
        speed_512 = (base_512 / cand_512) if cand_512 > 0 else float("inf")
        if speed_512 + 1e-9 < speed_128:
            gate_reasons.append("SCALING_SANITY_FAIL")

    report = {
        "schema_version": "sas_code_perf_report_v1",
        "eval_kind": eval_kind,
        "suite_id": suitepack.get("suite_id"),
        "suitepack_hash": suitepack.get("suitepack_hash"),
        "baseline_algo_id": baseline_algo_id,
        "candidate_algo_id": candidate_algo_id,
        "baseline_work_cost_total": int(baseline_total),
        "candidate_work_cost_total": int(candidate_total),
        "speedup_q32": speedup_q32,
        "gate": {
            "min_improvement_percent": int(min_improvement_percent),
            "passed": len(gate_reasons) == 0,
            "reasons": gate_reasons,
        },
    }
    return report


def ensure_perf_report(report: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(report, dict) or report.get("schema_version") != "sas_code_perf_report_v1":
        raise ValueError("SCHEMA_INVALID")
    return report


def is_sorted(xs: Iterable[int]) -> bool:
    vals = list(xs)
    return all(vals[i] <= vals[i + 1] for i in range(len(vals) - 1))


def is_perm(xs: Iterable[int], ys: Iterable[int]) -> bool:
    from collections import Counter

    return Counter(xs) == Counter(ys)


__all__ = [
    "compute_workvec",
    "compute_perf_report",
    "ensure_perf_report",
    "execute_algorithm",
    "is_sorted",
    "is_perm",
]
