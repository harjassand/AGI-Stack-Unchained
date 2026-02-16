"""Deterministic spec/test synthesis from counterexamples."""

from __future__ import annotations

import json
from typing import Any, Iterable


def synthesize_specs(counterexamples: list[dict], *, max_items: int = 5) -> dict[str, list[dict]]:
    return {
        "pyut_tests": _dedup_and_limit(_pyut_tests(counterexamples), max_items),
        "env_invariants": _dedup_and_limit(_env_invariants(counterexamples), max_items),
        "tooluse_invariants": _dedup_and_limit(_tooluse_invariants(counterexamples), max_items),
    }


def _pyut_tests(counterexamples: list[dict]) -> list[dict]:
    tests: list[dict] = []
    for example in counterexamples:
        if example.get("kind") != "pyut":
            continue
        args = example.get("args")
        expected = example.get("expected")
        if not isinstance(args, list):
            continue
        tests.append({"args": args, "expected": expected})
    return tests


def _env_invariants(counterexamples: list[dict]) -> list[dict]:
    invariants: list[dict] = []
    for example in counterexamples:
        if example.get("kind") != "env":
            continue
        steps = example.get("candidate_steps")
        if isinstance(steps, int):
            invariants.append({"invariant": "max_steps", "value": steps})
        if example.get("illegal_move") is True:
            invariants.append({"invariant": "no_illegal_moves"})
    return invariants


def _tooluse_invariants(counterexamples: list[dict]) -> list[dict]:
    invariants: list[dict] = []
    for example in counterexamples:
        if example.get("kind") != "tooluse":
            continue
        blocked_tool = example.get("blocked_tool")
        if isinstance(blocked_tool, str) and blocked_tool:
            invariants.append({"invariant": "no_tool", "tool": blocked_tool})
        path = example.get("path")
        if isinstance(path, str) and path.startswith("/"):
            invariants.append({"invariant": "sandbox_path_only"})
        steps = example.get("step_count")
        if isinstance(steps, int):
            invariants.append({"invariant": "max_steps", "value": steps})
    return invariants


def _dedup_and_limit(items: Iterable[dict], limit: int) -> list[dict]:
    seen: set[str] = set()
    ordered: list[dict] = []
    for item in items:
        key = _canonical_json(item)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(item)
        if len(ordered) >= limit:
            break
    return ordered


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
