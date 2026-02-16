from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List


def _capsule_id(model_spec: Dict[str, Any], metric_name: str) -> str:
    payload = json.dumps({"model_spec": model_spec, "metric": metric_name}, sort_keys=True, separators=(",", ":"))
    return str(uuid.uuid5(uuid.NAMESPACE_URL, payload))


def build_world_model_capsule(
    model_spec: Dict[str, Any],
    config: Dict[str, Any],
    parents: List[str] | None = None,
    operators: List[str] | None = None,
    repair_depth: int = 0,
) -> Dict[str, Any]:
    metric_name = config.get("world_model_metric_name", "wm_accuracy")
    target = config.get("world_model_target", -1.0)
    direction = config.get("world_model_direction", "maximize")
    risk_bound = config.get("world_model_risk_bound", -1.0)
    nontrivial = config.get("nontriviality") or {}
    min_variance = str(nontrivial.get("world_model_min_variance", "0.01"))
    min_margin = str(nontrivial.get("world_model_baseline_margin", "0.05"))

    resource_spec = {
        "max_wall_time_ms": int(config.get("world_model_max_wall_time_ms", 1000)),
        "max_memory_mb": int(config.get("world_model_max_memory_mb", 256)),
        "max_sample_count": int(config.get("world_model_max_sample_count", 0)),
        "max_gpu_seconds": 0,
    }

    budget_bid = config.get("default_bid") or model_spec.get("budget_bid")
    if not isinstance(budget_bid, dict):
        raise ValueError("default_bid is required for world model capsules")

    capsule = {
        "schema_version": "1.0.1",
        "capsule_version": "1.0.0",
        "forward_compat": "x_prefix_only",
        "canonicalization": "gcj-1",
        "capsule_id": _capsule_id(model_spec, metric_name),
        "artifact_type": "WORLD_MODEL",
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
            "format": "GIR1",
            "version": "1.0",
            "payload_base64": "AA==",
        },
        "entrypoints": [
            {
                "name": "predict",
                "signature": {
                    "inputs": [{"name": "batch", "type": "Tensor<float32>[n,d]"}],
                    "outputs": [{"name": "scores", "type": "Tensor<float32>[n]"}],
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
                        "text": "Predict returns a score per input row.",
                    }
                ],
            },
            "safety_spec": {
                "invariants": [
                    {
                        "id": "s-1",
                        "clause_type": "safety",
                        "text": "No NaNs in output.",
                    }
                ],
                "forbidden_behaviors": [],
            },
            "resource_spec": resource_spec,
            "statistical_spec": {
                "metrics": [
                    {
                        "name": metric_name,
                        "direction": direction,
                        "target": target,
                    }
                ],
                "decision_rule": "threshold",
                "confidence_requirement": {"delta": 0.001},
            },
            "robustness_spec": {
                "mode": "certified_slices",
                "slice_family": {
                    "family": "finite_template",
                    "capacity": {"parameters": {"templates": 3}},
                },
                "risk_metric": metric_name,
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
                {"type": "model_output_variance", "min_variance": min_variance},
                {"type": "baseline_improvement", "metric": metric_name, "min_margin": min_margin},
            ]
        },
        "x-harness": {"mode": "world_model_predict"},
        "x-world-model": model_spec,
        "x-repair_depth": repair_depth,
    }
    return capsule
