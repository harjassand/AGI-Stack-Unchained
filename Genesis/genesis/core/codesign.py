from __future__ import annotations

import copy
import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from genesis.capsules.canonicalize import capsule_hash
from genesis.capsules.policy_builder import build_policy_capsule
from genesis.capsules.system_builder import build_system_capsule
from genesis.capsules.world_model_builder import build_world_model_capsule
from genesis.core.component_store import ComponentStore
from genesis.core.counterexamples import CounterexampleDB
from genesis.core.failure_patterns import FailurePatternStore, operator_signature
from genesis.core.planning import plan_policy_from_model
from genesis.shadow_cdel.shadow_system_eval import ShadowSystemResult, evaluate_shadow_system
from genesis.shadow_cdel.nontriviality import margin_bucket


@dataclass
class SystemEvent:
    system_capsule: Dict[str, Any]
    policy_capsule: Dict[str, Any]
    model_capsule: Dict[str, Any]
    shadow: ShadowSystemResult
    operator: str
    repair_depth: int
    counterexample_id: str | None
    descriptor: Dict[str, Any]
    failure_pattern_id: str | None
    failure_patterns_top: List[Dict[str, Any]] | None


def _seed_model_specs() -> List[Dict[str, Any]]:
    return [
        {"model_family": "logistic_regression", "weights": [1.0, -1.0], "bias": 0.0},
        {"model_family": "linear_regression", "weights": [1.0, -1.0], "bias": 0.0},
    ]


def _seed_policy_specs() -> List[Dict[str, Any]]:
    return [
        {"policy_family": "linear", "weights": [1.0], "bias": 0.0},
        {
            "policy_family": "decision_tree",
            "tree": {"feature_index": 0, "threshold": 0.5, "left_action": 1, "right_action": 0},
        },
        {"policy_family": "linear", "weights": [1.0], "bias": -0.5},
        {"policy_family": "linear", "weights": [-1.0], "bias": 0.6},
    ]


