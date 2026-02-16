"""Benchmark harness for baseline vs VAL candidate hashing."""

from __future__ import annotations

import statistics
import time
from typing import Callable

from ..hotloop.hotloop_counter_v1 import sha256_subprocess_hex


class ValBenchmarkError(ValueError):
    pass


def _timed_ns(fn: Callable[[], None]) -> int:
    t0 = time.perf_counter_ns()
    fn()
    t1 = time.perf_counter_ns()
    return int(t1 - t0)


def benchmark_hash_paths(
    *,
    messages: list[bytes],
    benchmark_reps: int,
    warmup_reps: int,
    candidate_hash_hex: Callable[[bytes], str],
) -> dict[str, object]:
    if benchmark_reps <= 0 or warmup_reps < 0 or not messages:
        raise ValBenchmarkError("INVALID:SCHEMA_FAIL")

    def _run_baseline_once() -> None:
        for msg in messages:
            sha256_subprocess_hex(msg)

    def _run_candidate_once() -> None:
        for msg in messages:
            candidate_hash_hex(msg)

    for _ in range(warmup_reps):
        _run_baseline_once()
        _run_candidate_once()

    baseline_samples = [_timed_ns(_run_baseline_once) for _ in range(benchmark_reps)]
    candidate_samples = [_timed_ns(_run_candidate_once) for _ in range(benchmark_reps)]
    baseline_samples_sorted = sorted(int(x) for x in baseline_samples)
    candidate_samples_sorted = sorted(int(x) for x in candidate_samples)
    median_baseline = int(statistics.median(baseline_samples_sorted))
    median_candidate = int(statistics.median(candidate_samples_sorted))
    val_cycles_baseline = int(sum(baseline_samples_sorted))
    val_cycles_candidate = int(sum(candidate_samples_sorted))
    ratio_valcycles_q32 = int(
        ((val_cycles_candidate << 32) // max(val_cycles_baseline, 1))
        if val_cycles_baseline > 0
        else 0
    )
    ratio_wallclock_q32 = int(((median_candidate << 32) // max(median_baseline, 1)) if median_baseline > 0 else 0)

    return {
        "schema_version": "val_benchmark_report_v1",
        "timing_source": "MACH_ABSOLUTE_TIME_V1",
        "sample_count": int(benchmark_reps),
        "samples_ns_baseline": baseline_samples_sorted,
        "samples_ns_candidate": candidate_samples_sorted,
        "val_cycles_baseline": val_cycles_baseline,
        "val_cycles_candidate": val_cycles_candidate,
        "median_ns_baseline": median_baseline,
        "median_ns_candidate": median_candidate,
        "ratio_valcycles_q32": ratio_valcycles_q32,
        "ratio_wallclock_q32": ratio_wallclock_q32,
    }


__all__ = ["ValBenchmarkError", "benchmark_hash_paths"]
