from __future__ import annotations

import sys
import types
from typing import Any, Callable


def _iter_code_objects(code: types.CodeType) -> list[types.CodeType]:
    out = [code]
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            out.extend(_iter_code_objects(const))
    return out


def count_call_opcodes(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> int:
    tracked = {id(code) for code in _iter_code_objects(fn.__code__)}
    total = 0

    def tracer(frame: types.FrameType, event: str, arg: Any):
        nonlocal total
        if event == "call":
            if id(frame.f_code) in tracked:
                frame.f_trace_opcodes = True
                return tracer
            return tracer
        if event == "opcode" and id(frame.f_code) in tracked:
            total += 1
        return tracer

    prev = sys.gettrace()
    sys.settrace(tracer)
    try:
        fn(*args, **kwargs)
    finally:
        sys.settrace(prev)
    return total


def compute_brain_perf_report(
    *,
    contexts: list[dict[str, Any]],
    baseline_fn: Callable[[dict[str, Any]], dict[str, Any]],
    candidate_case_metrics: list[dict[str, Any]],
) -> dict[str, Any]:
    if len(contexts) != len(candidate_case_metrics):
        raise ValueError("candidate_case_metrics length must equal contexts length")

    baseline_total = 0
    candidate_total = 0
    per_case = []
    for ctx, metric in zip(contexts, candidate_case_metrics):
        baseline_opcodes = count_call_opcodes(baseline_fn, ctx)
        candidate_opcodes = int(metric["candidate_steps_u64"])
        if candidate_opcodes <= 0:
            raise ValueError("candidate_steps_u64 must be positive for every case")
        baseline_total += baseline_opcodes
        candidate_total += candidate_opcodes
        per_case.append(
            {
                "case_id": ctx["case_id"],
                "baseline_opcodes": baseline_opcodes,
                "candidate_opcodes": candidate_opcodes,
            }
        )

    # Regression-safety gate: kernel candidate work must stay bounded.
    gate_pass = (candidate_total <= (baseline_total * 1000)) if baseline_total > 0 else False

    return {
        "schema_version": "kernel_brain_perf_report_v1",
        "baseline_brain_opcodes_total": int(baseline_total),
        "candidate_brain_opcodes_total": int(candidate_total),
        "gate_multiplier": 1000,
        "gate_pass": bool(gate_pass),
        "per_case": per_case,
    }


__all__ = ["count_call_opcodes", "compute_brain_perf_report"]
