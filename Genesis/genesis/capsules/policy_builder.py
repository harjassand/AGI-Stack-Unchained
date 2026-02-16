from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List


def _capsule_id(policy_spec: Dict[str, Any], env_id: str) -> str:
    payload = json.dumps({"policy_spec": policy_spec, "env_id": env_id}, sort_keys=True, separators=(",", ":"))
    return str(uuid.uuid5(uuid.NAMESPACE_URL, payload))


def build_policy_capsule(
    policy_spec: Dict[str, Any],
    config: Dict[str, Any],
    parents: List[str] | None = None,
    operators: List[str] | None = None,
    repair_depth: int = 0,
    model_capsule_hash: str | None = None,
) -> Dict[str, Any]:
    env_id = policy_spec.get("env_id") or config.get("policy_env_id", "policy_env_tiny")
    policy_spec = dict(policy_spec)
    policy_spec["env_id"] = env_id

    return_target = float(config.get("policy_return_target", 0.5))
    cost_target = float(config.get("policy_cost_target", 0.5))
    return_direction = str(config.get("policy_return_direction", "maximize"))
    cost_direction = str(config.get("policy_cost_direction", "minimize"))
    risk_bound = float(config.get("policy_risk_bound", 0.0))
    nontrivial = config.get("nontriviality") or {}
    min_diversity = str(nontrivial.get("policy_min_diversity", "0.25"))
    min_entropy = str(nontrivial.get("policy_min_entropy", "0.05"))
    min_margin = str(nontrivial.get("policy_baseline_margin", "0.1"))

    resource_spec = {
        "max_wall_time_ms": int(config.get("policy_max_wall_time_ms", 1000)),
        "max_memory_mb": int(config.get("policy_max_memory_mb", 256)),
        "max_sample_count": int(config.get("policy_max_sample_count", 0)),
        "max_gpu_seconds": 0,
    }

    budget_bid = config.get("default_bid") or policy_spec.get("budget_bid")
    if not isinstance(budget_bid, dict):
        raise ValueError("default_bid is required for policy capsules")

    capsule = {
        "schema_version": "1.0.1",
        "capsule_version": "1.0.0",
        "forward_compat": "x_prefix_only",
        "canonicalization": "gcj-1",
        "capsule_id": _capsule_id(policy_spec, env_id),
        "artifact_type": "POLICY",
        "parents": parents or [],
        "operators_used": operators or [],
        "build_hashes": {
            "ir_hash": "a" * 64,
            "container_hash": "b" * 64,
            "dependency_hashes": [],
        },
        "commitments": {
            "capsule_hash": "0" * 64,
            "checkpoint_merkle_root": "6" * 64,
        },
        "ir_payload": {
            "format": "GIR1-POLICY",
            "version": "1.0",
            "payload_base64": "AA==",
        },
        "entrypoints": [
            {
                "name": "act",
                "signature": {
                    "inputs": [{"name": "observation", "type": "Tensor<float32>[d]"}],
                    "outputs": [{"name": "action", "type": "int"}],
                },
            }
        ],
        "effects": {
            "allow": ["pure"],
            "deny": ["network", "filesystem_write", "process_spawn"],
        },
        "contract": {
            "functional_spec": {
                "spec_language": "DSL1",
                "clauses": [
                    {
                        "id": "fs-1",
                        "clause_type": "functional",
                        "text": "act returns a discrete action.",
                    }
                ],
            },
            "safety_spec": {
                "invariants": [
                    {
                        "id": "s-1",
                        "clause_type": "safety",
                        "text": "Policy emits only valid actions.",
                    }
                ],
                "forbidden_behaviors": [],
            },
            "resource_spec": resource_spec,
            "statistical_spec": {
                "metrics": [
                    {
                        "name": "policy_return",
                        "direction": return_direction,
                        "target": return_target,
                    },
                    {
                        "name": "policy_cost",
                        "direction": cost_direction,
                        "target": cost_target,
                    },
                ],
                "decision_rule": "threshold",
                "confidence_requirement": {"delta": 0.001},
            },
            "robustness_spec": {
                "mode": "certified_slices",
                "slice_family": {
                    "family": "finite_template",
                    "capacity": {"parameters": {"templates": 2}},
                },
                "risk_metric": "policy_return",
                "risk_bound": risk_bound,
            },
        },
        "assumptions": [],
        "budget_bid": budget_bid,
        "evidence": {"certificates": [], "unit_tests": [], "property_tests": [], "checkpoints": []},
        "reproducibility": {
            "determinism_mode": "seeded",
            "seed_policy": "harness_seeded",
            "runtime_env": {
                "os": "linux",
                "arch": "x86_64",
                "kernel_isa": "KISA-1",
            },
        },
        "provenance": {
            "created_by": "genesis",
            "timestamp": "2025-01-01T00:00:00Z",
            "source_repo": "genesis",
        },
        "x-nontriviality": {
            "checks": [
                {"type": "no_nan_inf"},
                {"type": "policy_action_diversity", "min_diversity": min_diversity, "min_entropy": min_entropy},
                {"type": "baseline_improvement", "metric": "policy_return", "min_margin": min_margin},
            ]
        },
        "x-harness": {"mode": "policy_sim"},
        "x-policy": policy_spec,
        "x-repair_depth": repair_depth,
    }
    if model_capsule_hash:
        capsule["x-model_capsule_hash"] = model_capsule_hash
    return capsule
