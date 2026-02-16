from __future__ import annotations

import copy
import json
import random
from typing import Any, Dict


def _ensure_ops(out: Dict, op: str) -> None:
    ops = out.setdefault("operators_used", [])
    ops.append(op)


def mutate_constant(capsule: Dict, rng: random.Random) -> Dict:
    out = copy.deepcopy(capsule)
    metric = out["contract"]["statistical_spec"]["metrics"][0]
    target = float(metric.get("target", 0))
    delta = rng.choice([-0.1, 0.1])
    metric["target"] = target + delta
    _ensure_ops(out, "x-mutate_constant")
    return out


def swap_primitive(capsule: Dict, rng: random.Random) -> Dict:
    out = copy.deepcopy(capsule)
    metric = out["contract"]["statistical_spec"]["metrics"][0]
    direction = metric.get("direction", "maximize")
    metric["direction"] = "minimize" if direction == "maximize" else "maximize"
    _ensure_ops(out, "x-swap_primitive")
    return out


def compose_two_candidates(a: Dict, b: Dict) -> Dict:
    out = copy.deepcopy(a)
    _ensure_ops(out, "x-compose_two_candidates")
    parents = []
    seen = set()
    for item in list(a.get("parents", [])) + list(b.get("parents", [])):
        if item in seen:
            continue
        seen.add(item)
        parents.append(item)
    out["parents"] = parents
    return out


def shrink_on_fail(capsule: Dict, counterexample: Any | None) -> Dict:
    out = copy.deepcopy(capsule)
    shrunk = counterexample
    if isinstance(counterexample, list):
        shrunk = counterexample[: max(1, len(counterexample) // 2)]
    elif isinstance(counterexample, dict):
        keys = sorted(counterexample.keys())
        shrunk = {key: counterexample[key] for key in keys[: max(1, len(keys) // 2)]}
    elif isinstance(counterexample, (int, float)):
        shrunk = counterexample / 2
    out.setdefault("x-harness", {}).setdefault("args", [])
    out["x-harness"]["args"] = ["--counterexample", json.dumps(shrunk, sort_keys=True)]
    _ensure_ops(out, "x-shrink_on_fail")
    return out


def patch_parameter(capsule: Dict, counterexample: Any | None) -> Dict:
    out = copy.deepcopy(capsule)
    metric = out["contract"]["statistical_spec"]["metrics"][0]
    direction = metric.get("direction", "maximize")
    target = float(metric.get("target", 0))
    bound = None
    if isinstance(counterexample, dict):
        bound_val = counterexample.get("bound")
        if isinstance(bound_val, (int, float)):
            bound = float(bound_val)
    if direction == "maximize":
        if bound is not None:
            metric["target"] = min(target, bound - 0.01)
        else:
            metric["target"] = target - 0.05
    else:
        if bound is not None:
            metric["target"] = max(target, bound + 0.01)
        else:
            metric["target"] = target + 0.05
    if isinstance(counterexample, dict) and "input" in counterexample:
        input_val = counterexample.get("input")
        if isinstance(input_val, (int, float)):
            resource = out.setdefault("contract", {}).setdefault("resource_spec", {})
            current = int(resource.get("max_sample_count", 0))
            resource["max_sample_count"] = max(current, int(input_val))
    _ensure_ops(out, "x-patch_parameter")
    return out


def revert_last_mutation(parent: Dict) -> Dict:
    out = copy.deepcopy(parent)
    _ensure_ops(out, "x-revert_last_mutation")
    return out


def repair_by_guard(capsule: Dict, counterexample: Any | None) -> Dict:
    out = copy.deepcopy(capsule)
    safety = out.setdefault("contract", {}).setdefault("safety_spec", {})
    invariants = safety.setdefault("invariants", [])
    guard_id = f"guard-{len(invariants) + 1}"
    detail = ""
    if isinstance(counterexample, dict):
        detail = json.dumps(counterexample, sort_keys=True)
        input_val = counterexample.get("input")
        if isinstance(input_val, (int, float)):
            resource = out.setdefault("contract", {}).setdefault("resource_spec", {})
            current = int(resource.get("max_sample_count", 0))
            resource["max_sample_count"] = max(current, int(input_val))
    invariants.append(
        {
            "id": guard_id,
            "clause_type": "safety",
            "text": f"Guard against counterexample {detail}".strip(),
        }
    )
    _ensure_ops(out, "x-repair_by_guard")
    return out


def reuse_primitive(capsule: Dict, primitive: Any) -> Dict:
    out = copy.deepcopy(capsule)
    metric = out["contract"]["statistical_spec"]["metrics"][0]
    metric["target"] = float(getattr(primitive, "metric_target", metric.get("target", 0)))
    direction = getattr(primitive, "metric_direction", None)
    if direction:
        metric["direction"] = direction
    out.setdefault("x-primitive", {})["primitive_id"] = getattr(primitive, "primitive_id", "")
    _ensure_ops(out, "x-reuse_primitive")
    return out
