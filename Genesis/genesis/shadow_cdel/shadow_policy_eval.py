from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List

from genesis.core.counterexamples import Counterexample
from genesis.shadow_cdel.baseline_registry import BaselineRegistry
from genesis.shadow_cdel.lcb import hoeffding_lcb, hoeffding_ucb
from genesis.shadow_cdel.nontriviality import (
    MIN_ACTION_DIVERSITY,
    MIN_ACTION_ENTROPY,
    action_stats,
    is_finite,
)
from genesis.shadow_cdel.policy_env_registry import PolicyEnvRegistry

ROOT = Path(__file__).resolve().parents[1]

@dataclass
class ShadowPolicyTrace:
    status: str
    failing_test: str | None
    counterexample: Any | None


@dataclass
class ShadowPolicyResult:
    decision: str
    status: str
    return_value: float | None
    return_bound: float | None
    return_threshold: float | None
    cost_value: float | None
    cost_bound: float | None
    cost_threshold: float | None
    duration_ms: int
    sample_count: int
    forager_test_count: int
    tests_total: int
    tests_passed: int
    nontriviality_pass: bool
    baseline_margin: float | None
    trace: ShadowPolicyTrace | None


def _act(policy_spec: dict, obs: List[float]) -> int:
    family = policy_spec.get("policy_family")
    if family == "linear":
        weights = policy_spec.get("weights") or []
        bias = float(policy_spec.get("bias", 0.0))
        score = sum(float(w) * float(x) for w, x in zip(weights, obs)) + bias
        return 1 if score >= 0 else 0
    if family == "decision_tree":
        tree = policy_spec.get("tree") or {}
        idx = int(tree.get("feature_index", 0))
        threshold = float(tree.get("threshold", 0.0))
        left_action = int(tree.get("left_action", 0))
        right_action = int(tree.get("right_action", 1))
        if idx < 0 or idx >= len(obs):
            raise ValueError("feature index out of range")
        return left_action if float(obs[idx]) <= threshold else right_action
    raise ValueError("unsupported policy family")


def _compute_metrics(policy_spec: dict, rows: list[dict]) -> tuple[float, float, int, list[int]]:
    episodes = {}
    actions: list[int] = []
    for row in rows:
        episode_id = str(row.get("episode_id", 0))
        obs = row.get("obs")
        label = row.get("label")
        unsafe_action = row.get("unsafe_action", 1)
        scenario = row.get("scenario", "scenario:base")
        if not isinstance(obs, list) or label is None:
            continue
        action = _act(policy_spec, obs)
        actions.append(action)
        reward = 1.0 if int(label) == int(action) else 0.0
        cost = 1.0 if int(action) == int(unsafe_action) else 0.0
        entry = episodes.setdefault(episode_id, {"reward": [], "cost": [], "scenario": scenario})
        entry["reward"].append(reward)
        entry["cost"].append(cost)

    if not episodes:
        return 0.0, 0.0, 0, actions

    returns = []
    costs = []
    for entry in episodes.values():
        rewards = entry["reward"]
        cost_vals = entry["cost"]
        if not rewards:
            continue
        returns.append(sum(rewards) / len(rewards))
        costs.append(sum(cost_vals) / len(cost_vals))

    if not returns:
        return 0.0, 0.0, 0, actions

    avg_return = sum(returns) / len(returns)
    avg_cost = sum(costs) / len(costs)
    if avg_return < 0.0:
        avg_return = 0.0
    if avg_return > 1.0:
        avg_return = 1.0
    if avg_cost < 0.0:
        avg_cost = 0.0
    if avg_cost > 1.0:
        avg_cost = 1.0
    return avg_return, avg_cost, len(returns), actions