def _plan_system_policy(model_spec: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    planned = plan_policy_from_model(model_spec, config)
    weights = planned.get("weights") or [1.0]
    avg_weight = sum(float(w) for w in weights) / len(weights)
    return {"policy_family": "linear", "weights": [avg_weight], "bias": float(planned.get("bias", 0.0))}


def _mutate_model(model_spec: Dict[str, Any], rng: random.Random) -> Dict[str, Any]:
    out = copy.deepcopy(model_spec)
    delta = rng.choice([-0.2, -0.1, 0.1, 0.2])
    out["bias"] = float(out.get("bias", 0.0)) + delta
    weights = list(out.get("weights", []))
    if weights:
        idx = rng.randrange(len(weights))
        weights[idx] = float(weights[idx]) + delta
    out["weights"] = weights
    return out


def _mutate_policy(policy_spec: Dict[str, Any], rng: random.Random) -> Dict[str, Any]:
    out = copy.deepcopy(policy_spec)
    delta = rng.choice([-0.2, -0.1, 0.1, 0.2])
    if out.get("policy_family") == "linear":
        out["bias"] = float(out.get("bias", 0.0)) + delta
        weights = list(out.get("weights", []))
        if weights:
            weights[0] = float(weights[0]) + delta
        out["weights"] = weights
    elif out.get("policy_family") == "decision_tree":
        tree = dict(out.get("tree") or {})
        tree["threshold"] = float(tree.get("threshold", 0.0)) + delta
        out["tree"] = tree
    return out


def _repair_policy(policy_spec: Dict[str, Any], counterexample: Any | None) -> Dict[str, Any]:
    out = copy.deepcopy(policy_spec)
    if not isinstance(counterexample, dict):
        return out
    label = counterexample.get("label")
    if label is None:
        return out
    if out.get("policy_family") == "linear":
        bias = float(out.get("bias", 0.0))
        bias += 0.4 if int(label) == 1 else -0.4
        out["bias"] = bias
    return out


def _repair_model(model_spec: Dict[str, Any], counterexample: Any | None) -> Dict[str, Any]:
    out = copy.deepcopy(model_spec)
    if not isinstance(counterexample, dict):
        return out
    label = counterexample.get("label")
    if label is None:
        return out
    bias = float(out.get("bias", 0.0))
    bias += 0.3 if int(label) == 1 else -0.3
    out["bias"] = bias
    return out


def _descriptor(model_spec: Dict[str, Any], policy_spec: Dict[str, Any], operators: List[str]) -> Dict[str, Any]:
    model_family = str(model_spec.get("model_family", "unknown"))
    policy_family = str(policy_spec.get("policy_family", "unknown"))
    weights = model_spec.get("weights") or []
    model_bucket = "small" if len(weights) <= 2 else "large"
    policy_bucket = "small" if len(policy_spec.get("weights", [])) <= 2 else "large"
    op_history = ">".join(operators)
    op_signature = hashlib.sha256(op_history.encode("utf-8")).hexdigest()[:12] if op_history else "none"
    return {
        "model_family": model_family,
        "policy_family": policy_family,
        "model_bucket": model_bucket,
        "policy_bucket": policy_bucket,
        "operator_history_sig": op_signature,
    }


def run_codesign(config: Dict[str, Any]) -> Dict[str, Any]:
    seed = int(config.get("seed", 0))
    rng = random.Random(seed)
    iterations = int(config.get("iterations", 4))
    repair_attempts = int(config.get("repair_attempts", 2))
    shadow_margin = float(config.get("shadow_margin", 0.05))
    pattern_snapshot_every = int(config.get("failure_pattern_snapshot_every", 5))
    pattern_top_k = int(config.get("failure_pattern_top_k", 3))

    env_config = Path(config.get("policy_env_config", "genesis/configs/policy_envs.json"))
    env_id = str(config.get("policy_env_id", "policy_env_tiny"))
    forager_max_tests = int(config.get("forager_max_tests", 0))

    component_store_dir = Path(config.get("component_store_dir", "genesis/components"))
    component_store = ComponentStore(component_store_dir)
    counterexamples = CounterexampleDB()
    failure_patterns = FailurePatternStore()

    events: List[SystemEvent] = []

    model_seeds = _seed_model_specs()
    policy_seeds = _seed_policy_specs()

    operator_choices = ["x-policy_from_model_rollouts", "x-codesign-mutate"]

    for idx in range(iterations):
        if idx == 0:
            operator = "x-policy_from_model_rollouts"
        elif idx == 1:
            operator = "x-codesign-mutate"
        else:
            operator = failure_patterns.choose_operator(rng, operator_choices)

        model_spec = model_seeds[idx % len(model_seeds)] if idx < len(model_seeds) else _mutate_model(model_seeds[0], rng)
        if operator == "x-policy_from_model_rollouts":
            policy_spec = _plan_system_policy(model_spec, config)
        else:
            policy_spec = policy_seeds[idx % len(policy_seeds)] if idx < len(policy_seeds) else _mutate_policy(policy_seeds[0], rng)

        model_capsule = build_world_model_capsule(model_spec, config, parents=[], operators=[operator], repair_depth=0)
        policy_capsule = build_policy_capsule(policy_spec, config, parents=[], operators=[operator], repair_depth=0)

        model_hash = component_store.store(model_capsule)
        policy_hash = component_store.store(policy_capsule)

        system_capsule = build_system_capsule(
            policy_hash=policy_hash,
            world_model_hash=model_hash,
            config=config,
            parents=[model_hash, policy_hash],
            operators=[operator],
            repair_depth=0,
        )
        component_store.store(system_capsule)

        shadow = evaluate_shadow_system(
            system_capsule=system_capsule,
            policy_spec=policy_spec,
            model_spec=model_spec,
            seed=str(seed),
            margin=shadow_margin,
            counterexamples=counterexamples.entries(),
            env_config_path=env_config,
            env_id=env_id,
            forager_max_tests=forager_max_tests,
        )

        counterexample_id = None
        failure_pattern_id = None
        if shadow.trace is not None:
            trace_hash = None
            failure_class = shadow.trace.status
            if shadow.trace.counterexample is not None:
                entry = counterexamples.add(
                    test_name=shadow.trace.failing_test or "shadow_system",
                    input_value=shadow.trace.counterexample,
                    failure_class=shadow.trace.status,
                    capsule_hash=capsule_hash(system_capsule),
                )
                counterexample_id = entry.counterexample_id
                failure_class = entry.failure_class
                trace_hash = entry.input_hash
            else:
                fallback = shadow.trace.failing_test or shadow.trace.status
                trace_hash = hashlib.sha256(fallback.encode("utf-8")).hexdigest()
            failure_pattern_id = failure_patterns.add(
                failure_class=failure_class,
                env_id=env_id,
                operator_sig=operator_signature(system_capsule.get("operators_used", [])),
                trace_hash=trace_hash,
            )

        descriptor = _descriptor(model_spec, policy_spec, system_capsule.get("operators_used", []))
        descriptor["nontriviality_pass"] = getattr(shadow, "nontriviality_pass", None)
        descriptor["baseline_margin_bucket"] = margin_bucket(getattr(shadow, "baseline_margin", None))
        pattern_snapshot = []
        if pattern_snapshot_every > 0 and (len(events) + 1) % pattern_snapshot_every == 0:
            pattern_snapshot = failure_patterns.top_k(pattern_top_k)
        events.append(
            SystemEvent(
                system_capsule=system_capsule,
                policy_capsule=policy_capsule,
                model_capsule=model_capsule,
                shadow=shadow,
                operator=operator,
                repair_depth=0,
                counterexample_id=counterexample_id,
                descriptor=descriptor,
                failure_pattern_id=failure_pattern_id,
                failure_patterns_top=pattern_snapshot,
            )
        )

        if shadow.decision == "PASS":
            continue

        for attempt in range(repair_attempts):
            repair_operator = "x-codesign-repair"
            if attempt % 2 == 0:
                policy_spec = _repair_policy(policy_spec, shadow.trace.counterexample if shadow.trace else None)
            else:
                model_spec = _repair_model(model_spec, shadow.trace.counterexample if shadow.trace else None)

            model_capsule = build_world_model_capsule(
                model_spec, config, parents=[model_hash], operators=[operator, repair_operator], repair_depth=attempt + 1
            )
            policy_capsule = build_policy_capsule(
                policy_spec, config, parents=[policy_hash], operators=[operator, repair_operator], repair_depth=attempt + 1
            )

            model_hash = component_store.store(model_capsule)
            policy_hash = component_store.store(policy_capsule)

            system_capsule = build_system_capsule(
                policy_hash=policy_hash,
                world_model_hash=model_hash,
                config=config,
                parents=[model_hash, policy_hash],
                operators=[operator, repair_operator],
                repair_depth=attempt + 1,
            )

            shadow = evaluate_shadow_system(
                system_capsule=system_capsule,
                policy_spec=policy_spec,
                model_spec=model_spec,
                seed=str(seed),
                margin=shadow_margin,
                counterexamples=counterexamples.entries(),
                env_config_path=env_config,
                env_id=env_id,
                forager_max_tests=forager_max_tests,
            )

            counterexample_id = None
            failure_pattern_id = None
            if shadow.trace is not None:
                trace_hash = None
                failure_class = shadow.trace.status
                if shadow.trace.counterexample is not None:
                    entry = counterexamples.add(
                        test_name=shadow.trace.failing_test or "shadow_system",
                        input_value=shadow.trace.counterexample,
                        failure_class=shadow.trace.status,
                        capsule_hash=capsule_hash(system_capsule),
                    )
                    counterexample_id = entry.counterexample_id
                    failure_class = entry.failure_class
                    trace_hash = entry.input_hash
                else:
                    fallback = shadow.trace.failing_test or shadow.trace.status
                    trace_hash = hashlib.sha256(fallback.encode("utf-8")).hexdigest()
                failure_pattern_id = failure_patterns.add(
                    failure_class=failure_class,
                    env_id=env_id,
                    operator_sig=operator_signature(system_capsule.get("operators_used", [])),
                    trace_hash=trace_hash,
                )

            descriptor = _descriptor(model_spec, policy_spec, system_capsule.get("operators_used", []))
            descriptor["nontriviality_pass"] = getattr(shadow, "nontriviality_pass", None)
            descriptor["baseline_margin_bucket"] = margin_bucket(getattr(shadow, "baseline_margin", None))
            pattern_snapshot = []
            if pattern_snapshot_every > 0 and (len(events) + 1) % pattern_snapshot_every == 0:
                pattern_snapshot = failure_patterns.top_k(pattern_top_k)
            events.append(
                SystemEvent(
                    system_capsule=system_capsule,
                    policy_capsule=policy_capsule,
                    model_capsule=model_capsule,
                    shadow=shadow,
                    operator=repair_operator,
                    repair_depth=attempt + 1,
                    counterexample_id=counterexample_id,
                    descriptor=descriptor,
                    failure_pattern_id=failure_pattern_id,
                    failure_patterns_top=pattern_snapshot,
                )
            )

            if shadow.decision == "PASS":
                break

    return {"events": events, "component_store_dir": str(component_store_dir)}
