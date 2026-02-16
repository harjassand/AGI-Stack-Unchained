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
from genesis.core.counterexamples import CounterexampleDB
from genesis.core.planning import plan_policy_from_model
from genesis.core.archive import Archive
from genesis.core import distill
from genesis.core import library as lib
from genesis.core import operators as ops
from genesis.shadow_cdel.shadow_policy_eval import ShadowPolicyResult, evaluate_shadow_policy
from genesis.shadow_cdel.nontriviality import margin_bucket


@dataclass
class PolicyEvent:
    capsule: Dict[str, Any]
    shadow: ShadowPolicyResult
    operator: str
    repair_depth: int
    counterexample_id: str | None
    descriptor: Dict[str, Any]


def seed_policy_specs(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {"policy_family": "linear", "weights": [1.0, 1.0], "bias": 0.0},
        {
            "policy_family": "decision_tree",
            "tree": {"feature_index": 0, "threshold": 0.0, "left_action": 0, "right_action": 1},
        },
    ]


def _mutate_policy(policy_spec: Dict[str, Any], rng: random.Random) -> Dict[str, Any]:
    out = copy.deepcopy(policy_spec)
    delta = rng.choice([-0.2, -0.1, 0.1, 0.2])
    if out.get("policy_family") == "linear":
        out["bias"] = float(out.get("bias", 0.0)) + delta
        weights = list(out.get("weights", []))
        if weights:
            idx = rng.randrange(len(weights))
            weights[idx] = float(weights[idx]) + delta
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
    obs = counterexample.get("obs")
    label = counterexample.get("label")
    if obs is None or label is None:
        return out
    if out.get("policy_family") == "linear":
        bias = float(out.get("bias", 0.0))
        bias += 0.5 if int(label) == 1 else -0.5
        out["bias"] = bias
    elif out.get("policy_family") == "decision_tree":
        tree = dict(out.get("tree") or {})
        tree["threshold"] = float(tree.get("threshold", 0.0)) - 0.1
        out["tree"] = tree
    return out


def _descriptor(policy_spec: Dict[str, Any], operators: List[str]) -> Dict[str, Any]:
    family = str(policy_spec.get("policy_family", "unknown"))
    weights = policy_spec.get("weights") or []
    param_count = len(weights) + (1 if "bias" in policy_spec else 0)
    if param_count <= 2:
        bucket = "small"
    elif param_count <= 4:
        bucket = "medium"
    else:
        bucket = "large"
    op_history = ">".join(operators)
    op_signature = hashlib.sha256(op_history.encode("utf-8")).hexdigest()[:12] if op_history else "none"
    return {"policy_family": family, "param_bucket": bucket, "operator_history_sig": op_signature}