def _generate_forager_rows(
    rows: list[dict],
    counterexamples: list[Counterexample],
    max_tests: int,
) -> list[dict]:
    tests: list[dict] = []
    for row in rows[:max_tests]:
        obs = row.get("obs")
        if not isinstance(obs, list):
            continue
        flipped = [float(x) * -1.0 for x in obs]
        tests.append({"obs": flipped, "label": row.get("label"), "unsafe_action": row.get("unsafe_action", 1)})
        zeros = [0.0 for _ in obs]
        tests.append({"obs": zeros, "label": row.get("label"), "unsafe_action": row.get("unsafe_action", 1)})
        scaled = [float(x) * 1000.0 for x in obs]
        tests.append({"obs": scaled, "label": row.get("label"), "unsafe_action": row.get("unsafe_action", 1)})
        if len(tests) >= max_tests:
            break
    for entry in counterexamples:
        if len(tests) >= max_tests:
            break
        if isinstance(entry.input_value, dict):
            tests.append(entry.input_value)
    deduped = []
    seen = set()
    for test in tests:
        payload = json.dumps(test, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        deduped.append(test)
        if len(deduped) >= max_tests:
            break
    return deduped


def evaluate_shadow_policy(
    capsule: dict,
    seed: str = "0",
    margin: float = 0.0,
    counterexamples: list[Counterexample] | None = None,
    env_config_path: Path | None = None,
    env_id: str | None = None,
    forager_max_tests: int = 0,
) -> ShadowPolicyResult:
    start = time.time()
    counterexamples = counterexamples or []

    if capsule.get("artifact_type") != "POLICY":
        trace = ShadowPolicyTrace(status="VIOLATION", failing_test=None, counterexample=None)
        return ShadowPolicyResult(
            "FAIL",
            "VIOLATION",
            None,
            None,
            None,
            None,
            None,
            None,
            0,
            0,
            0,
            0,
            0,
            False,
            None,
            trace,
        )

    policy_spec = capsule.get("x-policy") or {}
    if policy_spec.get("policy_family") not in {"linear", "decision_tree"}:
        trace = ShadowPolicyTrace(status="VIOLATION", failing_test=None, counterexample=None)
        return ShadowPolicyResult(
            "FAIL",
            "VIOLATION",
            None,
            None,
            None,
            None,
            None,
            None,
            0,
            0,
            0,
            0,
            0,
            False,
            None,
            trace,
        )

    config_path = env_config_path or (ROOT / "configs" / "policy_envs.json")
    registry = PolicyEnvRegistry(config_path)
    env_key = env_id or policy_spec.get("env_id", "policy_env_tiny")
    handle = registry.resolve(env_key)
    if handle is None:
        trace = ShadowPolicyTrace(status="VIOLATION", failing_test=None, counterexample=None)
        return ShadowPolicyResult(
            "FAIL",
            "VIOLATION",
            None,
            None,
            None,
            None,
            None,
            None,
            0,
            0,
            0,
            0,
            0,
            False,
            None,
            trace,
        )

    rows = []
    with handle.path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))

    return_value, cost_value, n, actions = _compute_metrics(policy_spec, rows)
    confidence = (capsule.get("contract", {}).get("statistical_spec", {}).get("confidence_requirement") or {}).get(
        "delta", 0.01
    )
    try:
        delta = float(confidence)
    except Exception:
        delta = 0.01

    metrics = capsule.get("contract", {}).get("statistical_spec", {}).get("metrics") or []
    return_clause = next((m for m in metrics if m.get("name") == "policy_return"), {})
    cost_clause = next((m for m in metrics if m.get("name") == "policy_cost"), {})
    return_threshold = float(return_clause.get("target", 0.0))
    cost_threshold = float(cost_clause.get("target", 0.0))

    return_lcb = hoeffding_lcb(return_value, n, delta)
    cost_ucb = hoeffding_ucb(cost_value, n, delta)

    return_ok = return_lcb.bound >= return_threshold + margin
    cost_ok = cost_ucb.bound <= cost_threshold - margin
    decision = "PASS" if return_ok and cost_ok else "FAIL"

    diversity, entropy, _, _ = action_stats(actions)
    nonfinite = (not is_finite(return_value)) or (not is_finite(cost_value))
    diversity_pass = diversity >= MIN_ACTION_DIVERSITY and entropy >= MIN_ACTION_ENTROPY

    registry = BaselineRegistry()
    baseline_return = registry.get("POLICY", "policy_return")
    baseline_cost = registry.get("POLICY", "policy_cost")
    baseline_margin = None
    baseline_pass = False
    if baseline_return is not None and baseline_cost is not None:
        baseline_margin = return_value - baseline_return.value
        cost_margin = baseline_cost.value - cost_value
        baseline_pass = baseline_margin >= baseline_return.min_margin and cost_margin >= baseline_cost.min_margin

    nontriviality_pass = (not nonfinite) and diversity_pass and baseline_pass
    if decision == "PASS" and not nontriviality_pass:
        decision = "FAIL"

    forager_count = 0
    if decision == "PASS" and forager_max_tests > 0:
        tests = _generate_forager_rows(rows, counterexamples, forager_max_tests)
        forager_count = len(tests)
        if tests:
            f_return, f_cost, _, _ = _compute_metrics(policy_spec, tests)
            if f_return < return_threshold + margin:
                trace = ShadowPolicyTrace(
                    status="TEST_FAIL",
                    failing_test="forager_return",
                    counterexample=tests[0],
                )
                duration_ms = int((time.time() - start) * 1000)
                return ShadowPolicyResult(
                    "FAIL",
                    "TEST_FAIL",
                    return_value,
                    return_lcb.bound,
                    return_threshold,
                    cost_value,
                    cost_ucb.bound,
                    cost_threshold,
                    duration_ms,
                    n,
                    forager_count,
                    forager_count,
                    0,
                    nontriviality_pass,
                    baseline_margin,
                    trace,
                )
            if f_cost > cost_threshold - margin:
                trace = ShadowPolicyTrace(
                    status="TEST_FAIL",
                    failing_test="forager_cost",
                    counterexample=tests[0],
                )
                duration_ms = int((time.time() - start) * 1000)
                return ShadowPolicyResult(
                    "FAIL",
                    "TEST_FAIL",
                    return_value,
                    return_lcb.bound,
                    return_threshold,
                    cost_value,
                    cost_ucb.bound,
                    cost_threshold,
                    duration_ms,
                    n,
                    forager_count,
                    forager_count,
                    0,
                    nontriviality_pass,
                    baseline_margin,
                    trace,
                )

    duration_ms = int((time.time() - start) * 1000)
    if not nontriviality_pass:
        failing = "nontriviality"
        if nonfinite:
            failing = "nontriviality:nonfinite"
        elif not diversity_pass:
            failing = "nontriviality:action_diversity"
        elif not baseline_pass:
            failing = "nontriviality:baseline"
        trace = ShadowPolicyTrace(status="TEST_FAIL", failing_test=failing, counterexample=None)
        return ShadowPolicyResult(
            "FAIL",
            "TEST_FAIL",
            return_value,
            return_lcb.bound,
            return_threshold,
            cost_value,
            cost_ucb.bound,
            cost_threshold,
            duration_ms,
            n,
            forager_count,
            forager_count,
            0,
            nontriviality_pass,
            baseline_margin,
            trace,
        )
    if decision == "PASS":
        return ShadowPolicyResult(
            "PASS",
            "OK",
            return_value,
            return_lcb.bound,
            return_threshold,
            cost_value,
            cost_ucb.bound,
            cost_threshold,
            duration_ms,
            n,
            forager_count,
            forager_count,
            forager_count,
            nontriviality_pass,
            baseline_margin,
            None,
        )

    trace = ShadowPolicyTrace(
        status="TEST_FAIL",
        failing_test="threshold",
        counterexample={
            "obs": rows[0].get("obs") if rows else None,
            "label": rows[0].get("label") if rows else None,
            "unsafe_action": rows[0].get("unsafe_action", 1) if rows else None,
        },
    )
    return ShadowPolicyResult(
        "FAIL",
        "TEST_FAIL",
        return_value,
        return_lcb.bound,
        return_threshold,
        cost_value,
        cost_ucb.bound,
        cost_threshold,
        duration_ms,
        n,
        forager_count,
        forager_count,
        0,
        nontriviality_pass,
        baseline_margin,
        trace,
    )
