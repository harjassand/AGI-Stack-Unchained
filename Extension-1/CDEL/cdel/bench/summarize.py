"""Report summarizer for benchmark runs."""

from __future__ import annotations

import json
import math
from pathlib import Path


def summarize_report(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    results = data.get("results") or []
    total = len(results)
    accepted = [r for r in results if r.get("accepted")]
    rejected = total - len(accepted)
    accept_rate = (len(accepted) / total) if total else 0.0

    closure_symbols = [r.get("closure_symbols_count", 0) for r in accepted]
    closure_modules = [r.get("closure_modules_count", 0) for r in accepted]
    candidates = [r.get("candidates_tried", 0) for r in results]
    costs = [r.get("cost") for r in accepted if r.get("cost") is not None]
    remaining = [r.get("remaining_budget") for r in accepted if r.get("remaining_budget") is not None]

    summary = {
        "ledger_head": data.get("ledger_head"),
        "total_tasks": total,
        "accepted": len(accepted),
        "rejected": rejected,
        "accept_rate": accept_rate,
        "closure_symbols": _stats(closure_symbols),
        "closure_modules": _stats(closure_modules),
        "candidates_tried": _stats(candidates),
        "cost": _stats(costs),
        "remaining_budget_trajectory": remaining,
    }
    return summary


def _stats(values: list[int | float]) -> dict:
    if not values:
        return {"min": None, "median": None, "p90": None, "p99": None}
    sorted_vals = sorted(values)
    return {
        "min": sorted_vals[0],
        "median": _percentile(sorted_vals, 0.5),
        "p90": _percentile(sorted_vals, 0.9),
        "p99": _percentile(sorted_vals, 0.99),
    }


def _percentile(sorted_vals: list[int | float], p: float) -> int | float:
    if not sorted_vals:
        return None
    idx = max(0, math.ceil(p * len(sorted_vals)) - 1)
    return sorted_vals[idx]