def run_policy_search(config: Dict[str, Any], model_capsule: Dict[str, Any] | None = None) -> Dict[str, Any]:
    seed = int(config.get("seed", 0))
    rng = random.Random(seed)
    iterations = int(config.get("iterations", 4))
    repair_attempts = int(config.get("repair_attempts", 2))

    archive_path = Path(config.get("policy_archive_path", "genesis/policy_archive.jsonl"))
    archive = Archive(archive_path)
    library_path = Path(config.get("library_path", "genesis/library.json"))
    library = lib.Library.load(library_path)
    distill_every = int(config.get("distill_every", 1))
    distill_min_count = int(config.get("distill_min_count", 2))
    reuse_primitives = bool(config.get("reuse_policy_primitives", True))
    force_reuse_next = False

    env_config = Path(config.get("policy_env_config", "genesis/configs/policy_envs.json"))
    env_id = str(config.get("policy_env_id", "policy_env_tiny"))
    forager_max_tests = int(config.get("forager_max_tests", 0))
    shadow_margin = float(config.get("shadow_margin", 0.05))

    counterexamples = CounterexampleDB()
    events: List[PolicyEvent] = []

    seeds = seed_policy_specs(config)
    candidates: List[Dict[str, Any]] = []
    for idx in range(iterations):
        if idx < len(seeds):
            candidates.append(seeds[idx])
        else:
            if rng.choice([True, False]):
                weights = [round(rng.uniform(-1.0, 1.0), 2), round(rng.uniform(-1.0, 1.0), 2)]
                bias = round(rng.uniform(-0.5, 0.5), 2)
                candidates.append({"policy_family": "linear", "weights": weights, "bias": bias})
            else:
                threshold = round(rng.uniform(-0.5, 0.5), 2)
                candidates.append(
                    {
                        "policy_family": "decision_tree",
                        "tree": {
                            "feature_index": 0,
                            "threshold": threshold,
                            "left_action": 0,
                            "right_action": 1,
                        },
                    }
                )

    planned = None
    model_hash = None
    if model_capsule is not None:
        model_hash = capsule_hash(model_capsule)
        model_spec = model_capsule.get("x-world-model") or {}
        planned = plan_policy_from_model(model_spec, config)

    for idx, policy_spec in enumerate(candidates):
        operator = "x-policy-seed" if idx < len(seeds) else "x-policy-mutate"
        if idx == 0 and planned is not None:
            policy_spec = planned
            operator = "x-policy_from_model_rollouts"
        capsule = build_policy_capsule(
            policy_spec=policy_spec,
            config=config,
            parents=[model_hash] if model_hash else [],
            operators=[operator],
            repair_depth=0,
            model_capsule_hash=model_hash,
        )
        if force_reuse_next and library.primitives:
            primitive = library.select(rng)
            capsule = ops.reuse_primitive(capsule, primitive)
            operator = "x-reuse_primitive"
            force_reuse_next = False
        elif reuse_primitives and library.primitives and idx == 0:
            primitive = library.select(rng)
            capsule = ops.reuse_primitive(capsule, primitive)
            operator = "x-reuse_primitive"
        shadow = evaluate_shadow_policy(
            capsule=capsule,
            seed=str(seed),
            margin=shadow_margin,
            counterexamples=counterexamples.entries(),
            env_config_path=env_config,
            env_id=env_id,
            forager_max_tests=forager_max_tests,
        )
        counterexample_id = None
        if shadow.trace and shadow.trace.counterexample is not None:
            entry = counterexamples.add(
                test_name=shadow.trace.failing_test or "shadow_policy",
                input_value=shadow.trace.counterexample,
                failure_class=shadow.trace.status,
                capsule_hash=capsule_hash(capsule),
            )
            counterexample_id = entry.counterexample_id
        archive.append(
            capsule,
            status="shadow_pass" if shadow.decision == "PASS" else "shadow_fail",
            shadow_metric=shadow.return_value,
            shadow=shadow,
            repair_depth=0,
        )
        descriptor = _descriptor(policy_spec, capsule.get("operators_used", []))
        descriptor["nontriviality_pass"] = getattr(shadow, "nontriviality_pass", None)
        descriptor["baseline_margin_bucket"] = margin_bucket(getattr(shadow, "baseline_margin", None))
        events.append(
            PolicyEvent(
                capsule=capsule,
                shadow=shadow,
                operator=operator,
                repair_depth=0,
                counterexample_id=counterexample_id,
                descriptor=descriptor,
            )
        )

        if shadow.decision == "PASS":
            if distill_every > 0 and (idx + 1) % distill_every == 0:
                updated = distill.update_library(archive_path, library, distill_min_count)
                if updated:
                    library.save(library_path)
                    force_reuse_next = True
            continue

        for attempt in range(repair_attempts):
            repair_spec = _repair_policy(policy_spec, shadow.trace.counterexample if shadow.trace else None)
            repair_operator = "x-policy-repair"
            repair_capsule = build_policy_capsule(
                policy_spec=repair_spec,
                config=config,
                parents=[capsule_hash(capsule)],
                operators=[operator, repair_operator],
                repair_depth=attempt + 1,
                model_capsule_hash=model_hash,
            )
            shadow = evaluate_shadow_policy(
                capsule=repair_capsule,
                seed=str(seed),
                margin=shadow_margin,
                counterexamples=counterexamples.entries(),
                env_config_path=env_config,
                env_id=env_id,
                forager_max_tests=forager_max_tests,
            )
            counterexample_id = None
            if shadow.trace and shadow.trace.counterexample is not None:
                entry = counterexamples.add(
                    test_name=shadow.trace.failing_test or "shadow_policy",
                    input_value=shadow.trace.counterexample,
                    failure_class=shadow.trace.status,
                    capsule_hash=capsule_hash(repair_capsule),
                )
                counterexample_id = entry.counterexample_id
            archive.append(
                repair_capsule,
                status="shadow_pass" if shadow.decision == "PASS" else "shadow_fail",
                shadow_metric=shadow.return_value,
                shadow=shadow,
                repair_depth=attempt + 1,
            )
            descriptor = _descriptor(repair_spec, repair_capsule.get("operators_used", []))
            descriptor["nontriviality_pass"] = getattr(shadow, "nontriviality_pass", None)
            descriptor["baseline_margin_bucket"] = margin_bucket(getattr(shadow, "baseline_margin", None))
            events.append(
                PolicyEvent(
                    capsule=repair_capsule,
                    shadow=shadow,
                    operator=repair_operator,
                    repair_depth=attempt + 1,
                    counterexample_id=counterexample_id,
                    descriptor=descriptor,
                )
            )

            if shadow.decision == "PASS":
                if distill_every > 0 and (attempt + 1) % distill_every == 0:
                    updated = distill.update_library(archive_path, library, distill_min_count)
                    if updated:
                        library.save(library_path)
                        force_reuse_next = True
                break

    return {"events": events}
