from __future__ import annotations

import copy
import hashlib
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from genesis.capsules.canonicalize import capsule_hash
from genesis.capsules.world_model_builder import build_world_model_capsule
from genesis.core.counterexamples import CounterexampleDB
from genesis.shadow_cdel.shadow_world_model_eval import ShadowWorldModelResult, evaluate_shadow_world_model
from genesis.shadow_cdel.nontriviality import margin_bucket


@dataclass
class WorldModelEvent:
    capsule: Dict[str, Any]
    shadow: ShadowWorldModelResult
    operator: str
    repair_depth: int
    counterexample_id: str | None
    descriptor: Dict[str, Any]


def seed_model_specs(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {"model_family": "logistic_regression", "weights": [1.0], "bias": 0.0},
        {"model_family": "linear_regression", "weights": [1.0], "bias": 0.0},
    ]


def _predict_score(model_spec: Dict[str, Any], features: List[float]) -> float:
    weights = model_spec.get("weights") or []
    bias = float(model_spec.get("bias", 0.0))
    score = sum(float(w) * float(x) for w, x in zip(weights, features)) + bias
    if model_spec.get("model_family") == "logistic_regression":
        if score >= 0:
            z = math.exp(-score)
            return 1.0 / (1.0 + z)
        z = math.exp(score)
        return z / (1.0 + z)
    return float(score)


def _predict_label(model_spec: Dict[str, Any], features: List[float]) -> int:
    return 1 if _predict_score(model_spec, features) >= 0.5 else 0


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


def _repair_model(model_spec: Dict[str, Any], counterexample: Any | None) -> Dict[str, Any]:
    out = copy.deepcopy(model_spec)
    if not isinstance(counterexample, dict):
        return out
    features = counterexample.get("features")
    label = counterexample.get("label")
    if not isinstance(features, list) or label is None:
        return out
    pred = _predict_label(out, features)
    if pred == int(label):
        return out
    bias = float(out.get("bias", 0.0))
    if int(label) == 1:
        bias += 0.5
    else:
        bias -= 0.5
    out["bias"] = bias
    return out


def _descriptor(model_spec: Dict[str, Any], operators: List[str]) -> Dict[str, Any]:
    family = str(model_spec.get("model_family", "unknown"))
    weights = model_spec.get("weights") or []
    param_count = len(weights) + 1
    if param_count <= 2:
        bucket = "small"
    elif param_count <= 4:
        bucket = "medium"
    else:
        bucket = "large"
    op_history = ">".join(operators)
    op_signature = hashlib.sha256(op_history.encode("utf-8")).hexdigest()[:12] if op_history else "none"
    return {"model_family": family, "param_bucket": bucket, "operator_history_sig": op_signature}


def run_world_model_search(config: Dict[str, Any]) -> Dict[str, Any]:
    seed = int(config.get("seed", 0))
    rng = random.Random(seed)
    iterations = int(config.get("iterations", 4))
    repair_attempts = int(config.get("repair_attempts", 2))

    dataset_config = Path(config.get("dataset_config", "genesis/configs/datasets.json"))
    dataset_id = str(config.get("dataset_id", "shadow_world_model"))
    forager_max_tests = int(config.get("forager_max_tests", 0))
    shadow_margin = float(config.get("shadow_margin", 0.05))

    counterexamples = CounterexampleDB()
    events: List[WorldModelEvent] = []

    seeds = seed_model_specs(config)
    candidates: List[Dict[str, Any]] = []
    for idx in range(iterations):
        if idx < len(seeds):
            candidates.append(seeds[idx])
        else:
            family = rng.choice(["logistic_regression", "linear_regression"])
            weights = [round(rng.uniform(-1.0, 1.0), 2)]
            bias = round(rng.uniform(-0.5, 0.5), 2)
            candidates.append({"model_family": family, "weights": weights, "bias": bias})

    for idx, model_spec in enumerate(candidates):
        operator = "x-wm-seed" if idx < len(seeds) else "x-wm-mutate"
        capsule = build_world_model_capsule(
            model_spec=model_spec,
            config=config,
            parents=[],
            operators=[operator],
            repair_depth=0,
        )
        shadow = evaluate_shadow_world_model(
            capsule=capsule,
            seed=str(seed),
            margin=shadow_margin,
            counterexamples=counterexamples.entries(),
            dataset_config_path=dataset_config,
            dataset_id=dataset_id,
            forager_max_tests=forager_max_tests,
        )
        counterexample_id = None
        if shadow.trace and shadow.trace.counterexample is not None:
            entry = counterexamples.add(
                test_name=shadow.trace.failing_test or "shadow",
                input_value=shadow.trace.counterexample,
                failure_class=shadow.trace.status,
                capsule_hash=capsule_hash(capsule),
            )
            counterexample_id = entry.counterexample_id
        descriptor = _descriptor(model_spec, capsule.get("operators_used", []))
        descriptor["nontriviality_pass"] = getattr(shadow, "nontriviality_pass", None)
        descriptor["baseline_margin_bucket"] = margin_bucket(getattr(shadow, "baseline_margin", None))
        events.append(
            WorldModelEvent(
                capsule=capsule,
                shadow=shadow,
                operator=operator,
                repair_depth=0,
                counterexample_id=counterexample_id,
                descriptor=descriptor,
            )
        )

        if shadow.decision == "PASS":
            continue

        for attempt in range(repair_attempts):
            repair_spec = _repair_model(model_spec, shadow.trace.counterexample if shadow.trace else None)
            repair_operator = "x-wm-repair_bias"
            repair_capsule = build_world_model_capsule(
                model_spec=repair_spec,
                config=config,
                parents=[capsule_hash(capsule)],
                operators=[operator, repair_operator],
                repair_depth=attempt + 1,
            )
            shadow = evaluate_shadow_world_model(
                capsule=repair_capsule,
                seed=str(seed),
                margin=shadow_margin,
                counterexamples=counterexamples.entries(),
                dataset_config_path=dataset_config,
                dataset_id=dataset_id,
                forager_max_tests=forager_max_tests,
            )
            counterexample_id = None
            if shadow.trace and shadow.trace.counterexample is not None:
                entry = counterexamples.add(
                    test_name=shadow.trace.failing_test or "shadow",
                    input_value=shadow.trace.counterexample,
                    failure_class=shadow.trace.status,
                    capsule_hash=capsule_hash(repair_capsule),
                )
                counterexample_id = entry.counterexample_id
            descriptor = _descriptor(repair_spec, repair_capsule.get("operators_used", []))
            descriptor["nontriviality_pass"] = getattr(shadow, "nontriviality_pass", None)
            descriptor["baseline_margin_bucket"] = margin_bucket(getattr(shadow, "baseline_margin", None))
            events.append(
                WorldModelEvent(
                    capsule=repair_capsule,
                    shadow=shadow,
                    operator=repair_operator,
                    repair_depth=attempt + 1,
                    counterexample_id=counterexample_id,
                    descriptor=descriptor,
                )
            )
            if shadow.decision == "PASS":
                break

    return {"events": events}
