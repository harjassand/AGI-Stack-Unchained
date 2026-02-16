from __future__ import annotations

import copy
import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from genesis.capsules.canonicalize import capsule_hash
from genesis.capsules.causal_model_builder import build_causal_model_capsule
from genesis.core.counterexamples import CounterexampleDB
from genesis.shadow_cdel.shadow_causal_eval import ShadowCausalResult, evaluate_shadow_causal


@dataclass
class CausalEvent:
    capsule: Dict[str, Any]
    shadow: ShadowCausalResult
    operator: str
    repair_depth: int
    counterexample_id: str | None
    descriptor: Dict[str, Any]


def _base_graph() -> dict:
    return {
        "nodes": ["treatment", "outcome", "z", "w"],
        "edges": [
            {"from": "z", "to": "treatment"},
            {"from": "z", "to": "outcome"},
            {"from": "w", "to": "treatment"},
            {"from": "w", "to": "outcome"},
            {"from": "treatment", "to": "outcome"},
        ],
    }


def _build_witness(adjustment_set: list[str]) -> dict:
    return {
        "type": "backdoor_adjustment",
        "treatment": "treatment",
        "outcome": "outcome",
        "graph": _base_graph(),
        "adjustment_set": adjustment_set,
    }


def seed_causal_specs() -> list[dict]:
    return [
        {"estimator": "diff_in_means", "treatment": "treatment", "outcome": "outcome", "covariates": ["z", "w"]},
        {"estimator": "ols_adjustment", "treatment": "treatment", "outcome": "outcome", "covariates": ["z", "w"]},
    ]


def _mutate_spec(spec: dict, rng: random.Random) -> dict:
    out = copy.deepcopy(spec)
    if rng.random() < 0.5:
        out["estimator"] = "ols_adjustment" if spec.get("estimator") == "diff_in_means" else "diff_in_means"
    else:
        covariates = list(out.get("covariates", []))
        if covariates:
            covariates = covariates[:-1]
        else:
            covariates = ["z"]
        out["covariates"] = covariates
    return out


def _repair_spec(spec: dict) -> dict:
    out = copy.deepcopy(spec)
    out["covariates"] = ["z", "w"]
    return out


def _descriptor(spec: dict, witness: dict, operators: list[str]) -> dict:
    estimator = str(spec.get("estimator", "unknown"))
    adjustment = witness.get("adjustment_set") or []
    size = len(adjustment)
    if size <= 1:
        bucket = "adj_small"
    elif size == 2:
        bucket = "adj_medium"
    else:
        bucket = "adj_large"
    op_history = ">".join(operators)
    op_signature = hashlib.sha256(op_history.encode("utf-8")).hexdigest()[:12] if op_history else "none"
    return {"estimator": estimator, "adjustment_bucket": bucket, "operator_history_sig": op_signature}


def run_causal_search(config: Dict[str, Any]) -> Dict[str, Any]:
    seed = int(config.get("seed", 0))
    rng = random.Random(seed)
    iterations = int(config.get("iterations", 4))
    repair_attempts = int(config.get("repair_attempts", 2))

    dataset_config = Path(config.get("dataset_config", "genesis/configs/datasets.json"))
    dataset_id = str(config.get("dataset_id", "shadow_causal"))
    forager_max_tests = int(config.get("forager_max_tests", 0))
    shadow_margin = float(config.get("shadow_margin", 0.05))

    counterexamples = CounterexampleDB()
    events: list[CausalEvent] = []

    seeds = seed_causal_specs()
    adjustments = [["z", "w"], ["z"], ["w"]]
    candidates: list[tuple[dict, dict, str]] = []
    for idx in range(iterations):
        if idx < len(seeds):
            spec = seeds[idx]
            adj = adjustments[min(idx, len(adjustments) - 1)]
            candidates.append((spec, _build_witness(adj), "x-causal-seed"))
        else:
            spec = _mutate_spec(rng.choice(seeds), rng)
            adj = rng.choice(adjustments)
            candidates.append((spec, _build_witness(adj), "x-causal-mutate"))

    for spec, witness, operator in candidates:
        capsule = build_causal_model_capsule(
            causal_spec=spec,
            witness=witness,
            config=config,
            parents=[],
            operators=[operator],
            repair_depth=0,
        )
        shadow = evaluate_shadow_causal(
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
        descriptor = _descriptor(spec, witness, capsule.get("operators_used", []))
        events.append(
            CausalEvent(
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
            repair_spec = _repair_spec(spec)
            repair_witness = _build_witness(["z", "w"])
            repair_operator = "x-causal-repair_adjustment"
            repair_capsule = build_causal_model_capsule(
                causal_spec=repair_spec,
                witness=repair_witness,
                config=config,
                parents=[capsule_hash(capsule)],
                operators=[operator, repair_operator],
                repair_depth=attempt + 1,
            )
            shadow = evaluate_shadow_causal(
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
            descriptor = _descriptor(repair_spec, repair_witness, repair_capsule.get("operators_used", []))
            events.append(
                CausalEvent(
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
